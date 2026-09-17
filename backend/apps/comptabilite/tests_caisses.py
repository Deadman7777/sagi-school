"""Caisses de l'école : l'argent d'un service extra entre dans SA caisse.

Ce que ces tests rendent impossible :
- un encaissement de garderie noyé dans la caisse principale ;
- une caisse dont le solde n'apparaît ni dans les canaux de trésorerie ni dans
  la trésorerie de l'exercice ;
- la suppression d'une caisse qui a déjà reçu des règlements ;
- l'usage de la caisse d'une autre école.
"""
import datetime

from rest_framework.test import APITestCase

from apps.comptabilite.models import CaisseEncaissement, CompteComptable, JournalEntry
from apps.comptabilite.tresorerie import soldes_cloture
from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User

J = datetime.date


class CaissesTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Crèche Les Poussins', code_etablissement='POU')
        self.user = User.objects.create_user('dir@poussins.sn', 'x', nom='Directrice',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        today = datetime.date.today()
        self.ex = Exercice.objects.create(tenant=self.tenant, annee_scolaire='2026-2027', nb_mensualites=10,
                                          date_debut=J(today.year, today.month, 1),
                                          date_fin=J(today.year + 1, today.month, 1) - datetime.timedelta(days=1))
        self.section = Section.objects.create(tenant=self.tenant, nom='CI', frais_mensualite=30000)
        self.eleve = Eleve.objects.create(tenant=self.tenant, exercice=self.ex, section=self.section,
                                          nom_complet='Awa NDIAYE', date_inscription=self.ex.date_debut)

    def _caisse(self, nom='Caisse garderie', **extra):
        r = self.client.post('/api/comptabilite/caisses/', {'nom': nom, **extra}, format='json')
        self.assertEqual(r.status_code, 201, r.content[:300])
        return r.data

    def test_creation_propose_un_compte_et_le_pose_dans_le_plan(self):
        caisse = self._caisse()
        self.assertEqual(caisse['no_compte'], '5716')
        compte = CompteComptable.objects.get(tenant=self.tenant, no_compte='5716')
        self.assertEqual((compte.libelle, compte.classe), ('Caisse garderie', 5))
        self.assertEqual(self._caisse('Caisse cantine')['no_compte'], '5717')
        r = self.client.post('/api/comptabilite/caisses/', {'nom': 'Hors trésorerie', 'no_compte': '411'},
                             format='json')
        self.assertEqual(r.status_code, 400)

    def test_les_especes_entrent_dans_la_caisse_choisie(self):
        caisse = self._caisse()
        r = self.client.post('/api/paiements/paiements/', {
            'eleve': str(self.eleve.id), 'montant_mensualite': 2000, 'mode_paiement': 'ESPECE',
            'mois_regles': [self.ex.date_debut.month], 'caisse': caisse['id']}, format='json')
        self.assertEqual(r.status_code, 201, r.content[:300])
        lignes = {e.no_compte: float(e.debit) for e in JournalEntry.objects.filter(source_id=r.data['id'])}
        self.assertEqual(lignes.get('5716'), 2000)      # la caisse garderie
        self.assertNotIn('571', lignes)                 # pas la caisse principale
        solde = self.client.get('/api/comptabilite/caisses/').data
        ligne = (solde['results'] if isinstance(solde, dict) else solde)[0]
        self.assertEqual(ligne['solde'], 2000)

    def test_un_autre_mode_garde_son_compte(self):
        caisse = self._caisse()
        r = self.client.post('/api/paiements/paiements/', {
            'eleve': str(self.eleve.id), 'montant_mensualite': 3000, 'mode_paiement': 'WAVE',
            'mois_regles': [self.ex.date_debut.month], 'caisse': caisse['id']}, format='json')
        lignes = {e.no_compte: float(e.debit) for e in JournalEntry.objects.filter(source_id=r.data['id'])}
        self.assertEqual(lignes.get('5521'), 3000)      # Wave, pas une caisse en espèces
        self.assertNotIn('5716', lignes)

    def test_la_caisse_compte_dans_la_tresorerie_et_les_canaux(self):
        caisse = self._caisse()
        self.client.post('/api/paiements/paiements/', {
            'eleve': str(self.eleve.id), 'montant_mensualite': 5000, 'mode_paiement': 'ESPECE',
            'mois_regles': [self.ex.date_debut.month], 'caisse': caisse['id']}, format='json')
        self.assertEqual(soldes_cloture(self.ex)['caisse'], 5000)
        canaux = self.client.get('/api/gouvernance/canaux/').data['canaux']
        garderie = next(c for c in canaux if c['compte'] == '5716')
        self.assertEqual((garderie['libelle'], garderie['solde']), ('Caisse garderie', 5000))

    def test_caisse_utilisee_non_supprimable_mais_desactivable(self):
        caisse = self._caisse()
        self.client.post('/api/paiements/paiements/', {
            'eleve': str(self.eleve.id), 'montant_mensualite': 1000, 'mode_paiement': 'ESPECE',
            'mois_regles': [self.ex.date_debut.month], 'caisse': caisse['id']}, format='json')
        r = self.client.delete(f"/api/comptabilite/caisses/{caisse['id']}/")
        self.assertEqual(r.status_code, 409)
        r = self.client.patch(f"/api/comptabilite/caisses/{caisse['id']}/", {'actif': False}, format='json')
        self.assertEqual(r.status_code, 200)
        r = self.client.post('/api/paiements/paiements/', {
            'eleve': str(self.eleve.id), 'montant_mensualite': 1000, 'mode_paiement': 'ESPECE',
            'caisse': caisse['id']}, format='json')
        self.assertEqual(r.status_code, 400)            # caisse désactivée

    def test_la_caisse_d_une_autre_ecole_est_inconnue(self):
        autre = Tenant.objects.create(nom='Autre école', code_etablissement='AUT')
        ailleurs = CaisseEncaissement.objects.create(tenant=autre, nom='Caisse X', no_compte='5716')
        r = self.client.post('/api/paiements/paiements/', {
            'eleve': str(self.eleve.id), 'montant_mensualite': 1000, 'mode_paiement': 'ESPECE',
            'caisse': str(ailleurs.id)}, format='json')
        self.assertEqual(r.status_code, 400)
