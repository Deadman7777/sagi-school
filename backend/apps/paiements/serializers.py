from rest_framework import serializers
from .models import Paiement, Exercice


class ExerciceSerializer(serializers.ModelSerializer):
    solde_initial_caisse = serializers.FloatField()
    solde_initial_banque = serializers.FloatField()
    solde_initial_mobile = serializers.FloatField()

    class Meta:
        model  = Exercice
        fields = '__all__'
        extra_kwargs = {
            'tenant': {'required': False, 'read_only': True},
        }


class PaiementSerializer(serializers.ModelSerializer):
    total     = serializers.ReadOnlyField()
    caisse_nom = serializers.CharField(source='caisse.nom', read_only=True, default='')
    # Part « frais de l'année » : total − reliquat antérieur. C'est elle qui
    # constate un produit 706 (voir apps.paiements.ecritures).
    total_exercice = serializers.ReadOnlyField()
    eleve_nom = serializers.CharField(source='eleve.nom_complet', read_only=True)
    # Qui règle : vide quand c'est la famille. Affiché sur le reçu et dans
    # l'historique, pour qu'on ne confonde pas un versement d'organisme avec
    # un règlement des parents.
    organisme_nom = serializers.CharField(source='organisme.nom', read_only=True,
                                          default='')

    def validate_caisse(self, caisse):
        """Une caisse d'une AUTRE école n'existe pas pour ce règlement."""
        if caisse is None:
            return caisse
        from core.tenant import get_tenant
        request = self.context.get('request')
        tenant = get_tenant(request) if request is not None else None
        if tenant is not None and caisse.tenant_id != tenant.id:
            raise serializers.ValidationError('Caisse inconnue.')
        if not caisse.actif:
            raise serializers.ValidationError(f"La caisse « {caisse.nom} » est désactivée.")
        return caisse

    class Meta:
        model  = Paiement
        fields = '__all__'
        extra_kwargs = {
            'tenant':   {'required': False, 'read_only': True},
            'exercice': {'required': False, 'read_only': True},
            'no_piece': {'required': False, 'read_only': True},
        }
