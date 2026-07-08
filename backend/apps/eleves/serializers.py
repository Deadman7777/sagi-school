from rest_framework import serializers
from django.utils import timezone
from .models import Eleve, Section, Service, EleveService


class ServiceSerializer(serializers.ModelSerializer):
    montant = serializers.FloatField(required=False, default=0)

    class Meta:
        model  = Service
        fields = '__all__'
        extra_kwargs = {
            'tenant': {'required': False, 'read_only': True},
        }


class EleveSerializer(serializers.ModelSerializer):
    section_nom                  = serializers.CharField(source='section.nom', read_only=True)
    classe_nom                   = serializers.SerializerMethodField()
    total_theorique              = serializers.ReadOnlyField()
    total_attendu                = serializers.ReadOnlyField()
    montant_pec_inscription      = serializers.ReadOnlyField()
    montant_pec_mensualite_mensuel = serializers.ReadOnlyField()
    montant_pec_annuel           = serializers.ReadOnlyField()
    montant_services_annuel      = serializers.ReadOnlyField()
    abonnements                  = serializers.SerializerMethodField()
    total_paye                   = serializers.SerializerMethodField()
    reste_a_payer                = serializers.SerializerMethodField()
    niveau_alerte                = serializers.SerializerMethodField()

    class Meta:
        model  = Eleve
        fields = '__all__'
        extra_kwargs = {
            'tenant':   {'required': False, 'read_only': True},
            'exercice': {'required': False, 'read_only': True},
            # DRF 3.15 rend obligatoires les champs d'une UniqueConstraint
            # (uniq_matricule_par_tenant) ; or le matricule est généré par
            # perform_create — sans ceci, toute création d'élève renvoie 400.
            'matricule': {'required': False, 'allow_null': True, 'allow_blank': True},
        }

    def get_classe_nom(self, obj):
        return obj.classe.nom if obj.classe_id else ''

    def get_abonnements(self, obj):
        """Liste des IDs de services auxquels l'élève est abonné."""
        return [str(ab.service_id) for ab in obj.abonnements.all()]

    def _sync_abonnements(self, eleve):
        """Crée/supprime les abonnements selon la liste 'abonnements' (IDs de services) en entrée."""
        ids = self.initial_data.get('abonnements', None)
        if ids is None:
            return
        wanted   = {str(i) for i in ids}
        existing = {str(ab.service_id): ab for ab in eleve.abonnements.all()}
        for sid in wanted - set(existing):
            svc = Service.objects.filter(id=sid, tenant=eleve.tenant).first()
            if svc:
                EleveService.objects.create(tenant=eleve.tenant, eleve=eleve, service=svc)
        for sid in set(existing) - wanted:
            existing[sid].delete()

    def create(self, validated_data):
        eleve = super().create(validated_data)
        self._sync_abonnements(eleve)
        return eleve

    def update(self, instance, validated_data):
        eleve = super().update(instance, validated_data)
        self._sync_abonnements(eleve)
        return eleve

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
    frais_inscription  = serializers.FloatField(required=False, default=0)
    frais_mensualite   = serializers.FloatField(required=False, default=0)
    frais_uniforme     = serializers.FloatField(required=False, default=0)
    frais_fournitures  = serializers.FloatField(required=False, default=0)

    class Meta:
        model  = Section
        fields = '__all__'
        extra_kwargs = {
            'tenant': {'required': False, 'read_only': True},
        }