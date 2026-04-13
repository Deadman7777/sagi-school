from rest_framework import serializers
from .models import Paiement, Exercice


class ExerciceSerializer(serializers.ModelSerializer):
    solde_initial_caisse = serializers.FloatField()
    solde_initial_banque = serializers.FloatField()
    solde_initial_mobile = serializers.FloatField()

    class Meta:
        model  = Exercice
        fields = '__all__'


class PaiementSerializer(serializers.ModelSerializer):
    total       = serializers.ReadOnlyField()
    eleve_nom   = serializers.CharField(source='eleve.nom_complet', read_only=True)

    class Meta:
        model  = Paiement
        fields = '__all__'
