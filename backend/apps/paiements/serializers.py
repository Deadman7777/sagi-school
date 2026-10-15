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
    solde_initial_mobile = serializers.FloatField()          # Wave
    solde_initial_orange_money = serializers.FloatField(required=False)
    solde_initial_free_money = serializers.FloatField(required=False)

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
        self._verifier_annee_facturation(attrs, debut, fin)
        return attrs

    def _verifier_annee_facturation(self, attrs, debut, fin):
        """L'année de facturation (douze mois) doit contenir tout l'exercice."""
        mois = attrs.get('mois_debut_annee', getattr(self.instance, 'mois_debut_annee', None))
        if mois is None or not debut or not fin:
            return
        if not 1 <= int(mois) <= 12:
            raise serializers.ValidationError({'mois_debut_annee': 'Mois invalide (1 à 12).'})
        annee = debut.year if int(mois) <= debut.month else debut.year - 1
        if (fin.year * 12 + fin.month) - (annee * 12 + int(mois)) > 11:
            raise serializers.ValidationError({'mois_debut_annee': (
                "Commencer l'année de facturation à ce mois laisserait la fin de "
                "l'exercice hors des douze mois facturables.")})


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
    employe_compense_nom = serializers.CharField(source='employe_compense.nom_complet',
                                                 read_only=True, default='')

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
            # Posé par le serveur après contrôle du plafond (voir perform_create).
            'employe_compense': {'required': False, 'read_only': True},
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


def _nom_user(u):
    return f"{u.prenom or ''} {u.nom or ''}".strip() or u.email if u else ''


class ChequeRecuSerializer(TenantModelSerializer):
    """Un chèque du registre, avec les reçus qu'il règle et qui a fait quoi."""
    recus          = serializers.SerializerMethodField()
    montant_affecte = serializers.SerializerMethodField()
    recu_par_nom   = serializers.SerializerMethodField()
    remis_par_nom  = serializers.SerializerMethodField()
    encaisse_par_nom = serializers.SerializerMethodField()
    impaye_par_nom = serializers.SerializerMethodField()
    exercice_nom   = serializers.CharField(source='exercice.annee_scolaire', read_only=True)

    class Meta:
        from .models import ChequeRecu
        model  = ChequeRecu
        fields = '__all__'
        # Le cycle du chèque (statut, dates, auteurs, compte) ne se change que
        # par les actions du registre, qui passent les écritures.
        read_only_fields = [
            'tenant', 'exercice', 'statut', 'compte_reception', 'reference_groupe',
            'date_reception', 'recu_par', 'date_remise', 'bordereau', 'no_piece_remise',
            'remis_par', 'date_encaissement', 'encaisse_par', 'date_impaye',
            'motif_impaye', 'impaye_par', 'montant',
        ]

    def get_recus(self, c):
        return [{'paiement': str(a.paiement_id), 'no_piece': a.paiement.no_piece,
                 'eleve': a.paiement.eleve.nom_complet, 'montant': float(a.montant),
                 'statut': a.paiement.statut}
                for a in c.affectations.all()]

    def get_montant_affecte(self, c):
        return round(sum(float(a.montant) for a in c.affectations.all()
                         if a.paiement.statut == 'ACTIF'), 2)

    def get_recu_par_nom(self, c):     return _nom_user(c.recu_par)
    def get_remis_par_nom(self, c):    return _nom_user(c.remis_par)
    def get_encaisse_par_nom(self, c): return _nom_user(c.encaisse_par)
    def get_impaye_par_nom(self, c):   return _nom_user(c.impaye_par)
