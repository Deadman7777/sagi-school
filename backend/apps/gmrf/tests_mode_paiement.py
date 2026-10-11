"""Mode de paiement des cotisations NATT, de la cagnotte et des remboursements de prêt.

Ce que ces tests protègent :
  - le mode choisi décide du compte de trésorerie de l'écriture (Wave → 5521,
    virement → 521…), comme pour les recettes élèves ;
  - sans mode, l'ancien comportement reste (compte de l'opération) ;
  - un mode inconnu est refusé sans rien écrire ;
  - l'annulation extourne bien le compte du mode, puis l'efface.
"""
import datetime

from django.db.models import Sum
from rest_framework.test import APITestCase

from apps.comptabilite.models import JournalEntry
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant
from apps.users.models import User


class ModePaiementGmrfTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='École Test', code_etablissement='ETS')
        self.user = User.objects.create_user('a@a.sn', 'x', nom='A',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        today = datetime.date.today()
        Exercice.objects.create(tenant=self.tenant, annee_scolaire='courant',
                                date_debut=today.replace(month=1, day=1),
                                date_fin=today.replace(month=12, day=31))
        self.cycle = self.client.post('/api/gmrf/natt/', {
            'nom': 'Tontine', 'nb_participants': 5, 'duree': 5, 'periodicite': 'MENSUELLE',
            'montant_cotisation': 10000, 'date_debut': '2026-02-05'}, format='json').data
        self.pret = self.client.post('/api/gmrf/prets/', {
            'organisme_preteur': 'Banque', 'montant': 1200000, 'taux_interet': 0,
            'duree_mois': 12, 'date_deblocage': '2026-01-15',
            'date_premiere_echeance': '2026-02-28'}, format='json').data

    def _solde(self, compte, source_prefix='GMRF_'):
        a = JournalEntry.objects.filter(tenant=self.tenant, no_compte=compte,
                                        source__startswith=source_prefix).aggregate(
            d=Sum('debit'), c=Sum('credit'))
        return (a['d'] or 0) - (a['c'] or 0)

    def _payer_cotisation(self, n, **data):
        co = self.cycle['cotisations'][n]
        return self.client.patch(f"/api/gmrf/cotisations/{co['id']}/",
                                 {'action': 'payer', **data}, format='json')

    # ── NATT ──
    def test_cotisation_wave_sort_du_5521(self):
        r = self._payer_cotisation(0, mode_paiement='WAVE', date_paiement='2026-02-05')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual((r.data['mode_paiement'], r.data['compte_tresorerie']), ('WAVE', '5521'))
        self.assertEqual(self._solde('5521'), -10000)
        self.assertEqual(self._solde('571'), 0)

    def test_cotisation_sans_mode_garde_le_compte_du_cycle(self):
        r = self._payer_cotisation(0)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual((r.data['mode_paiement'], r.data['compte_tresorerie']), ('', '571'))
        self.assertEqual(self._solde('571'), -10000)

    def test_mode_inconnu_refuse_sans_ecriture(self):
        r = self._payer_cotisation(0, mode_paiement='BITCOIN')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(JournalEntry.objects.filter(source='GMRF_COTIS').exists())
        cycle = self.client.get(f"/api/gmrf/natt/{self.cycle['id']}/").data
        self.assertEqual(cycle['cotisations'][0]['statut'], 'A_PAYER')

    def test_annulation_extourne_le_compte_du_mode(self):
        co = self._payer_cotisation(0, mode_paiement='ORANGE_MONEY').data
        r = self.client.patch(f"/api/gmrf/cotisations/{co['id']}/", {'action': 'annuler'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self._solde('5522'), 0)
        self.assertEqual(r.data['mode_paiement'], '')

    def test_reception_cagnotte_par_virement(self):
        r = self.client.post(f"/api/gmrf/natt/{self.cycle['id']}/reception/", {
            'numero_echeance': 1, 'date_reception': '2026-02-05', 'montant_recu': 50000,
            'mode_paiement': 'VIREMENT'}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['reception']['mode_paiement'], 'VIREMENT')
        self.assertEqual(self._solde('521', 'GMRF_RECEP'), 50000)

    # ── Prêts ──
    def test_remboursement_pret_en_especes(self):
        e = self.pret['echeances'][0]
        r = self.client.patch(f"/api/gmrf/echeances/{e['id']}/", {
            'action': 'payer', 'date_paiement': '2026-02-28', 'mode_paiement': 'ESPECE'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual((r.data['mode_paiement'], r.data['compte_tresorerie']), ('ESPECE', '571'))
        self.assertEqual(self._solde('571', 'GMRF_PRET_ECH'), -100000)
        # Le déblocage, lui, reste sur le compte du prêt.
        self.assertEqual(self._solde('521', 'GMRF_PRET_ECH'), 0)

    def test_remboursement_sans_mode_garde_le_compte_du_pret(self):
        e = self.pret['echeances'][0]
        r = self.client.patch(f"/api/gmrf/echeances/{e['id']}/", {'action': 'payer'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['compte_tresorerie'], '521')
        self.assertEqual(self._solde('521', 'GMRF_PRET_ECH'), -100000)

    def test_annulation_remboursement_efface_le_mode(self):
        e = self.pret['echeances'][0]
        self.client.patch(f"/api/gmrf/echeances/{e['id']}/",
                          {'action': 'payer', 'mode_paiement': 'WAVE'}, format='json')
        r = self.client.patch(f"/api/gmrf/echeances/{e['id']}/", {'action': 'annuler'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self._solde('5521', 'GMRF_'), 0)
        self.assertEqual((r.data['mode_paiement'], r.data['compte_tresorerie']), ('', '521'))
