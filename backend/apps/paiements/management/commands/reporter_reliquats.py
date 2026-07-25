"""Reconduit les impayés d'un exercice sur le suivant (à-nouveaux 411/890).

Sert de rattrapage quand l'exercice précédent est DÉJÀ clôturé : les écritures
sont passées dans le nouvel exercice uniquement, l'année clôturée n'est jamais
modifiée. La commande est idempotente — la rejouer ne duplique rien.

  python manage.py reporter_reliquats --settings=config.settings.production
      [--tenant <code ou nom>] [--source 2024-2025] [--cible 2025-2026]
      [--sans-creation] [--appliquer]

Sans --appliquer : simulation, affiche le détail élève par élève.
"""
from django.core.management.base import BaseCommand, CommandError

from apps.paiements.models import Exercice
from apps.paiements.report_reliquats import (exercice_source_par_defaut,
                                             reporter_reliquats)
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Reporte les reliquats d'un exercice sur le suivant"

    def add_arguments(self, parser):
        parser.add_argument('--tenant', help='Code ou nom de l\'école (défaut : la seule école)')
        parser.add_argument('--source', help='Année scolaire d\'origine (ex. 2024-2025)')
        parser.add_argument('--cible',  help='Année scolaire de destination (défaut : exercice actif)')
        parser.add_argument('--sans-creation', action='store_true',
                            help='Ne pas réinscrire les élèves absents de la cible')
        parser.add_argument('--appliquer', action='store_true',
                            help='Écrire réellement (sinon simulation)')

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

    def _exercice(self, tenant, annee, label):
        ex = Exercice.objects.filter(tenant=tenant, annee_scolaire=annee).first()
        if not ex:
            dispo = ', '.join(Exercice.objects.filter(tenant=tenant)
                              .values_list('annee_scolaire', flat=True))
            raise CommandError(f"Exercice {label} « {annee} » introuvable. Disponibles : {dispo}")
        return ex

    def handle(self, *args, **opts):
        tenant = self._tenant(opts.get('tenant'))

        if opts.get('cible'):
            cible = self._exercice(tenant, opts['cible'], 'cible')
        else:
            cible = Exercice.objects.filter(
                tenant=tenant, cloture=False).order_by('-date_debut').first()
            if not cible:
                raise CommandError("Aucun exercice actif — précisez --cible.")

        if opts.get('source'):
            source = self._exercice(tenant, opts['source'], 'source')
        else:
            source = exercice_source_par_defaut(tenant, cible)
            if not source:
                raise CommandError(f"Aucun exercice antérieur à {cible.annee_scolaire}.")

        dry = not opts['appliquer']
        self.stdout.write(
            f"École : {tenant}\n"
            f"Report {source.annee_scolaire} → {cible.annee_scolaire}"
            f"{'  (SIMULATION)' if dry else ''}\n")

        try:
            rapport = reporter_reliquats(
                source, cible,
                creer_fiches=not opts['sans_creation'],
                dry_run=dry)
        except ValueError as exc:
            raise CommandError(str(exc))

        for ligne in rapport['reportes']:
            fiche = 'réinscrit' if ligne['fiche'] == 'creee' else 'fiche existante'
            self.stdout.write(
                f"  {ligne['nom_complet'][:34]:<34} {ligne['section'][:16]:<16} "
                f"{ligne['montant']:>12,.0f}  ({fiche})")

        for ligne in rapport['a_verifier']:
            self.stdout.write(self.style.WARNING(
                f"  ⚠ {ligne['nom_complet'][:34]:<34} {ligne['montant']:>12,.0f}  "
                f"ndongo passager — à réinscrire à la main, puis rejouer"))

        for ligne in rapport['ignores']:
            self.stdout.write(self.style.NOTICE(
                f"  · {ligne['nom_complet'][:34]:<34} {ligne['montant']:>12,.0f}  "
                f"ignoré ({ligne['motif']})"))

        self.stdout.write(
            f"\n{rapport['nb_reportes']} reliquat(s) — "
            f"{rapport['montant_total']:,.0f} FCFA"
            + (f" | {rapport['nb_a_verifier']} à vérifier "
               f"({rapport['montant_a_verifier']:,.0f} FCFA)"
               if rapport['nb_a_verifier'] else '')
            + (f" | {rapport['nb_ignores']} ignoré(s)" if rapport['nb_ignores'] else ''))

        if dry:
            self.stdout.write(self.style.WARNING(
                "\nSimulation — relancez avec --appliquer pour écrire."))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"\n✅ Report effectué sur {cible.annee_scolaire} "
                f"(à-nouveaux 411/890, pièces RAN-xxxx)."))
