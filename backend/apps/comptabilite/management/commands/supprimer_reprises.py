"""Supprime toutes les reprises de soldes (déjà payé migré) d'un exercice.

Remet à zéro le « déjà payé » de reprise de tous les élèves — les fiches élèves
sont conservées. Après, le reste à payer de chaque élève = son total attendu, et
on ressaisit les vraies valeurs élève par élève (bouton « Corriger le déjà payé »,
qui reste 706-neutre tant que des agrégats migrés existent).

Sont supprimés : les Paiement en mode REPRISE + leurs écritures (source PAIEMENT)
+ les écritures de neutralisation RECAL-REP. Les agrégats MIGRATION (produit 706
= 13,41M) et la trésorerie ne bougent PAS.

  python manage.py supprimer_reprises [--tenant_id UUID] [--exercice 2026] [--appliquer]

Sans --appliquer : rapport seul.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Sum

from apps.tenants.models import Tenant
from apps.paiements.models import Exercice, Paiement
from apps.comptabilite.models import JournalEntry


class Command(BaseCommand):
    help = "Supprime toutes les reprises de soldes d'un exercice (garde les élèves)."

    def add_arguments(self, parser):
        parser.add_argument('--tenant_id')
        parser.add_argument('--exercice')
        parser.add_argument('--appliquer', action='store_true')

    def handle(self, *args, **o):
        tenant = self._tenant(o.get('tenant_id'))
        ex = self._exercice(tenant, o.get('exercice'))

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n═══ Suppression des reprises — {tenant.nom} — {ex.annee_scolaire} ═══"))

        reprises = Paiement.objects.filter(tenant=tenant, exercice=ex, mode_paiement='REPRISE')
        ids = list(reprises.values_list('id', flat=True))
        nb = len(ids)
        total = Decimal(str(reprises.aggregate(
            t=Sum('montant_inscription') + Sum('montant_mensualite') +
              Sum('montant_uniforme') + Sum('montant_fournitures') +
              Sum('montant_cantine') + Sum('montant_divers'))['t'] or 0))
        nb_ecr = JournalEntry.objects.filter(
            tenant=tenant, exercice=ex, source='PAIEMENT', source_id__in=ids).count()
        nb_neu = JournalEntry.objects.filter(
            tenant=tenant, exercice=ex, no_piece='RECAL-REP').count()

        self.stdout.write(f"\n  Reprises à supprimer      : {nb} fiches ({total:,.0f} FCFA de déjà payé)")
        self.stdout.write(f"  Écritures de reprise      : {nb_ecr}")
        self.stdout.write(f"  Écritures de neutralisation RECAL-REP : {nb_neu}")
        self.stdout.write("  Conservés : fiches élèves, agrégats MIGRATION (706), trésorerie.")

        if nb == 0 and nb_neu == 0:
            self.stdout.write(self.style.WARNING("\n  Aucune reprise — rien à faire."))
            return
        if not o['appliquer']:
            self.stdout.write(self.style.MIGRATE_LABEL(
                "\n  DRY-RUN — aucune suppression. --appliquer pour supprimer."))
            return

        with transaction.atomic():
            JournalEntry.objects.filter(
                tenant=tenant, exercice=ex, source='PAIEMENT', source_id__in=ids).delete()
            JournalEntry.objects.filter(tenant=tenant, exercice=ex, no_piece='RECAL-REP').delete()
            reprises.delete()

        self.stdout.write(self.style.SUCCESS(
            f"\n  ✓ {nb} reprises supprimées. Le reste à payer de chaque élève = son total "
            f"attendu. Ressaisis les vraies valeurs via « Corriger le déjà payé »."))

    def _tenant(self, tid):
        if tid:
            try:
                return Tenant.objects.get(id=tid)
            except Tenant.DoesNotExist:
                raise CommandError(f'Tenant {tid} introuvable')
        ts = list(Tenant.objects.all()[:2])
        if len(ts) == 1:
            return ts[0]
        raise CommandError('Plusieurs tenants : préciser --tenant_id')

    def _exercice(self, tenant, annee):
        qs = Exercice.objects.filter(tenant=tenant)
        ex = qs.filter(annee_scolaire=annee).first() if annee else \
            qs.filter(cloture=False).order_by('-date_debut').first()
        if not ex:
            raise CommandError("Exercice introuvable : préciser --exercice")
        return ex
