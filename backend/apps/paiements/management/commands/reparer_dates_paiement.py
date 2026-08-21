"""Rétablit `Paiement.date_paiement` à partir du journal comptable.

Pourquoi cette commande existe : `date_paiement` a été déclaré
`auto_now_add=True`. Django applique ce champ jusque dans un `bulk_create` —
donc `importer_ecole`, qui insère toute une école par lots, réécrivait la date
de TOUS ses règlements avec la date de l'import. Au Complexe Shoumoul
Excellence, les 62 paiements se sont retrouvés au 19/08/2026 et le tableau de
bord (`TruncMonth('date_paiement')`) empilait l'année entière sur un seul mois.

La donnée n'est pas perdue pour autant : `JournalEntry.date_ecriture` est un
DateField ordinaire, transporté fidèlement, et chaque écriture de règlement
porte `source='PAIEMENT'` + `source_id` = l'UUID du paiement. Le journal fait
donc foi, et le rapprochement est un JOIN sur un identifiant, pas une
heuristique de date ou de montant.

  python manage.py reparer_dates_paiement --tenant Shoumoul [--appliquer]
      [--toutes-les-ecoles]

Sans --appliquer : rapport seul, rien n'est écrit.

Deux précautions tiennent dans le choix de `QuerySet.update()` plutôt que
`save()` : `update()` n'exécute pas `pre_save()`, donc il n'est pas repris par
`auto_now_add` (la commande répare même sur une base où le modèle n'a pas
encore été corrigé), et il laisse `updated_at` tranquille — une réparation
technique n'est pas une modification de la pièce.
"""
from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.comptabilite.models import JournalEntry
from apps.paiements.models import Paiement
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Rétablit la date des règlements d'après le journal comptable"

    def add_arguments(self, parser):
        parser.add_argument('--tenant', default=None,
                            help="Nom ou code de l'école à réparer")
        parser.add_argument('--toutes-les-ecoles', action='store_true',
                            help='Passer en revue toutes les écoles')
        parser.add_argument('--appliquer', action='store_true',
                            help='Écrire réellement (sinon rapport seul)')

    def handle(self, *args, **opts):
        if not opts['tenant'] and not opts['toutes_les_ecoles']:
            raise CommandError("Précisez --tenant, ou --toutes-les-ecoles.")

        if opts['toutes_les_ecoles']:
            tenants = list(Tenant.objects.order_by('nom'))
        else:
            arg = opts['tenant']
            tenant = (Tenant.objects.filter(code_etablissement__iexact=arg).first()
                      or Tenant.objects.filter(nom__icontains=arg).first())
            if not tenant:
                raise CommandError(f"École introuvable : {arg}")
            tenants = [tenant]

        total_corriges = 0
        for tenant in tenants:
            total_corriges += self._reparer(tenant, opts['appliquer'])

        if not opts['appliquer']:
            self.stdout.write(self.style.WARNING(
                f"\nRapport seul — {total_corriges} date(s) à corriger. "
                f"Relancez avec --appliquer pour écrire."))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"\n✅ {total_corriges} date(s) rétablie(s)."))

    # ── Une école ─────────────────────────────────────────────────────────
    def _reparer(self, tenant, appliquer):
        paiements = list(Paiement.objects.filter(tenant=tenant)
                         .order_by('no_piece'))
        if not paiements:
            return 0

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n{tenant.nom} ({tenant.code_etablissement}) — "
            f"{len(paiements)} règlement(s)"))

        dates_par_id, dates_par_piece = self._dates_du_journal(tenant)

        corrections, deja_bons, orphelins = [], 0, []
        for p in paiements:
            # L'UUID d'abord : c'est le lien explicite posé à la création de
            # l'écriture. Le numéro de pièce ne sert que pour les règlements
            # antérieurs à ce lien (écritures reprises d'une migration Excel).
            vraie = dates_par_id.get(p.id) or dates_par_piece.get(p.no_piece)
            if vraie is None:
                orphelins.append(p)
            elif vraie == p.date_paiement:
                deja_bons += 1
            else:
                corrections.append((p, vraie))

        for p, vraie in corrections:
            self.stdout.write(
                f"   {p.no_piece:<12} {p.eleve.nom_complet[:28]:<30} "
                f"{p.date_paiement}  →  {vraie}")
        if deja_bons:
            self.stdout.write(f"   {deja_bons} règlement(s) déjà à la bonne date")
        for p in orphelins:
            # Sans écriture, aucune source ne dit la vraie date : on ne devine
            # pas. Un règlement sans contrepartie au journal est de toute façon
            # une anomalie comptable à traiter pour elle-même.
            self.stdout.write(self.style.WARNING(
                f"   ⚠ {p.no_piece:<12} aucune écriture au journal — laissé tel quel"))

        if corrections and appliquer:
            with transaction.atomic():
                for p, vraie in corrections:
                    Paiement.objects.filter(pk=p.pk).update(date_paiement=vraie)

        return len(corrections)

    # ── La vérité, côté journal ───────────────────────────────────────────
    def _dates_du_journal(self, tenant):
        """{uuid_paiement: date} et {no_piece: date}, d'après le journal.

        Une pièce dont les lignes ne portent pas toutes la même date est
        écartée plutôt qu'arbitrée : ce serait le signe d'une écriture
        retouchée à la main, et choisir pour l'utilisateur masquerait le
        problème au lieu de le montrer.
        """
        par_id      = defaultdict(set)
        par_piece   = defaultdict(set)
        lignes = (JournalEntry.objects
                  .filter(tenant=tenant, source='PAIEMENT')
                  .values_list('source_id', 'no_piece', 'date_ecriture'))
        for source_id, no_piece, date in lignes:
            if source_id:
                par_id[source_id].add(date)
            par_piece[no_piece].add(date)

        def unanimes(table):
            resultat = {}
            for cle, dates in table.items():
                if len(dates) == 1:
                    resultat[cle] = next(iter(dates))
                else:
                    self.stdout.write(self.style.WARNING(
                        f"   ⚠ {cle} : {len(dates)} dates différentes au "
                        f"journal ({sorted(dates)}) — non arbitré"))
            return resultat

        return unanimes(par_id), unanimes(par_piece)
