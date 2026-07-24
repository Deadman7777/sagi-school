"""Réconcilie le double comptage des produits lors d'une migration.

Contexte (école Shoumoul, 2026) : on a d'abord migré le journal de caisse en
AGRÉGATS mensuels (`import_journal_caisse`, source='MIGRATION') → chaque mois
`571 D (caisse) / 706 C (produits)`, sans détail par élève. Puis on a importé
les élèves avec la reprise « déjà payé » (`apps.paiements.reprise`,
source='PAIEMENT' mode REPRISE) → `411 D / 706 C` puis `890 D / 411 C`.

Résultat : le produit 706 est compté DEUX FOIS (agrégats + par élève). La caisse
(571) n'est pas doublée (la reprise passe par 890), mais les produits/résultat
affichés valent ~2× la réalité.

Correction SYSCOHADA (jamais muter/supprimer : on contre-passe) : pour chaque
compte de produit scolarité agrégé (706, 706.1, 706.3, 707 par défaut), on crée
une écriture de reclassement `7xx D / 890 C` du montant migré → le produit
agrégé est neutralisé (la reprise par élève reste la seule reconnaissance des
produits), la caisse 571 est intacte, et le RÉSIDU sur 890 = l'écart entre le
cash migré et ce qui est attribué aux élèves (l'info à analyser).

  python manage.py reconcilier_migration_produits [--tenant_id UUID]
      [--exercice 2026] [--comptes 706,706.1,706.3,707] [--appliquer]

Sans --appliquer : RAPPORT seul (dry-run), aucune écriture. Idempotent : refuse
de ré-appliquer si un reclassement existe déjà pour l'exercice.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Sum

from apps.tenants.models import Tenant
from apps.paiements.models import Exercice, Paiement
from apps.comptabilite.models import JournalEntry

SOURCE_RECONCIL = 'RECONCIL_MIGRATION'
COMPTES_DEFAUT = ['706', '706.1', '706.3', '707']  # produits de scolarité


class Command(BaseCommand):
    help = "Réconcilie le double comptage des produits migrés (agrégats vs reprise élèves)."

    def add_arguments(self, parser):
        parser.add_argument('--tenant_id', help='UUID du tenant (facultatif si un seul)')
        parser.add_argument('--exercice', help="Année scolaire (ex. 2026). Défaut : exercice ouvert.")
        parser.add_argument('--comptes', default=','.join(COMPTES_DEFAUT),
                            help='Comptes de produits agrégés à neutraliser (défaut : %(default)s)')
        parser.add_argument('--appliquer', action='store_true',
                            help="Écrit les écritures de reclassement (sinon : rapport seul).")

    def handle(self, *args, **o):
        tenant = self._tenant(o.get('tenant_id'))
        exercice = self._exercice(tenant, o.get('exercice'))
        comptes = [c.strip() for c in (o['comptes'] or '').split(',') if c.strip()]

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n═══ Réconciliation produits — {tenant.nom} — exercice {exercice.annee_scolaire} ═══"))

        base = JournalEntry.objects.filter(tenant=tenant, exercice=exercice)

        # 1) Produits agrégés (MIGRATION) par compte
        agreges = base.filter(source='MIGRATION', credit__gt=0, no_compte__startswith='7') \
            .values('no_compte').annotate(m=Sum('credit')).order_by('no_compte')
        agreges = {r['no_compte']: float(r['m'] or 0) for r in agreges}
        total_agrege_cible = sum(v for c, v in agreges.items() if c in comptes)

        # 2) Reprise élèves (produits 706 des paiements mode REPRISE)
        rep_ids = Paiement.objects.filter(
            tenant=tenant, exercice=exercice, mode_paiement='REPRISE'
        ).values_list('id', flat=True)
        total_reprise = float(base.filter(
            source='PAIEMENT', source_id__in=list(rep_ids), no_compte='706', credit__gt=0
        ).aggregate(m=Sum('credit'))['m'] or 0)

        # 3) Caisse réelle (571) + 890 actuel
        c571 = base.filter(no_compte='571').aggregate(d=Sum('debit'), c=Sum('credit'))
        caisse = float(exercice.solde_initial_caisse or 0) + float(c571['d'] or 0) - float(c571['c'] or 0)
        s890 = base.filter(no_compte='890').aggregate(d=Sum('debit'), c=Sum('credit'))
        solde_890 = float(s890['c'] or 0) - float(s890['d'] or 0)  # sens créditeur

        # ── Rapport ──
        self.stdout.write("\n  Produits agrégés migrés (source MIGRATION) :")
        if agreges:
            for c, v in agreges.items():
                mark = '→ neutralisé' if c in comptes else '(conservé)'
                self.stdout.write(f"    {c:<8} {v:>15,.0f}   {mark}")
        else:
            self.stdout.write("    (aucun)")
        self.stdout.write(f"  Total à neutraliser (comptes {','.join(comptes)}) : "
                          f"{total_agrege_cible:,.0f} FCFA")
        self.stdout.write(f"\n  Reprise élèves (706, mode REPRISE)          : {total_reprise:,.0f} FCFA")
        ecart = total_agrege_cible - total_reprise
        self.stdout.write(self.style.WARNING(
            f"  Écart agrégats − reprise                    : {ecart:,.0f} FCFA"))
        self.stdout.write(f"\n  Caisse réelle (571 + solde initial)         : {caisse:,.0f} FCFA")
        self.stdout.write(f"  Solde 890 (bilan d'ouverture) actuel        : {solde_890:,.0f} FCFA")
        self.stdout.write(f"  Solde 890 après reclassement (estimé)       : "
                          f"{solde_890 + total_agrege_cible:,.0f} FCFA")

        deja = base.filter(source=SOURCE_RECONCIL).exists()
        if deja:
            self.stdout.write(self.style.WARNING(
                "\n  ⚠ Un reclassement RECONCIL_MIGRATION existe déjà pour cet exercice — rien à faire."))
            return
        if total_agrege_cible <= 0:
            self.stdout.write("\n  Aucun produit agrégé à neutraliser sur ces comptes.")
            return

        if not o['appliquer']:
            self.stdout.write(self.style.MIGRATE_LABEL(
                "\n  DRY-RUN — aucune écriture créée. Relancer avec --appliquer pour reclasser."))
            return

        # ── Application : contre-passation 7xx D / 890 C ──
        with transaction.atomic():
            no_piece = 'RECONCIL-0001'
            lignes, ordre = [], 0
            for c in comptes:
                m = agreges.get(c, 0)
                if m <= 0:
                    continue
                ordre += 1
                lignes.append(JournalEntry(
                    tenant=tenant, exercice=exercice, no_piece=no_piece,
                    date_ecriture=exercice.date_debut, source=SOURCE_RECONCIL,
                    no_compte=c, debit=Decimal(str(m)), credit=0, ordre=ordre,
                    libelle=f"Reclassement produit agrégé {c} → bilan d'ouverture (réconciliation migration)"))
            ordre += 1
            lignes.append(JournalEntry(
                tenant=tenant, exercice=exercice, no_piece=no_piece,
                date_ecriture=exercice.date_debut, source=SOURCE_RECONCIL,
                no_compte='890', debit=0, credit=Decimal(str(total_agrege_cible)), ordre=ordre,
                libelle="Contrepartie reclassement produits agrégés (réconciliation migration)"))
            JournalEntry.objects.bulk_create(lignes)

        self.stdout.write(self.style.SUCCESS(
            f"\n  ✓ Reclassement appliqué : {total_agrege_cible:,.0f} FCFA de produits agrégés "
            f"basculés en 890 ({len(lignes)} lignes, pièce {no_piece})."))

    # ── Helpers ──
    def _tenant(self, tenant_id):
        if tenant_id:
            try:
                return Tenant.objects.get(id=tenant_id)
            except Tenant.DoesNotExist:
                raise CommandError(f'Tenant {tenant_id} introuvable')
        tenants = list(Tenant.objects.all()[:2])
        if len(tenants) == 1:
            return tenants[0]
        raise CommandError('Plusieurs tenants : préciser --tenant_id UUID')

    def _exercice(self, tenant, annee):
        qs = Exercice.objects.filter(tenant=tenant)
        if annee:
            ex = qs.filter(annee_scolaire=annee).first()
            if not ex:
                raise CommandError(f"Exercice {annee} introuvable")
            return ex
        ex = qs.filter(cloture=False).order_by('-date_debut').first()
        if not ex:
            raise CommandError("Aucun exercice ouvert : préciser --exercice")
        return ex
