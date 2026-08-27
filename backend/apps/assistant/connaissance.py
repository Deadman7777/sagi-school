"""La mémoire documentaire de SAMA : ce qu'il a le droit d'affirmer.

**Le corpus est public, et il l'est par construction.** SAMA vit désormais sur
sagi-school.com, ouvert à tous. Or un assistant ne consulte pas une base de
données à laquelle il appliquerait des droits d'accès : les documents qu'on lui
confie sont dans son champ d'attention pendant toute la conversation, et rien
dans sa conception ne lui permet de retenir une information tout en refusant de
la restituer. Lui demander de se taire est une consigne, pas une serrure — il
suffit d'insister ou de reformuler.

Les documents confidentiels ne lui sont donc pas remis. Pas « masqués », pas
« réservés à certains visiteurs » : **absents**. `CONFIDENTIELS` ci-dessous
n'est pas une liste noire appliquée à l'exécution, c'est la trace écrite de ce
qui a été volontairement laissé de côté, et `corpus()` ne sait assembler que
`PUBLICS`.

Ce que le prospect perd : rien. Il n'a jamais eu besoin de lire nos modèles de
contrat pour savoir ce que fait le logiciel et ce qu'il coûte. Ce qu'il gagne
viendra plus tard, quand l'assistant conduira le diagnostic et laissera nos
serveurs produire le devis — avec les montants du catalogue plutôt que ceux
d'une mémoire.

**Ces fichiers ne partent pas dans l'installeur Windows.** Le dossier
`connaissances/` est exclu du paquet Electron (`electron/package.json`,
`extraResources`) : il était jusqu'ici recopié sur le disque de chaque école
cliente, documents confidentiels compris. Aucune installation locale ne les lit
— l'assistant qui s'en sert vit sur le site vitrine, côté serveur. Un document
déposé ici est donc lisible par nos serveurs, jamais par un client.

Le corpus public tient en 12 000 jetons environ. C'est assez petit pour être
remis EN ENTIER au modèle à chaque conversation, et c'est une décision
d'architecture, pas un raccourci. L'alternative habituelle est la recherche
documentaire : découper, indexer, ne remonter que les passages jugés pertinents.
Elle coûte une base vectorielle, un ré-indexage à chaque mise à jour, et une
classe entière de pannes — le passage qui contenait le tarif n'a pas été retenu,
et l'assistant répond « je ne sais pas » sur une information qu'il possède. Sur
un corpus de cette taille, tout donner supprime le problème au lieu de le gérer.

Le corpus est donc constant. Il est mis en cache côté Anthropic : la première
question d'un visiteur le paie, les suivantes le lisent à un dixième du prix. Il
ne doit donc contenir RIEN de variable — ni date du jour, ni identifiant de
session : un seul octet qui change invalide le cache pour tout le monde.
"""
from functools import lru_cache
from pathlib import Path

DOSSIER = Path(__file__).parent / 'connaissances'

# Ordre de priorité imposé par la direction. Il compte doublement : c'est
# l'ordre de lecture annoncé à l'assistant en cas de contradiction, et l'ordre
# physique dans le contexte — ce qui est lu en dernier pèse davantage.
PUBLICS = [
    ('HADY_GESMAN_Presentation_Institutionnelle 2026',
     "Présentation institutionnelle — identité, mission, métiers"),
    ('CATALOGUE_OFFICIEL_DES_OFFRES_ET_TARIFS',
     "Catalogue officiel des offres et tarifs 2026-2027"),
    ('ANNEXE_A_CONDITIONS_COMMERCIALES_LICENCES',
     "Conditions commerciales des licences"),
]

# Ce qui n'est PAS remis au modèle, et pourquoi. Ces fichiers restent dans
# `connaissances/` : ils servent de modèles aux documents que nos serveurs
# produiront (étape 4), où ils ne passent jamais par le modèle. Les ajouter ici
# les mettrait en ligne — voir l'en-tête de ce module.
CONFIDENTIELS = [
    ('HG-DEV-2026-0001_Devis_Commercial_SAGI_SCHOOL',
     "porte la mention « Confidentiel » — structure de prix et remises"),
    ('ANNEXE_02_FICHE_DIAGNOSTIC_CLIENT',
     "porte la mention « Confidentiel » — notre méthode de qualification"),
    ('ANNEXE_07_PV_INSTALLATION_MISE_EN_SERVICE',
     "porte la mention « Confidentiel »"),
    ('HG-OPS-003-V01_Fiche_Formation_Utilisateur',
     "porte la mention « Confidentiel »"),
    ('CONTRAT_PRESTATION_SERVICES_SAGI_SCHOOL',
     "clause de non-divulgation — engagements et limites de responsabilité"),
    ('ANNEXE_04_CONTRAT_PRESTATION_SERVICES',
     "clause de non-divulgation"),
    ('ANNEXE_01_FICHE_PROSPECT_COMMERCIAL',
     "méthode commerciale interne"),
    ('ANNEXE_05_BON_DE_COMMANDE_CLIENT', "modèle interne"),
    ('ANNEXE_06_FICHE_ONBOARDING_CLIENT', "modèle interne"),
    ('BON_DE_COMMANDE_ET_BULLETIN_DE_SOUSCRIPTION', "modèle interne"),
]


def _nettoyer(texte):
    """Les PDF extraits « en colonnes » arrivent avec une indentation massive
    qui ne porte aucun sens et gonfle le corpus d'un tiers. On la retire, on
    écrase les lignes vides en série, on garde le reste tel quel."""
    lignes, vides = [], 0
    for ligne in texte.splitlines():
        ligne = ligne.rstrip()
        if not ligne.strip():
            vides += 1
            if vides <= 1:
                lignes.append('')
            continue
        vides = 0
        lignes.append(ligne.strip() if ligne.startswith('    ') else ligne)
    return '\n'.join(lignes).strip()


@lru_cache(maxsize=1)
def corpus():
    """Le corpus PUBLIC, assemblé une fois pour la vie du processus.

    Tout ce qui sort d'ici peut être lu par n'importe quel visiteur du site :
    c'est la seule lecture correcte de ce que devient un document remis à un
    modèle.

    Le périmètre issu du code est placé EN DERNIER, après les documents
    commerciaux : c'est le passage le plus proche de la question posée, et c'est
    lui qui doit l'emporter quand une plaquette annonce une fonctionnalité que
    le logiciel n'a pas.
    """
    from .perimetre import texte_perimetre

    morceaux = ["# Documents publics HADY GESMAN\n"]
    for nom, titre in PUBLICS:
        fichier = DOSSIER / f'{nom}.txt'
        if not fichier.exists():          # document retiré : on n'invente pas
            continue
        morceaux.append(f"\n\n{'=' * 70}\n## {titre}\n{'=' * 70}\n")
        morceaux.append(_nettoyer(fichier.read_text(encoding='utf-8')))

    morceaux.append(f"\n\n{'=' * 70}\n{texte_perimetre()}")
    return ''.join(morceaux)
