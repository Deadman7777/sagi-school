"""Vérifie que le catalogue lu par SAMA dit la vérité sur le logiciel.

**Pourquoi une commande et pas un test.** `tests_catalogue.py` couvre déjà ces
règles, mais le lanceur de tests de Django crée une base de données — ce que
l'utilisateur applicatif n'a pas le droit de faire en production. Or c'est
précisément en production qu'on veut pouvoir répondre à la question « qu'est-ce
que l'assistant raconte à nos prospects, là, maintenant ? ».

Cette commande assemble le corpus exactement comme le fait le service, puis
compare fiche par fiche ce que le catalogue annonce à ce que `MODULES_PAR_TYPE`
ouvre réellement. Elle ne touche à rien, n'appelle aucun modèle et ne consomme
aucun budget.

    python manage.py verifier_catalogue --settings=config.settings.cloud

Sortie non nulle en cas d'écart : utilisable après un déploiement, ou dans une
intégration continue.
"""
import re

from django.core.management.base import BaseCommand

from apps.assistant.connaissance import corpus
from apps.assistant.perimetre import modules_de
from apps.licences.models import Licence

# La fonctionnalité que le catalogue promettait sans qu'elle existe. Elle doit
# rester dans la liste des non-fonctionnalités — sans elle, un prospect qui
# pose la question n'obtient qu'un silence, que le modèle est tenté de combler
# — mais ne jamais reparaître dans une fiche de licence.
# Singulier ET pluriel : la première version de ce contrôle cherchait
# « emploi du temps » et laissait passer « Gestion des emplois du temps ».
FANTOME = re.compile(r'emplois? du temps', re.I)
DEMENTI = 'aucune génération ni gestion'


def _bloc(texte, libelle):
    """Le passage consacré à une licence, borné à la suivante.

    La dernière licence n'est suivie d'aucune autre : la section des services
    lui sert de borne, faute de quoi le bloc avale la moitié du document.
    """
    marqueur = f'--- Licence {libelle} '
    if marqueur not in texte:
        return None
    debut = texte.index(marqueur)
    fins = [p for p in (texte.find('--- Licence ', debut + 1),
                        texte.find('SERVICES DE DÉPLOIEMENT', debut)) if p != -1]
    return texte[debut:min(fins)] if fins else texte[debut:]


class Command(BaseCommand):
    help = "Compare le catalogue lu par l'assistant au périmètre réel des licences."

    def handle(self, *args, **options):
        texte = corpus()
        ecarts = 0

        self.stdout.write(f'Corpus public : {len(texte)} caractères, '
                          f'environ {len(texte) // 4} jetons\n')

        blocs = {}
        for code, libelle in Licence.TYPE_CHOICES:
            bloc = _bloc(texte, libelle)
            if bloc is None:
                ecarts += 1
                self.stdout.write(self.style.ERROR(
                    f'ÉCART {libelle:16} aucune fiche dans le corpus'))
                continue
            blocs[libelle] = bloc

            # `[^:\n]+` et non `[^:]+` : sans la borne de ligne, la capture
            # déborde sur tout le reste du document.
            annonces = re.findall(r'^ *- ([^:\n]+) :', bloc, re.M)
            attendus = [nom for nom, _ in modules_de(code)]

            if annonces == attendus:
                self.stdout.write(
                    f'OK    {libelle:16} {len(annonces):2} modules, conformes au code')
            else:
                ecarts += 1
                self.stdout.write(self.style.ERROR(f'ÉCART {libelle:16}'))
                self.stdout.write(f'      annoncés : {annonces}')
                self.stdout.write(f'      attendus : {attendus}')

        fautives = [lib for lib, b in blocs.items() if FANTOME.search(b)]
        if fautives:
            ecarts += 1
            self.stdout.write(self.style.ERROR(
                f'\nÉCART emplois du temps annoncés sur : {", ".join(fautives)}'))
        else:
            self.stdout.write('\nOK    aucune licence n’annonce les emplois du temps')

        if DEMENTI in texte:
            self.stdout.write(
                'OK    la liste « ce que le logiciel ne fait pas » est transmise')
        else:
            ecarts += 1
            self.stdout.write(self.style.ERROR(
                'ÉCART la liste des non-fonctionnalités a disparu du corpus'))

        if ecarts:
            self.stderr.write(self.style.ERROR(
                f'\n{ecarts} écart(s). Régénérer avec `manage.py generer_catalogue`, '
                'puis commiter le corpus.'))
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS(
            '\nLe catalogue lu par l’assistant est conforme au logiciel.'))
