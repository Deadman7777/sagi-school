from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model  = User
        fields = ['id', 'nom', 'prenom', 'email', 'role', 'tenant', 'actif', 'created_at']


class CustomTokenSerializer(TokenObtainPairSerializer):
    """JWT enrichi avec les infos du user et du tenant."""

    def validate(self, attrs):
        data = super().validate(attrs)
        if not self.user.actif:
            from rest_framework_simplejwt.exceptions import AuthenticationFailed
            raise AuthenticationFailed('Compte désactivé.')
        return data

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['nom']       = user.nom
        token['role']      = user.role
        token['tenant_id'] = str(user.tenant_id) if user.tenant_id else None
        if user.tenant_id:
            try:
                licence = user.tenant.licence
                token['type_licence'] = licence.type
                token['modules']      = licence.modules
            except Exception:
                token['type_licence'] = None
                token['modules']      = []
        else:
            token['type_licence'] = None
            token['modules']      = []
        return token
