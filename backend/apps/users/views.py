from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView
from core.permissions import IsSuperAdmin, IsAdminEcole
from .models import User
from .serializers import UserSerializer, CustomTokenSerializer


def get_tenant(request):
    if request.tenant:
        return request.tenant
    if hasattr(request.user, 'tenant') and request.user.tenant:
        return request.user.tenant
    return None


class LoginView(TokenObtainPairView):
    serializer_class = CustomTokenSerializer


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer

    def get_permissions(self):
        if self.request.user.role == 'SUPER_ADMIN':
            return [IsSuperAdmin()]
        return [IsAdminEcole()]

    def get_queryset(self):
        user = self.request.user
        # Super admin voit tous les users
        if user.role == 'SUPER_ADMIN':
            tenant_id = self.request.query_params.get('tenant')
            if tenant_id:
                return User.objects.filter(tenant_id=tenant_id).order_by('nom')
            return User.objects.all().order_by('tenant__nom', 'nom')
        # Admin école voit seulement son école
        tenant = get_tenant(self.request)
        if tenant:
            return User.objects.filter(tenant=tenant).order_by('nom')
        return User.objects.none()

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        if self.request.user.role != 'SUPER_ADMIN':
            serializer.save(tenant=tenant)
        else:
            serializer.save()

    @action(detail=False, methods=['get'])
    def me(self, request):
        return Response(UserSerializer(request.user).data)

    @action(detail=True, methods=['post'])
    def changer_mot_de_passe(self, request, pk=None):
        user = self.get_object()
        mdp  = request.data.get('password')
        if not mdp or len(mdp) < 6:
            return Response({'error': 'Mot de passe trop court (min 6 caractères)'},
                            status=status.HTTP_400_BAD_REQUEST)
        user.set_password(mdp)
        user.save()
        return Response({'message': 'Mot de passe modifié ✅'})
