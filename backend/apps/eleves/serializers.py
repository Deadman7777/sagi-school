from rest_framework import serializers
from django.utils import timezone
from .models import Eleve, Section


class SectionSerializer(serializers.ModelSerializer):
    total_annuel = serializers.ReadOnlyField()

    class Meta:
        model  = Section
        fields = '__all__'


class EleveSerializer(serializers.ModelSerializer):
    section_nom   = serializers.CharField(source='section.nom', read_only=True)
    total_attendu = serializers.ReadOnlyField()
    total_paye    = serializers.SerializerMethodField()
    reste_a_payer = serializers.SerializerMethodField()
    niveau_alerte = serializers.SerializerMethodField()

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
        paye = self.get_total_paye(obj)
        return float(obj.total_attendu) - paye

    def get_niveau_alerte(self, obj):
        total = float(obj.total_attendu)
        paye  = self.get_total_paye(obj)
        if total <= 0 or paye >= total:
            return 'OK'
        if paye / total < 0.5:
            return 'URGENT'
        return 'ATTENTION'

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