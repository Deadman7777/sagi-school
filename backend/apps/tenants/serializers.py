from rest_framework import serializers
from .models import Tenant


class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = '__all__'

    # Jours de mois plafonnés à 28 : un 30 ou un 31 n'existe pas tous les mois,
    # et une échéance qui saute février serait pire qu'absente.
    JOURS = ('jour_echeance', 'rappel_jour_debut', 'rappel_jour_limite')

    def validate(self, attrs):
        for champ in self.JOURS:
            if champ in attrs and attrs[champ] is not None:
                if not 1 <= int(attrs[champ]) <= 28:
                    raise serializers.ValidationError(
                        {champ: 'Indiquez un jour entre 1 et 28.'})
        debut = attrs.get('rappel_jour_debut',
                          getattr(self.instance, 'rappel_jour_debut', 1))
        limite = attrs.get('rappel_jour_limite',
                           getattr(self.instance, 'rappel_jour_limite', 10))
        if debut and limite and int(debut) > int(limite):
            raise serializers.ValidationError(
                {'rappel_jour_limite':
                 "Le dernier délai ne peut pas précéder le début des rappels."})
        return attrs
