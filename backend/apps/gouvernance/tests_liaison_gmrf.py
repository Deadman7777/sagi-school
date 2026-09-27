"""Liaison Ressources financières (GMRF) ↔ Gouvernance.

Ce que ces tests rendent impossible :
- une ressource mobilisée dans Gouvernance sans compte de trésorerie ni écriture ;
- un financement ou un prêt GMRF qui doit être ressaisi dans Gouvernance ;
- deux ressources pour le même financement (double enregistrement) ;
- une ressource reliée qui diverge de son opération GMRF (montant, compte) ;
- un encaissement « reçu » sans écriture faute d'exercice ouvert.
"""
import datetime
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.db.models import Sum
from rest_framework.test import APITestCase

from apps.comptabilite.models import JournalEntry
from apps.gmrf.models import Financement, Pret
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant
from apps.users.models import User

from apps.gouvernance.models import Ressource


class Base(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='École A', code_etablissement='LGA')
        user = User.objects.create_user('a@a.sn', 'x', nom='A', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(user)
        self.exercice = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2025-2026',
            date_debut=datetime.date(2025, 10, 1), date_fin=datetime.date(2026, 9, 30))

    def _solde(self, compte):
        a = JournalEntry.objects.filter(tenant=self.tenant, no_compte=compte).aggregate(
            d=Sum('debit'), c=Sum('credit'))
        return (a['d'] or 0) - (a['c'] or 0)

    def _type(self, code):
        self.client.get('/api/gmrf/types/')
        return str(self.tenant.gmrf_typefinancement_set.get(code=code).id)


class GouvernanceVersGmrfTest(Base):
    def test_mobiliser_une_subvention_encaisse_sur_le_compte_choisi(self):
        r = self.client.post('/api/gouvernance/ressources/', {
            'type_ressource': 'SUBVENTION', 'libelle': 'Subvention mairie', 'organisme': 'Mairie',
            'montant': 500000, 'date_ressource': '2026-01-15', 'compte_tresorerie': '521'}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data['compte_tresorerie'], '521')
        self.assertEqual(r.data['origine'], 'FINANCEMENT')
        self.assertTrue(r.data['origine_reference'].startswith('GRF-'))
        # Encaissement comptabilisé une fois : banque débitée, subvention créditée.
        self.assertEqual(self._solde('521'), 500000)
        self.assertEqual(self._solde('71'), -500000)
        f = Financement.objects.get(tenant=self.tenant)
        self.assertEqual(f.statut, 'RECU')
        # Les lignes d'encaissement sont rattachées à la ressource.
        self.assertTrue(JournalEntry.objects.filter(ressource_id=r.data['id'], no_compte='521').exists())
        # …sans compter comme consommation.
        self.assertEqual(r.data['montant_consomme'], 0)

    def test_compte_de_tresorerie_obligatoire(self):
        r = self.client.post('/api/gouvernance/ressources/', {
            'type_ressource': 'DON', 'libelle': 'Don', 'montant': 10000}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Financement.objects.exists())
        self.assertFalse(Ressource.objects.exists())

    def test_apport_des_fondateurs_en_capitaux(self):
        r = self.client.post('/api/gouvernance/ressources/', {
            'type_ressource': 'FONDS_PROPRES', 'libelle': 'Apport du fondateur', 'montant': 2000000,
            'compte_tresorerie': '571'}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(self._solde('101'), -2000000)
        self.assertEqual(self._solde('571'), 2000000)

    def test_un_pret_se_saisit_dans_gmrf(self):
        r = self.client.post('/api/gouvernance/ressources/', {
            'type_ressource': 'PRET', 'libelle': 'Prêt', 'montant': 1000000,
            'compte_tresorerie': '521'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('Prêts', r.data['error'])

    def test_recettes_scolaires_sans_nouvel_encaissement(self):
        r = self.client.post('/api/gouvernance/ressources/', {
            'type_ressource': 'RECETTES_SCOLAIRES', 'libelle': 'Scolarité 2026',
            'montant': 3000000}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertFalse(JournalEntry.objects.exists())

    def test_fonds_attendus_la_ressource_nait_a_l_encaissement(self):
        r = self.client.post('/api/gouvernance/ressources/', {
            'type_ressource': 'DON', 'libelle': 'Don promis', 'montant': 80000,
            'encaissement': 'ATTENDU'}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.data['attendu'])
        self.assertFalse(Ressource.objects.exists())
        f = Financement.objects.get()
        self.client.patch(f'/api/gmrf/financements/{f.id}/', {'action': 'encaisser',
                                                               'compte_tresorerie': '5521'}, format='json')
        res = Ressource.objects.get(financement=f)
        self.assertEqual(res.compte_tresorerie, '5521')

    def test_sans_exercice_ouvert_rien_n_est_encaisse(self):
        self.exercice.cloture = True
        self.exercice.save()
        r = self.client.post('/api/gouvernance/ressources/', {
            'type_ressource': 'DON', 'libelle': 'Don', 'montant': 10000, 'compte_tresorerie': '571'},
            format='json')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Financement.objects.exists())


class GmrfVersGouvernanceTest(Base):
    def test_financement_recu_dans_gmrf_apparait_en_gouvernance(self):
        r = self.client.post('/api/gmrf/financements/', {
            'type_financement': self._type('DON'), 'libelle': 'Don entreprise', 'source': 'SOCOCIM',
            'montant': 250000, 'statut': 'RECU', 'compte_tresorerie': '521'}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.data['ressource_reference'].startswith('RES-'))
        res = self.client.get('/api/gouvernance/ressources/').data
        self.assertEqual(len(res), 1)
        self.assertEqual((res[0]['compte_tresorerie'], res[0]['type_ressource'], res[0]['organisme']),
                         ('521', 'DON', 'SOCOCIM'))
        # Une seule écriture d'encaissement : pas de double comptage.
        self.assertEqual(self._solde('521'), 250000)

    def test_financement_attendu_pas_encore_de_ressource(self):
        self.client.post('/api/gmrf/financements/', {
            'type_financement': self._type('DON'), 'libelle': 'Promesse', 'montant': 1000}, format='json')
        self.assertFalse(Ressource.objects.exists())

    def test_annuler_le_financement_annule_la_ressource(self):
        r = self.client.post('/api/gmrf/financements/', {
            'type_financement': self._type('DON'), 'libelle': 'Don', 'montant': 1000,
            'statut': 'RECU', 'compte_tresorerie': '571'}, format='json')
        self.client.patch(f"/api/gmrf/financements/{r.data['id']}/", {'action': 'annuler'}, format='json')
        self.assertEqual(Ressource.objects.get().statut, 'ANNULEE')
        self.assertEqual(self._solde('571'), 0)

    def test_pret_debloque_apparait_en_gouvernance(self):
        r = self.client.post('/api/gmrf/prets/', {
            'organisme_preteur': 'BNDE', 'objet': 'Bus scolaire', 'montant': 12000000,
            'taux_interet': 8, 'duree_mois': 24, 'date_deblocage': '2026-01-10',
            'compte_tresorerie': '521', 'frais_dossier': 100000}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        res = Ressource.objects.get()
        self.assertEqual((res.type_ressource, res.compte_tresorerie, res.montant),
                         ('PRET', '521', Decimal('12000000')))
        # Les frais de dossier (charge) ne comptent pas comme consommation du prêt.
        self.assertEqual(self.client.get(f'/api/gouvernance/ressources/{res.id}/').data['montant_consomme'], 0)


class VerrousTest(Base):
    def setUp(self):
        super().setUp()
        r = self.client.post('/api/gouvernance/ressources/', {
            'type_ressource': 'DON', 'libelle': 'Don', 'montant': 50000, 'compte_tresorerie': '571'},
            format='json')
        self.res = Ressource.objects.get(id=r.data['id'])

    def test_une_seule_ressource_par_financement(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Ressource.objects.create(tenant=self.tenant, reference='RES-9999', libelle='Doublon',
                                     montant=50000, financement=self.res.financement)

    def test_montant_et_compte_verrouilles_mais_le_reste_modifiable(self):
        r = self.client.patch(f'/api/gouvernance/ressources/{self.res.id}/', {'montant': 90000}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.client.patch(f'/api/gouvernance/ressources/{self.res.id}/', {'compte_tresorerie': '521'},
                              format='json')
        self.assertEqual(r.status_code, 400)
        # L'écran renvoie tout le formulaire : les valeurs inchangées passent.
        r = self.client.patch(f'/api/gouvernance/ressources/{self.res.id}/', {
            'montant': 50000, 'libelle': 'Don', 'observations': 'Pour la bibliothèque'}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data['observations'], 'Pour la bibliothèque')

    def test_suppression_renvoyee_a_gmrf(self):
        r = self.client.delete(f'/api/gouvernance/ressources/{self.res.id}/')
        self.assertEqual(r.status_code, 400)
        self.assertTrue(Ressource.objects.filter(id=self.res.id).exists())


class RepriseExistantTest(Base):
    def test_relie_la_saisie_manuelle_au_lieu_de_dupliquer(self):
        # Avant la v1.53 : don saisi dans GMRF ET ressaisi à la main dans Gouvernance.
        from apps.gmrf import services
        from apps.gmrf.models import TypeFinancement
        self.client.get('/api/gmrf/types/')
        tf = TypeFinancement.objects.get(tenant=self.tenant, code='DON')
        f = services.creer_financement(self.tenant, tf, Decimal('300000'), libelle='Don SOCOCIM',
                                       source='SOCOCIM', statut='RECU', compte_tresorerie='521')
        manuelle = Ressource.objects.create(tenant=self.tenant, reference='RES-0001', libelle='Don SOCOCIM',
                                            organisme='Sococim', montant=Decimal('300000'))
        orpheline = Ressource.objects.create(tenant=self.tenant, reference='RES-0002', libelle='Fonds divers',
                                             montant=Decimal('10000'), type_ressource='AUTRE')
        sortie = StringIO()
        call_command('lier_ressources_gmrf', stdout=sortie)          # simulation
        self.assertIsNone(Ressource.objects.get(id=manuelle.id).financement_id)
        call_command('lier_ressources_gmrf', '--appliquer', stdout=sortie)
        manuelle.refresh_from_db()
        self.assertEqual((manuelle.financement_id, manuelle.compte_tresorerie), (f.id, '521'))
        self.assertEqual(Ressource.objects.count(), 2)                 # aucun doublon créé
        self.assertIn('RES-0002', sortie.getvalue())                   # l'orpheline est signalée
        self.assertIsNone(Ressource.objects.get(id=orpheline.id).financement_id)
