from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import User


class UserSerializer(serializers.ModelSerializer):
    # write_only : reçu à la création/màj, jamais renvoyé. Doit passer par
    # set_password() pour être hashé — sinon le compte est créé sans mot de
    # passe utilisable et la connexion échoue jusqu'à un « changer mot de passe ».
    password = serializers.CharField(write_only=True, required=False,
                                     min_length=8, style={'input_type': 'password'})

    class Meta:
        model  = User
        fields = ['id', 'nom', 'prenom', 'email', 'role', 'tenant', 'actif',
                  'created_at', 'password', 'modules_autorises']

    def _demandeur(self):
        request = self.context.get('request')
        return getattr(request, 'user', None)

    def _demandeur_super_admin(self):
        return getattr(self._demandeur(), 'role', None) == 'SUPER_ADMIN'

    def validate_role(self, role):
        """Seul l'éditeur (SUPER_ADMIN) attribue le rôle SUPER_ADMIN.

        Sans ce contrôle, l'administrateur d'une école pouvait se créer un
        compte éditeur — et lire ou modifier TOUTES les écoles.
        """
        if role == 'SUPER_ADMIN' and not self._demandeur_super_admin():
            raise serializers.ValidationError("Rôle non autorisé.")
        return role

    def validate_tenant(self, tenant):
        """Une école ne rattache pas un compte à une autre école : le compte
        verrait alors les données de celle-ci. Seul l'éditeur choisit l'école."""
        if self._demandeur_super_admin():
            return tenant
        demandeur = self._demandeur()
        if tenant is not None and tenant.id != getattr(demandeur, 'tenant_id', None):
            raise serializers.ValidationError("École non autorisée.")
        return tenant

    def validate(self, attrs):
        # Un administrateur d'école ne modifie pas son PROPRE rôle ni ne se
        # désactive : il perdrait l'accès, et plus personne ne gérerait l'école.
        demandeur = self._demandeur()
        if (self.instance is not None and demandeur is not None
                and self.instance.pk == demandeur.pk and not self._demandeur_super_admin()):
            if 'role' in attrs and attrs['role'] != self.instance.role:
                raise serializers.ValidationError({'role': "Vous ne pouvez pas changer votre propre rôle."})
            if attrs.get('actif') is False:
                raise serializers.ValidationError({'actif': "Vous ne pouvez pas désactiver votre propre compte."})
        return attrs

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
                # Modules choisis par l'école pour cet utilisateur : ils
                # restreignent ceux de la licence, qui reste le plafond.
                perso = getattr(user, 'modules_autorises', None) or []
                if perso:
                    toujours = ('/ma-licence', '/parametres')
                    token['modules'] = [m for m in licence.modules
                                        if m.lstrip('/') in perso or m in toujours]
                    token['modules_perso'] = True
                else:
                    token['modules'] = licence.modules
            except Exception:
                token['type_licence'] = None
                token['modules']      = []
        else:
            token['type_licence'] = None
            token['modules']      = []
        return token
