from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import SimpleRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView
from core.permissions import IsSuperAdmin, IsAdminEcole
from core.tenant import get_tenant
from .models import User
from .serializers import UserSerializer, CustomTokenSerializer


class ConnexionThrottle(SimpleRateThrottle):
    """Freine l'essai de mots de passe en série sur UN compte.

    Compté par adresse e-mail saisie, pas par adresse IP : derrière le proxy
    du cloud, l'IP vue par Django se falsifie (X-Forwarded-For) et un
    attaquant la ferait varier à chaque essai. Taux dans
    REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['connexion'].
    """
    scope = 'connexion'

    def get_cache_key(self, request, view):
        email = str(request.data.get('email') or '').strip().lower()
        return self.cache_format % {'scope': self.scope, 'ident': email or self.get_ident(request)}


class LoginView(TokenObtainPairView):
    serializer_class = CustomTokenSerializer
    throttle_classes = [ConnexionThrottle]


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer

    def get_permissions(self):
        role = getattr(self.request.user, 'role', None)
        if role == 'SUPER_ADMIN':
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
        if tenant:
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
        if not mdp or len(mdp) < 8:
            return Response({'error': 'Mot de passe trop court (min 8 caractères)'},
                            status=status.HTTP_400_BAD_REQUEST)
        user.set_password(mdp)
        user.save()
        from core.models import log_audit
        log_audit(request, 'MODIFICATION', 'User', str(user.id),
                  f'Mot de passe changé pour {user.email}')
        return Response({'message': 'Mot de passe modifié ✅'})
