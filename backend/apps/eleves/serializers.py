from rest_framework import serializers
from django.utils import timezone
from .models import (ChampFiche, Eleve, EleveService, Famille, FormuleEleve, FormuleSection,
                     Organisme, PriseEnChargeOrganisme, ResponsableFamille, Section, Service)

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
            if 'composition_adhesion' not in attrs and self.instance is None:
                attrs['composition_adhesion'] = []
        else:
            # Le premier mois d'avance ne concerne qu'un service mensuel.
            attrs['premier_mois_a_inscription'] = False
        if 'composition_adhesion' in attrs:
            elements = []
            for el in attrs['composition_adhesion'] or []:
                libelle = str((el or {}).get('libelle', '')).strip()[:100]
                try:
                    montant = float((el or {}).get('montant', 0) or 0)
                except (TypeError, ValueError):
                    raise serializers.ValidationError({'composition_adhesion': f'Montant invalide pour « {libelle} ».'})
                if not libelle:
                    continue
                if montant < 0:
                    raise serializers.ValidationError({'composition_adhesion': f'« {libelle} » : montant négatif.'})
                elements.append({'libelle': libelle, 'montant': montant,
                                 'premiere_fois': bool(el.get('premiere_fois'))})
            libelles = [e['libelle'].lower() for e in elements]
            if len(set(libelles)) != len(libelles):
                raise serializers.ValidationError({'composition_adhesion': 'Deux éléments portent le même libellé.'})
            attrs['composition_adhesion'] = elements
        return attrs


class FormuleSectionSerializer(serializers.ModelSerializer):
    frais_mensualite = serializers.FloatField(min_value=0)
    nb_eleves = serializers.SerializerMethodField()

    class Meta:
        model  = FormuleSection
        fields = ['id', 'section', 'nom', 'frais_mensualite', 'ordre', 'actif', 'nb_eleves']

    def get_nb_eleves(self, obj):
        return obj.eleves.values('eleve').distinct().count()

    def validate_section(self, section):
        request = self.context.get('request')
        from core.tenant import get_tenant
        if request is not None and section.tenant_id != get_tenant(request).id:
            raise serializers.ValidationError('Section inconnue.')
        return section


class ChampFicheSerializer(serializers.ModelSerializer):
    """Un champ ajouté par l'école à la fiche élève."""
    nb_renseignes = serializers.SerializerMethodField()

    class Meta:
        model  = ChampFiche
        fields = ['id', 'libelle', 'type_champ', 'options', 'groupe', 'obligatoire',
                  'ordre', 'actif', 'nb_renseignes']

    def get_nb_renseignes(self, obj):
        """Combien de fiches portent une réponse : une école hésite à supprimer
        un champ sans savoir ce qu'elle perd."""
        return sum(1 for valeurs in Eleve.objects.filter(tenant=obj.tenant)
                   .values_list('champs_perso', flat=True)
                   if str(obj.id) in (valeurs or {}) and str((valeurs or {}).get(str(obj.id)) or '').strip())

    def validate(self, attrs):
        type_champ = attrs.get('type_champ', getattr(self.instance, 'type_champ', 'TEXTE'))
        options = attrs.get('options', getattr(self.instance, 'options', None) or [])
        if type_champ == 'LISTE':
            propres = [str(o).strip() for o in options if str(o).strip()]
            if len(propres) < 2:
                raise serializers.ValidationError(
                    {'options': 'Une liste de choix demande au moins deux valeurs.'})
            attrs['options'] = propres
        else:
            attrs['options'] = []
        libelle = str(attrs.get('libelle', getattr(self.instance, 'libelle', '')) or '').strip()
        if not libelle:
            raise serializers.ValidationError({'libelle': 'Donnez un nom au champ.'})
        attrs['libelle'] = libelle
        return attrs


def valider_champs_perso(tenant, valeurs, existantes=None, partiel=False):
    """Nettoie les réponses aux champs de l'école ({champ_id: valeur}).

    Un champ obligatoire vide est refusé ; une valeur hors liste aussi ; un
    champ inconnu (supprimé depuis) est ignoré. `partiel` : mise à jour qui ne
    touche qu'une partie des champs — les autres gardent leur réponse.
    """
    champs = {str(c.id): c for c in ChampFiche.objects.filter(tenant=tenant, actif=True)}
    propres = dict(existantes or {}) if partiel else {}
    for cid, brut in (valeurs or {}).items():
        champ = champs.get(str(cid))
        if champ is None:
            continue
        valeur = '' if brut is None else brut
        if isinstance(valeur, str):
            valeur = valeur.strip()
        if valeur in ('', None):
            propres.pop(str(cid), None)
            continue
        if champ.type_champ == 'NOMBRE':
            try:
                valeur = float(valeur)
            except (TypeError, ValueError):
                raise serializers.ValidationError({champ.libelle: 'Nombre attendu.'})
        elif champ.type_champ == 'DATE':
            import datetime as _dt
            try:
                valeur = _dt.date.fromisoformat(str(valeur)[:10]).isoformat()
            except ValueError:
                raise serializers.ValidationError({champ.libelle: 'Date attendue (AAAA-MM-JJ).'})
        elif champ.type_champ == 'OUI_NON':
            valeur = bool(valeur) and str(valeur).lower() not in ('false', 'non', '0')
        elif champ.type_champ == 'LISTE' and str(valeur) not in champ.options:
            raise serializers.ValidationError(
                {champ.libelle: f"Choisissez une valeur parmi : {', '.join(champ.options)}."})
        propres[str(cid)] = valeur
    for cid, champ in champs.items():
        if champ.obligatoire and not str(propres.get(cid, '') or '').strip():
            raise serializers.ValidationError({champ.libelle: 'Ce champ est obligatoire.'})
    return propres


class EleveSerializer(serializers.ModelSerializer):
    section_nom                  = serializers.CharField(source='section.nom', read_only=True)
    classe_nom                   = serializers.SerializerMethodField()
    # Fratrie : le nom du foyer et le contact réellement joignable. Le contact
    # vient de contact_effectif() et de nulle part ailleurs — c'est ce qui
    # garantit que la fiche, l'écran des rappels et le SMS donnent le même
    # numéro pour le même enfant.
    famille_nom                  = serializers.CharField(source='famille.nom', read_only=True,
                                                         default='')
    famille_code                 = serializers.CharField(source='famille.code', read_only=True,
                                                         default='')
    contact                      = serializers.SerializerMethodField()
    date_inscription_libelle     = serializers.ReadOnlyField()
    total_theorique              = serializers.ReadOnlyField()
    total_attendu                = serializers.ReadOnlyField()
    montant_pec_inscription      = serializers.ReadOnlyField()
    montant_pec_mensualite_mensuel = serializers.ReadOnlyField()
    montant_pec_annuel           = serializers.ReadOnlyField()
    montant_services_annuel      = serializers.ReadOnlyField()
    # « GUEYE Moustapha » : clé du tri alphabétique à l'écran, la même que celle
    # des listes PDF (apps/eleves/tri.py) — deux tris séparés divergeraient.
    nom_tri                      = serializers.SerializerMethodField()
    abonnements                  = serializers.SerializerMethodField()
    # Pour chaque service : première adhésion ou non (kimono dû ou pas).
    abonnements_detail           = serializers.SerializerMethodField()
    # Formule en vigueur ce mois-ci, et l'historique des changements datés.
    formule                      = serializers.SerializerMethodField()
    formules_historique          = serializers.SerializerMethodField()
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
    # Bourse : qui doit quoi. Le dû total ne bouge pas, il se répartit.
    part_organisme               = serializers.ReadOnlyField()
    part_famille                 = serializers.ReadOnlyField()
    reste_organisme              = serializers.ReadOnlyField()
    reste_famille                = serializers.ReadOnlyField()
    organisme_nom                = serializers.SerializerMethodField()

    def get_organisme_nom(self, obj):
        pec = obj.pec_organisme
        return pec.organisme.nom if pec else ''
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
        self._valider_champs_perso(attrs)
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
        # Revenir d'une sortie n'est pas un simple changement de statut : c'est
        # une RÉINTÉGRATION, avec ses règles (motif, dette reconnue, mois
        # d'absence non facturés — voir reintegration.py). Seule la correction
        # d'une sortie posée par erreur LE JOUR MÊME passe encore par ici.
        instance = self.instance
        if (instance is not None and not sort
                and instance.statut in STATUTS_SORTIE
                and instance.date_sortie and instance.date_sortie < timezone.now().date()):
            raise serializers.ValidationError({'statut': (
                f"{instance.nom_complet} est sorti le {instance.date_sortie:%d/%m/%Y}. "
                "Pour le faire revenir, utilisez « Réintégrer » : la date de retour, "
                "le motif et la dette du départ y sont vérifiés.")})
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

    def get_contact(self, obj):
        from .familles import contact_effectif
        return contact_effectif(obj)

    def get_classe_nom(self, obj):
        return obj.classe.nom if obj.classe_id else ''

    def get_abonnements(self, obj):
        """Liste des IDs de services auxquels l'élève est abonné."""
        return [str(ab.service_id) for ab in obj.abonnements.all()]

    def _tenant(self):
        tenant = getattr(self.instance, 'tenant', None) or self.context.get('tenant')
        if tenant is None:
            from core.tenant import get_tenant
            request = self.context.get('request')
            tenant = get_tenant(request) if request is not None else None
        return tenant

    def _valider_champs_perso(self, attrs):
        """Réponses aux champs de l'école : validées à la création, et dès que la
        requête y touche. Une fiche ancienne ne se bloque pas parce que l'école a
        ajouté un champ obligatoire depuis — on ne le réclame qu'à la prochaine
        saisie de ces champs."""
        touche = 'champs_perso' in self.initial_data
        if not touche and self.partial:
            return
        tenant = self._tenant()
        if tenant is not None:
            attrs['champs_perso'] = valider_champs_perso(
                tenant, self.initial_data.get('champs_perso') or {},
                existantes=getattr(self.instance, 'champs_perso', None),
                partiel=self.partial and touche)

    def _sync_abonnements(self, eleve):
        """Crée/supprime les abonnements selon la liste 'abonnements' (IDs de services) en entrée.

        À la création d'un abonnement, `premiere_adhesion` vaut vrai sauf si une
        fiche d'une année précédente du même enfant suivait déjà ce service.
        `premieres_adhesions` ({service_id: bool}) permet à l'école de corriger.
        """
        ids = self.initial_data.get('abonnements', None)
        corrections = self.initial_data.get('premieres_adhesions') or {}
        existing = {str(ab.service_id): ab for ab in eleve.abonnements.all()}
        if ids is not None:
            wanted = {str(i) for i in ids}
            deja_suivis = None
            for sid in wanted - set(existing):
                svc = Service.objects.filter(id=sid, tenant=eleve.tenant).first()
                if not svc:
                    continue
                if deja_suivis is None:
                    deja_suivis = services_deja_suivis(eleve)
                existing[sid] = EleveService.objects.create(
                    tenant=eleve.tenant, eleve=eleve, service=svc,
                    premiere_adhesion=sid not in deja_suivis)
            for sid in set(existing) - wanted:
                existing.pop(sid).delete()
        for sid, valeur in corrections.items():
            ab = existing.get(str(sid))
            if ab is not None and ab.premiere_adhesion != bool(valeur):
                ab.premiere_adhesion = bool(valeur)
                ab.save(update_fields=['premiere_adhesion', 'updated_at'])

    def _sync_formule(self, eleve, section_changee):
        """Formule choisie sur la fiche (`formule` : id).

        Sans historique, ou avec une seule ligne, c'est le choix initial : il
        vaut pour toute l'année. Un changement en cours d'année passe par
        l'action datée « changer de formule », jamais par ici — sinon on
        réécrirait les mois passés.
        """
        if section_changee:
            eleve.formules_eleve.exclude(formule__section_id=eleve.section_id).delete()
        if 'formule' not in self.initial_data:
            return
        fid = self.initial_data.get('formule')
        lignes = list(eleve.formules_eleve.all())
        if not fid:
            if len(lignes) <= 1:
                eleve.formules_eleve.all().delete()
            return
        formule = FormuleSection.objects.filter(id=fid, tenant=eleve.tenant,
                                                section_id=eleve.section_id).first()
        if formule is None:
            raise serializers.ValidationError({'formule': "Cette formule n'appartient pas à la section de l'élève."})
        if len(lignes) > 1:
            return
        from .echeancier import mois_factures
        mois = mois_factures(eleve, jusqu_a_la_sortie=False)
        debut = mois[0] if mois else (eleve.exercice.date_debut.month if eleve.exercice_id else 1)
        if lignes:
            ligne = lignes[0]
            ligne.formule, ligne.mois_debut = formule, debut
            ligne.save(update_fields=['formule', 'mois_debut', 'updated_at'])
        else:
            FormuleEleve.objects.create(tenant=eleve.tenant, eleve=eleve, formule=formule,
                                        mois_debut=debut)

    def create(self, validated_data):
        eleve = super().create(validated_data)
        self._sync_abonnements(eleve)
        self._sync_formule(eleve, section_changee=False)
        return eleve

    def update(self, instance, validated_data):
        ancienne_section = instance.section_id
        eleve = super().update(instance, validated_data)
        self._sync_abonnements(eleve)
        self._sync_formule(eleve, section_changee=eleve.section_id != ancienne_section)
        return eleve

    def get_abonnements_detail(self, obj):
        return [{'service': str(ab.service_id), 'nom': ab.service.nom,
                 'premiere_adhesion': ab.premiere_adhesion,
                 'a_des_frais_premiere_fois': any(el.get('premiere_fois')
                                                  for el in ab.service.composition_adhesion or [])}
                for ab in obj.abonnements.all()]

    def get_nom_tri(self, obj):
        from .tri import libelle_tri
        return libelle_tri(obj.nom_complet)

    def get_formule(self, obj):
        f = obj.formule_actuelle
        return str(f.id) if f else None

    def get_formules_historique(self, obj):
        return [{'formule': str(l.formule_id), 'nom': l.formule.nom, 'mois_debut': l.mois_debut,
                 'mois_libelle': _NOMS_MOIS.get(l.mois_debut, str(l.mois_debut)),
                 'mensualite': float(l.formule.frais_mensualite)}
                for l in obj._formules_datees()]

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

def services_deja_suivis(eleve):
    """Ids des services que l'enfant suivait sur une fiche d'une année précédente."""
    from .parcours import fiches_du_meme_eleve
    debut = eleve.exercice.date_debut if eleve.exercice_id else None
    suivis = set()
    for fiche in fiches_du_meme_eleve(eleve):
        if fiche.id == eleve.id or (debut and fiche.exercice.date_debut >= debut):
            continue
        suivis |= {str(ab.service_id) for ab in fiche.abonnements.all()}
    return suivis


class SectionSerializer(serializers.ModelSerializer):
    total_annuel = serializers.ReadOnlyField()
    formules = FormuleSectionSerializer(many=True, read_only=True)
    frais_inscription  = serializers.FloatField(required=False, default=0)
    frais_mensualite   = serializers.FloatField(required=False, default=0)
    frais_uniforme     = serializers.FloatField(required=False, default=0)
    frais_fournitures  = serializers.FloatField(required=False, default=0)
    # Ce que paie un ancien élève à la place de l'inscription, quand l'école a
    # activé le renouvellement.
    frais_renouvellement = serializers.FloatField(required=False, default=0)
    tarif_demi_journee = serializers.FloatField(required=False, default=0, min_value=0)
    tarif_journee      = serializers.FloatField(required=False, default=0, min_value=0)
    niveau_nom         = serializers.CharField(source='niveau.nom', read_only=True, default='')

    class Meta:
        model  = Section
        fields = '__all__'
        extra_kwargs = {
            'tenant': {'required': False, 'read_only': True},
            'niveau': {'required': False, 'allow_null': True},
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

        # À la journée, le mois ne coûte que ses jours de présence : une
        # mensualité restée saisie s'y ajouterait à chaque mois, en silence.
        mode = attrs.get('mode_tarif', getattr(self.instance, 'mode_tarif', 'MENSUEL'))
        if mode == 'JOURNEE':
            attrs['frais_mensualite'] = 0
            demi = attrs.get('tarif_demi_journee', getattr(self.instance, 'tarif_demi_journee', 0))
            journee = attrs.get('tarif_journee', getattr(self.instance, 'tarif_journee', 0))
            if not (float(demi or 0) > 0 or float(journee or 0) > 0):
                raise serializers.ValidationError(
                    {'tarif_journee': "Indiquez au moins un tarif (½ journée ou journée)."})
        return attrs

class OrganismeSerializer(serializers.ModelSerializer):
    type_libelle = serializers.CharField(source='get_type_display', read_only=True)
    nb_boursiers = serializers.SerializerMethodField()

    class Meta:
        model  = Organisme
        fields = '__all__'
        extra_kwargs = {'tenant': {'required': False, 'read_only': True}}

    def get_nb_boursiers(self, obj):
        # Annoté par la vue quand la liste est chargée : sinon une requête par
        # organisme, et le tableau redevient lent dès qu'il y en a vingt.
        if hasattr(obj, 'nb_boursiers_sql'):
            return obj.nb_boursiers_sql
        return obj.prises_en_charge.count()


class PriseEnChargeOrganismeSerializer(serializers.ModelSerializer):
    organisme_nom  = serializers.CharField(source='organisme.nom', read_only=True)
    organisme_type = serializers.CharField(source='organisme.get_type_display',
                                           read_only=True)
    montant_annuel = serializers.ReadOnlyField()
    eleve_nom      = serializers.CharField(source='eleve.nom_complet', read_only=True)
    matricule      = serializers.CharField(source='eleve.matricule', read_only=True)

    class Meta:
        model  = PriseEnChargeOrganisme
        fields = '__all__'
        extra_kwargs = {
            'tenant':   {'required': False, 'read_only': True},
            'exercice': {'required': False},
        }

    def validate(self, attrs):
        """Une prise en charge à zéro n'a pas de sens : elle laisserait croire
        qu'un organisme suit l'élève alors qu'il ne doit rien."""
        inscription = attrs.get('montant_inscription',
                                getattr(self.instance, 'montant_inscription', 0))
        mensualite = attrs.get('montant_mensualite',
                               getattr(self.instance, 'montant_mensualite', 0))
        services = attrs.get('couvre_services',
                             getattr(self.instance, 'couvre_services', False))
        if not (float(inscription or 0) or float(mensualite or 0) or services):
            raise serializers.ValidationError(
                "Indiquez au moins un montant pris en charge, ou cochez les "
                "services : sinon l'organisme ne doit rien pour cet élève.")
        return attrs


class ResponsableFamilleSerializer(serializers.ModelSerializer):
    lien_libelle = serializers.CharField(source='get_lien_display', read_only=True)

    class Meta:
        model  = ResponsableFamille
        fields = '__all__'
        extra_kwargs = {
            'tenant':  {'required': False, 'read_only': True},
            'famille': {'required': False},
        }


class FamilleSerializer(serializers.ModelSerializer):
    # Saisis avec la famille : créer le foyer puis ses responsables en deux
    # écrans obligerait l'école à enregistrer une famille sans personne à
    # appeler, ce que ce regroupement est justement censé éviter.
    responsables = ResponsableFamilleSerializer(many=True, required=False)
    nb_enfants   = serializers.SerializerMethodField()
    contact      = serializers.SerializerMethodField()

    class Meta:
        model  = Famille
        fields = '__all__'
        extra_kwargs = {
            'tenant': {'required': False, 'read_only': True},
            # Attribué par l'école à l'enregistrement (FAM-0001) : une saisie
            # libre finirait en doublon, et le code est unique par tenant.
            'code':   {'required': False, 'read_only': True},
        }

    def get_nb_enfants(self, obj):
        # Annoté par la vue sur la liste : sinon une requête par famille.
        if hasattr(obj, 'nb_enfants_sql'):
            return obj.nb_enfants_sql
        return obj.eleves.count()

    def get_contact(self, obj):
        responsable = obj.responsable_principal
        if responsable is None:
            return None
        return {'nom': responsable.nom, 'telephone': responsable.telephone,
                'lien': responsable.get_lien_display()}

    def create(self, validated_data):
        responsables = validated_data.pop('responsables', [])
        famille = Famille.objects.create(**validated_data)
        self._enregistrer_responsables(famille, responsables)
        return famille

    def update(self, instance, validated_data):
        responsables = validated_data.pop('responsables', None)
        for champ, valeur in validated_data.items():
            setattr(instance, champ, valeur)
        instance.save()
        if responsables is not None:
            # Remplacement en bloc : l'écran envoie la liste complète, et un
            # responsable retiré à l'écran doit disparaître de la base.
            instance.responsables.all().delete()
            self._enregistrer_responsables(instance, responsables)
        return instance

    def _enregistrer_responsables(self, famille, responsables):
        """Écrit les responsables en garantissant un seul principal.

        La contrainte de base refuse deux principaux pour une même famille :
        sans arbitrage ici, une saisie où l'école coche deux fois se solderait
        par une 500 au lieu d'un enregistrement.
        """
        principal_pris = False
        for donnees in responsables:
            donnees.pop('famille', None)
            donnees.pop('tenant', None)
            voulu = donnees.pop('principal', False)
            principal = bool(voulu) and not principal_pris
            principal_pris = principal_pris or principal
            ResponsableFamille.objects.create(famille=famille, tenant=famille.tenant,
                                              principal=principal, **donnees)
        # Personne de désigné : le premier saisi devient le contact, sinon
        # l'école se retrouve avec une famille que rien ne permet d'appeler.
        if not principal_pris:
            premier = famille.responsables.first()
            if premier is not None:
                premier.principal = True
                premier.save(update_fields=['principal'])
