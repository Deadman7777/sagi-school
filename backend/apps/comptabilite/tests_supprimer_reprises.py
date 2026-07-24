"""Test : suppression de toutes les reprises (garde élèves + agrégats)."""
import datetime
from io import StringIO

from django.core.management import call_command
from rest_framework.test import APITestCase

from apps.tenants.models import Tenant
from apps.paiements.models import Exercice, Paiement
from apps.eleves.models import Eleve
from apps.comptabilite.models import JournalEntry


class SupprimerReprisesTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul')
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', cloture=False,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))
        self.eleve = Eleve.objects.create(tenant=self.tenant, exercice=self.ex, nom_complet='Awa')

    def _je(self, compte, debit, credit, source, source_id=None, piece='X'):
        return JournalEntry.objects.create(
            tenant=self.tenant, exercice=self.ex, no_piece=piece, date_ecriture=self.ex.date_debut,
            no_compte=compte, debit=debit, credit=credit, source=source, source_id=source_id, ordre=1)

    def test_supprime_reprises_garde_eleves_et_agregats(self):
        # agrégat migration (571 D / 706 C) = produit réel à conserver
        self._je('571', 13337500, 0, 'MIGRATION', piece='M')
        self._je('706', 0, 13337500, 'MIGRATION', piece='M')
        # une reprise + ses écritures + neutralisation
        p = Paiement.objects.create(tenant=self.tenant, exercice=self.ex, eleve=self.eleve,
                                    no_piece='REP-1', mode_paiement='REPRISE', montant_mensualite=400000)
        self._je('706', 0, 400000, 'PAIEMENT', p.id, piece='REP-1')
        self._je('890', 400000, 0, 'PAIEMENT', p.id, piece='REP-1')
        self._je('706', 400000, 0, 'RECAL_MIGRATION', piece='RECAL-REP')
        self._je('890', 0, 400000, 'RECAL_MIGRATION', piece='RECAL-REP')

        call_command('supprimer_reprises', tenant_id=str(self.tenant.id), exercice='2026',
                     appliquer=True, stdout=StringIO())

        # Reprises et neutralisation supprimées
        self.assertFalse(Paiement.objects.filter(mode_paiement='REPRISE').exists())
        self.assertFalse(JournalEntry.objects.filter(no_piece='RECAL-REP').exists())
        # Élève conservé
        self.assertTrue(Eleve.objects.filter(id=self.eleve.id).exists())
        # Agrégat 706 conservé = 13 337 500
        from django.db.models import Sum
        net706 = JournalEntry.objects.filter(no_compte='706').aggregate(
            c=Sum('credit'), d=Sum('debit'))
        self.assertEqual(float(net706['c'] or 0) - float(net706['d'] or 0), 13337500)

    def test_dry_run_ne_supprime_rien(self):
        p = Paiement.objects.create(tenant=self.tenant, exercice=self.ex, eleve=self.eleve,
                                    no_piece='REP-1', mode_paiement='REPRISE', montant_mensualite=1)
        call_command('supprimer_reprises', tenant_id=str(self.tenant.id), exercice='2026',
                     stdout=StringIO())
        self.assertTrue(Paiement.objects.filter(id=p.id).exists())
