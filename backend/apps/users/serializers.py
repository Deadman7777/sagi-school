from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model  = User
        fields = ['id', 'nom', 'prenom', 'email', 'role', 'tenant', 'actif', 'created_at']


class CustomTokenSerializer(TokenObtainPairSerializer):
    """JWT enrichi avec les infos du user et du tenant."""
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['nom']       = user.nom
        token['role']      = user.role
        token['tenant_id'] = str(user.tenant_id) if user.tenant_id else None
        return token
