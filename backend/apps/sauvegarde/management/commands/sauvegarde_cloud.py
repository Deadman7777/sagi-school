"""
Commande : python manage.py sauvegarde_cloud [--local-seulement]

Sauvegarde la base locale (pg_dump -Fc, rotation 7 sur le poste) et
l'envoie au serveur cloud HADY GESMAN, authentifiée par la clé de licence.
Lancée par Electron à chaque démarrage puis toutes les 24 h ; peut aussi
être déclenchée depuis Paramètres → Sauvegarde ou à la main.

Le statut est écrit dans backups/statut.json (lu par l'API /api/sauvegarde/).
"""
from django.core.management.base import BaseCommand

from apps.sauvegarde.service import executer_sauvegarde


class Command(BaseCommand):
    help = 'Sauvegarde la base locale et l’envoie sur le cloud HADY GESMAN'

    def add_arguments(self, parser):
        parser.add_argument('--local-seulement', action='store_true',
                            help="Dump local sans envoi vers le serveur")

    def handle(self, *args, **options):
        statut = executer_sauvegarde(envoyer=not options['local_seulement'])
        style = self.style.SUCCESS if statut['statut'] == 'OK' else self.style.ERROR
        self.stdout.write(style(
            f"[{statut['statut']}] {statut.get('message', '')} "
            f"({statut.get('fichier', '—')}, {statut.get('taille', 0)} octets)"))
