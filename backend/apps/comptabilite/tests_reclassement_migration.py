"""Tests : reclassement des charges migrées vers un compte dédié.

Le compte 658 « Charges diverses » portait 98 % des charges de Shoumoul. Le
problème est l'intitulé, pas le classement : ce sont de vraies dépenses, les
sortir de la classe 6 gonflerait le résultat de 13 M.
"""
import datetime
from io import StringIO

from django.core.management import call_command
from django.db.models import Sum
from django.test import TestCase

from apps.comptabilite.models import CompteComptable, JournalEntry
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant


class ReclassementMigrationTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul', code_etablissement='CSE')
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', nb_mensualites=12,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))

    def _je(self, compte, debit, source, credit=0):
        return JournalEntry.objects.create(
            tenant=self.tenant, exercice=self.ex, no_piece='X',
            date_ecriture=self.ex.date_debut, no_compte=compte,
            debit=debit, credit=credit, source=source, ordre=1)

    def _run(self, *flags):
        out = StringIO()
        call_command('reclasser_charges_migration', *flags, stdout=out, stderr=out)
        return out.getvalue()

    def _charges(self):
        agg = JournalEntry.objects.filter(
            tenant=self.tenant, exercice=self.ex,
            no_compte__startswith='6').aggregate(d=Sum('debit'), c=Sum('credit'))
        return float(agg['d'] or 0) - float(agg['c'] or 0)

    # ── Le cas Shoumoul ───────────────────────────────────────────────────
    def test_les_charges_migrees_changent_de_compte(self):
        self._je('658', 13349500, 'MIGRATION')

        self._run('--appliquer')

        self.assertFalse(JournalEntry.objects.filter(no_compte='658').exists())
        self.assertEqual(
            float(JournalEntry.objects.filter(no_compte='6588')
                  .aggregate(d=Sum('debit'))['d']), 13349500)

    def test_le_total_des_charges_est_inchange(self):
        """C'est tout l'intérêt : l'intitulé change, pas le résultat."""
        self._je('658', 13349500, 'MIGRATION')
        self._je('661', 500000, 'CHARGE')
        avant = self._charges()

        self._run('--appliquer')

        self.assertEqual(self._charges(), avant)

    def test_le_compte_est_ajoute_au_plan_de_l_ecole(self):
        self._je('658', 100000, 'MIGRATION')
        self._run('--appliquer')
        compte = CompteComptable.objects.get(tenant=self.tenant, no_compte='6588')
        self.assertEqual(compte.type, 'CHARGE')
        self.assertEqual(compte.classe, 6)

    # ── Ce qu'elle ne doit PAS toucher ────────────────────────────────────
    def test_une_charge_saisie_a_la_main_reste_en_658(self):
        """Un vrai choix de l'école, pas un héritage d'import."""
        self._je('658', 40000, 'CHARGE')

        self._run('--appliquer')

        self.assertEqual(
            float(JournalEntry.objects.filter(no_compte='658')
                  .aggregate(d=Sum('debit'))['d']), 40000)

    def test_les_autres_comptes_migres_ne_bougent_pas(self):
        self._je('661', 800000, 'MIGRATION')
        self._run('--appliquer')
        self.assertTrue(JournalEntry.objects.filter(no_compte='661').exists())

    # ── Garde-fous ────────────────────────────────────────────────────────
    def test_dry_run_n_ecrit_rien(self):
        self._je('658', 13349500, 'MIGRATION')

        sortie = self._run()

        self.assertTrue(JournalEntry.objects.filter(no_compte='658').exists())
        self.assertIn('Diagnostic seul', sortie)

    def test_idempotente(self):
        self._je('658', 100000, 'MIGRATION')
        self._run('--appliquer')

        sortie = self._run('--appliquer')

        self.assertIn('rien à reclasser', sortie)

    def test_exercice_cloture_refuse(self):
        self.ex.cloture = True
        self.ex.save()
        with self.assertRaises(Exception):
            self._run('--appliquer')
