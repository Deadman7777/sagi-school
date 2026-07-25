"""Répare les produits faussés par les corrections de reprises successives.

Chaque correction de reprise faite depuis l'interface ajoutait une écriture de
neutralisation 706 D / 890 C sans retirer la précédente. Ces débits orphelins
s'accumulaient et rongeaient les produits migrés : au bout de quelques
corrections, le total des recettes du tableau de bord tombait à 0.

La commande recalcule la neutralisation à partir des reprises réellement en
base (une seule paire d'écritures), ce qui remet le net 706 à sa valeur juste :
le total des agrégats du journal de caisse.

  python manage.py reparer_neutralisation_reprises --settings=config.settings.production
      [--tenant <code ou nom>] [--exercice 2026] [--appliquer]

Sans --appliquer : diagnostic seul (net 706 avant / après). Idempotente.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Sum

from apps.comptabilite.models import JournalEntry
from apps.comptabilite.neutralisation import (PIECE_RECAL, SOURCE_RECAL,
                                              a_agregats_migration,
                                              neutraliser_reprises,
                                              total_produits_reprises)
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Recalcule la neutralisation des reprises (corrige le total des recettes à 0)"

    def add_arguments(self, parser):
        parser.add_argument('--tenant', help="Code ou nom de l'école (défaut : la seule école)")
        parser.add_argument('--exercice', help='Année scolaire (défaut : exercice actif)')
        parser.add_argument('--appliquer', action='store_true',
                            help='Écrire réellement (sinon diagnostic seul)')

    def _tenant(self, arg):
        qs = Tenant.objects.all()
        if arg:
            t = (qs.filter(code_etablissement__iexact=arg).first()
                 or qs.filter(nom__icontains=arg).first())
            if not t:
                raise CommandError(f"École introuvable : {arg}")
            return t
        if qs.count() != 1:
            raise CommandError("Plusieurs écoles en base — précisez --tenant.")
        return qs.first()

    def _net_70(self, tenant, exercice):
        agg = JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice, no_compte__startswith='70'
        ).aggregate(c=Sum('credit'), d=Sum('debit'))
        return float(agg['c'] or 0) - float(agg['d'] or 0)

    def handle(self, *args, **opts):
        tenant = self._tenant(opts.get('tenant'))

        if opts.get('exercice'):
            ex = Exercice.objects.filter(tenant=tenant,
                                         annee_scolaire=opts['exercice']).first()
            if not ex:
                raise CommandError(f"Exercice « {opts['exercice']} » introuvable.")
        else:
            ex = Exercice.objects.filter(tenant=tenant,
                                         cloture=False).order_by('-date_debut').first()
            if not ex:
                raise CommandError("Aucun exercice actif — précisez --exercice.")

        self.stdout.write(f"École : {tenant}\nExercice : {ex.annee_scolaire}\n")

        if not a_agregats_migration(tenant, ex):
            self.stdout.write(self.style.WARNING(
                "Aucun agrégat migré (706 en source MIGRATION) sur cet exercice : "
                "les reprises n'ont pas à être neutralisées, rien à réparer."))
            return

        agregats = float(JournalEntry.objects.filter(
            tenant=tenant, exercice=ex, source='MIGRATION',
            no_compte__startswith='70').aggregate(c=Sum('credit'))['c'] or 0)
        neutral = JournalEntry.objects.filter(
            tenant=tenant, exercice=ex, source=SOURCE_RECAL, no_piece=PIECE_RECAL)
        neutral_706 = float(neutral.filter(no_compte='706').aggregate(
            d=Sum('debit'))['d'] or 0)
        reprises_706 = total_produits_reprises(tenant, ex)
        net_avant = self._net_70(tenant, ex)

        self.stdout.write(
            f"  Produits migrés (agrégats)      : {agregats:>15,.0f}\n"
            f"  706 crédité par les reprises    : {reprises_706:>15,.0f}\n"
            f"  706 débité en neutralisation    : {neutral_706:>15,.0f}"
            f"   ({neutral.count()} écriture(s))\n"
            f"  → net produits actuel           : {net_avant:>15,.0f}")

        ecart = neutral_706 - reprises_706
        if abs(ecart) < 0.01:
            self.stdout.write(self.style.SUCCESS(
                "\n✓ Neutralisation déjà cohérente — rien à réparer."))
            return

        self.stdout.write(self.style.ERROR(
            f"\n⚠ {ecart:,.0f} FCFA de neutralisation en trop "
            f"(débits orphelins de corrections successives)."))

        if not opts['appliquer']:
            self.stdout.write(self.style.WARNING(
                f"\nAprès réparation, le net produits vaudrait "
                f"{net_avant + ecart:,.0f} FCFA.\n"
                "Diagnostic seul — relancez avec --appliquer pour corriger."))
            return

        with transaction.atomic():
            montant = neutraliser_reprises(tenant, ex)

        net_apres = self._net_70(tenant, ex)
        equilibre = JournalEntry.objects.filter(tenant=tenant, exercice=ex).aggregate(
            d=Sum('debit'), c=Sum('credit'))
        self.stdout.write(self.style.SUCCESS(
            f"\n✅ Neutralisation recalculée : {montant:,.0f} FCFA (1 paire d'écritures).\n"
            f"   Net produits : {net_avant:,.0f} → {net_apres:,.0f} FCFA\n"
            f"   Journal : débit {float(equilibre['d'] or 0):,.0f} / "
            f"crédit {float(equilibre['c'] or 0):,.0f}"))
