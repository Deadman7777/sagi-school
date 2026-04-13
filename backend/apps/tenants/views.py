from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from core.permissions import IsSuperAdmin
from .models import Tenant
from .serializers import TenantSerializer


def get_tenant(request):
    if request.tenant:
        return request.tenant
    if hasattr(request.user, 'tenant') and request.user.tenant:
        return request.user.tenant
    return None


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
