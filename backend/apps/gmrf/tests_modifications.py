"""Corriger une opération GMRF déjà enregistrée.

Ce que ces tests protègent :
  - un prêt enregistré sur la banque (521, valeur par défaut) alors que
    l'argent est entré en caisse se corrige : extourne + nouvelle pièce, le
    solde de chaque compte est juste et l'emprunt (162) ne bouge pas ;
  - les fonds d'un prêt peuvent être répartis sur plusieurs modes ;
  - le paiement d'une cotisation se modifie (date, mode) sans changer sa
    nature : versée avant la cagnotte, elle reste une créance ;
  - une opération annulée puis repassée est bien comptabilisée — la garde
    « déjà comptabilisé » ne regardait que l'existence d'une pièce, et une
    cotisation re-payée restait sans écriture.
"""
import datetime

from django.db.models import Sum
from rest_framework.test import APITestCase

from apps.comptabilite.models import JournalEntry
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant
from apps.users.models import User


class ModificationsGmrfTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='École Test', code_etablissement='ETS')
        self.user = User.objects.create_user('a@a.sn', 'x', nom='A',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        today = datetime.date.today()
        Exercice.objects.create(tenant=self.tenant, annee_scolaire='courant', nb_mensualites=10,
                                date_debut=today.replace(month=1, day=1),
                                date_fin=today.replace(month=12, day=31))

    def _solde(self, compte):
        a = JournalEntry.objects.filter(tenant=self.tenant, no_compte=compte).aggregate(
            d=Sum('debit'), c=Sum('credit'))
        return (a['d'] or 0) - (a['c'] or 0)

    # ── Prêts ──
    def _pret(self, **extra):
        data = {'organisme_preteur': 'Banque', 'montant': 410000, 'taux_interet': 0,
                'duree_mois': 10, 'date_deblocage': '2026-03-02', **extra}
        r = self.client.post('/api/gmrf/prets/', data, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        return r.data

    def _modifier_deblocage(self, pret, **data):
        return self.client.patch(f"/api/gmrf/prets/{pret['id']}/",
                                 {'action': 'modifier_deblocage', **data}, format='json')

    def test_pret_passe_de_la_banque_a_la_caisse(self):
        """Le cas réel : prêt créé sur 521 par défaut, argent reçu en caisse."""
        pret = self._pret()
        self.assertEqual(self._solde('521'), 410000)

        r = self._modifier_deblocage(pret, mode_paiement='ESPECE')

        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self._solde('571'), 410000)
        self.assertEqual(self._solde('521'), 0)
        self.assertEqual(self._solde('162'), -410000)
        self.assertEqual(r.data['compte_tresorerie'], '571')
        # Les remboursements partent désormais de la caisse par défaut.
        self.assertEqual(r.data['echeances'][0]['compte_tresorerie'], '571')
        caisse = next(c for c in self.client.get('/api/dashboard/tresorerie-canaux/').data['canaux']
                      if c['canal'] == 'ESPECE')
        self.assertEqual(caisse['solde'], 410000)

    def test_pret_reparti_puis_corrige_deux_fois(self):
        pret = self._pret()
        r = self._modifier_deblocage(pret, modes_deblocage=[
            {'mode': 'ESPECE', 'montant': 300000}, {'mode': 'VIREMENT', 'montant': 110000}])
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual((self._solde('571'), self._solde('521')), (300000, 110000))
        self.assertEqual(r.data['compte_tresorerie'], '571')

        r = self._modifier_deblocage(pret, mode_paiement='WAVE', date_deblocage='2026-03-05')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual((self._solde('571'), self._solde('521'), self._solde('5521')), (0, 0, 410000))
        self.assertEqual(self._solde('162'), -410000)
        self.assertEqual(r.data['date_deblocage'], '2026-03-05')
        self.assertEqual(r.data['modes_deblocage'], [])
        # Le journal garde l'erreur et ses corrections : 3 pièces, 2 extournes.
        self.assertEqual(JournalEntry.objects.filter(source='GMRF_PRET').values('no_piece').distinct().count(), 3)
        self.assertEqual(JournalEntry.objects.filter(source='GMRF_ANNUL_PRET').values('no_piece').distinct().count(), 2)

    def test_repartition_qui_ne_fait_pas_le_total_refusee(self):
        pret = self._pret()
        r = self._modifier_deblocage(pret, modes_deblocage=[
            {'mode': 'ESPECE', 'montant': 300000}, {'mode': 'VIREMENT', 'montant': 100000}])
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self._solde('521'), 410000)

    def test_pret_cree_directement_reparti(self):
        self._pret(modes_deblocage=[{'mode': 'ESPECE', 'montant': 300000},
                                    {'mode': 'ORANGE_MONEY', 'montant': 110000}],
                   frais_dossier=5000)
        self.assertEqual(self._solde('571'), 300000 - 5000)  # frais réglés en caisse
        self.assertEqual(self._solde('5522'), 110000)
        self.assertEqual(self._solde('6312'), 5000)

    def test_pret_cree_avec_un_seul_mode(self):
        self._pret(mode_paiement='ESPECE')
        self.assertEqual((self._solde('571'), self._solde('521')), (410000, 0))

    def test_echeance_annulee_puis_repayee_est_comptabilisee(self):
        pret = self._pret(mode_paiement='ESPECE')
        url = f"/api/gmrf/echeances/{pret['echeances'][0]['id']}/"
        self.client.patch(url, {'action': 'payer', 'mode_paiement': 'ESPECE'}, format='json')
        self.client.patch(url, {'action': 'annuler'}, format='json')
        self.client.patch(url, {'action': 'payer', 'mode_paiement': 'ESPECE'}, format='json')
        self.assertEqual(self._solde('571'), 410000 - 41000)
        self.assertEqual(self._solde('162'), -410000 + 41000)

    # ── NATT ──
    def _cycle(self):
        r = self.client.post('/api/gmrf/natt/', {
            'nom': 'Tontine', 'nb_participants': 5, 'duree': 5, 'periodicite': 'MENSUELLE',
            'montant_cotisation': 10000, 'date_debut': '2026-02-05'}, format='json')
        return r.data

    def _cotis(self, cycle, n, **data):
        co = cycle['cotisations'][n]
        return self.client.patch(f"/api/gmrf/cotisations/{co['id']}/", data, format='json')

    def test_modifier_le_paiement_d_une_cotisation(self):
        cycle = self._cycle()
        self._cotis(cycle, 0, action='payer', mode_paiement='ESPECE', date_paiement='2026-02-05')

        r = self._cotis(cycle, 0, action='modifier', mode_paiement='WAVE', date_paiement='2026-02-07')

        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual((r.data['mode_paiement'], r.data['date_paiement']), ('WAVE', '2026-02-07'))
        self.assertEqual((self._solde('571'), self._solde('5521')), (0, -10000))
        self.assertEqual(self._solde('4718'), 10000)
        nouvelle = JournalEntry.objects.filter(source='GMRF_COTIS').order_by('-no_piece').first()
        self.assertEqual(nouvelle.date_ecriture, datetime.date(2026, 2, 7))

    def test_cotisation_avant_cagnotte_reste_une_creance_apres_modification(self):
        cycle = self._cycle()
        self._cotis(cycle, 0, action='payer', mode_paiement='ESPECE')
        self.client.post(f"/api/gmrf/natt/{cycle['id']}/reception/", {
            'numero_echeance': 2, 'montant_recu': 50000, 'mode_paiement': 'ESPECE'}, format='json')
        creance, dette = self._solde('4718'), self._solde('4798')

        r = self._cotis(cycle, 0, action='modifier', mode_paiement='WAVE')

        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual((self._solde('4718'), self._solde('4798')), (creance, dette))

    def test_modifier_une_cotisation_non_payee_refuse(self):
        cycle = self._cycle()
        r = self._cotis(cycle, 0, action='modifier', mode_paiement='WAVE')
        self.assertEqual(r.status_code, 400)

    def test_cotisation_annulee_puis_repayee_est_comptabilisee(self):
        cycle = self._cycle()
        self._cotis(cycle, 0, action='payer', mode_paiement='ESPECE')
        self._cotis(cycle, 0, action='annuler')
        self._cotis(cycle, 0, action='payer', mode_paiement='ESPECE')
        self.assertEqual(self._solde('571'), -10000)
        self.assertEqual(self._solde('4718'), 10000)
