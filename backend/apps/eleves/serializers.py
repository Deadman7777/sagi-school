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

    def validate(self, attrs):
        """mois_unique n'a de sens que pour la périodicité UNIQUE
        (None = dû à l'inscription, 1..12 = mois calendaire)."""
        periodicite = attrs.get('periodicite',
                                getattr(self.instance, 'periodicite', 'MENSUEL'))
        if periodicite != 'UNIQUE':
            attrs['mois_unique'] = None
        return attrs


class EleveSerializer(serializers.ModelSerializer):
    section_nom                  = serializers.CharField(source='section.nom', read_only=True)
    classe_nom                   = serializers.SerializerMethodField()
    date_inscription_libelle     = serializers.ReadOnlyField()
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
    # Dette de l'exercice précédent — suivie en parallèle du dû de l'année,
    # jamais fondue dedans (le niveau d'alerte reste celui de l'année en cours).
    reliquat_paye                = serializers.ReadOnlyField()
    reliquat_restant             = serializers.ReadOnlyField()
    reliquat_origine_libelle     = serializers.ReadOnlyField()
    reste_a_payer_global         = serializers.SerializerMethodField()

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
            # Identité d'entrée : attribuée par le système (voir matricules.py)
            # et recopiée à chaque réinscription. Seule la date reste corrigeable
            # — une école qui migre découvre parfois la vraie date d'arrivée
            # après coup ; la promo, elle, découle de l'exercice d'entrée.
            'annee_entree':     {'read_only': True},
            'matricule_ancien': {'read_only': True},
        }

    def validate(self, attrs):
        """Régime passager (daara) : la durée en mois est obligatoire ;
        en régime exercice on nettoie le champ pour éviter toute ambiguïté."""
        regime = attrs.get('regime', getattr(self.instance, 'regime', 'EXERCICE'))
        nb     = attrs.get('nb_mois_passager', getattr(self.instance, 'nb_mois_passager', None))
        if regime == 'PASSAGER' and not nb:
            raise serializers.ValidationError(
                {'nb_mois_passager': 'Nombre de mois requis pour un ndongo passager.'})
        if regime == 'EXERCICE':
            attrs['nb_mois_passager'] = None
        self._valider_reliquat(attrs)
        return attrs

    def _valider_reliquat(self, attrs):
        """L'impayé antérieur porte une écriture de bilan (411/890) : on refuse
        ici ce que la comptabilité ne saurait pas représenter proprement."""
        if 'reliquat_anterieur' not in attrs:
            return
        montant = float(attrs['reliquat_anterieur'] or 0)
        if montant < 0:
            raise serializers.ValidationError(
                {'reliquat_anterieur': "L'impayé antérieur ne peut pas être négatif."})
        if not self.instance:
            return
        exercice = self.instance.exercice
        if exercice and exercice.cloture:
            raise serializers.ValidationError(
                {'reliquat_anterieur':
                 f"L'exercice {exercice.annee_scolaire} est clôturé : "
                 "l'impayé antérieur ne peut plus y être modifié."})
        # Descendre sous ce qui a déjà été encaissé afficherait un trop-perçu
        # fantôme sur la fiche — on annule d'abord les encaissements.
        deja = self.instance.reliquat_paye
        if montant and montant < deja:
            raise serializers.ValidationError(
                {'reliquat_anterieur':
                 f"Montant inférieur aux {deja:,.0f} FCFA déjà encaissés sur cet "
                 "impayé antérieur. Annulez d'abord les encaissements concernés."})

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

    def get_reste_a_payer_global(self, obj):
        """Dû réel de la famille : reste de l'année + reliquat encore ouvert."""
        return round(self.get_reste_a_payer(obj) + obj.reliquat_restant, 2)

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

    def validate(self, attrs):
        """Composition libre de l'inscription : quand des éléments sont définis,
        frais_inscription = somme des montants (source de vérité unique)."""
        compo = attrs.get('composition_inscription',
                          getattr(self.instance, 'composition_inscription', None))
        if compo:
            elements = []
            for el in compo:
                libelle = str(el.get('libelle', '')).strip()
                try:
                    montant = float(el.get('montant', 0) or 0)
                except (TypeError, ValueError):
                    montant = 0
                if libelle:
                    elements.append({'libelle': libelle, 'montant': montant})
            attrs['composition_inscription'] = elements
            attrs['frais_inscription'] = round(sum(e['montant'] for e in elements), 2)
        return attrs