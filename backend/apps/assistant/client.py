"""L'appel au modèle. Tout ce qui touche à Anthropic passe par ici.

Trois choses méritent d'être expliquées, parce qu'elles ne se devinent pas à la
lecture du code.

**La clé d'API ne quitte jamais le serveur.** Elle est lue dans la
configuration Django et n'apparaît dans aucune réponse d'API. Le navigateur
parle à SAGI SCHOOL, SAGI SCHOOL parle à Anthropic. Une clé posée dans le
frontend serait lisible par n'importe quel utilisateur de n'importe quelle
école.

**Le corpus est mis en cache une heure.** Il fait 28 000 jetons et ne change
jamais entre deux déploiements : le payer intégralement à chaque question
serait absurde. Le point de cache est posé sur le bloc système, qui est le
préfixe commun à toutes les conversations de toutes les écoles. D'où la règle
appliquée dans `prompt.py` : aucune donnée variable dans le système.

**Le contexte de l'utilisateur est un message, pas du système.** Le nom de
l'école, la licence, le rôle et la date changent à chaque conversation. Placés
dans le prompt système, ils feraient tomber le cache pour tout le monde ; placés
en tête des messages, ils arrivent après le préfixe mis en cache.
"""
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

MODELE = 'claude-opus-5'

# Assez pour un contrat ou une longue explication comptable, pas assez pour
# partir en vrille. La réflexion du modèle est comptée dans ce plafond.
MAX_JETONS = 16000

# `medium` plutôt que le défaut `high` : sur ce modèle les niveaux bas sont
# étonnamment solides, et un assistant conversationnel se juge autant à sa
# latence qu'à sa profondeur. À remonter si les réponses comptables manquent
# de rigueur — c'est le premier réglage à tester, pas le prompt.
EFFORT = 'medium'


class AssistantIndisponible(Exception):
    """Levée quand l'assistant ne peut pas répondre — et pourquoi.

    Le message est destiné à l'utilisateur final : il doit être compréhensible
    par une secrétaire d'école, pas par un développeur.
    """


def _client():
    cle = getattr(settings, 'ANTHROPIC_API_KEY', '') or ''
    if not cle:
        raise AssistantIndisponible(
            "L'assistant n'est pas configuré sur cette installation. "
            "Contactez HADY GESMAN pour l'activer."
        )
    try:
        import anthropic
    except ImportError:
        raise AssistantIndisponible(
            "L'assistant n'est pas disponible sur cette installation."
        )
    return anthropic.Anthropic(api_key=cle)


def contexte_utilisateur(user, tenant, licence=None):
    """Ce que SAMA sait de son interlocuteur avant qu'il ait parlé.

    Sans cela, l'assistant traite un client comme un inconnu et lui redemande
    le nom de son école — ce que l'application affiche déjà en haut de l'écran.
    """
    from datetime import date

    lignes = [
        "Contexte de cette conversation (ne le redemande pas à l'utilisateur) :",
        f"- Date du jour : {date.today():%d/%m/%Y}",
    ]
    if tenant:
        lignes.append(f"- Établissement : {tenant.nom}"
                      + (f" — {tenant.ville}" if getattr(tenant, 'ville', '') else ''))
    if licence:
        libelles = dict(licence.TYPE_CHOICES)
        lignes.append(f"- Licence : {libelles.get(licence.type, licence.type)} "
                      f"({licence.statut})")
    if user:
        role = dict(getattr(user, 'ROLE_CHOICES', [])).get(user.role, user.role)
        nom = ' '.join(p for p in (user.prenom, user.nom) if p) or user.email
        lignes.append(f"- Interlocuteur : {nom} — {role}")
    lignes.append(
        "\nCette personne utilise déjà SAGI SCHOOL : c'est un client, pas un "
        "prospect. Sauf si elle interroge explicitement une autre licence ou "
        "une offre, réponds-lui en support, en formation ou en conseil."
    )
    return "\n".join(lignes)


def repondre(messages, systeme):
    """Interroge le modèle et rend la réponse par morceaux, au fil de l'eau.

    Rend des tuples ('texte', str) pendant la génération, puis un unique
    ('fin', dict) portant la consommation. Le flux est indispensable : une
    réponse comptable détaillée met plusieurs secondes à s'écrire, et une page
    figée pendant ce temps passe pour une panne.
    """
    client = _client()
    try:
        with client.beta.messages.stream(
            model=MODELE,
            max_tokens=MAX_JETONS,
            betas=['server-side-fallback-2026-07-01'],
            # Une école qui pose une question légitime ne doit pas se heurter à
            # un refus de classificateur : la requête est alors reprise
            # automatiquement par un autre modèle, dans le même appel.
            fallbacks='default',
            output_config={'effort': EFFORT},
            system=[{
                'type': 'text',
                'text': systeme,
                # Une heure : le corpus est identique pour toutes les écoles,
                # donc une question posée à Dakar réchauffe le cache de Thiès.
                'cache_control': {'type': 'ephemeral', 'ttl': '1h'},
            }],
            messages=messages,
        ) as flux:
            for texte in flux.text_stream:
                yield ('texte', texte)
            final = flux.get_final_message()
    except AssistantIndisponible:
        raise
    except Exception as e:                       # réseau, quota, panne amont
        logger.warning('SAMA — appel modèle en échec : %s', e)
        raise AssistantIndisponible(
            "L'assistant n'est pas joignable pour le moment. Vérifiez votre "
            "connexion Internet, puis réessayez dans un instant."
        )

    # Un refus de classificateur revient en HTTP 200 : sans ce contrôle, on
    # afficherait une réponse vide sans savoir pourquoi.
    if final.stop_reason == 'refusal':
        raise AssistantIndisponible(
            "Je ne peux pas traiter cette demande. Reformulez-la, ou "
            "adressez-vous directement à l'équipe HADY GESMAN."
        )

    u = final.usage
    yield ('fin', {
        'jetons_entree': u.input_tokens,
        'jetons_sortie': u.output_tokens,
        'jetons_cache':  getattr(u, 'cache_read_input_tokens', 0) or 0,
        'tronque':       final.stop_reason == 'max_tokens',
    })
