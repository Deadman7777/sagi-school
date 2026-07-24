"""Test de la réconciliation du double comptage des produits migrés."""
import datetime
from io import StringIO

from django.core.management import call_command
from django.db.models import Sum
from rest_framework.test import APITestCase

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.paiements.models import Exercice, Paiement
from apps.comptabilite.models import JournalEntry


class ReconciliationProduitsTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul')
        self.user = User.objects.create_user(
            'a@a.sn', 'x', nom='Admin', role='ADMIN_ECOLE', tenant=self.tenant)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', cloture=False,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31),
            solde_initial_caisse=0)

    def _je(self, no_compte, debit, credit, source, source_id=None, ordre=1):
        return JournalEntry.objects.create(
            tenant=self.tenant, exercice=self.ex, no_piece='X',
            date_ecriture=self.ex.date_debut, no_compte=no_compte,
            debit=debit, credit=credit, source=source, source_id=source_id, ordre=ordre)

    def _net(self, no_compte, sens):
        agg = JournalEntry.objects.filter(tenant=self.tenant, no_compte=no_compte)\
            .aggregate(d=Sum('debit'), c=Sum('credit'))
        d, c = float(agg['d'] or 0), float(agg['c'] or 0)
        return d - c if sens == 'debit' else c - d

    def test_bascule_neutralise_le_double_706(self):
        # Migration agrégée : 571 D / 706 C = 500 000 (cash + produit agrégé)
        self._je('571', 500000, 0, 'MIGRATION')
        self._je('706', 0, 500000, 'MIGRATION')
        # Reprise élève : 411/706 puis 890/411 = 400 000 (produit par élève)
        from apps.eleves.models import Eleve
        eleve = Eleve.objects.create(tenant=self.tenant, exercice=self.ex, nom_complet='Awa')
        p = Paiement.objects.create(
            tenant=self.tenant, exercice=self.ex, eleve=eleve, no_piece='REP-0001',
            mode_paiement='REPRISE', montant_mensualite=400000)
        self._je('411', 400000, 0, 'PAIEMENT', p.id, 1)
        self._je('706', 0, 400000, 'PAIEMENT', p.id, 2)
        self._je('890', 400000, 0, 'PAIEMENT', p.id, 3)
        self._je('411', 0, 400000, 'PAIEMENT', p.id, 4)

        # Avant : 706 crédité 900 000 (500k agrégat + 400k reprise) → doublé
        self.assertEqual(self._net('706', 'credit'), 900000)

        out = StringIO()
        call_command('reconcilier_migration_produits',
                     tenant_id=str(self.tenant.id), exercice='2026',
                     comptes='706', appliquer=True, stdout=out)

        # Après : le produit agrégé (500k) est basculé en 890
        # 706 net crédit = 900 000 − 500 000 = 400 000 (seule la reprise reste)
        self.assertEqual(self._net('706', 'credit'), 400000)
        # Solde 890 créditeur = 500 000 (reclass C) − 400 000 (reprise D) = 100 000
        # → soit exactement l'écart agrégats(500k) − reprise(400k) : le résidu à analyser.
        self.assertEqual(self._net('890', 'credit'), 100000)
        # Caisse 571 intacte : 500 000
        self.assertEqual(self._net('571', 'debit'), 500000)
        # Ensemble équilibré
        agg = JournalEntry.objects.filter(tenant=self.tenant)\
            .aggregate(d=Sum('debit'), c=Sum('credit'))
        self.assertEqual(agg['d'], agg['c'])

    def test_dry_run_ne_modifie_rien(self):
        self._je('571', 500000, 0, 'MIGRATION')
        self._je('706', 0, 500000, 'MIGRATION')
        n = JournalEntry.objects.filter(tenant=self.tenant).count()
        out = StringIO()
        call_command('reconcilier_migration_produits',
                     tenant_id=str(self.tenant.id), exercice='2026', comptes='706', stdout=out)
        self.assertEqual(JournalEntry.objects.filter(tenant=self.tenant).count(), n)
        self.assertFalse(JournalEntry.objects.filter(source='RECONCIL_MIGRATION').exists())

    def test_idempotent_pas_de_double_application(self):
        self._je('571', 500000, 0, 'MIGRATION')
        self._je('706', 0, 500000, 'MIGRATION')
        for _ in range(2):
            out = StringIO()
            call_command('reconcilier_migration_produits',
                         tenant_id=str(self.tenant.id), exercice='2026',
                         comptes='706', appliquer=True, stdout=out)
        # Une seule pièce de reclassement (890 crédité une seule fois de 500 000)
        recl = JournalEntry.objects.filter(source='RECONCIL_MIGRATION', no_compte='890')\
            .aggregate(c=Sum('credit'))['c']
        self.assertEqual(float(recl), 500000)
