from rest_framework import serializers
from django.utils import timezone
from .models import Eleve, Section, Service, EleveService

# Numéro → nom. Volontairement distinct de import_eleves._MOIS_NOMS, qui va
# dans l'autre sens (nom → numéro) : deux tables homonymes seraient un piège.
_NOMS_MOIS = {1: 'janvier', 2: 'février', 3: 'mars', 4: 'avril',
              5: 'mai', 6: 'juin', 7: 'juillet', 8: 'août',
              9: 'septembre', 10: 'octobre', 11: 'novembre', 12: 'décembre'}


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
    # Mois réellement dus + d'où ils viennent : l'école doit voir si le chiffre
    # est le sien ou celui du prorata, sinon elle ne sait pas quoi corriger.
    nb_mensualites_dues          = serializers.ReadOnlyField()
    mois_dus_effectifs           = serializers.SerializerMethodField()
    mois_dus_origine             = serializers.SerializerMethodField()

    def get_mois_dus_effectifs(self, obj):
        """Les mois facturés, saisis ou déduits du prorata."""
        if obj.mois_dus:
            return sorted(int(m) for m in obj.mois_dus)
        if not obj.exercice_id:
            return []
        debut = obj.exercice.date_debut
        nb    = obj.nb_mensualites_dues
        # Les mois dus courent depuis le premier mois facturé jusqu'au bout du
        # compte : le prorata ne dit qu'un NOMBRE, on le déroule en calendrier.
        premier = obj.exercice.nb_mensualites - nb
        return [((debut.month - 1 + premier + i) % 12) + 1 for i in range(nb)]

    def get_mois_dus_origine(self, obj):
        return 'SAISI' if obj.mois_dus else 'PRORATA'

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
        self._dater_la_sortie(attrs)
        self._valider_mois_dus(attrs)
        self._valider_reliquat(attrs)
        return attrs

    def _dater_la_sortie(self, attrs):
        """Pose (ou retire) la date de sortie quand le statut bascule.

        Sans date, l'horloge des arriérés continue de tourner après le départ
        et la fiche finit en CRITIQUE pour une scolarité non suivie. On la met
        donc au jour du changement si l'école ne l'a pas précisée — elle reste
        corrigeable ensuite.

        Réinscrire un ancien sortant efface la date : la fiche redevient celle
        d'un élève présent, elle ne peut pas garder une sortie.
        """
        from .parcours import STATUTS_SORTIE

        if 'statut' not in attrs:
            return
        sort = attrs['statut'] in STATUTS_SORTIE
        deja = attrs.get('date_sortie') or getattr(self.instance, 'date_sortie', None)
        if sort:
            attrs['date_sortie'] = attrs.get('date_sortie') or deja or timezone.now().date()
        else:
            attrs['date_sortie'] = None

    def _valider_mois_dus(self, attrs):
        """Mois facturés : numéros valides, et jamais retirer un mois déjà réglé.

        Décocher un mois qu'un paiement a déjà soldé creuserait un trop-perçu
        fantôme sur la fiche — l'élève aurait payé un mois qu'il ne doit pas.
        On refuse avec le nom du mois plutôt que de laisser corriger à l'aveugle.
        """
        if 'mois_dus' not in attrs:
            return
        brut = attrs['mois_dus'] or []
        if not isinstance(brut, list):
            raise serializers.ValidationError(
                {'mois_dus': 'Format attendu : une liste de numéros de mois.'})
        try:
            mois = sorted({int(m) for m in brut})
        except (TypeError, ValueError):
            raise serializers.ValidationError(
                {'mois_dus': 'Les mois doivent être des nombres de 1 à 12.'})
        if any(m < 1 or m > 12 for m in mois):
            raise serializers.ValidationError(
                {'mois_dus': 'Les mois doivent être compris entre 1 et 12.'})
        attrs['mois_dus'] = mois

        if not self.instance or not mois:
            return
        regles = set()
        for p in self.instance.paiements.filter(statut='ACTIF'):
            regles.update(int(m) for m in (p.mois_regles or []))
        retires = sorted(regles - set(mois))
        if retires:
            noms = ', '.join(_NOMS_MOIS.get(m, str(m)) for m in retires)
            raise serializers.ValidationError(
                {'mois_dus': f"Déjà réglé pour : {noms}. Annulez d'abord "
                             "les paiements concernés."})

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