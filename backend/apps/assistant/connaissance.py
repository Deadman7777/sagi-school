"""La mémoire documentaire de SAMA : ce qu'il a le droit d'affirmer.

Le corpus tient en 28 000 jetons environ. C'est petit — assez petit pour être
remis EN ENTIER au modèle à chaque conversation, et c'est une décision
d'architecture, pas un raccourci.

L'alternative habituelle est la recherche documentaire : découper les documents,
les indexer, n'en remonter que les passages jugés pertinents. Elle coûte une
base vectorielle, un ré-indexage à chaque mise à jour, et une classe entière de
pannes — le passage qui contenait le tarif n'a pas été retenu, et l'assistant
répond « je ne sais pas » sur une information qu'il possède. Sur un corpus de
cette taille, tout donner supprime le problème au lieu de le gérer.

Le corpus est donc constant. Il est mis en cache côté Anthropic (une heure) :
la première question d'une école le paie, les suivantes le lisent à un dixième
du prix. Il ne doit donc contenir RIEN de variable — ni date du jour, ni nom
d'école, ni identifiant de session : un seul octet qui change invalide le cache
pour tout le monde.
"""
from functools import lru_cache
from pathlib import Path

DOSSIER = Path(__file__).parent / 'connaissances'

# Ordre de priorité imposé par la direction. Il compte doublement : c'est
# l'ordre de lecture annoncé à l'assistant en cas de contradiction, et l'ordre
# physique dans le contexte — ce qui est lu en dernier pèse davantage.
ORDRE = [
    ('HADY_GESMAN_Presentation_Institutionnelle 2026',
     "Présentation institutionnelle — identité, mission, métiers"),
    ('CATALOGUE_OFFICIEL_DES_OFFRES_ET_TARIFS',
     "Catalogue officiel des offres et tarifs 2026-2027"),
    ('ANNEXE_A_CONDITIONS_COMMERCIALES_LICENCES',
     "Conditions commerciales des licences"),
    ('CONTRAT_PRESTATION_SERVICES_SAGI_SCHOOL',
     "Contrat de prestation de services — modèle"),
    ('ANNEXE_04_CONTRAT_PRESTATION_SERVICES',
     "Annexe 4 — contrat de prestation de services"),
    ('HG-DEV-2026-0001_Devis_Commercial_SAGI_SCHOOL',
     "Devis commercial — modèle de référence"),
    ('BON_DE_COMMANDE_ET_BULLETIN_DE_SOUSCRIPTION',
     "Bon de commande et bulletin de souscription — modèle"),
    ('ANNEXE_05_BON_DE_COMMANDE_CLIENT',
     "Annexe 5 — bon de commande client"),
    ('ANNEXE_01_FICHE_PROSPECT_COMMERCIAL',
     "Annexe 1 — fiche prospect commercial"),
    ('ANNEXE_02_FICHE_DIAGNOSTIC_CLIENT',
     "Annexe 2 — fiche de diagnostic client"),
    ('ANNEXE_06_FICHE_ONBOARDING_CLIENT',
     "Annexe 6 — fiche d'accueil client"),
    ('ANNEXE_07_PV_INSTALLATION_MISE_EN_SERVICE',
     "Annexe 7 — PV d'installation et de mise en service"),
    ('HG-OPS-003-V01_Fiche_Formation_Utilisateur',
     "Fiche de formation utilisateur"),
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
    """Le corpus complet, assemblé une fois pour la vie du processus.

    Le périmètre issu du code est placé EN DERNIER, après tous les documents
    commerciaux : c'est le passage le plus proche de la question posée, et c'est
    lui qui doit l'emporter quand une plaquette annonce une fonctionnalité que
    le logiciel n'a pas.
    """
    from .perimetre import texte_perimetre

    morceaux = ["# Documents officiels HADY GESMAN\n"]
    for nom, titre in ORDRE:
        fichier = DOSSIER / f'{nom}.txt'
        if not fichier.exists():          # document retiré : on n'invente pas
            continue
        morceaux.append(f"\n\n{'=' * 70}\n## {titre}\n{'=' * 70}\n")
        morceaux.append(_nettoyer(fichier.read_text(encoding='utf-8')))

    morceaux.append(f"\n\n{'=' * 70}\n{texte_perimetre()}")
    return ''.join(morceaux)


def taille_corpus():
    """Nombre de mots — pour la commande de diagnostic, pas pour le modèle."""
    return len(corpus().split())
