from rest_framework import serializers
from .models import Licence


class LicenceSerializer(serializers.ModelSerializer):
    est_active     = serializers.ReadOnlyField()
    jours_restants = serializers.ReadOnlyField()
    tenant_nom     = serializers.CharField(source='tenant.nom', read_only=True)

    class Meta:
        model = Licence
        fields = '__all__'
