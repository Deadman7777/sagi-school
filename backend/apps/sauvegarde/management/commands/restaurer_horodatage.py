"""Rend à une école importée ses `created_at` / `updated_at` d'origine.

Deuxième volet de la réparation de la bascule en cloud. `importer_ecole`
insérait par `bulk_create`, qui applique `auto_now_add` / `auto_now` comme
n'importe quel INSERT : toutes les lignes copiées se sont retrouvées créées
et modifiées le jour de l'import. Pour les règlements, la vraie date se
retrouve dans le journal (`reparer_dates_paiement`) ; pour les horodatages
techniques, aucune autre table ne les porte — la seule source est le dump.

D'où cette commande, qui suit le même chemin que l'import :

  1. pg_restore du dump d'origine dans une base TEMPORAIRE
  2. restaurer_horodatage : recopie les horodatages de CETTE école
  3. suppression de la base temporaire

  python manage.py restaurer_horodatage --source-db sagi_temp --tenant Shoumoul
      [--source-host --source-port --source-user --source-password]
      [--appliquer]

Sans --appliquer : inventaire seul, rien n'est écrit.

Le rapprochement est exact et non ambigu : les clés primaires sont des UUID,
transportés tels quels par l'import. Une ligne de la cible et son homologue de
la source portent le même identifiant, ou n'existent pas.

Ce que cette commande répare vraiment : le journal d'audit. `AuditLog` est
ordonné sur `created_at` — tous ses horodatages écrasés le même jour, il perd
sa chronologie et ne prouve plus rien. Les `created_at` du reste sont des
métadonnées, mais elles datent l'entrée de chaque élève et de chaque pièce
dans le système, et rien ne justifie de les laisser fausses.

L'écriture passe par `QuerySet.update()`, qui n'exécute pas `pre_save()` :
c'est la seule façon de poser une valeur sur un champ `auto_now` — un `save()`
la remplacerait par l'heure courante, reproduisant exactement le bug.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.tenants.models import Tenant

from .importer_ecole import SOURCE, arguments_source, brancher_source
from .importer_ecole import Command as CommandeImport


class Command(BaseCommand):
    help = "Restaure les created_at/updated_at d'une école importée"

    def add_arguments(self, parser):
        arguments_source(parser)

    def handle(self, *args, **opts):
        brancher_source(opts)

        arg = opts['tenant']
        source_qs = Tenant.objects.using(SOURCE)
        tenant_source = (source_qs.filter(code_etablissement__iexact=arg).first()
                         or source_qs.filter(nom__icontains=arg).first())
        if not tenant_source:
            raise CommandError(f"École introuvable dans la base source : {arg}")

        # L'école doit être des DEUX côtés : on répare un import déjà fait,
        # on n'en amorce pas un nouveau.
        if not Tenant.objects.filter(pk=tenant_source.pk).exists():
            raise CommandError(
                f"L'école « {tenant_source.nom} » n'est pas dans la base "
                f"courante. Cette commande répare une école DÉJÀ importée — "
                f"lancez d'abord importer_ecole.")

        self.stdout.write(f"École  : {tenant_source.nom} "
                          f"({tenant_source.code_etablissement})")
        self.stdout.write(f"Source : {opts['source_db']}\n")

        modeles = [m for m in CommandeImport()._modeles() if self._colonnes(m)]
        # Le tenant lui-même porte aussi des horodatages, et il est copié à
        # part par l'import : sans lui, l'école resterait « créée » le jour
        # de la bascule.
        if self._colonnes(Tenant):
            modeles = [Tenant] + modeles

        plan, total = [], 0
        for modele in modeles:
            ecarts = self._ecarts(modele, tenant_source)
            if ecarts:
                plan.append((modele, ecarts))
                total += len(ecarts)

        if not plan:
            self.stdout.write(self.style.SUCCESS(
                "Tous les horodatages sont déjà conformes à la source."))
            return

        self.stdout.write("Horodatages à restaurer :")
        for modele, ecarts in plan:
            self.stdout.write(f"   {modele._meta.label:<38} {len(ecarts):>7}")
        self.stdout.write(self.style.MIGRATE_LABEL(
            f"   {'TOTAL':<38} {total:>7}\n"))

        if not opts['appliquer']:
            self.stdout.write(self.style.WARNING(
                "Inventaire seul — relancez avec --appliquer pour écrire."))
            return

        with transaction.atomic():
            for modele, ecarts in plan:
                for pk, valeurs in ecarts:
                    modele.objects.filter(pk=pk).update(**valeurs)

        self.stdout.write(self.style.SUCCESS(
            f"\n✅ {total} horodatage(s) restauré(s) pour "
            f"« {tenant_source.nom} »."))

    # ── Ce qu'il y a à réparer ────────────────────────────────────────────
    def _colonnes(self, modele):
        """Champs date/heure posés par l'horloge du serveur, donc écrasés."""
        return [c.name for c in modele._meta.fields
                if getattr(c, 'auto_now_add', False) or getattr(c, 'auto_now', False)]

    def _ecarts(self, modele, tenant_source):
        """[(pk, {colonne: valeur_source})] pour les lignes qui divergent.

        Une ligne absente de la source est ignorée sans bruit : elle a été
        saisie dans le cloud APRÈS la bascule, son horodatage est le bon.
        """
        colonnes = self._colonnes(modele)
        if modele is Tenant:
            filtre_source = {'pk': tenant_source.pk}
            filtre_cible  = {'pk': tenant_source.pk}
        else:
            filtre_source = {'tenant': tenant_source}
            filtre_cible  = {'tenant_id': tenant_source.pk}

        source = {ligne[0]: ligne[1:] for ligne in
                  modele.objects.using(SOURCE).filter(**filtre_source)
                  .values_list('pk', *colonnes)}
        if not source:
            return []

        ecarts = []
        for ligne in (modele.objects.filter(**filtre_cible)
                      .values_list('pk', *colonnes)):
            pk, actuels = ligne[0], ligne[1:]
            attendus = source.get(pk)
            if attendus is None or attendus == actuels:
                continue
            ecarts.append((pk, dict(zip(colonnes, attendus))))
        return ecarts
