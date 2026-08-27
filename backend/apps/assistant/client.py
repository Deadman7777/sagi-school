"""L'appel au modèle. Tout ce qui touche à Anthropic passe par ici.

**La clé d'API ne quitte jamais le serveur.** Elle est lue dans la
configuration Django et n'apparaît dans aucune réponse d'API. Le navigateur du
visiteur parle à nos serveurs, nos serveurs parlent à Anthropic. Une clé posée
dans le site vitrine serait lisible par n'importe qui.

**Le modèle est Haiku 4.5, et c'est un choix chiffré.** Les questions posées sur
un site vitrine sont commerciales — nos offres, nos tarifs, nos délais — et non
des raisonnements comptables sur un dossier réel. Sur ce registre, Haiku répond
aussi bien qu'Opus pour environ un cinquième du prix. À l'intérieur de
l'application, où SAMA devait raisonner sur de la comptabilité SYSCOHADA, le
choix était l'inverse ; le site n'est pas ce contexte.

**Le cache est en cinq minutes, pas en une heure.** Un cache d'une heure est
réécrit toutes les heures qu'il soit relu ou non. Dans l'application, le trafic
continu de plusieurs écoles rendait cette réécriture largement rentable. Sur un
site vitrine peu fréquenté, elle se paierait dans le vide — jusqu'à vingt-quatre
réécritures quotidiennes du corpus pour quelques conversations. La fenêtre de
cinq minutes couvre les tours d'une même conversation, ce qui est exactement le
besoin ici. À repasser en une heure le jour où le trafic dépasse environ trois
conversations par heure ; le coût mesuré par `garde_fous` le dira.

**Ni `effort` ni réflexion adaptative.** Ces réglages n'existent pas sur
Haiku 4.5 : les passer ferait échouer la requête. Le paramétrage ci-dessous est
donc volontairement plus simple que celui de l'ancienne version, pas incomplet.
"""
import logging
from decimal import Decimal

from django.conf import settings

logger = logging.getLogger(__name__)

MODELE = 'claude-haiku-4-5'

# Une réponse de fenêtre de discussion, pas un rapport. Le prompt le demande
# déjà ; ce plafond garantit qu'un modèle bavard ne fait pas dériver la note.
MAX_JETONS = 2000

# Tarifs Anthropic pour Haiku 4.5, en dollars par million de jetons
# (relevés le 2026-08-27). L'écriture de cache coûte 1,25 × l'entrée sur la
# fenêtre de cinq minutes, la lecture 0,10 × — c'est tout l'intérêt du cache.
# À revoir en même temps que MODELE : ces nombres ne valent que pour lui.
TARIFS_USD_PAR_MJETONS = {
    'entree':         Decimal('1.00'),
    'sortie':         Decimal('5.00'),
    'cache_ecriture': Decimal('1.25'),
    'cache_lecture':  Decimal('0.10'),
}


class AssistantIndisponible(Exception):
    """Levée quand l'assistant ne peut pas répondre — et pourquoi.

    Le message est destiné au visiteur : il doit être compréhensible par le
    directeur d'un daara, pas par un développeur.
    """


def _client():
    cle = getattr(settings, 'ANTHROPIC_API_KEY', '') or ''
    if not cle:
        raise AssistantIndisponible(
            "L'assistant n'est pas disponible pour le moment. "
            "Écrivez-nous et nous vous répondrons directement."
        )
    try:
        import anthropic
    except ImportError:
        raise AssistantIndisponible(
            "L'assistant n'est pas disponible pour le moment."
        )
    return anthropic.Anthropic(api_key=cle)


def cout_fcfa(usage):
    """Ce que cet échange a coûté, en francs CFA.

    Prend le `usage` normalisé rendu par `repondre()`. Le calcul vit ici, avec
    les tarifs, et nulle part ailleurs : le coupe-circuit de `garde_fous` et
    l'écran de suivi doivent additionner exactement la même chose, sans quoi
    l'un couperait le service que l'autre déclare bon marché.
    """
    taux = Decimal(str(getattr(settings, 'SAMA_TAUX_USD_FCFA', 610)))
    dollars = sum(
        Decimal(usage.get(f'jetons_{poste}', 0) or 0)
        * prix / Decimal(1_000_000)
        for poste, prix in (
            ('entree',         TARIFS_USD_PAR_MJETONS['entree']),
            ('sortie',         TARIFS_USD_PAR_MJETONS['sortie']),
            ('cache_ecriture', TARIFS_USD_PAR_MJETONS['cache_ecriture']),
            ('cache_lecture',  TARIFS_USD_PAR_MJETONS['cache_lecture']),
        )
    )
    return (dollars * taux).quantize(Decimal('0.0001'))


def _cumuler(total, usage):
    """Additionne la consommation d'un tour à celle de l'échange.

    Un échange peut compter plusieurs allers-retours avec le modèle quand un
    outil est appelé : chacun se facture, et le plafond doit tous les voir.
    Ne sommer que le dernier sous-estimerait la dépense — dans le sens qui
    désarme le coupe-circuit.
    """
    total['jetons_entree']         += usage.input_tokens
    total['jetons_sortie']         += usage.output_tokens
    total['jetons_cache_lecture']  += getattr(usage, 'cache_read_input_tokens', 0) or 0
    total['jetons_cache_ecriture'] += getattr(usage, 'cache_creation_input_tokens', 0) or 0


def repondre(messages, systeme, outils=None, executer_outil=None,
             max_tours_outil=2):
    """Interroge le modèle et rend la réponse par morceaux, au fil de l'eau.

    Rend des tuples ('texte', str) pendant la génération, ('outil', str) quand
    un outil est exécuté, puis un unique ('fin', dict) portant la consommation
    de TOUT l'échange. Le flux n'est pas un confort : une réponse met plusieurs
    secondes à s'écrire, et une fenêtre figée pendant ce temps passe pour une
    panne — sur un site vitrine, le visiteur ferme l'onglet.

    **La boucle d'outils est écrite à la main** plutôt que confiée au
    `tool_runner` du SDK : celui-ci rend des messages complets, alors qu'il faut
    ici diffuser le texte à mesure qu'il s'écrit, y compris avant et après
    l'appel d'outil.

    `max_tours_outil` borne cette boucle. Un modèle qui rappelle indéfiniment le
    même outil est rare mais possible, et chaque tour renvoie tout le contexte :
    sans borne, une seule conversation peut coûter le budget d'une journée.
    """
    client = _client()
    fil = list(messages)
    total = {'jetons_entree': 0, 'jetons_sortie': 0,
             'jetons_cache_lecture': 0, 'jetons_cache_ecriture': 0}
    tours = 0

    while True:
        parametres = {
            'model': MODELE,
            'max_tokens': MAX_JETONS,
            'system': [{
                'type': 'text',
                'text': systeme,
                # Fenêtre par défaut : cinq minutes. Le corpus est identique
                # pour tous les visiteurs, donc une question posée à Dakar
                # réchauffe le cache de la suivante, d'où qu'elle vienne.
                'cache_control': {'type': 'ephemeral'},
            }],
            'messages': fil,
        }
        # Les outils sont rendus AVANT le bloc système : constants, ils font
        # partie du préfixe mis en cache. Une définition qui varierait d'un
        # appel à l'autre ferait tomber le cache pour tout le monde.
        if outils:
            parametres['tools'] = outils

        try:
            with client.messages.stream(**parametres) as flux:
                for texte in flux.text_stream:
                    yield ('texte', texte)
                final = flux.get_final_message()
        except AssistantIndisponible:
            raise
        except Exception as e:                   # réseau, quota, panne amont
            logger.warning('SAMA — appel modèle en échec : %s', e)
            raise AssistantIndisponible(
                "L'assistant n'est pas joignable pour le moment. Vérifiez votre "
                "connexion, puis réessayez dans un instant."
            )

        _cumuler(total, final.usage)

        # Un refus de classificateur reviendrait en HTTP 200 : sans ce contrôle
        # on afficherait une réponse vide sans savoir pourquoi. Le cas n'existe
        # pas sur Haiku 4.5 ; le garde reste pour le jour où MODELE changera.
        if getattr(final, 'stop_reason', None) == 'refusal':
            raise AssistantIndisponible(
                "Je ne peux pas traiter cette demande. Reformulez-la, ou "
                "adressez-vous directement à l'équipe HADY GESMAN."
            )

        appels = [bloc for bloc in final.content if bloc.type == 'tool_use']
        if not appels or executer_outil is None or tours >= max_tours_outil:
            break

        tours += 1
        fil.append({'role': 'assistant', 'content': final.content})
        resultats = []
        for appel in appels:
            # `appel.input` est déjà un dictionnaire : le SDK a fait l'analyse.
            # Ne jamais le traiter comme une chaîne — l'échappement JSON varie
            # d'un modèle à l'autre.
            resultats.append({
                'type': 'tool_result',
                'tool_use_id': appel.id,
                'content': executer_outil(appel.name, appel.input),
            })
            yield ('outil', appel.name)
        # Tous les résultats dans UN seul message : les séparer apprend au
        # modèle à ne plus appeler ses outils en parallèle.
        fil.append({'role': 'user', 'content': resultats})

    total['tronque'] = final.stop_reason == 'max_tokens'
    yield ('fin', total)
