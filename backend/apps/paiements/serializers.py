from rest_framework import serializers
from core.serializers import TenantModelSerializer
from .models import Paiement, Exercice, Receveur


def erreur_libelle_exercice(libelle, debut):
    """Message si l'année scolaire saisie contredit la date de début, sinon None.

    Le libellé est une saisie libre, mais tout ce qui compte (matricules, promo,
    année des bulletins) se lit sur `date_debut`. Un exercice « 2026-2027 » qui
    commence le 01/10/2025 donnait des matricules 2025-… : l'école croyait avoir
    réglé l'année et le système en voyait une autre. Le libellé doit donc
    commencer par l'année de début (« 2026-2027 » ou « 2026 »).
    """
    import datetime
    libelle = (libelle or '').strip()
    if not libelle or not debut:
        return None
    if isinstance(debut, str):
        try:
            debut = datetime.date.fromisoformat(debut)
        except ValueError:
            return None
    if libelle.startswith(str(debut.year)):
        return None
    return (f"L'année scolaire « {libelle} » ne correspond pas à la date de début "
            f"({debut:%d/%m/%Y}). Corrigez la date de début : c'est elle qui fixe "
            f"l'année des matricules.")


class ExerciceSerializer(TenantModelSerializer):
    solde_initial_caisse = serializers.FloatField()
    solde_initial_banque = serializers.FloatField()
    solde_initial_mobile = serializers.FloatField()

    class Meta:
        model  = Exercice
        fields = '__all__'
        extra_kwargs = {
            'tenant': {'required': False, 'read_only': True},
            'an_source': {'read_only': True},
            'an_genere_le': {'read_only': True},
        }

    def validate(self, attrs):
        """Plusieurs exercices, oui ; qui se chevauchent, non.

        Une école peut créer un exercice ANTÉRIEUR à l'exercice courant (année
        non régularisée à son arrivée) : il suffit qu'il ne recouvre aucun
        autre, sinon une écriture datée appartiendrait à deux exercices.
        """
        debut = attrs.get('date_debut', getattr(self.instance, 'date_debut', None))
        fin = attrs.get('date_fin', getattr(self.instance, 'date_fin', None))
        if debut and fin:
            if fin <= debut:
                raise serializers.ValidationError({'date_fin': 'La fin doit suivre le début.'})
            request = self.context.get('request')
            from core.tenant import get_tenant
            tenant = get_tenant(request) if request else getattr(self.instance, 'tenant', None)
            if tenant is not None:
                autres = Exercice.objects.filter(tenant=tenant, date_debut__lte=fin, date_fin__gte=debut)
                if self.instance is not None:
                    autres = autres.exclude(id=self.instance.id)
                if (conflit := autres.first()) is not None:
                    raise serializers.ValidationError({'date_debut': (
                        f"Cet exercice chevauche l'exercice {conflit.annee_scolaire} "
                        f"({conflit.date_debut:%d/%m/%Y} – {conflit.date_fin:%d/%m/%Y}).")})
        if 'annee_scolaire' in attrs or 'date_debut' in attrs:
            libelle = attrs.get('annee_scolaire', getattr(self.instance, 'annee_scolaire', ''))
            if (erreur := erreur_libelle_exercice(libelle, debut)):
                raise serializers.ValidationError({'annee_scolaire': erreur})
        return attrs


class PaiementSerializer(TenantModelSerializer):
    total     = serializers.ReadOnlyField()
    caisse_nom = serializers.CharField(source='caisse.nom', read_only=True, default='')
    # Part « frais de l'année » : total − reliquat antérieur. C'est elle qui
    # constate un produit 706 (voir apps.paiements.ecritures).
    total_exercice = serializers.ReadOnlyField()
    eleve_nom = serializers.CharField(source='eleve.nom_complet', read_only=True)
    # Qui règle : vide quand c'est la famille. Affiché sur le reçu et dans
    # l'historique, pour qu'on ne confonde pas un versement d'organisme avec
    # un règlement des parents.
    organisme_nom = serializers.CharField(source='organisme.nom', read_only=True,
                                          default='')

    def validate_payeur(self, payeur):
        """Le payeur d'un règlement appartient à l'école qui encaisse.

        Même précaution que pour la caisse : un identifiant venu d'ailleurs
        rattacherait le versement d'une famille à une autre école.
        """
        if payeur is None:
            return payeur
        from core.tenant import get_tenant
        request = self.context.get('request')
        tenant = get_tenant(request) if request else None
        if tenant and payeur.tenant_id != tenant.id:
            raise serializers.ValidationError("Ce responsable n'appartient pas à l'école.")
        return payeur

    receveur_nom = serializers.CharField(source='receveur.nom', read_only=True, default='')

    def validate_receveur(self, receveur):
        """Le receveur est une personne de l'école, encore en activité."""
        if receveur is None:
            return receveur
        from core.tenant import get_tenant
        request = self.context.get('request')
        tenant = get_tenant(request) if request is not None else None
        if tenant is not None and receveur.tenant_id != tenant.id:
            raise serializers.ValidationError('Receveur inconnu.')
        if not receveur.actif:
            raise serializers.ValidationError(f"« {receveur.nom} » ne reçoit plus de règlements.")
        return receveur

    def validate_caisse(self, caisse):
        """Une caisse d'une AUTRE école n'existe pas pour ce règlement."""
        if caisse is None:
            return caisse
        from core.tenant import get_tenant
        request = self.context.get('request')
        tenant = get_tenant(request) if request is not None else None
        if tenant is not None and caisse.tenant_id != tenant.id:
            raise serializers.ValidationError('Caisse inconnue.')
        if not caisse.actif:
            raise serializers.ValidationError(f"La caisse « {caisse.nom} » est désactivée.")
        return caisse

    class Meta:
        model  = Paiement
        fields = '__all__'
        extra_kwargs = {
            'tenant':   {'required': False, 'read_only': True},
            'exercice': {'required': False, 'read_only': True},
            'no_piece': {'required': False, 'read_only': True},
        }


class ReceveurSerializer(TenantModelSerializer):
    """Une personne qui reçoit des règlements (Paramètres → Caisses)."""
    nb_paiements = serializers.SerializerMethodField()

    class Meta:
        model  = Receveur
        fields = ['id', 'nom', 'actif', 'nb_paiements']

    def get_nb_paiements(self, obj):
        return obj.paiements.filter(statut='ACTIF').count()

    def validate_nom(self, nom):
        nom = (nom or '').strip()
        if not nom:
            raise serializers.ValidationError('Donnez le nom du receveur.')
        from core.tenant import get_tenant
        tenant = get_tenant(self.context['request'])
        doublon = Receveur.objects.filter(tenant=tenant, nom__iexact=nom)
        if self.instance is not None:
            doublon = doublon.exclude(pk=self.instance.pk)
        if doublon.exists():
            raise serializers.ValidationError(f"« {nom} » existe déjà.")
        return nom
