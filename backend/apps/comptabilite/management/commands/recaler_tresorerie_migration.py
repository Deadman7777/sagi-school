"""Recale la trésorerie et les produits d'une migration sur les valeurs réelles.

Cas Shoumoul (2026) : après migration des agrégats du journal de caisse
(produits = fichier Excel = vrais 706) PUIS import élèves avec reprise
« déjà payé », le 706 est doublé (reprise) et les soldes de trésorerie ne
reflètent pas la réalité physique des comptes.

Cet outil, en une passe, sans muter/supprimer l'existant (contre-passation) :

  1. `--neutraliser-reprise` : reclasse le produit 706 de la reprise élèves vers
     890 (`706 D / 890 C`). → 706 ne garde que le réel (agrégats Excel + paiements
     récents). Le RESTE DÛ par élève est préservé (il vient des fiches Paiement,
     pas des écritures).
  2. Ajuste chaque compte de trésorerie à sa valeur réelle cible (contrepartie
     890), calculée EXACTEMENT comme le tableau de bord (solde initial + net des
     écritures) : caisse 571, banque 521, Wave 5521, Orange Money 5522, Free 5523.

  python manage.py recaler_tresorerie_migration [--tenant_id UUID] [--exercice 2026]
      --caisse 17000 --banque 10000 --wave 15000 --om 3000 --free 0
      [--neutraliser-reprise] [--appliquer]

Sans --appliquer : RAPPORT seul. Idempotent (refuse si un recalage existe déjà).
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Sum

from apps.tenants.models import Tenant
from apps.paiements.models import Exercice, Paiement
from apps.comptabilite.models import JournalEntry

SOURCE_RECAL = 'RECAL_MIGRATION'

# (compte, clé solde initial de l'exercice) — même mapping que le dashboard canaux.
COMPTES_TRESO = [
    ('571',  'caisse'),
    ('521',  'banque'),
    ('5521', 'mobile'),
    ('5522', None),
    ('5523', None),
]


class Command(BaseCommand):
    help = "Recale trésorerie (valeurs réelles) + neutralise le double 706 de la reprise."

    def add_arguments(self, parser):
        parser.add_argument('--tenant_id')
        parser.add_argument('--exercice')
        parser.add_argument('--caisse', type=Decimal, default=None, help='Solde réel 571')
        parser.add_argument('--banque', type=Decimal, default=None, help='Solde réel 521')
        parser.add_argument('--wave',   type=Decimal, default=None, help='Solde réel 5521')
        parser.add_argument('--om',     type=Decimal, default=None, help='Solde réel 5522')
        parser.add_argument('--free',   type=Decimal, default=None, help='Solde réel 5523')
        parser.add_argument('--neutraliser-reprise', action='store_true',
                            help="Reclasse le 706 de la reprise élèves vers 890.")
        parser.add_argument('--appliquer', action='store_true')

    def handle(self, *args, **o):
        tenant = self._tenant(o.get('tenant_id'))
        ex = self._exercice(tenant, o.get('exercice'))
        base = JournalEntry.objects.filter(tenant=tenant, exercice=ex)

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n═══ Recalage trésorerie — {tenant.nom} — exercice {ex.annee_scolaire} ═══"))

        cibles = {'571': o['caisse'], '521': o['banque'], '5521': o['wave'],
                  '5522': o['om'], '5523': o['free']}
        soldes_init = {'caisse': Decimal(str(ex.solde_initial_caisse or 0)),
                       'banque': Decimal(str(ex.solde_initial_banque or 0)),
                       'mobile': Decimal(str(ex.solde_initial_mobile or 0)),
                       None: Decimal('0')}

        # ── Soldes affichés actuels (solde initial + net écritures) ──
        def net(compte):
            a = base.filter(no_compte=compte).aggregate(d=Sum('debit'), c=Sum('credit'))
            return Decimal(str(a['d'] or 0)) - Decimal(str(a['c'] or 0))

        self.stdout.write("\n  Trésorerie — actuel → cible (ajustement) :")
        ajustements = {}
        total_cible = Decimal('0')
        for compte, key in COMPTES_TRESO:
            affiche = soldes_init[key] + net(compte)
            cible = cibles.get(compte)
            if cible is None:
                self.stdout.write(f"    {compte:<6} actuel {affiche:>14,.0f}   (cible non fournie, inchangé)")
                continue
            adj = cible - affiche
            ajustements[compte] = adj
            total_cible += cible
            self.stdout.write(
                f"    {compte:<6} actuel {affiche:>14,.0f}  →  cible {cible:>12,.0f}   "
                f"ajustement {adj:>+14,.0f}")
        self.stdout.write(self.style.MIGRATE_LABEL(
            f"  Trésorerie générale cible : {total_cible:,.0f} FCFA"))

        # ── Reprise 706 (double comptage) ──
        rep_ids = list(Paiement.objects.filter(
            tenant=tenant, exercice=ex, mode_paiement='REPRISE').values_list('id', flat=True))
        reprise_706 = Decimal(str(base.filter(
            source='PAIEMENT', source_id__in=rep_ids, no_compte='706', credit__gt=0
        ).aggregate(c=Sum('credit'))['c'] or 0))
        # net('706') est créditeur (négatif) ; on affiche les produits en positif.
        produits_actuels = -net('706')
        self.stdout.write(f"\n  Produits 706 actuels (crédit)       : {produits_actuels:,.0f} FCFA")
        self.stdout.write(f"  dont reprise élèves (à neutraliser) : {reprise_706:,.0f} FCFA")
        if o['neutraliser_reprise']:
            self.stdout.write(f"  Produits 706 après neutralisation   : {produits_actuels - reprise_706:,.0f} FCFA "
                              f"(= agrégats Excel + paiements récents)")

        if base.filter(source=SOURCE_RECAL).exists():
            self.stdout.write(self.style.WARNING(
                "\n  ⚠ Un recalage RECAL_MIGRATION existe déjà pour cet exercice — rien à faire."))
            return
        if not o['appliquer']:
            self.stdout.write(self.style.MIGRATE_LABEL(
                "\n  DRY-RUN — aucune écriture. Relancer avec --appliquer (+ --neutraliser-reprise si voulu)."))
            return
        if any(v is None for v in cibles.values()):
            raise CommandError("Cibles manquantes : préciser --caisse --banque --wave --om --free.")

        # ── Application (contre-passation, contrepartie 890) ──
        with transaction.atomic():
            lignes, ordre = [], 0

            if o['neutraliser_reprise'] and reprise_706 > 0:
                ordre += 1
                lignes.append(self._je(tenant, ex, 'RECAL-REP', '706', reprise_706, 0, ordre,
                              "Neutralisation produit reprise élèves (recalage migration)"))
                ordre += 1
                lignes.append(self._je(tenant, ex, 'RECAL-REP', '890', 0, reprise_706, ordre,
                              "Contrepartie neutralisation reprise (recalage migration)"))

            # Ajustements trésorerie ↔ 890
            ordre = 0
            treso_lignes = []
            net_890 = Decimal('0')  # sens créditeur (ce qui va au crédit de 890)
            for compte, adj in ajustements.items():
                if adj == 0:
                    continue
                ordre += 1
                if adj > 0:   # augmenter la trésorerie : 5xx D / 890 C
                    treso_lignes.append(self._je(tenant, ex, 'RECAL-TRESO', compte, adj, 0, ordre,
                                        f"Recalage {compte} sur solde réel"))
                    net_890 += adj
                else:         # diminuer : 890 D / 5xx C
                    treso_lignes.append(self._je(tenant, ex, 'RECAL-TRESO', compte, 0, -adj, ordre,
                                        f"Recalage {compte} sur solde réel"))
                    net_890 -= (-adj)
            if treso_lignes:
                ordre += 1
                if net_890 >= 0:
                    treso_lignes.append(self._je(tenant, ex, 'RECAL-TRESO', '890', 0, net_890, ordre,
                                        "Contrepartie recalage trésorerie (bilan d'ouverture)"))
                else:
                    treso_lignes.append(self._je(tenant, ex, 'RECAL-TRESO', '890', -net_890, 0, ordre,
                                        "Contrepartie recalage trésorerie (bilan d'ouverture)"))
            JournalEntry.objects.bulk_create(lignes + treso_lignes)

        self.stdout.write(self.style.SUCCESS(
            f"\n  ✓ Recalage appliqué. Trésorerie générale = {total_cible:,.0f} FCFA. "
            f"{'Reprise 706 neutralisée. ' if o['neutraliser_reprise'] else ''}"
            f"Reste dû par élève préservé (fiches Paiement inchangées)."))

    # ── Helpers ──
    def _je(self, tenant, ex, no_piece, compte, debit, credit, ordre, libelle):
        return JournalEntry(
            tenant=tenant, exercice=ex, no_piece=no_piece, date_ecriture=ex.date_debut,
            source=SOURCE_RECAL, no_compte=compte, debit=debit, credit=credit,
            ordre=ordre, libelle=libelle)

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
