"""Tests : suppression des extournes d'annulation orphelines.

Une extourne dont le paiement d'origine a été supprimé par un outil de
migration continue de débiter 706 sans rien annuler — le net produits est
amputé en silence (810 000 FCFA chez Shoumoul sur l'exercice 2026).
"""
import datetime
from io import StringIO

from django.core.management import call_command
from django.db.models import Sum
from django.test import TestCase

from apps.comptabilite.models import JournalEntry
from apps.eleves.models import Eleve
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant


class AnnulationsOrphelinesTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul', code_etablissement='SHE')
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', cloture=False,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))
        self.eleve = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, nom_complet='Awa Ndiaye')
        # Produits migrés : 571 D / 706 C
        self._je('571', 1000000, 0, 'MIGRATION')
        self._je('706', 0, 1000000, 'MIGRATION')

    def _je(self, compte, debit, credit, source, source_id=None, piece='X', ordre=1):
        return JournalEntry.objects.create(
            tenant=self.tenant, exercice=self.ex, no_piece=piece,
            date_ecriture=self.ex.date_debut, no_compte=compte,
            debit=debit, credit=credit, source=source, source_id=source_id, ordre=ordre)

    def _paiement(self):
        return Paiement.objects.create(
            tenant=self.tenant, exercice=self.ex, eleve=self.eleve,
            no_piece='REC-1', mode_paiement='ESPECE', montant_mensualite=100000)

    def _extourne(self, source_id, montant, piece='ANN-REC-0001'):
        """Miroir équilibré d'un paiement : 706 D / 571 C.

        Les lignes portent des `ordre` DIFFÉRENTS, comme en vrai : c'est ce qui
        fait ressortir un groupe plusieurs fois si le .distinct() du code hérite
        de Meta.ordering (bug constaté chez Shoumoul, totaux ×4)."""
        self._je('706', montant, 0, 'ANNUL_PAIEMENT', source_id, piece, ordre=1)
        self._je('571', 0, montant, 'ANNUL_PAIEMENT', source_id, piece, ordre=2)

    def _net70(self):
        agg = JournalEntry.objects.filter(
            tenant=self.tenant, exercice=self.ex,
            no_compte__startswith='70').aggregate(c=Sum('credit'), d=Sum('debit'))
        return float(agg['c'] or 0) - float(agg['d'] or 0)

    def _equilibre(self):
        agg = JournalEntry.objects.filter(
            tenant=self.tenant, exercice=self.ex).aggregate(d=Sum('debit'), c=Sum('credit'))
        return float(agg['d'] or 0), float(agg['c'] or 0)

    def _run(self, *flags):
        out = StringIO()
        call_command('reparer_annulations_orphelines', *flags, stdout=out, stderr=out)
        return out.getvalue()

    # ── Le cas Shoumoul ───────────────────────────────────────────────────
    def test_extourne_orpheline_supprimee_et_net_produits_restaure(self):
        import uuid
        orphelin = uuid.uuid4()          # paiement supprimé par un recalage
        self._extourne(orphelin, 810000)
        self.assertEqual(self._net70(), 190000)   # 1 000 000 − 810 000

        self._run('--appliquer')

        self.assertEqual(self._net70(), 1000000)
        self.assertFalse(JournalEntry.objects.filter(
            source='ANNUL_PAIEMENT', source_id=orphelin).exists())

    def test_un_groupe_de_plusieurs_lignes_n_est_compte_qu_une_fois(self):
        """Régression : Meta.ordering s'invitait dans le DISTINCT et chaque
        groupe était compté autant de fois qu'il avait de lignes (×4 chez
        Shoumoul : 810 000 annoncés en 3 240 000)."""
        import uuid
        sid = uuid.uuid4()
        # Extourne à 4 lignes, ordres distincts, comme une vraie reprise.
        self._je('706', 810000, 0, 'ANNUL_PAIEMENT', sid, 'ANN-4L', ordre=1)
        self._je('571', 0, 400000, 'ANNUL_PAIEMENT', sid, 'ANN-4L', ordre=2)
        self._je('571', 0, 400000, 'ANNUL_PAIEMENT', sid, 'ANN-4L', ordre=3)
        self._je('571', 0, 10000, 'ANNUL_PAIEMENT', sid, 'ANN-4L', ordre=4)

        sortie = self._run()

        self.assertIn('dont ORPHELINES           : 1', sortie)
        # Net projeté = 190 000 + 810 000 une seule fois, pas 4 fois.
        self.assertIn('1,000,000', sortie)
        self.assertNotIn('4,240,000', sortie)

    def test_le_journal_reste_equilibre(self):
        import uuid
        self._extourne(uuid.uuid4(), 810000)
        self._run('--appliquer')
        d, c = self._equilibre()
        self.assertEqual(d, c)

    # ── Ce qu'elle ne doit PAS toucher ────────────────────────────────────
    def test_extourne_dont_le_paiement_existe_est_conservee(self):
        p = self._paiement()
        self._je('706', 0, 100000, 'PAIEMENT', p.id)
        self._je('571', 100000, 0, 'PAIEMENT', p.id)
        self._extourne(p.id, 100000)
        net = self._net70()

        self._run('--appliquer')

        self.assertEqual(self._net70(), net)
        self.assertEqual(JournalEntry.objects.filter(
            source='ANNUL_PAIEMENT', source_id=p.id).count(), 2)

    def test_groupe_orphelin_desequilibre_signale_mais_intact(self):
        import uuid
        boiteux = uuid.uuid4()
        self._je('706', 500000, 0, 'ANNUL_PAIEMENT', boiteux, 'ANN-BOITEUX')

        sortie = self._run('--appliquer')

        self.assertIn('DÉSÉQUILIBRÉ', sortie.upper())
        self.assertTrue(JournalEntry.objects.filter(source_id=boiteux).exists())

    # ── Garde-fous ────────────────────────────────────────────────────────
    def test_dry_run_n_ecrit_rien(self):
        import uuid
        self._extourne(uuid.uuid4(), 810000)
        avant = self._net70()

        sortie = self._run()

        self.assertEqual(self._net70(), avant)
        self.assertIn('Diagnostic seul', sortie)

    def test_idempotente(self):
        import uuid
        self._extourne(uuid.uuid4(), 810000)
        self._run('--appliquer')
        net = self._net70()

        sortie = self._run('--appliquer')

        self.assertEqual(self._net70(), net)
        self.assertIn('rien à réparer', sortie)

    def test_exercice_cloture_refuse(self):
        self.ex.cloture = True
        self.ex.save()
        with self.assertRaises(Exception):
            self._run('--appliquer')
