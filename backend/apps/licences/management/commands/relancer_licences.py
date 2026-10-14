"""Relance les écoles dont la licence arrive à échéance (J-7, J-3, J-1, J0).

À lancer chaque jour sur le cloud (cron). Sans danger à relancer : un palier
déjà envoyé pour une échéance ne repart jamais.

  python manage.py relancer_licences --settings=config.settings.cloud [--simuler]
"""
from django.core.management.base import BaseCommand

from apps.licences.relances import executer


class Command(BaseCommand):
    help = "Relance par e-mail les licences qui expirent dans 7 jours ou moins"

    def add_arguments(self, parser):
        parser.add_argument('--simuler', action='store_true',
                            help="Ne rien envoyer : journaliser ce qui partirait")

    def handle(self, *args, **opts):
        rapport = executer(simuler=opts['simuler'])
        if rapport['motif']:
            self.stdout.write(rapport['motif'])
            return
        for ligne in rapport['envoyees']:
            self.stdout.write(self.style.SUCCESS(('[simulée] ' if opts['simuler'] else '') + ligne))
        for ligne in rapport['echecs']:
            self.stdout.write(self.style.ERROR(ligne))
        self.stdout.write(f"{len(rapport['envoyees'])} relance(s), {len(rapport['echecs'])} échec(s), "
                          f"{rapport['deja']} déjà faite(s).")
