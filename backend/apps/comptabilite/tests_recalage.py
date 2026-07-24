"""Test du recalage de trésorerie + neutralisation reprise (migration)."""
import datetime
from io import StringIO

from django.core.management import call_command
from django.db.models import Sum
from rest_framework.test import APITestCase

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.paiements.models import Exercice, Paiement
from apps.eleves.models import Eleve
from apps.comptabilite.models import JournalEntry


class RecalageTresorerieTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul')
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', cloture=False,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31),
            solde_initial_caisse=0, solde_initial_banque=0, solde_initial_mobile=0)

    def _je(self, no_compte, debit, credit, source, source_id=None):
        return JournalEntry.objects.create(
            tenant=self.tenant, exercice=self.ex, no_piece='X', date_ecriture=self.ex.date_debut,
            no_compte=no_compte, debit=debit, credit=credit, source=source, source_id=source_id, ordre=1)

    def _net(self, no_compte):
        a = JournalEntry.objects.filter(tenant=self.tenant, no_compte=no_compte)\
            .aggregate(d=Sum('debit'), c=Sum('credit'))
        return float(a['d'] or 0) - float(a['c'] or 0)

    def _seed(self):
        # Agrégats Excel : caisse nette -12 000 (produits 13 337 500 / charges 13 349 500 simplifiés)
        self._je('571', 13337500, 0, 'MIGRATION')
        self._je('706', 0, 13337500, 'MIGRATION')
        self._je('658', 13349500, 0, 'MIGRATION')
        self._je('571', 0, 13349500, 'MIGRATION')
        # Reprise élève : 706 doublé de 27 653 100 (réglé via 890)
        eleve = Eleve.objects.create(tenant=self.tenant, exercice=self.ex, nom_complet='Awa')
        p = Paiement.objects.create(
            tenant=self.tenant, exercice=self.ex, eleve=eleve, no_piece='REP-0001',
            mode_paiement='REPRISE', montant_mensualite=27653100)
        self._je('411', 27653100, 0, 'PAIEMENT', p.id)
        self._je('706', 0, 27653100, 'PAIEMENT', p.id)
        self._je('890', 27653100, 0, 'PAIEMENT', p.id)
        self._je('411', 0, 27653100, 'PAIEMENT', p.id)
        return p

    def test_recalage_atteint_les_cibles_et_neutralise_la_reprise(self):
        p = self._seed()
        avant_paiement_total = float(p.total)

        call_command('recaler_tresorerie_migration',
                     tenant_id=str(self.tenant.id), exercice='2026',
                     caisse=17000, banque=10000, wave=15000, om=3000, free=0,
                     neutraliser_reprise=True, appliquer=True, stdout=StringIO())

        # Trésorerie recalée au franc près (solde initial 0 → net = cible)
        self.assertEqual(self._net('571'), 17000)
        self.assertEqual(self._net('521'), 10000)
        self.assertEqual(self._net('5521'), 15000)
        self.assertEqual(self._net('5522'), 3000)
        self.assertEqual(self._net('5523'), 0)
        # Trésorerie générale = 45 000
        total = sum(self._net(c) for c in ('571', '521', '5521', '5522', '5523'))
        self.assertEqual(total, 45000)

        # 706 = agrégats seuls (13 337 500), la reprise est neutralisée
        self.assertEqual(self._net('706'), -13337500)  # net créditeur = 13 337 500

        # Reste dû préservé : la fiche Paiement REPRISE est intacte
        p.refresh_from_db()
        self.assertEqual(float(p.total), avant_paiement_total)
        self.assertEqual(p.mode_paiement, 'REPRISE')

        # Ensemble équilibré
        agg = JournalEntry.objects.filter(tenant=self.tenant).aggregate(d=Sum('debit'), c=Sum('credit'))
        self.assertEqual(agg['d'], agg['c'])

    def test_dry_run_ne_modifie_rien_et_rapport_correct(self):
        self._seed()
        n = JournalEntry.objects.filter(tenant=self.tenant).count()
        out = StringIO()
        call_command('recaler_tresorerie_migration',
                     tenant_id=str(self.tenant.id), exercice='2026',
                     caisse=17000, banque=10000, wave=15000, om=3000, free=0,
                     neutraliser_reprise=True, stdout=out)
        self.assertEqual(JournalEntry.objects.filter(tenant=self.tenant).count(), n)
        self.assertFalse(JournalEntry.objects.filter(source='RECAL_MIGRATION').exists())
        # Le rapport affiche les produits après neutralisation en positif et juste
        # (13 337 500 agrégats, sans la reprise 27 653 100), pas un montant négatif.
        texte = out.getvalue()
        self.assertIn('13,337,500', texte)
        self.assertNotIn('-68,716,700', texte)

    def test_idempotent(self):
        self._seed()
        for _ in range(2):
            call_command('recaler_tresorerie_migration',
                         tenant_id=str(self.tenant.id), exercice='2026',
                         caisse=17000, banque=10000, wave=15000, om=3000, free=0,
                         neutraliser_reprise=True, appliquer=True, stdout=StringIO())
        self.assertEqual(self._net('571'), 17000)  # pas de double application
