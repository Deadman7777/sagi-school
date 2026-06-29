from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import User


class UserSerializer(serializers.ModelSerializer):
    # write_only : reçu à la création/màj, jamais renvoyé. Doit passer par
    # set_password() pour être hashé — sinon le compte est créé sans mot de
    # passe utilisable et la connexion échoue jusqu'à un « changer mot de passe ».
    password = serializers.CharField(write_only=True, required=False,
                                     min_length=6, style={'input_type': 'password'})

    class Meta:
        model  = User
        fields = ['id', 'nom', 'prenom', 'email', 'role', 'tenant', 'actif',
                  'created_at', 'password']

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


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
