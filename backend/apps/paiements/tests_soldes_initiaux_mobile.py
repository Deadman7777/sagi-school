"""Soldes initiaux du mobile money : un par opérateur (Wave, Orange Money, Free Money).

Demande du 11/10/2026 : en Paramètres, un seul « solde initial Mobile Money »
était porté en entier par Wave (5521) ; Orange Money et Free Money ouvraient
toujours à zéro.

Ce que ces tests protègent :
  - chaque solde se saisit et se relit ;
  - chaque canal du tableau de bord ouvre sur SON solde, et le total les
    additionne ;
  - la balance (552 synthétique) et le résultat de trésorerie les comptent tous ;
  - la clôture et les à-nouveaux reportent chaque opérateur sur son champ, au
    lieu de verser tout le mobile money sur Wave.
"""
import datetime

from rest_framework.test import APITestCase

from apps.comptabilite import exercices
from apps.comptabilite.models import JournalEntry
from apps.paiements.cloturer import cloturer_exercice
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant
from apps.users.models import User


class SoldesInitiauxMobileTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='École Test', code_etablissement='ETS')
        self.user = User.objects.create_user('a@a.sn', 'x', nom='A',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        today = datetime.date.today()
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire=str(today.year),
            date_debut=today.replace(month=1, day=1), date_fin=today.replace(month=12, day=31),
            solde_initial_caisse=1000)

    def _saisir(self):
        r = self.client.patch(f'/api/paiements/exercices/{self.ex.id}/', {
            'solde_initial_mobile': 10000, 'solde_initial_orange_money': 20000,
            'solde_initial_free_money': 5000}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.ex.refresh_from_db()
        return r.data

    def test_saisie_et_relecture(self):
        d = self._saisir()
        self.assertEqual((d['solde_initial_mobile'], d['solde_initial_orange_money'],
                          d['solde_initial_free_money']), (10000, 20000, 5000))
        self.assertEqual(self.ex.solde_initial_mobile_money, 35000)
        self.assertEqual(self.ex.solde_initial_total, 36000)

    def test_chaque_canal_ouvre_sur_son_solde(self):
        self._saisir()
        d = self.client.get('/api/dashboard/tresorerie-canaux/').data
        initial = {c['canal']: c['solde_initial'] for c in d['canaux']}
        self.assertEqual((initial['WAVE'], initial['ORANGE_MONEY'], initial['FREE_MONEY']),
                         (10000, 20000, 5000))
        self.assertEqual({c['canal']: c['solde'] for c in d['canaux']}['ORANGE_MONEY'], 20000)
        self.assertEqual(d['totaux']['solde_initial'], 36000)
        self.assertEqual(d['totaux']['solde_initial'], sum(initial.values()))

    def test_balance_552_compte_les_trois_operateurs(self):
        self._saisir()
        JournalEntry.objects.create(tenant=self.tenant, exercice=self.ex, no_piece='X1',
                                    date_ecriture=self.ex.date_debut, no_compte='5522',
                                    debit=0, credit=3000, libelle='retrait', source='CHARGE')
        JournalEntry.objects.create(tenant=self.tenant, exercice=self.ex, no_piece='X1',
                                    date_ecriture=self.ex.date_debut, no_compte='6052',
                                    debit=3000, credit=0, libelle='retrait', source='CHARGE')
        r = self.client.get('/api/comptabilite/balance/')
        self.assertEqual(r.status_code, 200)
        ligne = next(l for l in r.data['lignes'] if l['no_compte'] == '552')
        self.assertEqual(ligne['so_debiteur'], 35000)
        self.assertEqual(ligne['sf_debiteur'], 32000)

    def test_cloture_reporte_chaque_operateur(self):
        self._saisir()
        JournalEntry.objects.create(tenant=self.tenant, exercice=self.ex, no_piece='X1',
                                    date_ecriture=self.ex.date_debut, no_compte='5523',
                                    debit=2000, credit=0, libelle='recette', source='RECETTE')
        JournalEntry.objects.create(tenant=self.tenant, exercice=self.ex, no_piece='X1',
                                    date_ecriture=self.ex.date_debut, no_compte='758',
                                    debit=0, credit=2000, libelle='recette', source='RECETTE')
        cloturer_exercice(self.ex, reporter_impayes=False)
        suivant = exercices.exercice_suivant(self.ex)
        self.assertEqual((suivant.solde_initial_caisse, suivant.solde_initial_mobile,
                          suivant.solde_initial_orange_money, suivant.solde_initial_free_money),
                         (1000, 10000, 20000, 7000))

    def test_a_nouveaux_reportent_chaque_operateur(self):
        self._saisir()
        today = datetime.date.today()
        cible = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire=str(today.year + 1),
            date_debut=today.replace(year=today.year + 1, month=1, day=1),
            date_fin=today.replace(year=today.year + 1, month=12, day=31))
        res = exercices.generer_a_nouveaux(self.ex, cible)
        cible.refresh_from_db()
        self.assertEqual((cible.solde_initial_mobile, cible.solde_initial_orange_money,
                          cible.solde_initial_free_money), (10000, 20000, 5000))
        self.assertEqual(res['tresorerie']['mobile'], 35000)
        self.assertEqual(exercices.controle_continuite(self.ex, cible), [])
