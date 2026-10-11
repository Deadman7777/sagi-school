"""Date de souscription ≠ 1ʳᵉ échéance, et correction des dates saisies par erreur.

Ce que ces tests protègent :
  - la souscription (adhésion au NATT, signature du prêt) est distincte de la
    1ʳᵉ échéance, d'où part l'échéancier ;
  - corriger la 1ʳᵉ échéance redate tout l'échéancier sans toucher aux
    montants, aux paiements ni aux écritures déjà passées ;
  - une souscription postérieure à la 1ʳᵉ échéance est refusée.
"""
import datetime

from rest_framework.test import APITestCase

from apps.comptabilite.models import JournalEntry
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant
from apps.users.models import User


class DatesSouscriptionTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='École Test', code_etablissement='ETS')
        self.user = User.objects.create_user('a@a.sn', 'x', nom='A',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        today = datetime.date.today()
        Exercice.objects.create(tenant=self.tenant, annee_scolaire='courant',
                                date_debut=today.replace(month=1, day=1),
                                date_fin=today.replace(month=12, day=31))

    def _ecritures(self):
        return list(JournalEntry.objects.filter(tenant=self.tenant)
                    .order_by('no_piece', 'ordre')
                    .values_list('no_piece', 'date_ecriture', 'no_compte', 'debit', 'credit'))

    # ── NATT ──
    def _natt(self, **extra):
        data = {'nom': 'Tontine', 'nb_participants': 5, 'duree': 5, 'periodicite': 'MENSUELLE',
                'montant_cotisation': 10000, 'date_souscription': '2026-01-20',
                'date_debut': '2026-02-05', **extra}
        return self.client.post('/api/gmrf/natt/', data, format='json')

    def test_natt_souscription_distincte_de_la_premiere_echeance(self):
        r = self._natt()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['date_souscription'], '2026-01-20')
        self.assertEqual([c['date_echeance'] for c in r.data['cotisations']],
                         ['2026-02-05', '2026-03-05', '2026-04-05', '2026-05-05', '2026-06-05'])
        self.assertEqual(r.data['date_fin'], '2026-06-05')

    def test_natt_correction_redate_sans_toucher_aux_paiements(self):
        cycle = self._natt().data
        payee = cycle['cotisations'][0]
        self.client.patch(f"/api/gmrf/cotisations/{payee['id']}/",
                          {'action': 'payer', 'date_paiement': '2026-02-06'}, format='json')
        avant = self._ecritures()

        r = self.client.patch(f"/api/gmrf/natt/{cycle['id']}/",
                              {'date_souscription': '2026-01-25', 'date_debut': '2026-02-10'},
                              format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['date_souscription'], '2026-01-25')
        self.assertEqual(r.data['date_debut'], '2026-02-10')
        self.assertEqual(r.data['date_fin'], '2026-06-10')
        cotis = r.data['cotisations']
        self.assertEqual([c['date_echeance'] for c in cotis][:2], ['2026-02-10', '2026-03-10'])
        self.assertEqual(cotis[0]['statut'], 'PAYE')
        self.assertEqual(cotis[0]['date_paiement'], '2026-02-06')
        self.assertEqual(r.data['total_verse'], 10000)
        self.assertEqual(self._ecritures(), avant)

    def test_natt_souscription_apres_premiere_echeance_refusee(self):
        r = self._natt(date_souscription='2026-03-01')
        self.assertEqual(r.status_code, 400)
        cycle = self._natt().data
        r = self.client.patch(f"/api/gmrf/natt/{cycle['id']}/",
                              {'date_souscription': '2026-02-06'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_natt_statut_suit_la_nouvelle_date(self):
        """Une échéance repoussée dans le futur n'est plus « en retard »."""
        cycle = self._natt(date_souscription='2020-01-01', date_debut='2020-01-05').data
        self.client.get('/api/gmrf/dashboard/')  # bascule les retards
        futur = (datetime.date.today() + datetime.timedelta(days=40)).isoformat()
        r = self.client.patch(f"/api/gmrf/natt/{cycle['id']}/", {'date_debut': futur}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual({c['statut'] for c in r.data['cotisations']}, {'A_PAYER'})

    # ── Prêts ──
    def _pret(self, **extra):
        data = {'organisme_preteur': 'Banque', 'montant': 1200000, 'taux_interet': 0,
                'duree_mois': 12, 'periodicite': 'MENSUELLE', 'mode_amortissement': 'CONSTANT',
                'date_souscription': '2026-01-10', 'date_deblocage': '2026-01-15',
                'date_premiere_echeance': '2026-02-28', **extra}
        return self.client.post('/api/gmrf/prets/', data, format='json')

    def test_pret_trois_dates_distinctes(self):
        r = self._pret()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['date_souscription'], '2026-01-10')
        self.assertEqual(r.data['date_deblocage'], '2026-01-15')
        self.assertEqual(r.data['date_premiere_echeance'], '2026-02-28')
        self.assertEqual([e['date_echeance'] for e in r.data['echeances']][:3],
                         ['2026-02-28', '2026-03-28', '2026-04-28'])

    def test_pret_correction_redate_sans_toucher_a_la_compta(self):
        pret = self._pret().data
        e1 = pret['echeances'][0]
        self.client.patch(f"/api/gmrf/echeances/{e1['id']}/",
                          {'action': 'payer', 'date_paiement': '2026-03-01'}, format='json')
        avant = self._ecritures()

        r = self.client.patch(f"/api/gmrf/prets/{pret['id']}/",
                              {'date_souscription': '2026-01-12', 'date_premiere_echeance': '2026-02-05'},
                              format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['date_souscription'], '2026-01-12')
        self.assertEqual(r.data['date_deblocage'], '2026-01-15')
        echs = r.data['echeances']
        self.assertEqual([e['date_echeance'] for e in echs][:2], ['2026-02-05', '2026-03-05'])
        self.assertEqual(echs[0]['statut'], 'PAYE')
        self.assertEqual(echs[0]['montant_echeance'], e1['montant_echeance'])
        self.assertEqual(self._ecritures(), avant)

    def test_pret_souscription_apres_premiere_echeance_refusee(self):
        pret = self._pret().data
        r = self.client.patch(f"/api/gmrf/prets/{pret['id']}/",
                              {'date_souscription': '2026-03-01'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_pdf_affiche_les_dates(self):
        pret = self._pret().data
        cycle = self._natt().data
        for url in (f"/api/gmrf/prets/{pret['id']}/pdf/", f"/api/gmrf/natt/{cycle['id']}/pdf/"):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.content.startswith(b'%PDF'))
