"""Test : le compte de résultat retient la contribution NETTE des comptes.

Sommer le seul sens naturel (crédit pour un produit, débit pour une charge)
ignore les annulations et les neutralisations de migration. Chez Shoumoul, la
ligne « Prestations de services — Scolarité » affichait 29 877 500 (crédit
brut) alors que le net valait 13 410 500.
"""
import datetime

from rest_framework.test import APITestCase

from apps.comptabilite.models import JournalEntry
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant
from apps.users.models import User


class CompteResultatNetTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul', code_etablissement='SHE')
        self.user = User.objects.create_user(
            'a@a.sn', 'x', nom='Admin', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', cloture=False,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))

    def _je(self, compte, debit, credit, source='MIGRATION'):
        return JournalEntry.objects.create(
            tenant=self.tenant, exercice=self.ex, no_piece='X',
            date_ecriture=self.ex.date_debut, no_compte=compte,
            debit=debit, credit=credit, source=source, ordre=1)

    def _resultat(self):
        r = self.client.get('/api/comptabilite/compte-resultat/')
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.data

    def test_produits_nets_de_la_neutralisation(self):
        # Agrégats migrés + reprises créditées puis neutralisées
        self._je('571', 13337500, 0)
        self._je('706', 0, 13337500)
        self._je('706', 0, 16540000, 'PAIEMENT')
        self._je('706', 16417000, 0, 'RECAL_MIGRATION')   # neutralisation
        self._je('706', 50000, 0, 'ANNUL_PAIEMENT')       # annulation

        d = self._resultat()

        # 29 877 500 de crédit brut − 16 467 000 de débit = 13 410 500
        self.assertEqual(d['sig']['production_exercice'], 13410500)
        self.assertEqual(d['total_produits'], 13410500)
        # La ligne de détail doit dire la MÊME chose que le total.
        ligne706 = [l for l in d['detail_produits'] if l['compte'] == '706'][0]
        self.assertEqual(ligne706['montant'], 13410500)

    def test_charges_nettes_de_leurs_contre_ecritures(self):
        self._je('658', 500000, 0, 'CHARGE')
        self._je('658', 0, 200000, 'CHARGE')   # contre-écriture d'annulation

        d = self._resultat()

        self.assertEqual(d['sig']['autres_charges'], 300000)
        ligne658 = [l for l in d['detail_charges'] if l['compte'] == '658'][0]
        self.assertEqual(ligne658['montant'], 300000)

    def test_sans_contre_ecriture_le_resultat_est_inchange(self):
        """Garde-fou : le netting ne doit rien changer au cas nominal."""
        self._je('706', 0, 1000000)
        self._je('658', 400000, 0, 'CHARGE')

        d = self._resultat()

        self.assertEqual(d['sig']['production_exercice'], 1000000)
        self.assertEqual(d['sig']['autres_charges'], 400000)
