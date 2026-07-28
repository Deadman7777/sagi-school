"""Envoie les rappels de paiement du mois — à brancher sur une tâche planifiée.

En mode cloud, un cron quotidien suffit : la commande ne fait rien hors de la
fenêtre de rappel de l'école, et ne prévient jamais deux fois le même élève
dans le mois. La lancer tous les jours est donc sans danger.

En local (Electron), il n'y a pas de cron : l'école déclenche depuis l'écran
Paramètres, ou cette commande se lance à la main.

  python manage.py envoyer_rappels --settings=config.settings.production
      [--tenant <code ou nom>] [--forcer] [--simuler]

Par défaut, RIEN n'est réellement émis tant que l'école n'a pas activé l'envoi
SMS ET renseigné une passerelle. Le mode simulation journalise tout sans rien
envoyer — c'est là que l'on vérifie ses textes avant de les adresser à des
centaines de familles.
"""
from django.core.management.base import BaseCommand, CommandError

from apps.eleves.rappels import envoyer_rappels
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Envoie les rappels de paiement du mois aux familles en retard"

    def add_arguments(self, parser):
        parser.add_argument('--tenant', help="Code ou nom de l'école (défaut : toutes)")
        parser.add_argument('--forcer', action='store_true',
                            help='Envoyer même hors de la fenêtre de rappel')
        parser.add_argument('--simuler', action='store_true',
                            help="N'émettre aucun SMS, quel que soit le réglage")

    def handle(self, *args, **opts):
        qs = Tenant.objects.all()
        if arg := opts.get('tenant'):
            qs = (qs.filter(code_etablissement__iexact=arg)
                  or qs.filter(nom__icontains=arg))
            if not qs:
                raise CommandError(f"École introuvable : {arg}")

        total = {'envoyes': 0, 'simules': 0, 'echecs': 0, 'ignores': 0}
        for tenant in qs:
            exercice = Exercice.objects.filter(
                tenant=tenant, cloture=False).order_by('-date_debut').first()
            if not exercice:
                continue

            if opts['simuler']:
                # Neutralise l'envoi réel sans toucher au réglage enregistré :
                # l'objet n'est pas sauvegardé.
                tenant.sms_actif = False

            rapport = envoyer_rappels(tenant, exercice, forcer=opts['forcer'])
            if motif := rapport.get('motif'):
                self.stdout.write(f"{tenant.nom} — {motif}")
                continue

            for cle in total:
                total[cle] += rapport[cle]
            mode = 'ENVOI RÉEL' if rapport['reel'] else 'simulation'
            self.stdout.write(
                f"{tenant.nom} [{mode}] période {rapport['periode']} : "
                f"{rapport['envoyes']} envoyé(s), {rapport['simules']} simulé(s), "
                f"{rapport['echecs']} échec(s), {rapport['ignores']} ignoré(s)")
            for ligne in rapport['lignes']:
                if ligne['statut'] in ('ECHEC', 'SANS_CONTACT'):
                    self.stdout.write(self.style.WARNING(
                        f"   ⚠ {ligne['nom_complet']} — {ligne['statut']} "
                        f"{ligne.get('detail', '')}"))

        self.stdout.write(self.style.SUCCESS(
            f"\nTotal : {total['envoyes']} envoyé(s), {total['simules']} simulé(s), "
            f"{total['echecs']} échec(s), {total['ignores']} ignoré(s)."))
