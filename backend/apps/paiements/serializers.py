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
    # Part « frais de l'année » : total − reliquat antérieur. C'est elle qui
    # constate un produit 706 (voir apps.paiements.ecritures).
    total_exercice = serializers.ReadOnlyField()
    eleve_nom = serializers.CharField(source='eleve.nom_complet', read_only=True)
    # Qui règle : vide quand c'est la famille. Affiché sur le reçu et dans
    # l'historique, pour qu'on ne confonde pas un versement d'organisme avec
    # un règlement des parents.
    organisme_nom = serializers.CharField(source='organisme.nom', read_only=True,
                                          default='')

    class Meta:
        model  = Paiement
        fields = '__all__'
        extra_kwargs = {
            'tenant':   {'required': False, 'read_only': True},
            'exercice': {'required': False, 'read_only': True},
            'no_piece': {'required': False, 'read_only': True},
        }
