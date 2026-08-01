"""Test : le bilan s'équilibre quand le grand livre est équilibré.

Les comptes 10 à 14 — capital, réserves, report à nouveau et surtout
SUBVENTIONS D'INVESTISSEMENT — n'étaient ramassés par aucune rubrique du
passif. Une école ayant reçu une subvention d'investissement lisait un bilan
« déséquilibré » du montant exact de cette subvention, alors que ses écritures
étaient justes au franc près.
"""
import datetime

from django.db.models import Sum
from rest_framework.test import APITestCase

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.paiements.models import Exercice
from apps.comptabilite.models import JournalEntry


class BilanEquilibreTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Les Palmiers')
        self.user = User.objects.create_user(
            'dir@palmiers.sn', 'x', nom='Directrice', role='ADMIN_ECOLE',
            tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2025-2026', cloture=False,
            date_debut=datetime.date(2025, 10, 1), date_fin=datetime.date(2026, 7, 31))

    def _je(self, compte, debit, credit, source='PAIEMENT'):
        return JournalEntry.objects.create(
            tenant=self.tenant, exercice=self.ex, no_piece='X',
            date_ecriture=self.ex.date_debut, no_compte=compte,
            debit=debit, credit=credit, source=source, ordre=1)

    def _bilan(self):
        r = self.client.get('/api/comptabilite/bilan/')
        self.assertEqual(r.status_code, 200, r.content)
        return r.data

    def _grand_livre_equilibre(self):
        agg = JournalEntry.objects.filter(tenant=self.tenant).aggregate(
            d=Sum('debit'), c=Sum('credit'))
        self.assertEqual(float(agg['d'] or 0), float(agg['c'] or 0),
                         "le jeu d'essai lui-même doit être équilibré")

    def test_subvention_d_investissement_au_passif(self):
        # Scolarité encaissée
        self._je('571', 5000000, 0)
        self._je('706', 0, 5000000)
        # Subvention d'investissement reçue en banque, créditée au 141
        self._je('521', 3500000, 0, 'GMRF_FINANCEMENT')
        self._je('141', 0, 3500000, 'GMRF_FINANCEMENT')

        self._grand_livre_equilibre()
        b = self._bilan()
        self.assertEqual(
            b['passif']['capitaux_propres']['subventions_investissement'], 3500000)
        self.assertEqual(b['actif']['total_actif'], b['passif']['total_passif'])
        self.assertTrue(b['equilibre'])

    def test_le_resultat_n_est_pas_compte_deux_fois(self):
        """Le 13x est exclu des capitaux propres : le résultat vient des 6/7/8."""
        self._je('571', 4000000, 0)
        self._je('706', 0, 4000000)
        self._je('622', 1000000, 0, 'CHARGE')
        self._je('571', 0, 1000000, 'CHARGE')

        b = self._bilan()
        self.assertEqual(b['passif']['capitaux_propres']['resultat_net'], 3000000)
        self.assertEqual(b['actif']['total_actif'], b['passif']['total_passif'])
