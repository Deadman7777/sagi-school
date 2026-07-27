"""Reclasse les sorties de caisse migrées vers un compte dédié.

L'import d'un journal de caisse verse toute sortie non identifiée dans 658,
« Charges diverses ». Chez Shoumoul, ce compte porte 13 349 500 FCFA — 98 %
des charges de l'exercice. Un comptable, un banquier ou un fiscaliste
s'arrêtent tous à la même question : qu'y a-t-il là-dedans ?

Ce sont de VRAIES dépenses. Les sortir de la classe 6 ferait passer le
résultat de −151 000 à +13 198 500 : une école qui gonfle son résultat en
reclassant ses dépenses hors charges. Le problème n'est pas le classement,
c'est l'intitulé.

La commande les déplace donc vers 6588, « Charges reprises à la migration
(détail non communiqué) ». Même classe, même effet sur le résultat, même
trésorerie — mais la ligne dit enfin ce qu'elle est, et l'école pourra
reventiler au fil du temps ce dont elle retrouve le détail.

  python manage.py reclasser_charges_migration --settings=config.settings.production
      [--tenant <code ou nom>] [--exercice 2026] [--compte 658] [--appliquer]

Sans --appliquer : diagnostic seul. Idempotente.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Sum

from apps.comptabilite.models import JournalEntry
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant

COMPTE_CIBLE = '6588'
LIBELLE_CIBLE = 'Charges reprises à la migration (détail non communiqué)'


class Command(BaseCommand):
    help = ("Reclasse les charges migrées de 658 vers 6588 (compte dédié, "
            "sans effet sur le résultat)")

    def add_arguments(self, parser):
        parser.add_argument('--tenant', help="Code ou nom de l'école")
        parser.add_argument('--exercice', help='Année scolaire (défaut : exercice actif)')
        parser.add_argument('--compte', default='658',
                            help='Compte source à reclasser (défaut : 658)')
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

    def _charges(self, tenant, ex):
        agg = JournalEntry.objects.filter(
            tenant=tenant, exercice=ex, no_compte__startswith='6'
        ).aggregate(d=Sum('debit'), c=Sum('credit'))
        return float(agg['d'] or 0) - float(agg['c'] or 0)

    def handle(self, *args, **opts):
        tenant = self._tenant(opts.get('tenant'))
        source = opts['compte']

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

        # UNIQUEMENT les écritures issues de la migration : une charge saisie
        # à la main dans 658 est un vrai choix de l'école, on n'y touche pas.
        lignes = JournalEntry.objects.filter(
            tenant=tenant, exercice=ex, no_compte=source, source='MIGRATION')
        montant = float(lignes.aggregate(d=Sum('debit'))['d'] or 0)
        autres = JournalEntry.objects.filter(
            tenant=tenant, exercice=ex, no_compte=source).exclude(source='MIGRATION')
        montant_autres = float(autres.aggregate(d=Sum('debit'))['d'] or 0)
        charges_avant = self._charges(tenant, ex)

        self.stdout.write(
            f"  Compte {source} — écritures de MIGRATION : {lignes.count()} ligne(s), "
            f"{montant:,.0f} FCFA\n"
            f"  Compte {source} — autres sources (non touchées) : {autres.count()} "
            f"ligne(s), {montant_autres:,.0f} FCFA\n"
            f"  Total des charges de l'exercice : {charges_avant:,.0f} FCFA")

        if not lignes.exists():
            self.stdout.write(self.style.SUCCESS(
                f"\n✓ Aucune charge migrée sur le compte {source} — rien à reclasser."))
            return

        self.stdout.write(
            f"\n  → {montant:,.0f} FCFA passeraient de « {source} » à "
            f"« {COMPTE_CIBLE} — {LIBELLE_CIBLE} ».\n"
            "  Le total des charges et le résultat sont INCHANGÉS : même classe 6, "
            "seul l'intitulé change.")

        if not opts['appliquer']:
            self.stdout.write(self.style.WARNING(
                "\nDiagnostic seul — relancez avec --appliquer pour reclasser."))
            return

        with transaction.atomic():
            self._creer_compte(tenant)
            nb = lignes.update(no_compte=COMPTE_CIBLE)

        charges_apres = self._charges(tenant, ex)
        self.stdout.write(self.style.SUCCESS(
            f"\n✅ {nb} écriture(s) reclassée(s) vers {COMPTE_CIBLE}.\n"
            f"   Charges de l'exercice : {charges_avant:,.0f} → {charges_apres:,.0f} FCFA"
            f"{'  ✓ inchangées' if abs(charges_avant - charges_apres) < 0.01 else '  ⚠ ÉCART'}"))

    def _creer_compte(self, tenant):
        """Ajoute 6588 au plan de l'école s'il n'y est pas encore."""
        from apps.comptabilite.models import CompteComptable
        CompteComptable.objects.get_or_create(
            tenant=tenant, no_compte=COMPTE_CIBLE,
            defaults={'libelle': LIBELLE_CIBLE, 'type': 'CHARGE',
                      'classe': 6, 'est_actif': True})
