"""Reçu de paiement : impayés antérieurs, reçus annulés, format et multi-mode.

Ce que ces tests rendent impossible :
- un reçu sans la ligne « Impayés antérieurs » (« Néant » compris) ;
- un « déjà versé » gonflé par un reçu ANNULÉ (reste à payer faux sur le reçu) ;
- un reçu demandé en A4 qui sort en A5 (seconde règle @page oubliée) ;
- un reçu A5 ordinaire qui déborde sur une deuxième page ;
- un règlement multi-mode rangé sous « MIXTE » au lieu d'être réparti.
"""
from io import BytesIO

from pypdf import PdfReader

from apps.comptabilite.tresorerie import encaissements_par_mode
from apps.paiements.models import Paiement
from apps.paiements.report_reliquats import reporter_reliquats
from apps.eleves.models import Eleve

from .tests_report_reliquats import ReportReliquatsBase


class RecuImpayesAnterieursTest(ReportReliquatsBase):
    def setUp(self):
        super().setUp()
        self._payer(self.eleve, self.ex1, montant_inscription=50000, montant_mensualite=100000)
        self._cloturer(self.ex1)
        reporter_reliquats(self.ex1, self.ex2)
        self.fiche = Eleve.objects.get(exercice=self.ex2)

    def _encaisser(self, **data):
        data = {'eleve': str(self.fiche.id), 'mode_paiement': 'ESPECE', **data}
        r = self.client.post('/api/paiements/paiements/', data, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        return Paiement.objects.get(id=r.data['id'])

    def test_le_recu_porte_les_impayes_anterieurs_restants(self):
        p = self._encaisser(montant_inscription=50000, montant_reliquat=30000)
        r = self.client.get(f'/api/paiements/paiements/{p.id}/recu/')
        self.assertEqual(r.data['reliquat_du'], 150000)
        self.assertEqual(r.data['reliquat_restant_apres'], 120000)
        # Le suivi de l'année n'ajoute que la part « année » du reçu.
        self.assertEqual(r.data['part_exercice'], 50000)
        self.assertEqual(r.data['total_paye_apres'], r.data['deja_paye_avant'] + 50000)

    def test_un_recu_annule_ne_compte_pas_dans_le_deja_verse(self):
        annule = self._encaisser(montant_inscription=20000)
        self.client.post(f'/api/paiements/paiements/{annule.id}/annuler/', {}, format='json')
        p = self._encaisser(montant_inscription=50000)
        r = self.client.get(f'/api/paiements/paiements/{p.id}/recu/')
        self.assertEqual(r.data['deja_paye_avant'], 0)

    def _pdf(self, p, taille):
        r = self.client.get(f'/api/paiements/paiements/{p.id}/recu-pdf/?taille={taille}')
        self.assertEqual(r.status_code, 200)
        return PdfReader(BytesIO(r.content))

    def test_formats_et_une_seule_page(self):
        p = self._encaisser(montant_inscription=50000, montant_mensualite=25000,
                            montant_reliquat=30000, mode_paiement='MIXTE',
                            modes_reglement=[{'mode': 'ESPECE', 'montant': 60000},
                                             {'mode': 'WAVE', 'montant': 45000}],
                            observations='Versement du père')
        a4 = self._pdf(p, 'A4')
        self.assertAlmostEqual(float(a4.pages[0].mediabox.width), 595.28, places=1)
        self.assertEqual(len(a4.pages), 1)
        a5 = self._pdf(p, 'A5')
        self.assertAlmostEqual(float(a5.pages[0].mediabox.width), 419.53, places=1)
        self.assertEqual(len(a5.pages), 1)
        texte = a5.pages[0].extract_text()
        self.assertIn('Impayés antérieurs', texte)

    def test_neant_quand_aucun_impaye_anterieur(self):
        autre = Eleve.objects.create(tenant=self.tenant, exercice=self.ex2, nom_complet='Awa SY',
                                     section=self.section, numero=9,
                                     date_inscription=self.ex2.date_debut)
        r = self.client.post('/api/paiements/paiements/', {
            'eleve': str(autre.id), 'montant_inscription': 50000, 'mode_paiement': 'ESPECE'},
            format='json')
        texte = self._pdf(Paiement.objects.get(id=r.data['id']), 'A5').pages[0].extract_text()
        self.assertIn('Néant', texte)

    def test_multi_mode_reparti_par_mode(self):
        mixte = self._encaisser(montant_inscription=50000, mode_paiement='MIXTE',
                                modes_reglement=[{'mode': 'ESPECE', 'montant': 30000},
                                                 {'mode': 'WAVE', 'montant': 20000}])
        wave = self._encaisser(montant_inscription=10000, mode_paiement='WAVE')
        par_mode = encaissements_par_mode(Paiement.objects.filter(
            tenant=self.tenant, exercice=self.ex2, statut='ACTIF'))
        self.assertNotIn('MIXTE', par_mode)
        self.assertEqual(par_mode['ESPECE'], {'nb': 1, 'montant': 30000.0})
        self.assertEqual(par_mode['WAVE'], {'nb': 2, 'montant': 30000.0})

        stats = self.client.get('/api/paiements/paiements/stats/').data
        self.assertEqual({m['mode'] for m in stats['par_mode']}, {'ESPECE', 'WAVE'})
        canaux = {c['canal']: c for c in self.client.get('/api/dashboard/tresorerie-canaux/').data['canaux']}
        self.assertEqual(canaux['ESPECE']['encaissements'], 30000)
        self.assertEqual(canaux['WAVE']['encaissements'], 30000)
        # Le filtre par mode retrouve aussi le règlement mixte.
        liste = self.client.get('/api/paiements/paiements/?mode=WAVE').data
        lignes = liste['results'] if isinstance(liste, dict) else liste
        self.assertEqual({l['id'] for l in lignes}, {str(mixte.id), str(wave.id)})
