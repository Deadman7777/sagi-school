"""Cloisonnement des relations dans les serializers.

`get_tenant()` protège les listes et les fiches : une vue ne renvoie que les
objets de l'école de l'utilisateur. Elle ne protège pas ce que le client
ENVOIE. Un `PrimaryKeyRelatedField` cherche l'identifiant reçu dans
`Model.objects.all()` — toutes écoles confondues. Un paiement pouvait ainsi
être rattaché à l'élève d'une autre école, une note à l'évaluation d'une autre
école, un bulletin à l'employé d'une autre école : il suffisait d'en connaître
l'identifiant.

Le mixin restreint chaque relation vers un modèle d'école (TenantModel) aux
objets de l'école de la requête. Un identifiant étranger reçoit la même réponse
qu'un identifiant inexistant : « objet introuvable », sans rien révéler.
"""
from rest_framework import serializers
from rest_framework.relations import ManyRelatedField, RelatedField

from core.models import TenantModel


def _cloisonner(champ, tenant):
    if isinstance(champ, ManyRelatedField):
        _cloisonner(champ.child_relation, tenant)
        return
    if not isinstance(champ, RelatedField) or champ.read_only:
        return
    qs = getattr(champ, 'queryset', None)
    if qs is None or not issubclass(qs.model, TenantModel):
        return
    champ.queryset = qs.filter(tenant=tenant)


class CloisonTenantMixin:
    """À placer AVANT ModelSerializer dans les bases d'un serializer."""

    def get_fields(self):
        champs = super().get_fields()
        request = self.context.get('request')
        if request is None:
            return champs
        from core.tenant import get_tenant
        tenant = get_tenant(request)
        # Super admin sans école sélectionnée : rien à cloisonner (il n'écrit
        # pas de données d'école sans en avoir choisi une).
        if tenant is None:
            return champs
        for champ in champs.values():
            _cloisonner(champ, tenant)
        return champs


class TenantModelSerializer(CloisonTenantMixin, serializers.ModelSerializer):
    """ModelSerializer dont les relations restent dans l'école de la requête."""
