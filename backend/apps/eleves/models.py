import datetime
from django.db import models
from core.models import TenantModel


class Section(TenantModel):
    nom                = models.CharField(max_length=100)
    frais_inscription  = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    frais_mensualite   = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    frais_uniforme     = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    frais_fournitures  = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # Composition libre de l'inscription globale, définie par l'école :
    # [{"libelle": "Frais de dossier", "montant": 5000}, ...]. Quand elle est
    # renseignée, frais_inscription = somme des éléments (calculée au save du
    # serializer) — les paiements/reçus continuent de travailler sur le total.
    composition_inscription = models.JSONField(default=list, blank=True)
    ordre              = models.IntegerField(default=0)

    class Meta:
        db_table = 'sections'
        ordering = ['ordre', 'nom']

    def __str__(self):
        return self.nom

    def total_annuel_pour(self, nb_mois):
        """Total annuel brut pour un nombre de mensualités donné."""
        return (self.frais_inscription + self.frais_uniforme +
                self.frais_fournitures + (self.frais_mensualite * nb_mois))

    @property
    def total_annuel(self):
        """Rétro-compat affichage (admin/serializer) — base 10 mois.
        Le calcul réel par élève passe par total_annuel_pour(exercice.nb_mensualites)."""
        return self.total_annuel_pour(10)


class Eleve(TenantModel):
    GENRE_CHOICES  = [('G', 'Garçon'), ('F', 'Fille')]
    STATUT_CHOICES = [
        ('INSCRIT',   'Inscrit'),
        ('TRANSFERE', 'Transféré'),
        ('ABANDONNE', 'Abandonné'),
        ('DIPLOME',   'Diplômé'),
    ]
    PRISE_EN_CHARGE_CHOICES = [
        ('ORPHELIN',        'Orphelin'),
        ('HANDICAP',        'Handicap'),
        ('FAMILLE_DEMUNIE', 'Famille démunie'),
        ('AUTRE',           'Autre'),
    ]
    TYPE_PEC_CHOICES = [
        ('INSCRIPTION',  "Frais d'inscription uniquement"),
        ('MENSUALITES',  'Mensualités uniquement'),
        ('TOTALE',       'Prise en charge totale'),
    ]
    # Daara (licence Taxawu Daara) : un ndongo « passager » arrive à n'importe
    # quel moment (ex. vacances de son école classique) pour une durée convenue.
    # Il doit nb_mois_passager mensualités à partir de sa date d'entrée — ni les
    # mois de l'exercice avant son arrivée, ni le plafond de fin d'exercice.
    # Si son séjour déborde sur l'exercice suivant, on le réinscrit avec les
    # mois restants (le solde impayé passe par la reprise à la clôture).
    REGIME_CHOICES = [
        ('EXERCICE', "Permanent — mensualités de l'exercice"),
        ('PASSAGER', 'Passager — durée convenue en mois'),
    ]

    ETAT_SANTE_CHOICES = [
        ('SAIN',      'Sain'),
        ('SUIVI',     'Sous suivi médical'),
        ('CHRONIQUE', 'Maladie chronique'),
    ]

    exercice              = models.ForeignKey('paiements.Exercice', on_delete=models.CASCADE, related_name='eleves')
    section               = models.ForeignKey(Section, null=True, on_delete=models.SET_NULL, related_name='eleves')
    # Classe précise de l'élève (CI A, CI B…) au sein de sa section. Une section à classe
    # unique a une classe portant son nom. FK string pour éviter l'import circulaire.
    classe                = models.ForeignKey('academique.Classe', null=True, blank=True,
                                              on_delete=models.SET_NULL, related_name='eleves_classe')
    numero                = models.IntegerField(null=True, blank=True)
    matricule             = models.CharField(max_length=20, blank=True, null=True)
    # Matricule porté avant le passage au format promo (AAAA-CODE-NNNN).
    # Conservé pour que les carnets papier et les anciens reçus de l'école
    # restent exploitables : on retrouve l'élève par son ancien numéro.
    matricule_ancien      = models.CharField(max_length=20, blank=True,
                                             help_text="Matricule d'avant le rebasage")
    # ── Entrée dans l'établissement — figée à vie ─────────────────────────
    # date_inscription est repositionnée au début de chaque exercice pour le
    # prorata des mensualités : elle ne peut donc PAS servir de référence
    # historique. Ces deux champs, eux, ne bougent jamais et sont recopiés à
    # chaque réinscription — c'est le socle de la base « année après année ».
    annee_entree          = models.CharField(max_length=20, blank=True,
                                             help_text="Année scolaire d'entrée (promo), ex. 2025-2026")
    date_entree           = models.DateField(null=True, blank=True,
                                             help_text="Date de première entrée dans l'établissement")
    nom_complet           = models.CharField(max_length=200)
    genre                 = models.CharField(max_length=1, choices=GENRE_CHOICES, blank=True)
    date_naissance        = models.DateField(null=True, blank=True)
    lieu_naissance        = models.CharField(max_length=200, blank=True)
    nom_pere              = models.CharField(max_length=200, blank=True)
    telephone_pere        = models.CharField(max_length=20, blank=True)
    nom_mere              = models.CharField(max_length=200, blank=True)
    telephone_mere        = models.CharField(max_length=20, blank=True)
    # Tuteur — peut différer des parents (famille d'accueil, oncle, marabout…)
    nom_tuteur            = models.CharField(max_length=200, blank=True)
    telephone_tuteur      = models.CharField(max_length=20, blank=True)
    lien_tuteur           = models.CharField(max_length=100, blank=True,
                                             help_text="Lien avec l'élève (oncle, grand-père, tuteur légal…)")
    # Santé — état général + observations (allergies, traitements, maladies…)
    etat_sante            = models.CharField(max_length=20, choices=ETAT_SANTE_CHOICES,
                                             default='SAIN', blank=True)
    observations_sante    = models.TextField(blank=True,
                                             help_text='Allergies, maladies chroniques, traitements en cours…')
    date_inscription      = models.DateField(default=datetime.date.today,
                                              help_text="Date d'entrée — sert au prorata des mensualités dues")
    # Jour d'inscription inconnu (données historiques) : la date est stockée au
    # 1er du mois, mais on n'affiche que « Mois AAAA ». Le prorata n'utilise que
    # le mois et l'année — le jour est donc sans effet sur les calculs.
    date_inscription_jour_estime = models.BooleanField(default=False)
    regime                = models.CharField(max_length=10, choices=REGIME_CHOICES, default='EXERCICE')
    nb_mois_passager      = models.PositiveIntegerField(null=True, blank=True,
                                              help_text='Mensualités dues depuis la date d\'entrée (régime passager)')
    # Mois réellement dus, saisis par l'école — mêmes numéros que
    # Paiement.mois_regles (1=janvier … 12=décembre).
    # VIDE = le prorata automatique sur la date d'entrée fait foi : une école
    # qui ne touche à rien garde exactement le comportement d'avant. Renseigné,
    # il PRIME — l'école sait mieux que le calendrier quels mois elle facture
    # (entrée en fin de mois, vacances, arrangement particulier).
    mois_dus              = models.JSONField(default=list, blank=True,
                                             help_text='Mois facturés (1-12) — vide = prorata automatique')
    statut                = models.CharField(max_length=20, choices=STATUT_CHOICES, default='INSCRIT')
    # Prise en charge sociale — motif
    prise_en_charge       = models.CharField(max_length=20, choices=PRISE_EN_CHARGE_CHOICES, blank=True, null=True)
    obs_prise_en_charge   = models.TextField(blank=True)
    # Prise en charge — MONTANTS directs (plus simple à saisir). Le dû se calcule
    # « frais − PEC ». S'ils sont > 0, ils priment sur les anciens taux.
    pec_inscription       = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                                help_text="Montant pris en charge sur l'inscription (FCFA)")
    pec_mensualite        = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                                help_text="Montant pris en charge par mois (FCFA)")
    # Anciens taux — conservés pour compatibilité / migration.
    type_pec              = models.CharField(max_length=20, choices=TYPE_PEC_CHOICES, blank=True, null=True)
    taux_pec_inscription  = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                                 help_text='% réduction sur frais inscription')
    taux_pec_mensualite   = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                                 help_text='% réduction sur mensualités')
    taux_prise_en_charge  = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    # ── Réinscription & reliquat antérieur ────────────────────────────────
    # Une fiche appartient à UN exercice : au passage à l'année suivante, une
    # nouvelle fiche est créée et pointe vers celle de l'année précédente.
    # L'identité (matricule, numéro) est conservée — c'est le même enfant.
    eleve_precedent    = models.ForeignKey('self', null=True, blank=True,
                                           on_delete=models.SET_NULL, related_name='reinscriptions',
                                           help_text="Fiche du même élève sur l'exercice précédent")
    # Reste dû antérieur à l'exercice en cours, figé. Deux origines :
    #   - le report automatique d'un exercice à l'autre (reliquat_exercice_origine) ;
    #   - une SAISIE de migration, quand l'année d'avant n'existe pas dans le
    #     système — l'école arrive avec une ardoise et aucun détail exploitable
    #     (reliquat_note). Voir apps.paiements.reliquat_migration.
    # Ce n'est PAS un produit de l'exercice en cours (le 706 a été constaté
    # l'année où les frais sont nés) : il n'entre donc jamais dans
    # total_attendu, seulement dans le dû global — voir reste_a_payer_global.
    reliquat_anterieur = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                             help_text="Reste dû des années antérieures (FCFA)")
    reliquat_exercice_origine = models.ForeignKey('paiements.Exercice', null=True, blank=True,
                                                  on_delete=models.SET_NULL,
                                                  related_name='reliquats_reportes',
                                                  help_text="Exercice d'où provient le reliquat")
    # Origine libre, quand elle ne correspond à aucun exercice du système :
    # « 2024-2025 », « ardoise cahier », « ancien logiciel »… Volontairement un
    # texte et non une liste : sur le terrain, la provenance exacte de la dette
    # est rarement reconstituable, l'important est que l'école puisse l'assumer.
    reliquat_note = models.CharField(max_length=120, blank=True,
                                     help_text="Origine de l'impayé antérieur saisi à la migration")
    # Fiche ouverte UNIQUEMENT pour porter la créance d'un élève qui a quitté
    # l'établissement (diplômé, transféré, abandon) en laissant une ardoise.
    # Elle existe parce que l'à-nouveaux 411/890 doit être passé dans le
    # nouvel exercice — sans elle, la créance disparaîtrait du bilan. Mais
    # l'enfant n'est plus élève : elle est tenue hors de la liste et des
    # effectifs, et se consulte depuis « Anciens élèves ».
    fiche_creance = models.BooleanField(default=False,
                                        help_text="Fiche de suivi de créance — l'élève a quitté l'établissement")

    class Meta:
        db_table = 'eleves'
        ordering = ['numero', 'nom_complet']
        # Le matricule (AAAA-CODE-NNNNNN) est généré PAR école : son numéro est
        # séquentiel par tenant et le code établissement peut rester au défaut 'ETB'.
        # Il doit donc être unique par tenant, jamais globalement, sinon deux écoles
        # sur 'ETB' entrent en collision (2026-ETB-000001) → IntegrityError 500.
        # L'exercice fait partie de la clé : le même enfant garde son matricule
        # d'une année sur l'autre (réinscription = une fiche par exercice), il
        # ne doit être unique qu'À L'INTÉRIEUR d'un exercice.
        # Les NULL restent autorisés en multiple (matricule optionnel).
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'exercice', 'matricule'],
                                    name='uniq_matricule_par_exercice'),
        ]

    def __str__(self):
        return self.nom_complet

    MOIS_FR = ('', 'janvier', 'février', 'mars', 'avril', 'mai', 'juin',
               'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre')

    @property
    def date_inscription_libelle(self):
        """Affichage lisible : « Juillet 2025 » quand le jour est estimé
        (données historiques), sinon « JJ/MM/AAAA »."""
        d = self.date_inscription
        if not d:
            return ''
        if self.date_inscription_jour_estime:
            return f'{self.MOIS_FR[d.month].capitalize()} {d.year}'
        return d.strftime('%d/%m/%Y')

    # ── Prise en charge ──────────────────────────────────────────────────
    @property
    def montant_pec_inscription(self):
        """Montant pris en charge sur l'inscription — le champ fait foi.

        Plus de repli sur l'ancien taux : il rendait 0 INSAISISSABLE. Une école
        qui retirait une prise en charge en remettant le montant à zéro voyait
        le taux reprendre la main et la réduction revenir intacte. Les taux ont
        été matérialisés en montants par la migration 0024, ils ne servent plus
        qu'à l'historique."""
        if not self.section:
            return 0.0
        return round(min(float(self.pec_inscription or 0),
                         float(self.section.frais_inscription)), 2)

    @property
    def montant_pec_mensualite_mensuel(self):
        """Réduction sur une mensualité (montant mensuel) — voir ci-dessus."""
        if not self.section:
            return 0.0
        return round(min(float(self.pec_mensualite or 0),
                         float(self.section.frais_mensualite)), 2)

    @property
    def nb_mensualites_dues(self):
        """Nombre de mensualités réellement dues, au prorata de la date d'entrée.
        Ex. exercice débutant en octobre, élève inscrit en janvier → on ne compte
        pas oct/nov/déc. Plafonné à nb_mensualites de l'exercice.
        Régime PASSAGER (daara) : la durée convenue prime — le ndongo doit
        nb_mois_passager mensualités depuis son entrée, sans plafond de fin
        d'exercice (séjour à cheval → réinscrire avec les mois restants).

        Mois saisis par l'école (`mois_dus`) : ils priment sur tout le reste —
        c'est une décision explicite, elle ne se fait pas corriger par un
        calendrier."""
        if self.mois_dus:
            return len(self.mois_dus)
        if self.regime == 'PASSAGER' and self.nb_mois_passager:
            return self.nb_mois_passager
        if not self.exercice_id:
            return 10
        nb    = self.exercice.nb_mensualites
        debut = self.exercice.date_debut
        insc  = self.date_inscription or debut
        if insc <= debut:
            return nb
        mois_ecoules = (insc.year - debut.year) * 12 + (insc.month - debut.month)
        return max(0, nb - mois_ecoules)

    @property
    def montant_pec_annuel(self):
        """Total annuel pris en charge (inscription + mensualités dues × réduction mensualité)."""
        return round(self.montant_pec_inscription +
                     self.montant_pec_mensualite_mensuel * self.nb_mensualites_dues, 2)

    @property
    def total_theorique(self):
        """Total annuel brut sans prise en charge (mensualité × nb de mensualités dues)."""
        if not self.section:
            return 0.0
        return float(self.section.total_annuel_pour(self.nb_mensualites_dues))

    @property
    def frais_mensualite_effectif(self):
        """Mensualité réelle après prise en charge."""
        if not self.section:
            return 0.0
        base = float(self.section.frais_mensualite)
        return round(max(base - self.montant_pec_mensualite_mensuel, 0.0), 2)

    @property
    def montant_services_annuel(self):
        """Total annuel des services optionnels auxquels l'élève est abonné.
        Mensuel → montant × mensualités dues (prorata entrée) ; Unique → montant une fois.
        Les services ne sont PAS soumis à la prise en charge."""
        nb_mois = self.nb_mensualites_dues
        total = 0.0
        for ab in self.abonnements.all():
            s = ab.service
            total += float(s.montant) * (nb_mois if s.periodicite == 'MENSUEL' else 1)
        return round(total, 2)

    # ── Montants attendus / payés ─────────────────────────────────────────
    @property
    def total_attendu(self):
        """Total annuel réel attendu : frais section − prise en charge + services optionnels.

        Une fiche de créance ne doit RIEN au titre de l'année : l'enfant a
        quitté l'établissement, la fiche n'existe que pour porter son ardoise
        (qui, elle, est dans reliquat_anterieur). Lui compter la scolarité
        reviendrait à facturer une année qu'il ne fera pas."""
        if self.fiche_creance:
            return 0.0
        base = max(self.total_theorique - self.montant_pec_annuel, 0.0)
        return round(base + self.montant_services_annuel, 2)

    @property
    def total_paye(self):
        # Utilise le prefetch si disponible, sinon requête
        if hasattr(self, '_total_paye_cache'):
            return self._total_paye_cache
        from django.db.models import Sum
        result = self.paiements.aggregate(
            t=Sum('montant_inscription') + Sum('montant_mensualite') +
            Sum('montant_uniforme')    + Sum('montant_fournitures') +
            Sum('montant_cantine')     + Sum('montant_divers')
        )
        return result['t'] or 0

    @property
    def reste_a_payer(self):
        # float des deux côtés : total_attendu est un float, total_paye peut
        # être un Decimal (agrégat SQL) → sinon TypeError float − Decimal.
        return round(float(self.total_attendu) - float(self.total_paye), 2)

    # ── Reliquat antérieur (dette de l'exercice précédent) ────────────────
    @property
    def reliquat_paye(self):
        """Montant déjà encaissé sur le reliquat reporté.
        Utilise l'annotation `reliquat_paye_sql` quand elle existe (liste
        d'élèves, dashboard) pour éviter une requête par élève."""
        val = getattr(self, 'reliquat_paye_sql', None)
        if val is not None:
            return round(float(val), 2)
        from django.db.models import Sum
        agg = self.paiements.filter(statut='ACTIF').aggregate(t=Sum('montant_reliquat'))
        return round(float(agg['t'] or 0), 2)

    @property
    def reliquat_restant(self):
        """Dette de l'année précédente encore ouverte, en temps réel."""
        return round(max(float(self.reliquat_anterieur or 0) - self.reliquat_paye, 0.0), 2)

    @property
    def reste_a_payer_global(self):
        """Dû total toutes années confondues : reste de l'année + reliquat ouvert.
        C'est le montant que la famille doit réellement à l'établissement."""
        return round(self.reste_a_payer + self.reliquat_restant, 2)

    @property
    def reliquat_origine_libelle(self):
        """Origine du reliquat, pour les libellés (« Reliquat 2024-2025 »).
        L'exercice d'origine prime ; à défaut la note saisie à la migration."""
        if self.reliquat_exercice_origine_id and self.reliquat_exercice_origine:
            return self.reliquat_exercice_origine.annee_scolaire
        return self.reliquat_note or ''

    def mois_echus(self, today=None):
        """Nombre de mensualités échues à ce jour : mois commencés depuis l'entrée
        de l'élève (mois courant inclus), plafonné au nombre de mensualités dues.
        Le plafond nb_mensualites_dues couvre les deux régimes : fin d'exercice
        pour EXERCICE, durée convenue pour PASSAGER (qui peut dépasser l'exercice)."""
        from django.utils import timezone
        if not self.exercice_id:
            return 0
        today = today or timezone.now().date()
        debut = self.exercice.date_debut
        insc  = self.date_inscription or debut
        mois_avant = max(0, (insc.year - debut.year) * 12 + (insc.month - debut.month)) if insc > debut else 0
        elapsed_incl = (today.year - debut.year) * 12 + (today.month - debut.month) + 1
        return max(0, min(elapsed_incl - mois_avant, self.nb_mensualites_dues))

    def niveau_alerte_detail(self, total_paye, mensualites_payees, today=None):
        """Source de vérité unique des alertes paiement → (niveau, nb_mois_arrieres).

        Niveaux :
          - A_JOUR    : rien dû / entièrement payé
          - OK        : reliquat sur les mois à venir, mais aucun arriéré (à jour)
          - ATTENTION : 1 mois de retard
          - URGENT    : 2 mois de retard
          - CRITIQUE  : 3 mois de retard ou plus

        total_paye / mensualites_payees peuvent provenir d'annotations pour éviter
        les requêtes (cohérence garantie entre module Élèves et tableau de bord)."""
        total = float(self.total_attendu)
        paye  = float(total_paye)
        if total <= 0 or paye >= total:
            return ('A_JOUR', 0)

        mensualite = self.frais_mensualite_effectif  # tient compte de la prise en charge
        if mensualite <= 0:
            ratio = paye / total if total > 0 else 0
            return ('URGENT' if ratio < 0.5 else 'ATTENTION', 0)

        arrieres = max(0.0, self.mois_echus(today) * mensualite - float(mensualites_payees))
        nb_arr   = int(round(arrieres / mensualite))
        if nb_arr <= 0:
            return ('OK', 0)
        if nb_arr >= 3:
            return ('CRITIQUE', nb_arr)
        if nb_arr == 2:
            return ('URGENT', nb_arr)
        return ('ATTENTION', nb_arr)

    @property
    def niveau_alerte(self):
        from django.db.models import Sum
        agg = self.paiements.filter(statut='ACTIF').aggregate(
            tp=Sum('montant_inscription') + Sum('montant_mensualite') +
               Sum('montant_uniforme')    + Sum('montant_fournitures') +
               Sum('montant_cantine')     + Sum('montant_divers'),
            tm=Sum('montant_mensualite'),
        )
        niveau, _ = self.niveau_alerte_detail(agg['tp'] or 0, agg['tm'] or 0)
        return niveau


class Service(TenantModel):
    """Service optionnel proposé par l'école (cantine, karaté, transport...).
    L'élève s'y abonne librement ; le montant entre alors dans son total dû."""
    PERIODICITE_CHOICES = [
        ('UNIQUE',  'Paiement unique'),
        ('MENSUEL', 'Mensuel'),
    ]
    nom         = models.CharField(max_length=100)
    montant     = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    periodicite = models.CharField(max_length=10, choices=PERIODICITE_CHOICES, default='MENSUEL')
    # Période d'exigibilité d'un service à paiement UNIQUE :
    # None = dû à l'inscription ; 1..12 = dû au mois calendaire indiqué.
    mois_unique = models.PositiveSmallIntegerField(null=True, blank=True)
    actif       = models.BooleanField(default=True)

    class Meta:
        db_table = 'services'
        ordering = ['nom']

    def __str__(self):
        return self.nom


class EleveService(TenantModel):
    """Abonnement d'un élève à un service optionnel."""
    eleve   = models.ForeignKey(Eleve, on_delete=models.CASCADE, related_name='abonnements')
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='abonnements')

    class Meta:
        db_table = 'eleve_services'
        unique_together = ['tenant', 'eleve', 'service']

    def __str__(self):
        return f"{self.eleve} → {self.service}"
