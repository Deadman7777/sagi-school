"""API sauvegarde cloud.

Côté poste local (mode Electron) :
  GET  /api/sauvegarde/statut/     → dernière sauvegarde + dumps locaux
  POST /api/sauvegarde/declencher/ → lance dump + envoi immédiatement

Côté serveur HADY GESMAN (mode cloud) :
  POST /api/sauvegarde/recevoir/   → reçoit le dump d'une école locale,
       authentifié par la signature de la clé de licence (en-tête
       X-Cle-Licence), stocké sous SAGI_BACKUPS_DIR/<école>/, rétention 30.
"""
import base64
import hashlib
import os
import re
from datetime import datetime

from django.conf import settings
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsTenantMember

from .service import (executer_sauvegarde, lire_statut, lister_dumps_locaux,
                      validation_cle)

TAILLE_MAX = 200 * 1024 * 1024          # 200 Mo — très large pour ces bases
RETENTION_CLOUD = 30


class StatutSauvegardeView(APIView):
    permission_classes = [IsAuthenticated, IsTenantMember]

    def get(self, request):
        dumps = lister_dumps_locaux()
        return Response({
            'statut': lire_statut(),
            'nb_dumps_locaux': len(dumps),
            'dernier_dump_local': os.path.basename(dumps[-1]) if dumps else None,
        })


class DeclencherSauvegardeView(APIView):
    permission_classes = [IsAuthenticated, IsTenantMember]

    def post(self, request):
        statut = executer_sauvegarde()
        code = 200 if statut['statut'] == 'OK' else 502
        return Response(statut, status=code)


class RecevoirSauvegardeView(APIView):
    """Réception d'un dump depuis une installation locale. AllowAny : la
    machine émettrice n'a pas de compte sur le cloud — l'authentification
    est la signature de la clé de licence, vérifiable sans état."""
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        cle = request.headers.get('X-Cle-Licence', '')
        if not validation_cle(cle):
            return Response({'detail': 'Clé de licence invalide.'}, status=403)

        corps = request.body
        if not corps:
            return Response({'detail': 'Corps vide.'}, status=400)
        if len(corps) > TAILLE_MAX:
            return Response({'detail': 'Sauvegarde trop volumineuse.'}, status=413)

        empreinte = request.headers.get('X-Empreinte', '')
        if empreinte and hashlib.sha256(corps).hexdigest() != empreinte:
            return Response({'detail': 'Empreinte SHA-256 invalide (transfert corrompu).'},
                            status=400)

        # Dossier par école : nom lisible + hash de la clé (unicité stable)
        try:
            nom = base64.b64decode(request.headers.get('X-Ecole-B64', '')).decode('utf-8')
        except Exception:
            nom = ''
        slug = re.sub(r'[^a-zA-Z0-9_-]+', '-', nom).strip('-')[:40] or 'ecole'
        slug = f"{slug}-{hashlib.sha256(cle.encode()).hexdigest()[:8]}"

        dossier = os.path.join(str(settings.SAGI_BACKUPS_DIR), slug)
        os.makedirs(dossier, exist_ok=True)

        # Horodatage serveur — on ne fait pas confiance au nom client
        fichier = f"sagi_{datetime.now().strftime('%Y%m%d_%H%M%S')}.dump"
        with open(os.path.join(dossier, fichier), 'wb') as f:
            f.write(corps)

        # Rétention : garder les RETENTION_CLOUD plus récents
        dumps = sorted(d for d in os.listdir(dossier) if d.endswith('.dump'))
        for ancien in dumps[:-RETENTION_CLOUD]:
            try:
                os.remove(os.path.join(dossier, ancien))
            except OSError:
                pass

        return Response({'success': True, 'fichier': fichier,
                         'conservees': min(len(dumps), RETENTION_CLOUD)})
