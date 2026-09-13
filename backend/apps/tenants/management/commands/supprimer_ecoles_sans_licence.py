"""Supprime DÉFINITIVEMENT les écoles restées en base sans licence.

Ce sont les écoles dont on n'avait retiré que la licence avec l'ancien bouton
« Supprimer ». Simulation par défaut :

    python manage.py supprimer_ecoles_sans_licence --settings=config.settings.cloud
    python manage.py supprimer_ecoles_sans_licence --appliquer --settings=config.settings.cloud

--garder <id> (répétable) exclut une école de la suppression.
"""
from django.core.management.base import BaseCommand

from apps.tenants.suppression import compter, ecoles_sans_licence, supprimer_ecole


class Command(BaseCommand):
    help = "Supprime définitivement les écoles sans licence (simulation par défaut)."

    def add_arguments(self, parser):
        parser.add_argument('--appliquer', action='store_true')
        parser.add_argument('--garder', action='append', default=[], help="id d'une école à conserver")

    def handle(self, *args, appliquer, garder, **options):
        ecoles = [t for t in ecoles_sans_licence() if str(t.id) not in set(garder)]
        self.stdout.write('SUPPRESSION DÉFINITIVE' if appliquer else 'SIMULATION (rien supprimé)')
        for t in ecoles:
            c = compter(t)
            self.stdout.write(f"  {t.id}  {t.nom[:50]:<50} {c['eleves']:>4} élèves  "
                              f"{c['paiements']:>4} paiements  {c['utilisateurs']:>3} utilisateurs")
            if appliquer:
                supprimer_ecole(t)
        self.stdout.write(f"{len(ecoles)} école(s) {'supprimée(s)' if appliquer else 'à supprimer'}.")
        if not appliquer and ecoles:
            self.stdout.write(self.style.WARNING('Relancez avec --appliquer pour supprimer définitivement.'))
