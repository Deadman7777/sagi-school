"""Où en est la dépense de SAMA — depuis le serveur, sans passer par l'admin.

Sur le cloud, vérifier une consommation ne doit pas demander d'ouvrir une
session d'administration dans un navigateur. Cette commande donne l'état en une
ligne de terminal :

    python manage.py sama_budget --settings=config.settings.cloud
"""
from django.core.management.base import BaseCommand

from apps.assistant.client import MAX_JETONS, MODELE
from apps.assistant.connaissance import corpus
from apps.assistant.garde_fous import etat_budget, historique


class Command(BaseCommand):
    help = "Affiche la consommation de l'assistant SAMA et l'état des plafonds."

    def add_arguments(self, parseur):
        parseur.add_argument('--jours', type=int, default=14,
                             help="Nombre de jours d'historique (défaut : 14).")

    def handle(self, *args, **options):
        etat = etat_budget()

        def francs(montant):
            return f'{montant:,.0f}'.replace(',', ' ') + ' F'

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('SAMA — configuration'))
        # La taille du corpus est l'autre moitié du coût : c'est elle qu'on
        # paie à chaque conversation, en écriture puis en lectures de cache.
        self.stdout.write(f"  Modèle      : {MODELE}"
                          f"   (réponse plafonnée à {MAX_JETONS} jetons)")
        self.stdout.write(f"  Corpus      : {len(corpus().split()):,} mots"
                          .replace(',', ' ') + " — remis en entier à chaque conversation")

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('SAMA — consommation'))
        self.stdout.write(f"  Aujourd'hui : {francs(etat['depense_jour']):>12}"
                          f"   / plafond {francs(etat['plafond_jour'])}")
        self.stdout.write(f"  Ce mois-ci  : {francs(etat['depense_mois']):>12}"
                          f"   / plafond {francs(etat['plafond_mois'])}"
                          f"   ({etat['part_mois']} %)")

        if etat['suspendu']:
            self.stdout.write(self.style.ERROR(
                '\n  SERVICE SUSPENDU — un plafond est atteint. Le site '
                "n'affiche plus l'assistant."))
        else:
            self.stdout.write(self.style.SUCCESS('\n  Service actif.'))

        lignes = historique(options['jours'])
        if not lignes:
            self.stdout.write('\n  Aucune consommation enregistrée.')
            return

        self.stdout.write('')
        self.stdout.write(f"  {'Jour':<12}{'Coût':>10}{'Convers.':>10}"
                          f"{'Messages':>10}{'Jetons sortie':>16}")
        for ligne in lignes:
            self.stdout.write(
                f"  {ligne.jour:%d/%m/%Y}  {francs(ligne.cout_fcfa):>10}"
                f"{ligne.nb_conversations:>10}{ligne.nb_messages:>10}"
                f"{ligne.jetons_sortie:>16,}".replace(',', ' '))
        self.stdout.write('')
