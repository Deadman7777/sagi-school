"""L'API de SAMA : lister, ouvrir, écrire.

L'envoi d'un message répond en **flux** (Server-Sent Events) : le texte
s'affiche au fur et à mesure. Une réponse comptable détaillée met plusieurs
secondes à s'écrire, et un écran figé pendant ce temps passe pour une panne.
"""
import json

from django.db import transaction
from django.http import StreamingHttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.tenant import get_tenant

from .client import AssistantIndisponible, contexte_utilisateur, repondre
from .models import Conversation, Message
from .prompt import prompt_systeme

# Au-delà, la conversation est repliée sur ses derniers tours. Une école qui
# discute une heure durant ne doit pas voir sa facture enfler à chaque message,
# ni buter sur la fenêtre de contexte.
MAX_TOURS = 40


class ConversationViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def _mes_conversations(self, request):
        return Conversation.objects.filter(
            tenant=get_tenant(request), utilisateur=request.user)

    def list(self, request):
        return Response([{
            'id':      str(c.id),
            'titre':   c.titre,
            'maj':     c.updated_at,
        } for c in self._mes_conversations(request)[:50]])

    def retrieve(self, request, pk=None):
        conv = self._mes_conversations(request).filter(pk=pk).first()
        if not conv:
            return Response({'error': 'Conversation introuvable.'}, status=404)
        return Response({
            'id':    str(conv.id),
            'titre': conv.titre,
            'messages': [{
                'role':    m.role,
                'contenu': m.contenu,
                'date':    m.created_at,
            } for m in conv.messages.all()],
        })

    def destroy(self, request, pk=None):
        conv = self._mes_conversations(request).filter(pk=pk).first()
        if not conv:
            return Response({'error': 'Conversation introuvable.'}, status=404)
        conv.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['get'], url_path='etat')
    def etat(self, request):
        """L'assistant est-il utilisable sur cette installation ?

        Une école en local sans accès Internet, ou une installation sans clé,
        ne doit pas voir un bouton qui ne répondra jamais. Mieux vaut aucune
        commande qu'une commande morte.
        """
        from django.conf import settings
        return Response({
            'disponible': bool(getattr(settings, 'ANTHROPIC_API_KEY', '')),
        })

    @action(detail=False, methods=['post'], url_path='message')
    def message(self, request):
        """Envoie un message et diffuse la réponse au fil de l'eau.

        Attend {"contenu": "...", "conversation": "<id>"} — sans identifiant,
        une conversation est ouverte.
        """
        tenant = get_tenant(request)
        contenu = (request.data.get('contenu') or '').strip()
        if not contenu:
            return Response({'error': 'Message vide.'}, status=400)
        if len(contenu) > 20000:
            return Response({'error': 'Message trop long.'}, status=400)

        conv = None
        if cid := request.data.get('conversation'):
            conv = self._mes_conversations(request).filter(pk=cid).first()
        if conv is None:
            conv = Conversation.objects.create(
                tenant=tenant, utilisateur=request.user,
                # Le titre par défaut est la question elle-même : c'est ce qui
                # permet de retrouver un échange dans la liste.
                titre=contenu[:80] + ('…' if len(contenu) > 80 else ''))

        Message.objects.create(tenant=tenant, conversation=conv,
                               role='user', contenu=contenu)

        # Le contexte de l'école ouvre la conversation, jamais le prompt
        # système : le système est mis en cache et doit rester identique pour
        # toutes les écoles (voir client.py).
        from apps.licences.models import Licence
        licence = Licence.objects.filter(tenant=tenant).first()
        entete = contexte_utilisateur(request.user, tenant, licence)

        tours = list(conv.messages.all())[-MAX_TOURS:]
        messages = [{'role': m.role, 'content': m.contenu} for m in tours]
        messages[0]['content'] = f"{entete}\n\n---\n\n{messages[0]['content']}"

        return StreamingHttpResponse(
            self._diffuser(tenant, conv, messages),
            content_type='text/event-stream',
            headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
        )

    def _diffuser(self, tenant, conv, messages):
        def evenement(type_, donnees):
            return f'data: {json.dumps({"type": type_, **donnees}, ensure_ascii=False)}\n\n'

        yield evenement('debut', {'conversation': str(conv.id), 'titre': conv.titre})

        morceaux, usage = [], {}
        try:
            for genre, charge in repondre(messages, prompt_systeme()):
                if genre == 'texte':
                    morceaux.append(charge)
                    yield evenement('texte', {'texte': charge})
                else:
                    usage = charge
        except AssistantIndisponible as e:
            yield evenement('erreur', {'message': str(e)})
            return
        except Exception:                     # ne jamais rompre le flux nu
            yield evenement('erreur', {'message':
                            "Une erreur inattendue est survenue. Réessayez."})
            return

        # La réponse n'est enregistrée qu'une fois complète : un flux
        # interrompu ne doit pas laisser un demi-message dans l'historique.
        reponse = ''.join(morceaux)
        if reponse:
            with transaction.atomic():
                Message.objects.create(
                    tenant=tenant, conversation=conv, role='assistant',
                    contenu=reponse,
                    jetons_entree=usage.get('jetons_entree', 0),
                    jetons_sortie=usage.get('jetons_sortie', 0),
                    jetons_cache=usage.get('jetons_cache', 0))
                conv.save(update_fields=['updated_at'])

        yield evenement('fin', {'tronque': usage.get('tronque', False)})
