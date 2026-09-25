"""Encaisser pour une famille ou un organisme, et un seul recouvrement.

Ce que ces tests rendent impossible :
- une famille qui ne peut pas payer d'avance un mois pas encore échu ;
- une cantine réglée en famille comptée en service éducatif (706) ;
- un acompte sur un mois à venir imputé sur un autre mois ;
- un versement d'organisme qui ne solde pas sa créance (4112) ou qu'on
  réclame ensuite à la famille ;
- un tableau de bord et un suivi mensuel qui annoncent deux impayés différents.
"""
import datetime

from rest_framework.test import APITestCase

from apps.comptabilite.models import JournalEntry
from apps.eleves.models import (EleveService, Organisme, PriseEnChargeOrganisme, Service)
from apps.paiements.models import Paiement

from apps.eleves.tests_familles import BaseFamille

MARS = datetime.date(2026, 3, 15)


class EncaissementFamilleTest(BaseFamille):

    def setUp(self):
        super().setUp()
        self.famille = self._famille()
        self.ex.nb_mensualites = 10
        self.ex.save()

    def _enfant(self, nom, **kwargs):
        return self._eleve(nom, famille=self.famille, **kwargs)

    def _enfants(self, today=MARS):
        from apps.eleves.echeancier import precharger
        from apps.eleves.encaissement_groupe import echeances_eleve
        return [echeances_eleve(e, today=today)
                for e in precharger(self.famille.eleves.filter(exercice=self.ex))]

    def _encaisser(self, lignes):
        for ligne in lignes:
            for reglement in ligne['reglements']:
                corps = {k: v for k, v in reglement.items() if k not in ('detail', 'total')}
                corps.update({'mode_paiement': 'ESPECE', 'date_paiement': '2026-03-15'})
                r = self.client.post('/api/paiements/paiements/', corps, format='json')
                self.assertEqual(r.status_code, 201, r.content[:400])

    # ── Anticiper ────────────────────────────────────────────────────────
    def test_sans_anticipation_seul_l_echu_est_servi(self):
        from apps.eleves.encaissement_groupe import repartir_montant
        self._enfant('Seul NDIAYE')
        # Inscription 25 000 + trois mois échus (janvier-mars) = 70 000.
        selection, reste = repartir_montant(self._enfants(), 100000)
        self.assertEqual(round(sum(s['montant'] for s in selection), 2), 70000)
        self.assertEqual(reste, 30000)

    def test_la_famille_peut_payer_d_avance(self):
        from apps.eleves.encaissement_groupe import repartir_montant
        self._enfant('Seul NDIAYE')
        selection, reste = repartir_montant(self._enfants(), 100000, anticiper=True)
        self.assertEqual(reste, 0)
        mois = [s['cle'] for s in selection if s['cle'].startswith('M')]
        self.assertEqual(mois, ['M1', 'M2', 'M3', 'M4', 'M5'])

    def test_un_mois_a_venir_coche_est_encaisse_et_solde(self):
        from apps.eleves.encaissement_groupe import preparer
        enfant = self._enfant('Seul NDIAYE')
        enfants = self._enfants()
        lignes = preparer(enfants, [{'eleve_id': str(enfant.id), 'cle': 'M6', 'montant': 15000}])
        self.assertEqual(lignes[0]['reglements'][0]['mois_regles'], [6])
        self._encaisser(lignes)
        from apps.eleves.echeancier import construire_echeancier
        juin = next(l for l in construire_echeancier(enfant, today=MARS)['lignes'] if l['mois'] == 6)
        self.assertEqual(juin['statut'], 'SOLDE')

    def test_un_acompte_sur_un_mois_a_venir_reste_sur_ce_mois(self):
        """Non désigné, l'acompte d'avril irait solder janvier : le parent
        croirait avoir payé avril, la fiche dirait l'inverse."""
        from apps.eleves.echeancier import construire_echeancier
        from apps.eleves.encaissement_groupe import preparer
        enfant = self._enfant('Seul NDIAYE')
        lignes = preparer(self._enfants(), [{'eleve_id': str(enfant.id), 'cle': 'M4', 'montant': 5000}])
        self._encaisser(lignes)
        par_mois = {l['mois']: l for l in construire_echeancier(enfant, today=MARS)['lignes']}
        self.assertEqual(par_mois[4]['paye'], 5000)
        self.assertEqual(par_mois[1]['paye'], 0)

    def test_deux_mois_de_montants_differents_ne_se_faussent_pas(self):
        """L'échéancier partage un règlement à parts égales entre ses mois :
        deux montants différents dans un même règlement fausseraient les deux."""
        from apps.eleves.encaissement_groupe import preparer_reglements
        enfant = self._enfant('Seul NDIAYE')
        fiche = self._enfants()[0]
        reglements = preparer_reglements(fiche, {'M1': 15000, 'M2': 15000, 'M3': 9000})
        self.assertEqual(sorted(r['mois_regles'] for r in reglements), [[1, 2], [3]])
        self.assertEqual(enfant.nom_complet, fiche['nom_complet'])

    # ── Services ─────────────────────────────────────────────────────────
    def test_la_cantine_reglee_en_famille_va_au_758(self):
        from apps.eleves.encaissement_groupe import preparer
        enfant = self._enfant('Seul NDIAYE')
        cantine = Service.objects.create(tenant=self.tenant, nom='Cantine', montant=5000,
                                         periodicite='MENSUEL')
        EleveService.objects.create(tenant=self.tenant, eleve=enfant, service=cantine)
        lignes = preparer(self._enfants(), [{'eleve_id': str(enfant.id), 'cle': 'M1', 'montant': 20000}])
        reglement = lignes[0]['reglements'][0]
        self.assertEqual(reglement['montant_mensualite'], 15000)
        self.assertEqual(reglement['services_regles'],
                         [{'nom': 'Cantine', 'montant': 5000.0, 'nature': 'MENSUEL'}])
        self.assertEqual(reglement['part_accessoire'], 5000)
        self._encaisser(lignes)
        credit_758 = sum(float(e.credit) for e in JournalEntry.objects.filter(
            tenant=self.tenant, no_compte='758'))
        self.assertEqual(credit_758, 5000)

    # ── API ──────────────────────────────────────────────────────────────
    def test_l_api_prepare_une_selection_et_un_montant(self):
        enfant = self._enfant('Seul NDIAYE')
        r = self.client.get(f'/api/eleves/familles/{self.famille.id}/echeances/')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertTrue(any(not p['echu'] for p in r.data['enfants'][0]['postes'])
                        or datetime.date.today() > self.ex.date_fin)
        r = self.client.post(f'/api/eleves/familles/{self.famille.id}/preparer/',
                             {'selection': [{'eleve_id': str(enfant.id), 'cle': 'ENTREE',
                                             'montant': 25000}]}, format='json')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(r.data['total'], 25000)
        r = self.client.post(f'/api/eleves/familles/{self.famille.id}/preparer/',
                             {'montant': 0}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_la_situation_de_la_famille_se_telecharge(self):
        self._enfant('Aine NDIAYE')
        self._enfant('Cadet NDIAYE')
        r = self.client.get(f'/api/eleves/familles/{self.famille.id}/situation-pdf/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')
        self.assertIn('situation_FamilleNDIAYE', r['Content-Disposition'])


class EncaissementOrganismeTest(BaseFamille):

    def setUp(self):
        super().setUp()
        self.ex.nb_mensualites = 10
        self.ex.save()
        self.organisme = Organisme.objects.create(tenant=self.tenant, nom='Fondation Horizon',
                                                  type='FONDATION')
        self.boursier = self._eleve('Boursier FALL')
        r = self.client.post('/api/eleves/bourses/', {
            'eleve': str(self.boursier.id), 'organisme': str(self.organisme.id),
            'exercice': str(self.ex.id), 'montant_mensualite': 7500}, format='json')
        self.assertEqual(r.status_code, 201, r.content[:300])

    def test_le_versement_de_l_organisme_solde_sa_creance(self):
        r = self.client.post(f'/api/eleves/organismes/{self.organisme.id}/preparer/',
                             {'montant': 30000}, format='json')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(r.data['total'], 30000)
        for ligne in r.data['lignes']:
            for reglement in ligne['reglements']:
                self.assertEqual(reglement['organisme'], str(self.organisme.id))
                corps = {k: v for k, v in reglement.items() if k not in ('detail', 'total')}
                corps['mode_paiement'] = 'VIREMENT'
                p = self.client.post('/api/paiements/paiements/', corps, format='json')
                self.assertEqual(p.status_code, 201, p.content[:300])
        self.boursier.refresh_from_db()
        self.assertEqual(self.boursier.paye_organisme, 30000)
        self.assertEqual(self.boursier.reste_organisme, 75000 - 30000)
        credit_4112 = sum(float(e.credit) for e in JournalEntry.objects.filter(
            tenant=self.tenant, no_compte='4112'))
        self.assertEqual(credit_4112, 30000)

    def test_la_famille_n_est_pas_relancee_pour_la_part_de_l_organisme(self):
        from apps.eleves.encaissement_groupe import echeances_eleve
        fiche = echeances_eleve(self.boursier, today=MARS)
        janvier = next(p for p in fiche['postes'] if p['cle'] == 'M1')
        self.assertEqual(janvier['part_organisme'], 7500)
        self.assertEqual(janvier['reste_famille'], 7500)

    def test_le_suivi_montre_chaque_versement_du_boursier(self):
        Paiement.objects.all().delete()
        r = self.client.post('/api/paiements/paiements/', {
            'eleve': str(self.boursier.id), 'organisme': str(self.organisme.id),
            'montant_mensualite': 7500, 'mode_paiement': 'VIREMENT'}, format='json')
        self.assertEqual(r.status_code, 201, r.content[:300])
        suivi = self.client.get('/api/eleves/organismes/suivi/').data
        eleve = suivi['lignes'][0]['eleves'][0]
        self.assertEqual(len(eleve['versements']), 1)
        self.assertEqual(eleve['versements'][0]['montant'], 7500)

    def test_le_releve_de_l_organisme_se_telecharge(self):
        r = self.client.get(f'/api/eleves/organismes/{self.organisme.id}/releve-pdf/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')


class RecouvrementUniqueTest(BaseFamille):
    """Tableau de bord et suivi mensuel : le même impayé, au franc près."""

    def test_un_eleve_parti_ne_fausse_pas_l_un_des_deux(self):
        present = self._eleve('Present NDIAYE')
        parti = self._eleve('Parti FALL')
        for eleve, montant in ((present, 25000), (parti, 40000)):
            r = self.client.post('/api/paiements/paiements/', {
                'eleve': str(eleve.id), 'montant_inscription': 25000,
                'montant_mensualite': montant - 25000, 'mode_paiement': 'ESPECE',
                'date_paiement': '2026-01-10'}, format='json')
            self.assertEqual(r.status_code, 201, r.content[:300])
        parti.statut = 'TRANSFERE'
        parti.date_sortie = datetime.date(2026, 2, 1)
        parti.save()

        kpis = self.client.get('/api/dashboard/kpis/').data
        suivi = self.client.get('/api/eleves/suivi-mensuel/').data['synthese']
        impayes = kpis.get('total_impayes', kpis.get('kpis', {}).get('total_impayes'))
        self.assertEqual(impayes, suivi['reste'])
        self.assertEqual(kpis.get('taux_recouvrement', kpis.get('kpis', {}).get('taux_recouvrement')),
                         suivi['taux_recouvrement'])
        # L'argent du parti reste une recette de l'année.
        self.assertEqual(suivi['total_encaisse'], 65000)


class ExportClasseTest(BaseFamille):

    def test_la_liste_financiere_d_une_seule_classe(self):
        from apps.academique.models import Classe, NiveauScolaire
        niveau = NiveauScolaire.objects.create(tenant=self.tenant, nom='Élémentaire', code='EL')
        cp = Classe.objects.create(tenant=self.tenant, niveau=niveau, nom='CP', code='CP')
        self._eleve('Dans CP', classe=cp)
        self._eleve('Ailleurs FALL')
        r = self.client.get('/api/eleves/export-pdf/', {'classe': str(cp.id)})
        self.assertEqual(r.status_code, 200, r.content[:300])
        r = self.client.get('/api/eleves/export-pdf/', {'classe': str(cp.id), 'financier': '0'})
        self.assertEqual(r.status_code, 200, r.content[:300])


del APITestCase
