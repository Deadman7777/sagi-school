from rest_framework import serializers

from .models import Sourate, Subdivision, NiveauDaara, ParcoursNongo, SuiviQuotidien


class SourateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sourate
        fields = '__all__'


class SubdivisionSerializer(serializers.ModelSerializer):
    sourate_numero = serializers.IntegerField(source='sourate_debut.numero', read_only=True)
    sourate_nom_fr = serializers.CharField(source='sourate_debut.nom_fr', read_only=True)
    sourate_nom_ar = serializers.CharField(source='sourate_debut.nom_ar', read_only=True)

    class Meta:
        model = Subdivision
        fields = '__all__'


class NiveauDaaraSerializer(serializers.ModelSerializer):
    class Meta:
        model = NiveauDaara
        fields = '__all__'
        extra_kwargs = {'tenant': {'required': False, 'read_only': True}}


class ParcoursNongoSerializer(serializers.ModelSerializer):
    eleve_nom   = serializers.CharField(source='eleve.nom_complet', read_only=True)
    niveau_nom  = serializers.CharField(source='niveau.nom_fr', read_only=True)

    class Meta:
        model = ParcoursNongo
        fields = '__all__'
        extra_kwargs = {
            'tenant': {'required': False, 'read_only': True},
            'niveau': {'required': False, 'allow_null': True},
        }


class SuiviQuotidienSerializer(serializers.ModelSerializer):
    sourate_debut_nom = serializers.CharField(source='sourate_debut.nom_fr', read_only=True)
    sourate_fin_nom   = serializers.CharField(source='sourate_fin.nom_fr', read_only=True)

    class Meta:
        model = SuiviQuotidien
        fields = '__all__'
        extra_kwargs = {
            'tenant': {'required': False, 'read_only': True},
            'sourate_debut': {'required': False, 'allow_null': True},
            'sourate_fin': {'required': False, 'allow_null': True},
        }
