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
        formule = {}
        if licence is not None:
            from .renouvellement import formule_demandee
            formule = formule_demandee(licence, {'mois': d.get('mois'), 'type': d.get('type_demande'),
                                                 'moyen_paiement': d.get('moyen_paiement'),
                                                 'reference_paiement': d.get('reference_paiement')})
        demande = DemandeRenouvellement.objects.create(
            **formule,
            tenant=licence.tenant if licence else None, licence=licence,
            ecole_nom=champ('ecole_nom') or 'École (installation locale)',
            cle_licence=cle, type_licence=champ('type_licence', 20), date_fin=date_fin,
            demandeur=champ('demandeur'), email_demandeur=champ('email_demandeur', 254),
            telephone=champ('telephone', 60), message=champ('message', 2000),
            origine='RELAIS', relayee=True,
        )
        ok, _ = notifier_par_courriel(demande)
        return Response({'recue': True, 'courriel_envoye': ok, 'reference': str(demande.id)})


class EtatDistantThrottle(AnonRateThrottle):
    rate = '120/hour'


class EtatDistantView(APIView):
    """L'état d'une licence et les réglages des alertes, pour une installation locale.

    Le poste de l'école y lit la date de fin que connaît le cloud : un
    renouvellement confirmé ici prolonge la licence locale à la consultation
    suivante (voir apps/licences/alertes.py). Ne révèle que la licence dont on
    présente la clé.
    """
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [EtatDistantThrottle]

    def post(self, request):
        from .alertes import config_publique
        cle = request.headers.get('X-Cle-Licence', '')
        if not validation_cle(cle):
            return Response({'detail': 'Clé de licence invalide.'}, status=403)
        licence = Licence.objects.filter(cle_licence=cle).first()
        return Response({
            'licence': {'date_fin': str(licence.date_fin), 'type': licence.type,
                        'statut': licence.statut} if licence else None,
            'config': config_publique(),
        })
