"""Tests : boursiers et organismes payeurs.

La distinction qui structure tout : une prise en charge SOCIALE est une remise
— l'école renonce, personne ne paie. Une prise en charge par un ORGANISME
change le débiteur — un tiers doit cet argent à l'école.

Les confondre ferait disparaître des créances réelles du suivi financier. Pour
un centre de formation dont la moitié des étudiants sont boursiers de l'État,
c'est la moitié de ses recettes qui deviendrait invisible.
"""
import datetime

from rest_framework.test import APITestCase

from apps.eleves.models import Eleve, Organisme, PriseEnChargeOrganisme, Section
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User


class OrganismeBase(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Centre', code_etablissement='CFP')
        self.user = User.objects.create_user(
            'a@a.sn', 'x', nom='Admin', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', nb_mensualites=10,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='BTS', frais_inscription=100000,
            frais_mensualite=50000, frais_uniforme=0, frais_fournitures=0)
        self.eleve = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, section=self.section,
            nom_complet='Awa NDIAYE', date_inscription=self.ex.date_debut)
        self.etat = Organisme.objects.create(
            tenant=self.tenant, nom='Ministère de la Formation', type='ETAT',
            reference='Arrêté 2026-118')

    def _boursier(self, inscription=100000, mensualite=50000):
        return PriseEnChargeOrganisme.objects.create(
            tenant=self.tenant, eleve=self.eleve, organisme=self.etat,
            exercice=self.ex, montant_inscription=inscription,
            montant_mensualite=mensualite)

    def _payer(self, montant, organisme=None):
        return Paiement.objects.create(
            tenant=self.tenant, exercice=self.ex, eleve=self.eleve,
            no_piece=f'REC-{Paiement.objects.count() + 1}', mode_paiement='ESPECE',
            montant_mensualite=montant, organisme=organisme, statut='ACTIF')

    def _relire(self):
        return Eleve.objects.get(pk=self.eleve.pk)


class RepartitionDuTest(OrganismeBase):
    def test_sans_organisme_tout_est_a_la_charge_de_la_famille(self):
        e = self._relire()
        self.assertEqual(e.part_organisme, 0)
        self.assertEqual(e.part_famille, e.total_attendu)

    def test_une_bourse_totale_decharge_la_famille(self):
        self._boursier()                       # 100 000 + 50 000 × 10

        e = self._relire()

        self.assertEqual(e.total_attendu, 600000)
        self.assertEqual(e.part_organisme, 600000)
        self.assertEqual(e.part_famille, 0)

    def test_une_bourse_partielle_partage_le_du(self):
        self._boursier(inscription=100000, mensualite=30000)   # 400 000

        e = self._relire()

        self.assertEqual(e.part_organisme, 400000)
        self.assertEqual(e.part_famille, 200000)

    def test_la_bourse_ne_reduit_PAS_le_du_total(self):
        """C'est toute la différence avec une remise sociale : l'école attend
        toujours 600 000, simplement pas de la même personne."""
        avant = self._relire().total_attendu
        self._boursier()
        self.assertEqual(self._relire().total_attendu, avant)

    def test_une_convention_trop_genereuse_ne_cree_pas_de_creance_fantome(self):
        self._boursier(inscription=900000, mensualite=0)
        self.assertEqual(self._relire().part_organisme, 600000)   # plafonné

    def test_la_remise_sociale_reduit_le_du_elle(self):
        """Contraste : la prise en charge de la fiche, elle, fait disparaître
        la somme — personne ne la paiera jamais."""
        self.eleve.pec_inscription = 100000
        self.eleve.save()
        self.assertEqual(self._relire().total_attendu, 500000)


class QuiDoitQuoiTest(OrganismeBase):
    def test_un_versement_de_l_organisme_solde_sa_part_seule(self):
        self._boursier(inscription=100000, mensualite=30000)     # 400 000
        self._payer(400000, organisme=self.etat)

        e = self._relire()

        self.assertEqual(e.reste_organisme, 0)
        self.assertEqual(e.reste_famille, 200000)

    def test_un_versement_de_la_famille_ne_solde_pas_l_organisme(self):
        self._boursier(inscription=100000, mensualite=30000)
        self._payer(200000)                                      # la famille

        e = self._relire()

        self.assertEqual(e.reste_famille, 0)
        self.assertEqual(e.reste_organisme, 400000)

    def test_le_total_paye_reste_la_somme_de_tout(self):
        self._boursier(inscription=100000, mensualite=30000)
        self._payer(400000, organisme=self.etat)
        self._payer(200000)

        e = self._relire()

        self.assertEqual(e.total_paye, 600000)
        self.assertEqual(e.reste_a_payer, 0)


class AlerteTest(OrganismeBase):
    """L'alerte juge la FAMILLE, jamais l'organisme."""

    JUIN = datetime.date(2026, 6, 15)

    def test_une_famille_a_jour_reste_verte_meme_si_l_etat_n_a_pas_paye(self):
        self._boursier(inscription=100000, mensualite=30000)
        self._payer(200000)                     # la famille a tout réglé

        niveau, arrieres = self._relire().niveau_alerte_detail(
            600000 - 400000, 200000, today=self.JUIN)

        self.assertEqual((niveau, arrieres), ('A_JOUR', 0))

    def test_un_boursier_integral_n_est_jamais_en_alerte(self):
        self._boursier()                        # bourse totale
        niveau, _ = self._relire().niveau_alerte_detail(0, 0, today=self.JUIN)
        self.assertEqual(niveau, 'A_JOUR')

    def test_sans_bourse_le_calcul_est_inchange(self):
        niveau, _ = self._relire().niveau_alerte_detail(0, 0, today=self.JUIN)
        self.assertNotEqual(niveau, 'A_JOUR')   # elle doit bien 600 000


class ContraintesTest(OrganismeBase):
    def test_un_seul_organisme_par_eleve_et_par_exercice(self):
        from django.db import IntegrityError
        self._boursier()
        autre = Organisme.objects.create(tenant=self.tenant, nom='ONG X', type='ONG')
        with self.assertRaises(IntegrityError):
            PriseEnChargeOrganisme.objects.create(
                tenant=self.tenant, eleve=self.eleve, organisme=autre,
                exercice=self.ex, montant_mensualite=1000)

    def test_un_organisme_qui_a_des_boursiers_ne_se_supprime_pas(self):
        from django.db.models import ProtectedError
        self._boursier()
        with self.assertRaises(ProtectedError):
            self.etat.delete()

    def test_nom_d_organisme_unique_par_ecole(self):
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            Organisme.objects.create(tenant=self.tenant,
                                     nom='Ministère de la Formation', type='ETAT')


class ApiOrganismesTest(OrganismeBase):
    def test_creer_un_organisme(self):
        r = self.client.post('/api/eleves/organismes/', {
            'nom': 'Fondation Sonatel', 'type': 'FONDATION',
            'reference': 'Convention 2026-04'}, format='json')
        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(r.data['type_libelle'], 'Fondation')

    def test_un_organisme_avec_boursiers_ne_se_supprime_pas(self):
        self._boursier()
        r = self.client.delete(f'/api/eleves/organismes/{self.etat.id}/')
        self.assertEqual(r.status_code, 400)
        self.assertIn('boursier', str(r.data).lower())

    def test_un_organisme_sans_boursier_se_supprime(self):
        ong = Organisme.objects.create(tenant=self.tenant, nom='ONG Y', type='ONG')
        self.assertEqual(
            self.client.delete(f'/api/eleves/organismes/{ong.id}/').status_code, 204)

    def test_attribuer_une_bourse(self):
        r = self.client.post('/api/eleves/bourses/', {
            'eleve': str(self.eleve.id), 'organisme': str(self.etat.id),
            'montant_inscription': 100000, 'montant_mensualite': 30000,
            'reference': 'Bourse 2026-0042'}, format='json')

        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(self._relire().part_organisme, 400000)

    def test_une_bourse_vide_est_refusee(self):
        r = self.client.post('/api/eleves/bourses/', {
            'eleve': str(self.eleve.id), 'organisme': str(self.etat.id)},
            format='json')
        self.assertEqual(r.status_code, 400)

    def test_retirer_une_bourse_rend_le_du_a_la_famille(self):
        pec = self._boursier(inscription=100000, mensualite=30000)
        self.client.delete(f'/api/eleves/bourses/{pec.id}/')
        self.assertEqual(self._relire().part_famille, 600000)


class SuiviFinancierTest(OrganismeBase):
    def test_le_suivi_donne_couvert_recu_et_reste(self):
        self._boursier(inscription=100000, mensualite=30000)   # 400 000
        self._payer(150000, organisme=self.etat)

        r = self.client.get('/api/eleves/organismes/suivi/')

        self.assertEqual(r.status_code, 200, r.content[:300])
        ligne = r.data['lignes'][0]
        self.assertEqual(ligne['nom'], 'Ministère de la Formation')
        self.assertEqual((ligne['couvert'], ligne['recu'], ligne['reste']),
                         (400000, 150000, 250000))
        self.assertEqual(ligne['nb_boursiers'], 1)

    def test_le_suivi_liste_les_boursiers(self):
        self._boursier()
        eleves = self.client.get('/api/eleves/organismes/suivi/').data['lignes'][0]['eleves']
        self.assertEqual(eleves[0]['nom_complet'], 'Awa NDIAYE')

    def test_les_totaux_somment_les_lignes(self):
        self._boursier(inscription=100000, mensualite=30000)
        self._payer(150000, organisme=self.etat)

        d = self.client.get('/api/eleves/organismes/suivi/').data

        self.assertEqual(d['totaux']['couvert'],
                         sum(l['couvert'] for l in d['lignes']))
        self.assertEqual(d['totaux']['reste'], 250000)

    def test_un_versement_de_la_famille_ne_compte_pas_pour_l_organisme(self):
        self._boursier(inscription=100000, mensualite=30000)
        self._payer(200000)                       # la famille

        ligne = self.client.get('/api/eleves/organismes/suivi/').data['lignes'][0]

        self.assertEqual(ligne['recu'], 0)
        self.assertEqual(ligne['reste'], 400000)


class PaiementOrganismeApiTest(OrganismeBase):
    """Un versement d'organisme se saisit comme un paiement ordinaire."""

    def test_enregistrer_un_versement_d_organisme(self):
        self._boursier(inscription=100000, mensualite=30000)     # 400 000

        r = self.client.post('/api/paiements/paiements/', {
            'eleve': str(self.eleve.id), 'exercice': str(self.ex.id),
            'montant_inscription': 100000, 'montant_mensualite': 0,
            'montant_uniforme': 0, 'montant_fournitures': 0,
            'montant_cantine': 0, 'montant_divers': 0,
            'mode_paiement': 'VIREMENT', 'organisme': str(self.etat.id),
        }, format='json')

        self.assertEqual(r.status_code, 201, r.content[:400])
        self.assertEqual(r.data['organisme_nom'], 'Ministère de la Formation')

        e = self._relire()
        self.assertEqual(e.paye_organisme, 100000)
        self.assertEqual(e.reste_organisme, 300000)
        self.assertEqual(e.reste_famille, 200000)   # inchangé

    def test_sans_organisme_le_versement_est_celui_de_la_famille(self):
        self._boursier(inscription=100000, mensualite=30000)

        self.client.post('/api/paiements/paiements/', {
            'eleve': str(self.eleve.id), 'exercice': str(self.ex.id),
            'montant_inscription': 200000, 'montant_mensualite': 0,
            'montant_uniforme': 0, 'montant_fournitures': 0,
            'montant_cantine': 0, 'montant_divers': 0,
            'mode_paiement': 'ESPECE',
        }, format='json')

        e = self._relire()
        self.assertEqual(e.paye_organisme, 0)
        self.assertEqual(e.reste_famille, 0)
        self.assertEqual(e.reste_organisme, 400000)


class SyntheseBoursierTest(OrganismeBase):
    """La synthèse remise à la famille sépare sa part de celle de l'organisme."""

    def _synthese(self):
        from apps.eleves.echeancier import construire_echeancier
        return construire_echeancier(
            self._relire(), today=datetime.date(2026, 12, 15))['synthese']

    def test_sans_bourse_le_total_famille_egale_le_total(self):
        s = self._synthese()
        self.assertEqual(s['total_restant_du_famille'], s['total_restant_du'])
        self.assertEqual(s['organisme_nom'], '')

    def test_avec_bourse_la_famille_ne_doit_que_sa_part(self):
        self._boursier(inscription=100000, mensualite=30000)   # 400 000

        s = self._synthese()

        self.assertEqual(s['organisme_nom'], 'Ministère de la Formation')
        self.assertEqual(s['reste_organisme'], 400000)
        self.assertEqual(s['total_restant_du_famille'],
                         s['total_restant_du'] - 400000)

    def test_un_boursier_integral_ne_doit_rien_a_sa_famille(self):
        self._boursier()                                       # bourse totale
        self.assertEqual(self._synthese()['total_restant_du_famille'], 0)

    def test_le_versement_de_l_organisme_ne_reduit_pas_la_part_famille(self):
        self._boursier(inscription=100000, mensualite=30000)
        avant = self._synthese()['total_restant_du_famille']

        self._payer(400000, organisme=self.etat)

        self.assertEqual(self._synthese()['total_restant_du_famille'], avant)

    def test_le_pdf_de_situation_se_genere_pour_un_boursier(self):
        self._boursier(inscription=100000, mensualite=30000)
        r = self.client.get(f'/api/eleves/{self.eleve.id}/situation-pdf/')
        self.assertEqual(r.status_code, 200, r.content[:400])
        self.assertEqual(r['Content-Type'], 'application/pdf')


class CreanceComptableTest(OrganismeBase):
    """La bourse est une créance ferme : elle s'écrit au grand livre.

    Sinon le compte 4112 resterait vide et le bilan ne dirait pas ce que les
    partenaires institutionnels doivent — c'est pourtant la première question
    d'un bailleur devant un centre de formation public.
    """

    def _solde(self, compte):
        from django.db.models import Sum
        from apps.comptabilite.models import JournalEntry
        agg = (JournalEntry.objects.filter(tenant=self.tenant, exercice=self.ex,
                                           no_compte=compte)
               .aggregate(d=Sum('debit'), c=Sum('credit')))
        return round(float(agg['d'] or 0) - float(agg['c'] or 0), 2)

    def _equilibre(self):
        from django.db.models import Sum
        from apps.comptabilite.models import JournalEntry
        agg = (JournalEntry.objects.filter(tenant=self.tenant, exercice=self.ex)
               .aggregate(d=Sum('debit'), c=Sum('credit')))
        return round(float(agg['d'] or 0), 2), round(float(agg['c'] or 0), 2)

    def _attribuer(self, inscription=100000, mensualite=30000):
        return self.client.post('/api/eleves/bourses/', {
            'eleve': str(self.eleve.id), 'organisme': str(self.etat.id),
            'montant_inscription': inscription, 'montant_mensualite': mensualite,
        }, format='json')

    def test_l_attribution_constate_la_creance(self):
        self._attribuer()                                   # 400 000

        self.assertEqual(self._solde('4112'), 400000)
        self.assertEqual(self._solde('706'), -400000)       # produit crédité
        d, c = self._equilibre()
        self.assertEqual(d, c)

    def test_corriger_la_bourse_ne_laisse_qu_une_ecriture(self):
        """Auto-réparateur : dix corrections, une seule pièce."""
        r = self._attribuer(mensualite=30000)
        bourse_id = r.data['id']

        for montant in (40000, 20000, 10000):
            self.client.patch(f'/api/eleves/bourses/{bourse_id}/',
                              {'montant_mensualite': montant}, format='json')

        # 100 000 + 10 000 × 10
        self.assertEqual(self._solde('4112'), 200000)
        from apps.comptabilite.models import JournalEntry
        self.assertEqual(
            JournalEntry.objects.filter(tenant=self.tenant,
                                        source='CREANCE_ORGANISME').count(), 2)

    def test_retirer_la_bourse_efface_la_creance(self):
        r = self._attribuer()
        self.client.delete(f"/api/eleves/bourses/{r.data['id']}/")

        self.assertEqual(self._solde('4112'), 0)
        self.assertEqual(self._solde('706'), 0)

    def test_le_versement_solde_le_4112_sans_reconstater_de_produit(self):
        """Le piège : recréditer 706 à l'encaissement compterait la subvention
        deux fois."""
        self._attribuer()                                   # 4112 D 400 000

        self.client.post('/api/paiements/paiements/', {
            'eleve': str(self.eleve.id), 'exercice': str(self.ex.id),
            'montant_inscription': 400000, 'montant_mensualite': 0,
            'montant_uniforme': 0, 'montant_fournitures': 0,
            'montant_cantine': 0, 'montant_divers': 0,
            'mode_paiement': 'VIREMENT', 'organisme': str(self.etat.id),
        }, format='json')

        self.assertEqual(self._solde('4112'), 0)            # créance soldée
        self.assertEqual(self._solde('706'), -400000)       # produit UNE fois
        d, c = self._equilibre()
        self.assertEqual(d, c)

    def test_le_solde_4112_egale_ce_que_l_organisme_doit_encore(self):
        self._attribuer()                                   # 400 000
        self.client.post('/api/paiements/paiements/', {
            'eleve': str(self.eleve.id), 'exercice': str(self.ex.id),
            'montant_inscription': 150000, 'montant_mensualite': 0,
            'montant_uniforme': 0, 'montant_fournitures': 0,
            'montant_cantine': 0, 'montant_divers': 0,
            'mode_paiement': 'VIREMENT', 'organisme': str(self.etat.id),
        }, format='json')

        self.assertEqual(self._solde('4112'), 250000)
        self.assertEqual(self._relire().reste_organisme, 250000)

    def test_un_reglement_de_famille_ne_touche_pas_le_4112(self):
        self._attribuer()
        self.client.post('/api/paiements/paiements/', {
            'eleve': str(self.eleve.id), 'exercice': str(self.ex.id),
            'montant_inscription': 200000, 'montant_mensualite': 0,
            'montant_uniforme': 0, 'montant_fournitures': 0,
            'montant_cantine': 0, 'montant_divers': 0,
            'mode_paiement': 'ESPECE',
        }, format='json')

        self.assertEqual(self._solde('4112'), 400000)       # intact
        self.assertEqual(self._solde('411'), 0)             # créance famille soldée

    def test_le_bilan_montre_la_creance_sur_l_organisme(self):
        """Le but de tout ce lot : qu'un bailleur puisse lire au bilan ce que
        les partenaires institutionnels doivent."""
        self._attribuer()                                   # 400 000

        r = self.client.get('/api/comptabilite/bilan/')

        self.assertEqual(r.status_code, 200, r.content[:300])
        creances = r.data['actif']['circulant_ao']['creances']
        ligne = next((c for c in creances if c['compte'] == '4112'), None)
        self.assertIsNotNone(ligne, f"4112 absent du bilan : {creances}")
        self.assertEqual(ligne['montant'], 400000)
        self.assertIn('organismes', ligne['libelle'].lower())


class ContenuSituationPdfTest(OrganismeBase):
    """Ce que le document DIT, pas seulement qu'il se génère.

    Les tests précédents vérifiaient un code 200 : ils sont restés verts alors
    que le gabarit affichait encore le dû global à une famille boursière.
    """

    def _html(self):
        from django.template.loader import render_to_string
        from django.utils import timezone

        from apps.eleves.echeancier import NOMS_MOIS, construire_echeancier

        eleve = self._relire()
        ech = construire_echeancier(eleve)
        for ligne in ech['lignes']:
            ligne['libelle'] = f"{NOMS_MOIS[ligne['mois']]} {ligne['annee']}"
        return render_to_string('pdf/situation_eleve.html', {
            'tenant': self.tenant, 'eleve': eleve,
            'section_nom': eleve.section.nom, 'exercice': self.ex,
            'date_edition': timezone.now(), 'paiements': [],
            'echeancier': ech['lignes'], 'hors_mensualite': ech['hors_mensualite'],
            'ech_totaux': ech['totaux'], 'synthese': ech['synthese'],
            'total_paye': eleve.total_paye, 'total_attendu': eleve.total_attendu,
            'reste': eleve.reste_a_payer, 'reliquat_du': 0, 'reliquat_restant': 0,
            'reliquat_annee': '', 'reste_global': 0, 'nb_paiements': 0,
        })

    def test_sans_bourse_le_total_est_celui_de_l_annee(self):
        html = self._html()
        self.assertIn("TOTAL RESTANT DÛ POUR L'ANNÉE", html)
        self.assertNotIn('PAR LA FAMILLE', html)

    def test_avec_bourse_le_total_est_celui_de_la_famille(self):
        self._boursier(inscription=100000, mensualite=30000)   # 400 000

        html = self._html()

        self.assertIn('TOTAL RESTANT DÛ PAR LA FAMILLE', html)
        self.assertIn('Ministère de la Formation', html)
        # La part du tiers apparaît en déduction, pas dans le total réclamé.
        self.assertIn('à sa charge', html)

    def test_un_boursier_integral_ne_se_voit_rien_reclamer(self):
        self._boursier()                                       # bourse totale
        self.assertIn('Rien à votre charge', self._html())

    def test_aucun_commentaire_de_gabarit_n_est_imprime(self):
        """Django ne gère {# #} que sur UNE ligne : un commentaire multi-ligne
        se retrouverait imprimé dans le document remis aux parents."""
        self._boursier()
        html = self._html()
        self.assertNotIn('{#', html)
        self.assertNotIn('{% comment', html)
