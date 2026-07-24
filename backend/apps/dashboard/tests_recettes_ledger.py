"""Test : le KPI « Total recettes » lit le grand livre (produits 70), pas la
somme des fiches de paiement (qui gonfle en migration avec les reprises)."""
import datetime

from django.db.models import Sum
from rest_framework.test import APITestCase

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.paiements.models import Exercice, Paiement
from apps.eleves.models import Eleve
from apps.comptabilite.models import JournalEntry


class RecettesLedgerTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul')
        self.user = User.objects.create_user(
            'a@a.sn', 'x', nom='Admin', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', cloture=False,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))

    def _je(self, compte, debit, credit, source, source_id=None):
        return JournalEntry.objects.create(
            tenant=self.tenant, exercice=self.ex, no_piece='X', date_ecriture=self.ex.date_debut,
            no_compte=compte, debit=debit, credit=credit, source=source, source_id=source_id, ordre=1)

    def test_total_recettes_vient_du_grand_livre(self):
        # Migration : produits réels 706 = 13 337 500 (571 D / 706 C)
        self._je('571', 13337500, 0, 'MIGRATION')
        self._je('706', 0, 13337500, 'MIGRATION')
        # Reprise gonflée : 706 crédité 30 000 000 PUIS neutralisé (706 D 30M / 890 C)
        eleve = Eleve.objects.create(tenant=self.tenant, exercice=self.ex, nom_complet='Awa')
        p = Paiement.objects.create(tenant=self.tenant, exercice=self.ex, eleve=eleve,
                                    no_piece='REP-1', mode_paiement='REPRISE',
                                    montant_mensualite=30000000)
        self._je('706', 0, 30000000, 'PAIEMENT', p.id)   # crédit reprise
        self._je('706', 30000000, 0, 'RECAL_MIGRATION')   # neutralisation

        r = self.client.get('/api/dashboard/kpis/')
        self.assertEqual(r.status_code, 200, r.content)
        # La somme des paiements donnerait 30M ; le grand livre donne 13 337 500.
        self.assertEqual(r.data['kpis']['total_recettes'], 13337500)
