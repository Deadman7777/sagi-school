"""Supprime les extournes d'annulation devenues orphelines.

Annuler ou modifier un paiement écrit une EXTOURNE : le miroir de l'écriture
d'origine, débit/crédit inversés (`source='ANNUL_PAIEMENT'`, `source_id` =
le paiement, préfixe « ANNUL — » ou « MODIF — »). Tant que l'écriture
d'origine est là, la paire s'annule et le compte de produits reste juste.

Quand un outil de migration supprime ensuite le paiement et ses écritures
`PAIEMENT` sans emporter l'extourne, celle-ci reste seule : elle continue de
débiter 706 sans crédit à annuler. Le net produits est amputé d'autant, en
silence — chez Shoumoul, 810 000 FCFA sur l'exercice 2026.

Une extourne est le miroir d'une écriture équilibrée, donc elle est
équilibrée en elle-même : supprimer le GROUPE ENTIER (toutes les lignes d'un
même `source_id`) laisse le journal équilibré. La commande le vérifie groupe
par groupe et refuse de toucher un groupe qui ne l'est pas.

  python manage.py reparer_annulations_orphelines --settings=config.settings.production
      [--tenant <code ou nom>] [--exercice 2026] [--appliquer]

Sans --appliquer : diagnostic seul. Idempotente.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Sum

from apps.comptabilite.models import JournalEntry
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant

SOURCE_ANNUL = 'ANNUL_PAIEMENT'
SOURCE_PAIEMENT = 'PAIEMENT'


class Command(BaseCommand):
    help = ("Supprime les extournes d'annulation dont le paiement d'origine "
            "n'existe plus (corrige un net produits amputé)")

    def add_arguments(self, parser):
        parser.add_argument('--tenant', help="Code ou nom de l'école (défaut : la seule école)")
        parser.add_argument('--exercice', help='Année scolaire (défaut : exercice actif)')
        parser.add_argument('--appliquer', action='store_true',
                            help='Supprimer réellement (sinon diagnostic seul)')

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

    def _equilibre(self, tenant, exercice):
        agg = JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice).aggregate(d=Sum('debit'), c=Sum('credit'))
        return float(agg['d'] or 0), float(agg['c'] or 0)

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

        if ex.cloture:
            raise CommandError(
                f"L'exercice {ex.annee_scolaire} est clôturé : on n'y touche plus.")

        self.stdout.write(f"École : {tenant}\nExercice : {ex.annee_scolaire}\n")

        annul = JournalEntry.objects.filter(
            tenant=tenant, exercice=ex, source=SOURCE_ANNUL)
        # .order_by() VIDE avant .distinct() : JournalEntry.Meta.ordering porte
        # sur (date_ecriture, no_piece, ordre), et Django ajoute les colonnes de
        # tri au SELECT d'un DISTINCT. Sans ce reset, le DISTINCT porte sur
        # (source_id, date_ecriture, no_piece, ordre) et chaque groupe ressort
        # autant de fois qu'il a de lignes — les totaux sont multipliés d'autant.
        source_ids = [s for s in annul.order_by().values_list(
            'source_id', flat=True).distinct() if s]
        if not source_ids:
            self.stdout.write(self.style.SUCCESS(
                "Aucune extourne d'annulation sur cet exercice — rien à réparer."))
            return

        orphelins, desequilibres, sains = [], [], 0
        for sid in source_ids:
            groupe = annul.filter(source_id=sid)
            # L'écriture d'origine existe-t-elle encore ? C'est elle que
            # l'extourne annule ; sans elle, l'extourne n'annule plus rien.
            origine = JournalEntry.objects.filter(
                tenant=tenant, exercice=ex, source=SOURCE_PAIEMENT, source_id=sid).exists()
            paiement = Paiement.objects.filter(id=sid).exists()
            if origine or paiement:
                sains += 1
                continue

            agg = groupe.aggregate(d=Sum('debit'), c=Sum('credit'))
            gd, gc = float(agg['d'] or 0), float(agg['c'] or 0)
            d70 = float(groupe.filter(no_compte__startswith='70').aggregate(
                d=Sum('debit'))['d'] or 0)
            piece = groupe.values_list('no_piece', flat=True).first() or '?'
            libelle = (groupe.values_list('libelle', flat=True).first() or '')[:44]
            info = dict(sid=sid, piece=piece, libelle=libelle, lignes=groupe.count(),
                        debit=gd, credit=gc, debit70=d70)
            # Un groupe non équilibré ne peut pas être supprimé tel quel sans
            # déséquilibrer le journal : on le signale, on n'y touche pas.
            (orphelins if abs(gd - gc) < 0.01 else desequilibres).append(info)

        net_avant = self._net_70(tenant, ex)
        self.stdout.write(
            f"  Extournes d'annulation      : {len(source_ids)} groupe(s)\n"
            f"    dont origine encore là    : {sains}\n"
            f"    dont ORPHELINES           : {len(orphelins)}\n"
            f"    dont orphelines DÉSÉQUILIBRÉES (non touchées) : {len(desequilibres)}\n"
            f"  → net produits 70 actuel    : {net_avant:>15,.0f}")

        if desequilibres:
            self.stdout.write(self.style.ERROR(
                "\n  ⚠ Groupes orphelins déséquilibrés — à examiner à la main :"))
            for o in desequilibres:
                self.stdout.write(
                    f"    {o['piece']:<14} {o['lignes']} ligne(s)  "
                    f"débit {o['debit']:,.0f} ≠ crédit {o['credit']:,.0f}  {o['libelle']}")

        if not orphelins:
            self.stdout.write(self.style.SUCCESS(
                "\n✓ Aucune extourne orpheline supprimable — rien à réparer."))
            return

        total_70 = sum(o['debit70'] for o in orphelins)
        total_lignes = sum(o['lignes'] for o in orphelins)
        self.stdout.write("\n  Extournes orphelines à supprimer :")
        for o in orphelins:
            self.stdout.write(
                f"    {o['piece']:<14} {o['lignes']} ligne(s)  "
                f"débit 70 {o['debit70']:>12,.0f}   {o['libelle']}")
        self.stdout.write(self.style.ERROR(
            f"\n  ⚠ {total_70:,.0f} FCFA de débit sur les comptes 70 sans "
            f"contrepartie ({total_lignes} ligne(s), {len(orphelins)} groupe(s))."))

        if not opts['appliquer']:
            self.stdout.write(self.style.WARNING(
                f"\nAprès réparation, le net produits vaudrait "
                f"{net_avant + total_70:,.0f} FCFA.\n"
                "Diagnostic seul — relancez avec --appliquer pour corriger."))
            return

        with transaction.atomic():
            supprimees = 0
            for o in orphelins:
                n, _ = annul.filter(source_id=o['sid']).delete()
                supprimees += n

        net_apres = self._net_70(tenant, ex)
        d, c = self._equilibre(tenant, ex)
        self.stdout.write(self.style.SUCCESS(
            f"\n✅ {supprimees} écriture(s) supprimée(s) "
            f"({len(orphelins)} extourne(s) orpheline(s)).\n"
            f"   Net produits : {net_avant:,.0f} → {net_apres:,.0f} FCFA\n"
            f"   Journal : débit {d:,.0f} / crédit {c:,.0f}"
            f"{'  ✓ équilibré' if abs(d - c) < 0.01 else '  ⚠ DÉSÉQUILIBRÉ'}"))
