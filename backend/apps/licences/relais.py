"""Réception, sur le cloud, des demandes de renouvellement des installations locales.

Public (la machine de l'école n'a pas de compte cloud) : l'authentification est
la SIGNATURE de la clé de licence, vérifiable sans état — la même que pour les
sauvegardes. Limité en débit.
"""
import datetime

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.sauvegarde.service import validation_cle

from .models import DemandeRenouvellement, Licence
from .renouvellement import notifier_par_courriel


class RelaisThrottle(AnonRateThrottle):
    rate = '10/hour'


class RelaisRenouvellementView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [RelaisThrottle]

    def post(self, request):
        cle = request.headers.get('X-Cle-Licence', '')
        if not validation_cle(cle):
            return Response({'recue': False, 'detail': 'Clé de licence invalide.'}, status=403)
        d = request.data
        champ = lambda k, n=200: str(d.get(k, '') or '').strip()[:n]
        try:
            date_fin = datetime.date.fromisoformat(champ('date_fin', 10)) if champ('date_fin', 10) else None
        except ValueError:
            date_fin = None
        licence = Licence.objects.filter(cle_licence=cle).select_related('tenant').first()
        demande = DemandeRenouvellement.objects.create(
            tenant=licence.tenant if licence else None, licence=licence,
            ecole_nom=champ('ecole_nom') or 'École (installation locale)',
            cle_licence=cle, type_licence=champ('type_licence', 20), date_fin=date_fin,
            demandeur=champ('demandeur'), email_demandeur=champ('email_demandeur', 254),
            telephone=champ('telephone', 60), message=champ('message', 2000),
            origine='RELAIS', relayee=True,
        )
        ok, _ = notifier_par_courriel(demande)
        return Response({'recue': True, 'courriel_envoye': ok, 'reference': str(demande.id)})
