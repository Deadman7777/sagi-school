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

    # Utilise l'annotation SQL si disponible
    total_paye = serializers.SerializerMethodField()
    reste_a_payer = serializers.SerializerMethodField()
    niveau_alerte = serializers.SerializerMethodField()

    class Meta:
        model  = Eleve
        fields = '__all__'

    def get_total_paye(self, obj):
        # Annotation SQL disponible → instantané
        if hasattr(obj, 'total_paye_sql') and obj.total_paye_sql is not None:
            return float(obj.total_paye_sql)
        return float(obj.total_paye)

    def get_reste_a_payer(self, obj):
        paye = self.get_total_paye(obj)
        return float(obj.total_attendu) - paye

    def get_niveau_alerte(self, obj):
        reste = self.get_reste_a_payer(obj)
        if reste <= 0:
            return 'OK'
        jours = (timezone.now().date() - obj.date_inscription).days
        if jours > 60:  return 'URGENT'
        if jours > 30:  return 'ATTENTION'
        return 'OK'

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