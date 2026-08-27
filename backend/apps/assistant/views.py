"""L'API publique de SAMA, pour le site vitrine sagi-school.com.

**Aucune authentification.** C'est la nature du service : un visiteur qui
découvre SAGI SCHOOL n'a pas de compte, et lui en demander un reviendrait à ne
parler qu'à ceux qui sont déjà clients. Ce que l'ouverture retire en contrôle
d'accès, `garde_fous` le rend en bornes de dépense — c'est le vrai sujet ici,
pas la confidentialité : le corpus remis au modèle est public par construction
(voir `connaissance.py`).

**Le visiteur ne choisit pas sa conversation.** L'identifiant rendu au début du
flux permet de poursuivre le fil ; il ne permet pas de lire celui d'un autre —
`retrieve` et `list` n'existent pas sur cette API. Un identifiant deviné ne
donne accès à rien, seulement à la possibilité d'écrire à la suite, ce que les
mêmes bornes encadrent.

**Deux points d'entrée seulement** : l'état du service, et l'envoi d'un message.
Tout le reste — historique, suppression, titres — appartenait à la version
interne et n'a pas de sens pour un visiteur de passage.
"""
import json
import logging

from django.db import transaction
from django.http import StreamingHttpResponse
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .client import AssistantIndisponible, cout_fcfa, repondre
from .garde_fous import (LimiteAtteinte, cle_visiteur, conversation_est_au_bout,
                         enregistrer_consommation, etat_budget, origine,
                         verifier_avant_message)
from .models import Conversation, Message
from .outils import MAX_APPELS_PAR_TOUR, OUTILS, definition_outil
from .prompt import prompt_systeme

logger = logging.getLogger(__name__)

# Longueur d'une question posée dans une fenêtre de discussion. L'ancienne
# limite — 20 000 caractères — venait de l'application, où un comptable pouvait
# coller un extrait de grand livre. Ici, un message démesuré n'est pas un
# usage, c'est une façon de faire grossir la facture.
MAX_CARACTERES = 2000


class MessageThrottle(AnonRateThrottle):
    """Première barrière, en amont des plafonds de dépense.

    Elle ne protège pas le budget — c'est le rôle de `garde_fous` — mais le
    serveur : sans elle, un client automatisé ouvre autant de flux simultanés
    qu'il veut, et chacun mobilise un processus pendant plusieurs secondes.

    Elle s'appuie sur le cache de Django, qui est ici local à chaque processus :
    avec quatre `gunicorn`, un même visiteur dispose en pratique de quatre fois
    ce quota. C'est assumé — la borne qui compte est en base, dans
    `garde_fous`, et celle-là est exacte.
    """
    scope = 'sama'
    rate = '20/hour'


class EtatView(APIView):
    """GET /api/assistant/etat/ — le site doit-il afficher l'assistant ?

    Une installation sans clé, ou un service suspendu par le coupe-circuit, ne
    doit pas montrer une fenêtre de discussion qui ne répondra jamais. Mieux
    vaut aucun bouton qu'un bouton mort.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        from django.conf import settings
        budget = etat_budget()
        return Response({
            'disponible': bool(getattr(settings, 'ANTHROPIC_API_KEY', ''))
                          and not budget['suspendu'],
        })


class MessageView(APIView):
    """POST /api/assistant/message/ — envoie un message, diffuse la réponse.

    Attend {"contenu": "...", "conversation": "<id>"} — sans identifiant, une
    conversation est ouverte. Répond en **flux** (Server-Sent Events) : le texte
    s'affiche à mesure qu'il s'écrit.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [MessageThrottle]

    def post(self, request):
        contenu = (request.data.get('contenu') or '').strip()
        if not contenu:
            return Response({'error': 'Message vide.'}, status=400)
        if len(contenu) > MAX_CARACTERES:
            return Response(
                {'error': "Votre message est trop long. Résumez votre question "
                          "en quelques phrases."}, status=400)

        conv = None
        if cid := request.data.get('conversation'):
            # Restreint au visiteur : un identifiant récupéré ailleurs ne
            # permet pas d'écrire dans le fil de quelqu'un d'autre.
            conv = Conversation.objects.filter(
                pk=cid, cle_visiteur=cle_visiteur(request)).first()

        try:
            verifier_avant_message(request, conv)
        except LimiteAtteinte as e:
            logger.info('SAMA — refus : %s', e.raison)
            return Response({'error': str(e), 'raison': e.raison}, status=429)

        nouvelle = conv is None
        if nouvelle:
            conv = Conversation.objects.create(
                cle_visiteur=cle_visiteur(request), origine=origine(request),
                # Le titre par défaut est la question elle-même : c'est ce qui
                # rend un échange reconnaissable dans le suivi commercial.
                titre=contenu[:80] + ('…' if len(contenu) > 80 else ''))

        Message.objects.create(conversation=conv, role='user', contenu=contenu)

        messages = [{'role': m.role, 'content': m.contenu}
                    for m in conv.messages.all()]

        # Les blocs d'appel d'outil ne sont pas conservés d'un tour à l'autre :
        # l'historique remis au modèle reste du texte, donc court. Sans rappel,
        # SAMA rouvrirait une fiche déjà transmise à chaque message. La note est
        # jointe au dernier message du visiteur — après le point de cache, elle
        # ne coûte rien au préfixe.
        if conv.prospect_id:
            messages[-1]['content'] = (
                "[Note du serveur : la situation de cet établissement a déjà "
                "été transmise à l'équipe commerciale. N'appelle "
                f"{definition_outil()['name']} que pour signaler une "
                "information NOUVELLE, jamais pour retransmettre la même.]\n\n"
                f"{messages[-1]['content']}")

        return StreamingHttpResponse(
            self._diffuser(conv, messages, nouvelle),
            content_type='text/event-stream',
            headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
        )

    def _diffuser(self, conv, messages, nouvelle):
        def evenement(type_, donnees):
            return f'data: {json.dumps({"type": type_, **donnees}, ensure_ascii=False)}\n\n'

        yield evenement('debut', {'conversation': str(conv.id)})

        def executer_outil(nom, donnees):
            fonction = OUTILS.get(nom)
            if fonction is None:                 # outil inconnu : ne pas mentir
                return "Cet outil n'existe pas. Réponds sans l'utiliser."
            texte, _ = fonction(donnees, conversation=conv)
            return texte

        morceaux, usage = [], {}
        try:
            for genre, charge in repondre(
                    messages, prompt_systeme(),
                    outils=[definition_outil()],
                    executer_outil=executer_outil,
                    max_tours_outil=MAX_APPELS_PAR_TOUR):
                if genre == 'texte':
                    morceaux.append(charge)
                    yield evenement('texte', {'texte': charge})
                elif genre == 'outil':
                    # Le site peut afficher « transmission à l'équipe… » : un
                    # silence de plusieurs secondes pendant l'enregistrement
                    # passerait pour une panne.
                    yield evenement('outil', {'nom': charge})
                else:
                    usage = charge
        except AssistantIndisponible as e:
            yield evenement('erreur', {'message': str(e)})
            return
        except Exception:                     # ne jamais rompre le flux nu
            logger.exception('SAMA — erreur inattendue pendant la diffusion')
            yield evenement('erreur', {'message':
                            "Une erreur est survenue. Réessayez dans un instant."})
            return

        # La réponse n'est enregistrée qu'une fois complète : un flux
        # interrompu ne doit pas laisser un demi-message dans l'historique.
        reponse = ''.join(morceaux)
        if reponse:
            cout = cout_fcfa(usage)
            with transaction.atomic():
                Message.objects.create(
                    conversation=conv, role='assistant', contenu=reponse,
                    jetons_entree=usage.get('jetons_entree', 0),
                    jetons_sortie=usage.get('jetons_sortie', 0),
                    jetons_cache_lecture=usage.get('jetons_cache_lecture', 0),
                    jetons_cache_ecriture=usage.get('jetons_cache_ecriture', 0),
                    cout_fcfa=cout)
                conv.save(update_fields=['updated_at'])
            # Hors de la transaction du message : le compteur du jour est
            # partagé par tous les visiteurs, et le tenir verrouillé pendant
            # l'écriture d'un message sérialiserait toutes les conversations.
            enregistrer_consommation(usage, cout, nouvelle_conversation=nouvelle)

            # La borne atteinte est inscrite sur la conversation : le prochain
            # message est refusé sans avoir à recompter, et le suivi commercial
            # voit qu'un visiteur est allé au bout de ce qui lui était offert.
            if conversation_est_au_bout(conv):
                conv.close = True
                conv.save(update_fields=['close', 'updated_at'])

        yield evenement('fin', {'tronque': usage.get('tronque', False)})
