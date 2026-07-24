"""Test de la reconstruction du reste dû par élève (modèle Shoumoul)."""
import datetime
from io import StringIO

from django.core.management import call_command
from django.db.models import Sum
from rest_framework.test import APITestCase

from apps.tenants.models import Tenant
from apps.paiements.models import Exercice
from apps.eleves.models import Eleve, Section
from apps.comptabilite.models import JournalEntry


class ResteDuShoumoulTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Complexe Shoumoul Excellence')
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', cloture=False, nb_mensualites=12,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))
        # Section : renouvellement 55 000 (= frais_inscription) + 12 × 30 000
        self.section = Section.objects.create(
            tenant=self.tenant, nom='Internat Tahfiiz',
            frais_inscription=55000, frais_mensualite=30000,
            frais_uniforme=0, frais_fournitures=0)

    def _eleve(self, nom):
        # date d'inscription = début d'exercice → dû sur les 12 mensualités pleines
        return Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, nom_complet=nom, section=self.section,
            date_inscription=datetime.date(2026, 1, 1))

    def test_reste_du_reconstruit_selon_le_modele(self):
        paye = self._eleve('Keba FALL')          # renouvellement versé 55 000
        non_paye = self._eleve('Ndeye FAKE')      # pas dans la liste → doit 55 000

        call_command('recaler_reste_du_shoumoul',
                     tenant_id=str(self.tenant.id), exercice='2026',
                     appliquer=True, stdout=StringIO())

        # M = 30 000 ; reste = 5 × 30 000 + (55 000 − versé)
        paye.refresh_from_db(); non_paye.refresh_from_db()
        # Élève ayant versé le renouvellement : reste = 150 000 + 0 = 150 000
        self.assertEqual(paye.reste_a_payer, 150000)
        # Élève sans renouvellement : reste = 150 000 + 55 000 = 205 000
        self.assertEqual(non_paye.reste_a_payer, 205000)

        # 706 non doublé : les reprises reconstruites sont neutralisées (net reprise 706 = 0)
        rep_ids = list(paye.paiements.filter(mode_paiement='REPRISE').values_list('id', flat=True)) + \
                  list(non_paye.paiements.filter(mode_paiement='REPRISE').values_list('id', flat=True))
        rep_706 = JournalEntry.objects.filter(
            source='PAIEMENT', source_id__in=rep_ids, no_compte='706'
        ).aggregate(c=Sum('credit'))['c'] or 0
        neutral = JournalEntry.objects.filter(
            no_piece='RECAL-REP', no_compte='706').aggregate(d=Sum('debit'))['d'] or 0
        self.assertEqual(float(rep_706), float(neutral))  # crédit reprise = débit neutralisation

        # Ensemble équilibré
        agg = JournalEntry.objects.filter(tenant=self.tenant).aggregate(d=Sum('debit'), c=Sum('credit'))
        self.assertEqual(agg['d'], agg['c'])

    def test_dry_run_ne_cree_rien(self):
        self._eleve('Keba FALL')
        call_command('recaler_reste_du_shoumoul',
                     tenant_id=str(self.tenant.id), exercice='2026', stdout=StringIO())
        self.assertFalse(JournalEntry.objects.filter(tenant=self.tenant).exists())
