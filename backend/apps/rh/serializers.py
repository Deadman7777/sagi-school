from rest_framework import serializers
from .models import Employe, Paie, ParametresFiscaux, AvanceSalaire, BulletinPaie


class EmployeSerializer(serializers.ModelSerializer):
    salaire_net = serializers.ReadOnlyField()

    class Meta:
        model  = Employe
        fields = '__all__'
        extra_kwargs = {
            'tenant':    {'required': False, 'read_only': True},
            'matricule': {'required': False},
        }

    def to_internal_value(self, data):
        # Les champs date nullable arrivent souvent en chaîne vide depuis le formulaire
        # → convertir '' en None (DRF DateField refuse la chaîne vide).
        if hasattr(data, 'dict'):
            data = data.dict()
        else:
            data = dict(data)
        for f in ('autorisation_date', 'date_fin_contrat'):
            if data.get(f) == '':
                data[f] = None
        return super().to_internal_value(data)


class PaieSerializer(serializers.ModelSerializer):
    employe_nom = serializers.CharField(source='employe.nom_complet', read_only=True)

    class Meta:
        model  = Paie
        fields = '__all__'
        extra_kwargs = {
            'tenant': {'required': False, 'read_only': True},
        }


class ParametresFiscauxSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ParametresFiscaux
        fields = '__all__'
        extra_kwargs = {'id': {'read_only': True}}


class AvanceSalaireSerializer(serializers.ModelSerializer):
    employe_nom = serializers.CharField(source='employe.nom_complet', read_only=True)
    # Solde encore à retenir : une avance trop lourde pour un seul salaire est
    # retenue sur plusieurs bulletins.
    montant_restant = serializers.ReadOnlyField()

    class Meta:
        model  = AvanceSalaire
        fields = '__all__'
        extra_kwargs = {
            'tenant':         {'required': False, 'read_only': True},
            'no_piece':       {'required': False},
            'montant_impute': {'read_only': True},
        }


class BulletinPaieSerializer(serializers.ModelSerializer):
    employe_nom     = serializers.CharField(source='employe.nom_complet', read_only=True)
    employe_matricule = serializers.CharField(source='employe.matricule', read_only=True)
    employe_poste   = serializers.CharField(source='employe.poste', read_only=True)
    employe_niveau  = serializers.CharField(source='employe.niveau_enseignement', read_only=True)
    periode         = serializers.ReadOnlyField()

    class Meta:
        model  = BulletinPaie
        fields = '__all__'
        extra_kwargs = {
            'tenant': {'required': False, 'read_only': True},
        }


class BulletinPaieCreateSerializer(serializers.Serializer):
    """Paramètres d'entrée pour créer / prévisualiser un bulletin."""
    employe_id             = serializers.UUIDField()
    mois                   = serializers.IntegerField(min_value=1, max_value=12)
    annee                  = serializers.IntegerField(min_value=2000, max_value=2100)
    nb_heures_effectuees   = serializers.DecimalField(max_digits=5, decimal_places=2, default=0)
    prime_transport        = serializers.DecimalField(max_digits=12, decimal_places=2, default=0)
    indemnite_sujetion     = serializers.DecimalField(max_digits=12, decimal_places=2, default=0)
    indemnite_logement     = serializers.DecimalField(max_digits=12, decimal_places=2, default=0)
    primes_diverses        = serializers.DecimalField(max_digits=12, decimal_places=2, default=0)
    avantages_nature       = serializers.DecimalField(max_digits=12, decimal_places=2, default=0)
    opposition_saisie      = serializers.DecimalField(max_digits=12, decimal_places=2, default=0)
    autres_retenues        = serializers.DecimalField(max_digits=12, decimal_places=2, default=0)
    mode_paiement_effectif = serializers.CharField(max_length=15, required=False)
    avance_ids             = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list
    )
    inclure_avances        = serializers.BooleanField(default=False)
