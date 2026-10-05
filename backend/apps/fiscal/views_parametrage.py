"""Paramétrage fiscal : profil de l'établissement, paramètres datés,
référentiel des obligations (voir apps/fiscal/models.py)."""
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsAdminEcole
from core.tenant import get_tenant

from .models import ObligationFiscale, ParametreFiscal, ProfilFiscal
from .moteur import profil_de


def _super_admin(request):
    return getattr(request.user, 'role', None) == 'SUPER_ADMIN'


class ProfilFiscalSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProfilFiscal
        exclude = ('tenant',)

    def validate_exonerations(self, valeur):
        if not isinstance(valeur, list):
            raise serializers.ValidationError('Liste attendue.')
        codes = set(ObligationFiscale.objects.values_list('code', flat=True))
        for i, e in enumerate(valeur, start=1):
            if (e.get('obligation') or '').upper() not in codes:
                raise serializers.ValidationError(f"Exonération {i} : obligation inconnue.")
            if not str(e.get('motif') or '').strip():
                raise serializers.ValidationError(f"Exonération {i} : motif obligatoire (texte, agrément…).")
            e['obligation'] = e['obligation'].upper()
        return valeur


class ProfilFiscalView(APIView):
    """GET/PATCH /fiscal/profil/ — le profil fiscal de l'établissement."""

    def get_permissions(self):
        return [IsAdminEcole()] if self.request.method != 'GET' else [IsAuthenticated()]

    def get(self, request):
        tenant = get_tenant(request)
        if tenant is None:
            return Response({'error': 'Aucune école.'}, status=400)
        p = profil_de(tenant)
        data = ProfilFiscalSerializer(p).data
        data['choix'] = {'forme_juridique': ProfilFiscal.FORME_CHOICES, 'statut': ProfilFiscal.STATUT_CHOICES,
                         'regime': ProfilFiscal.REGIME_CHOICES}
        data['obligations'] = list(ObligationFiscale.objects.filter(actif=True).values('code', 'libelle'))
        return Response(data)

    def patch(self, request):
        tenant = get_tenant(request)
        p = profil_de(tenant)
        s = ProfilFiscalSerializer(p, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        from core.models import log_audit
        log_audit(request, 'MODIFIER', 'ProfilFiscal', str(p.id), 'Profil fiscal modifié')
        return Response(ProfilFiscalSerializer(p).data)


class ParametreFiscalSerializer(serializers.ModelSerializer):
    national = serializers.SerializerMethodField()

    class Meta:
        model = ParametreFiscal
        exclude = ('tenant',)

    def get_national(self, obj):
        return obj.tenant_id is None


class ParametresFiscauxView(APIView):
    """Paramètres fiscaux datés.

    GET — valeurs nationales et surcharges de l'école, avec la valeur en
          vigueur aujourd'hui pour chaque code.
    POST — nouvelle valeur datée : surcharge de l'école, ou valeur nationale
           (`national: true`, réservé au super-administrateur HADY GESMAN).
    PATCH/DELETE ?id= — une surcharge de l'école (national : super-admin).
    """

    def get_permissions(self):
        return [IsAdminEcole()] if self.request.method != 'GET' else [IsAuthenticated()]

    def get(self, request):
        from .parametres import parametre
        tenant = get_tenant(request)
        qs = ParametreFiscal.objects.filter(tenant__isnull=True)
        if tenant is not None:
            qs = qs | ParametreFiscal.objects.filter(tenant=tenant)
        lignes = ParametreFiscalSerializer(qs.order_by('code', '-date_effet'), many=True).data
        en_vigueur = {}
        for code in sorted({l['code'] for l in lignes}):
            p = parametre(code, tenant)
            if p is not None:
                en_vigueur[code] = {'id': str(p.id), 'valeur': float(p.valeur), 'national': p.tenant_id is None}
        return Response({'parametres': lignes, 'en_vigueur': en_vigueur,
                         'peut_modifier_national': _super_admin(request)})

    def post(self, request):
        tenant = get_tenant(request)
        national = bool(request.data.get('national'))
        if national and not _super_admin(request):
            return Response({'error': 'Seul HADY GESMAN modifie les valeurs nationales.'}, status=403)
        s = ParametreFiscalSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        if not national and tenant is None:
            return Response({'error': 'Aucune école.'}, status=400)
        try:
            p = s.save(tenant=None if national else tenant)
        except Exception:
            return Response({'error': 'Une valeur existe déjà pour ce code à cette date.'}, status=409)
        return Response(ParametreFiscalSerializer(p).data, status=201)

    def _objet(self, request):
        p = ParametreFiscal.objects.filter(id=request.query_params.get('id')).first()
        if p is None:
            return None, Response({'error': 'Paramètre introuvable.'}, status=404)
        if p.tenant_id is None and not _super_admin(request):
            return None, Response({'error': 'Valeur nationale : créez une surcharge pour votre école.'},
                                  status=403)
        if p.tenant_id is not None and p.tenant_id != getattr(get_tenant(request), 'id', None):
            return None, Response({'error': 'Paramètre introuvable.'}, status=404)
        return p, None

    def patch(self, request):
        p, err = self._objet(request)
        if err:
            return err
        s = ParametreFiscalSerializer(p, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)

    def delete(self, request):
        p, err = self._objet(request)
        if err:
            return err
        p.delete()
        return Response(status=204)


class ObligationFiscaleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ObligationFiscale
        fields = '__all__'


class ReferentielObligationsView(APIView):
    """GET /fiscal/referentiel/ — obligations décrites en base ; PATCH ?id=
    (super-admin) pour faire évoluer une règle sans redéploiement."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(ObligationFiscaleSerializer(ObligationFiscale.objects.all(), many=True).data)

    def patch(self, request):
        if not _super_admin(request):
            return Response({'error': 'Réservé à HADY GESMAN.'}, status=403)
        ob = ObligationFiscale.objects.filter(id=request.query_params.get('id')).first()
        if ob is None:
            return Response({'error': 'Obligation introuvable.'}, status=404)
        s = ObligationFiscaleSerializer(ob, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)
