from rest_framework import serializers
from django.utils import timezone
from .models import Eleve, Section


class EleveSerializer(serializers.ModelSerializer):
    section_nom                  = serializers.CharField(source='section.nom', read_only=True)
    total_theorique              = serializers.ReadOnlyField()
    total_attendu                = serializers.ReadOnlyField()
    montant_pec_inscription      = serializers.ReadOnlyField()
    montant_pec_mensualite_mensuel = serializers.ReadOnlyField()
    montant_pec_annuel           = serializers.ReadOnlyField()
    total_paye                   = serializers.SerializerMethodField()
    reste_a_payer                = serializers.SerializerMethodField()
    niveau_alerte                = serializers.SerializerMethodField()

    class Meta:
        model  = Eleve
        fields = '__all__'
        extra_kwargs = {
            'tenant':   {'required': False, 'read_only': True},
            'exercice': {'required': False, 'read_only': True},
        }

    def get_total_paye(self, obj):
        if hasattr(obj, 'total_paye_sql') and obj.total_paye_sql is not None:
            return float(obj.total_paye_sql)
        return float(obj.total_paye)

    def get_reste_a_payer(self, obj):
        return round(float(obj.total_attendu) - self.get_total_paye(obj), 2)

    def get_niveau_alerte(self, obj):
        # Délègue au modèle pour cohérence avec le dashboard
        return obj.niveau_alerte

class SectionSerializer(serializers.ModelSerializer):
    total_annuel = serializers.ReadOnlyField()
    frais_inscription  = serializers.FloatField()
    frais_mensualite   = serializers.FloatField()
    frais_uniforme     = serializers.FloatField()
    frais_fournitures  = serializers.FloatField()
    frais_yendu        = serializers.FloatField()

    class Meta:
        model  = Section
        fields = '__all__'
        extra_kwargs = {
            'tenant': {'required': False, 'read_only': True},
        }