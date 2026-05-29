from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from core.permissions import IsSuperAdmin
from .models import Tenant
from .serializers import TenantSerializer
from apps.paiements.models import Exercice


def get_tenant(request):
    if request.tenant:
        return request.tenant
    if hasattr(request.user, 'tenant') and request.user.tenant:
        return request.user.tenant
    return None


def _exercice_to_dict(ex):
    return {
        'id':                    ex.id,
        'annee_scolaire':        ex.annee_scolaire,
        'date_debut':            str(ex.date_debut),
        'date_fin':              str(ex.date_fin),
        'solde_initial_caisse':  float(ex.solde_initial_caisse),
        'solde_initial_banque':  float(ex.solde_initial_banque),
        'solde_initial_mobile':  float(ex.solde_initial_mobile),
        'cloture':               ex.cloture,
    }


class TenantViewSet(viewsets.ModelViewSet):
    serializer_class = TenantSerializer

    def get_permissions(self):
        if self.action in ['create', 'destroy']:
            return [IsSuperAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        if self.request.user.role == 'SUPER_ADMIN':
            return Tenant.objects.all().order_by('nom')
        tenant = get_tenant(self.request)
        if tenant:
            return Tenant.objects.filter(id=tenant.id)
        return Tenant.objects.none()

    @action(detail=False, methods=['get', 'patch'])
    def mon_ecole(self, request):
        """Récupère ou met à jour les infos de l'école connectée."""
        tenant = get_tenant(request)
        if not tenant:
            return Response({'error': 'Aucun tenant'}, status=400)

        if request.method == 'PATCH':
            serializer = TenantSerializer(tenant, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=400)

        return Response(TenantSerializer(tenant).data)

    @action(detail=True, methods=['get', 'patch'], permission_classes=[IsSuperAdmin])
    def details(self, request, pk=None):
        """Lecture/édition complète école + exercice courant (super_admin)."""
        tenant = self.get_object()
        exercice = (Exercice.objects.filter(tenant=tenant, cloture=False)
                                    .order_by('-date_debut').first())

        if request.method == 'GET':
            return Response({
                'tenant':   TenantSerializer(tenant).data,
                'exercice': _exercice_to_dict(exercice) if exercice else None,
            })

        tenant_data   = request.data.get('tenant', {})
        exercice_data = request.data.get('exercice', {})

        with transaction.atomic():
            t_ser = TenantSerializer(tenant, data=tenant_data, partial=True)
            t_ser.is_valid(raise_exception=True)
            t_ser.save()

            if exercice and exercice_data:
                for field in ('annee_scolaire', 'date_debut', 'date_fin',
                              'solde_initial_caisse', 'solde_initial_banque',
                              'solde_initial_mobile'):
                    if field in exercice_data:
                        setattr(exercice, field, exercice_data[field])
                exercice.save()

        return Response({
            'tenant':   t_ser.data,
            'exercice': _exercice_to_dict(exercice) if exercice else None,
        })

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Stats globales pour le super admin."""
        if request.user.role != 'SUPER_ADMIN':
            return Response({'error': 'Accès refusé'}, status=403)
        return Response({
            'total':   Tenant.objects.count(),
            'actifs':  Tenant.objects.filter(actif=True).count(),
            'inactifs': Tenant.objects.filter(actif=False).count(),
        })
