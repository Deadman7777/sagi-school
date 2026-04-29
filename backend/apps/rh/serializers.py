from rest_framework import serializers
from .models import Employe, Paie


class EmployeSerializer(serializers.ModelSerializer):
    salaire_net = serializers.ReadOnlyField()

    class Meta:
        model  = Employe
        fields = '__all__'
        extra_kwargs = {
            'tenant':    {'required': False, 'read_only': True},
            'matricule': {'required': False},
        }


class PaieSerializer(serializers.ModelSerializer):
    employe_nom = serializers.CharField(source='employe.nom_complet', read_only=True)

    class Meta:
        model  = Paie
        fields = '__all__'
        extra_kwargs = {
            'tenant': {'required': False, 'read_only': True},
        }
