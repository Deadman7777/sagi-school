"""Factures proforma de scolarité.

Règles vérifiées — des cohérences, pas des montants en dur :
  - la proforma d'un élève inscrit annonce le reste de SON échéancier : ni plus
    (un mois soldé ne réapparaît pas), ni moins ;
  - la proforma d'un futur élève chiffre ce que la fiche réelle lui ferait
    devoir une fois inscrit, prorata d'entrée compris ;
  - la somme des lignes est le total, l'échéancier se règle au même montant ;
  - la remise ne touche que le règlement en une fois ;
  - numérotation par école, pièce figée, annulation motivée, isolation.
"""
import datetime

from rest_framework.test import APITestCase

from apps.eleves.echeancier import construire_echeancier
from apps.eleves.models import Eleve, EleveService, FormuleSection, Section, Service
from apps.paiements import proformas as P
from apps.paiements.models import Exercice, Paiement, Proforma
from apps.tenants.models import Tenant
from apps.users.models import User

AUJOURDHUI = datetime.date(2026, 11, 15)


class ProformaBase(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='École Les Pionniers', code_etablissement='PIO',
                                            ninea='123456789', telephone='77 000 00 00')
        self.user = User.objects.create_user(
            'dir@pio.sn', 'x', nom='DIOP', prenom='Awa', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026-2027', nb_mensualites=9,
            date_debut=datetime.date(2026, 10, 1), date_fin=datetime.date(2027, 7, 31))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='CE1', frais_inscription=25000, frais_mensualite=15000,
            composition_inscription=[{'libelle': 'Frais de dossier', 'montant': 20000},
                                     {'libelle': 'Assurance', 'montant': 5000}])
        self.cantine = Service.objects.create(tenant=self.tenant, nom='Cantine',
                                              montant=10000, periodicite='MENSUEL')
        self.tenue = Service.objects.create(tenant=self.tenant, nom='Tenue de sport',
                                            montant=7500, periodicite='UNIQUE')

    def _eleve(self, nom='Moussa NDOUR', services=(), **kw):
        base = dict(tenant=self.tenant, exercice=self.ex, section=self.section,
                    nom_complet=nom, statut='INSCRIT', date_inscription=self.ex.date_debut,
                    nom_pere='Ousseynou NDOUR', telephone_pere='770000001')
        base.update(kw)
        e = Eleve.objects.create(**base)
        for s in services:
            EleveService.objects.create(tenant=self.tenant, eleve=e, service=s)
        return e

    def _payer(self, eleve, mensualite=0, inscription=0, mois=()):
        return Paiement.objects.create(
            tenant=self.tenant, exercice=self.ex, eleve=eleve,
            no_piece=f'REC-{Paiement.objects.count() + 1:04d}', mode_paiement='ESPECE',
            montant_mensualite=mensualite, montant_inscription=inscription,
            mois_regles=list(mois), date_paiement=datetime.date(2026, 10, 5))

    def _reste(self, eleve):
        return construire_echeancier(eleve, today=AUJOURDHUI)['totaux']['reste']


class EleveInscritTest(ProformaBase):
    def test_sans_paiement_la_proforma_vaut_le_total_attendu(self):
        e = self._eleve(services=[self.cantine, self.tenue])
        r = P.finaliser(P.chiffrer_eleve(e, today=AUJOURDHUI), today=AUJOURDHUI)
        self.assertAlmostEqual(r['total_du'], e.total_attendu)
        self.assertAlmostEqual(r['net_a_payer'], e.total_attendu)
        self.assertAlmostEqual(sum(l['montant'] for l in r['lignes']), r['total_du'])

    def test_le_net_est_le_reste_de_l_echeancier(self):
        e = self._eleve(services=[self.cantine])
        self._payer(e, inscription=25000)
        self._payer(e, mensualite=25000, mois=[10])     # octobre soldé (15 000 + cantine)
        self._payer(e, mensualite=10000, mois=[11])     # novembre partiel
        r = P.finaliser(P.chiffrer_eleve(e, today=AUJOURDHUI), today=AUJOURDHUI)
        self.assertAlmostEqual(r['net_a_payer'], self._reste(e))
        # Octobre est soldé : il n'est plus chiffré. Novembre, partiel, l'est,
        # et ce qui en a été payé est déduit.
        details = ' '.join(l['detail'] for l in r['lignes'])
        self.assertNotIn('Octobre', details)
        self.assertIn('Novembre', details)
        self.assertAlmostEqual(r['deja_regle'], 10000)
        # Inscription soldée : plus de ligne d'inscription.
        self.assertFalse(any(l['nature'] == 'ENTREE' for l in r['lignes']))

    def test_l_echeancier_se_regle_au_meme_montant(self):
        e = self._eleve(services=[self.cantine])
        self._payer(e, mensualite=10000, mois=[10])
        r = P.finaliser(P.chiffrer_eleve(e, today=AUJOURDHUI), today=AUJOURDHUI)
        self.assertAlmostEqual(sum(x['montant'] for x in r['echeancier']), r['reste'])
        # Les échéances passées sont regroupées en une seule, datée du jour.
        self.assertEqual(r['echeancier'][0]['date'], AUJOURDHUI.isoformat())
        self.assertTrue(all(x['date'] > AUJOURDHUI.isoformat() for x in r['echeancier'][1:]))

    def test_la_reduction_apparait_et_le_total_ne_bouge_pas(self):
        e = self._eleve(prise_en_charge='FRATRIE', pec_mensualite=3000, pec_inscription=5000)
        r = P.finaliser(P.chiffrer_eleve(e, today=AUJOURDHUI), today=AUJOURDHUI)
        reductions = [l for l in r['lignes'] if l['nature'] == 'REDUCTION']
        self.assertTrue(reductions)
        self.assertTrue(all(l['montant'] < 0 for l in reductions))
        self.assertIn('fratrie', reductions[0]['designation'].lower())
        self.assertAlmostEqual(r['total_du'], e.total_attendu)

    def test_la_composition_de_l_inscription_est_detaillee(self):
        e = self._eleve()
        r = P.finaliser(P.chiffrer_eleve(e, today=AUJOURDHUI), today=AUJOURDHUI)
        inscription = next(l for l in r['lignes'] if l['nature'] == 'ENTREE')
        self.assertIn('Frais de dossier', inscription['detail'])
        self.assertIn('Assurance', inscription['detail'])

    def test_les_mois_choisis_seulement(self):
        e = self._eleve()
        r = P.finaliser(P.chiffrer_eleve(e, mois=[12, 1], inclure_entree=False,
                                         today=AUJOURDHUI), today=AUJOURDHUI)
        self.assertAlmostEqual(r['net_a_payer'], 2 * 15000)

    def test_un_eleve_solde_n_a_pas_de_proforma(self):
        e = self._eleve()
        self._payer(e, inscription=25000, mensualite=9 * 15000, mois=[10, 11, 12, 1, 2, 3, 4, 5, 6])
        with self.assertRaises(P.ProformaErreur):
            P.chiffrer_eleve(e, today=AUJOURDHUI)


class FuturEleveTest(ProformaBase):
    def test_meme_montant_que_la_fiche_une_fois_inscrit(self):
        """Arrivée en janvier : le prorata de la proforma est celui de la fiche."""
        entree = datetime.date(2027, 1, 10)
        r = P.finaliser(P.chiffrer_nouvel_eleve(
            self.tenant, self.ex, self.section, date_entree=entree,
            services=[self.cantine, self.tenue]), today=AUJOURDHUI)
        inscrit = self._eleve(date_inscription=entree, services=[self.cantine, self.tenue])
        self.assertAlmostEqual(r['total_du'], inscrit.total_attendu)
        self.assertAlmostEqual(sum(x['montant'] for x in r['echeancier']), r['total_du'])

    def test_aucune_echeance_avant_l_arrivee(self):
        entree = datetime.date(2027, 1, 20)
        r = P.finaliser(P.chiffrer_nouvel_eleve(self.tenant, self.ex, self.section,
                                                date_entree=entree), today=AUJOURDHUI)
        self.assertTrue(all(x['date'] >= entree.isoformat() for x in r['echeancier']))

    def test_la_formule_choisie_fixe_la_mensualite(self):
        formule = FormuleSection.objects.create(tenant=self.tenant, section=self.section,
                                                nom='08H-17H', frais_mensualite=40000)
        r = P.finaliser(P.chiffrer_nouvel_eleve(self.tenant, self.ex, self.section,
                                                formule=formule), today=AUJOURDHUI)
        mensualite = next(l for l in r['lignes'] if l['nature'] == 'MENSUALITE')
        self.assertEqual(mensualite['prix_unitaire'], 40000)
        self.assertEqual(mensualite['quantite'], 9)
        self.assertIn('08H-17H', mensualite['designation'])

    def test_annee_suivante(self):
        r = P.finaliser(P.chiffrer_nouvel_eleve(self.tenant, self.ex, self.section,
                                                annee_suivante=True), today=AUJOURDHUI)
        self.assertEqual(r['annee_scolaire'], '2027-2028')
        self.assertTrue(all(x['date'] >= '2027-10-01' for x in r['echeancier']))

    def test_premier_mois_a_l_inscription(self):
        self.tenant.premier_mois_a_inscription = True
        self.tenant.save()
        r = P.finaliser(P.chiffrer_nouvel_eleve(self.tenant, self.ex, self.section,
                                                date_entree=datetime.date(2026, 12, 1)),
                        today=AUJOURDHUI)
        premiere = next(x for x in r['echeancier'] if x['libelle'].startswith("À l'inscription"))
        self.assertAlmostEqual(premiere['montant'], 25000 + 15000)

    def test_entree_apres_la_fin_d_annee_refusee(self):
        with self.assertRaises(P.ProformaErreur):
            P.chiffrer_nouvel_eleve(self.tenant, self.ex, self.section,
                                    date_entree=datetime.date(2027, 9, 1))


class RemiseEtLignesLibresTest(ProformaBase):
    def test_remise_en_pourcentage_sur_le_reglement_en_une_fois(self):
        r = P.finaliser(P.chiffrer_nouvel_eleve(self.tenant, self.ex, self.section),
                        remise_type='TAUX', remise_valeur=10, today=AUJOURDHUI)
        total = 25000 + 9 * 15000
        self.assertAlmostEqual(r['remise_montant'], total * 0.10)
        self.assertAlmostEqual(r['net_a_payer'], total * 0.90)
        # L'échéancier reste la formule SANS remise.
        self.assertAlmostEqual(sum(x['montant'] for x in r['echeancier']), total)
        self.assertTrue(r['remise_libelle'])

    def test_remise_plafonnee_au_reste(self):
        r = P.finaliser(P.chiffrer_nouvel_eleve(self.tenant, self.ex, self.section),
                        remise_type='MONTANT', remise_valeur=10_000_000, today=AUJOURDHUI)
        self.assertEqual(r['net_a_payer'], 0)

    def test_ligne_libre_ajoutee_au_total_et_a_l_echeancier(self):
        r = P.finaliser(P.chiffrer_nouvel_eleve(self.tenant, self.ex, self.section),
                        lignes_libres=[{'designation': 'Tenue de cérémonie', 'quantite': 2,
                                        'prix_unitaire': 6000}], today=AUJOURDHUI)
        self.assertAlmostEqual(r['total_du'], 25000 + 9 * 15000 + 12000)
        self.assertAlmostEqual(sum(x['montant'] for x in r['echeancier']), r['total_du'])


class ApiTest(ProformaBase):
    URL = '/api/paiements/proformas/'

    def test_emission_numerotee_et_pdf(self):
        e = self._eleve()
        rep = self.client.post(self.URL, {'mode': 'ELEVE', 'eleve_id': str(e.id)}, format='json')
        self.assertEqual(rep.status_code, 201, rep.content)
        p = rep.json()
        self.assertRegex(p['numero'], r'^PF-\d{4}-0001$')
        self.assertEqual(p['parent_nom'], 'Ousseynou NDOUR')
        self.assertFalse(p['nouvel_eleve'])
        rep2 = self.client.post(self.URL, {'mode': 'NOUVEAU', 'section_id': str(self.section.id),
                                           'beneficiaire': 'Fatou SALL'}, format='json')
        self.assertTrue(rep2.json()['numero'].endswith('-0002'))
        self.assertTrue(rep2.json()['nouvel_eleve'])

        pdf = self.client.get(f"{self.URL}{p['id']}/pdf/")
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf['Content-Type'], 'application/pdf')
        self.assertIn('MoussaNDOUR', pdf['Content-Disposition'])

    def test_la_proforma_est_figee(self):
        e = self._eleve()
        p = self.client.post(self.URL, {'mode': 'ELEVE', 'eleve_id': str(e.id)},
                             format='json').json()
        self.section.frais_mensualite = 99000
        self.section.save()
        relue = self.client.get(f"{self.URL}{p['id']}/").json()
        self.assertEqual(relue['net_a_payer'], p['net_a_payer'])

    def test_apercu_n_enregistre_rien(self):
        rep = self.client.post(f'{self.URL}apercu/', {'mode': 'NOUVEAU',
                                                      'section_id': str(self.section.id),
                                                      'service_ids': [str(self.cantine.id)],
                                                      'date_entree': '2027-01'}, format='json')
        self.assertEqual(rep.status_code, 200, rep.content)
        self.assertEqual(Proforma.objects.count(), 0)
        self.assertAlmostEqual(rep.json()['net_a_payer'], 25000 + 6 * 25000)

    def test_futur_eleve_sans_nom_refuse(self):
        rep = self.client.post(self.URL, {'mode': 'NOUVEAU', 'section_id': str(self.section.id)},
                               format='json')
        self.assertEqual(rep.status_code, 400)
        self.assertIn("nom", rep.json()['error'])

    def test_annulation_motivee(self):
        e = self._eleve()
        p = self.client.post(self.URL, {'mode': 'ELEVE', 'eleve_id': str(e.id)},
                             format='json').json()
        url = f"{self.URL}{p['id']}/annuler/"
        self.assertEqual(self.client.post(url, {}, format='json').status_code, 400)
        rep = self.client.post(url, {'motif': 'Erreur de classe'}, format='json')
        self.assertEqual(rep.json()['statut'], 'ANNULEE')
        self.assertEqual(self.client.get(f"{self.URL}{p['id']}/pdf/").status_code, 200)

    def test_chaque_ecole_a_sa_sequence_et_ne_voit_que_les_siennes(self):
        e = self._eleve()
        p = self.client.post(self.URL, {'mode': 'ELEVE', 'eleve_id': str(e.id)},
                             format='json').json()

        autre = Tenant.objects.create(nom='Autre école', code_etablissement='AUT')
        Exercice.objects.create(tenant=autre, annee_scolaire='2026-2027',
                                date_debut=datetime.date(2026, 10, 1),
                                date_fin=datetime.date(2027, 7, 31))
        section = Section.objects.create(tenant=autre, nom='CP', frais_inscription=10000,
                                         frais_mensualite=10000)
        self.client.force_authenticate(User.objects.create_user(
            'b@aut.sn', 'x', nom='Admin', role='ADMIN_ECOLE', tenant=autre))
        self.assertEqual(self.client.get(f"{self.URL}{p['id']}/").status_code, 404)
        self.assertEqual(self.client.get(f"{self.URL}{p['id']}/pdf/").status_code, 404)
        self.assertEqual(self.client.get(self.URL).json(), [])
        # L'élève d'une autre école est introuvable.
        rep = self.client.post(self.URL, {'mode': 'ELEVE', 'eleve_id': str(e.id)}, format='json')
        self.assertEqual(rep.status_code, 400)
        rep = self.client.post(self.URL, {'mode': 'NOUVEAU', 'section_id': str(section.id),
                                          'beneficiaire': 'X'}, format='json')
        self.assertTrue(rep.json()['numero'].endswith('-0001'))
