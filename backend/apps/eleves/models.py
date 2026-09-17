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
    # Ce que paie un ANCIEN élève à la place de l'inscription, quand l'école a
    # activé le renouvellement (Tenant.renouvellement_actif). Le montant varie
    # d'un niveau à l'autre comme l'inscription. Sans effet tant que le réglage
    # de l'école est désactivé.
    frais_renouvellement = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    ordre              = models.IntegerField(default=0)

    # ── Facturation à la journée (garderie ponctuelle) ───────────────────
    # Une crèche accueille, dans la même classe, des enfants au mois et
    # d'autres à la journée. Pour ceux-là, rien n'est dû d'avance : le dû
    # naît de chaque jour de présence (voir apps/eleves/garderie.py), et
    # chaque paiement s'y impute quel que soit le rythme de la famille —
    # au jour, à la semaine, au mois.
    MODE_TARIF_CHOICES = [
        ('MENSUEL', 'Au mois'),
        ('JOURNEE', 'À la journée'),
    ]
    mode_tarif         = models.CharField(max_length=10, choices=MODE_TARIF_CHOICES,
                                          default='MENSUEL')
    tarif_demi_journee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tarif_journee      = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        db_table = 'sections'
        ordering = ['ordre', 'nom']

    def __str__(self):
        return self.nom

    def total_annuel_pour(self, nb_mois, frais_entree=None):
        """Total annuel brut pour un nombre de mensualités donné.

        `frais_entree` remplace l'inscription — c'est le renouvellement pour un
        ancien élève d'une école qui en pratique un."""
        from decimal import Decimal
        entree = (self.frais_inscription if frais_entree is None
                  else Decimal(str(frais_entree)))
        return (entree + self.frais_uniforme +
                self.frais_fournitures + (self.frais_mensualite * nb_mois))

    @property
    def a_la_journee(self):
        return self.mode_tarif == 'JOURNEE'

    def tarif_formule(self, formule):
        """Le tarif d'une formule de garderie (DEMI_JOURNEE ou JOURNEE)."""
        return self.tarif_demi_journee if formule == 'DEMI_JOURNEE' else self.tarif_journee

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
    # Répartition du déjà-payé sur les mois, corrigée à la main par l'école :
    # {"7": 60000, "8": 30000}. VIDE = imputation automatique (mois désignés
    # par les paiements, puis les plus anciens ouverts).
    # Le TOTAL est verrouillé sur ce qui a réellement été encaissé : cette
    # correction déplace de l'argent entre les mois, elle n'en crée pas.
    # Corriger un MONTANT encaissé passe par la modification du paiement, qui
    # écrit au grand livre — sinon la fiche et la comptabilité divergeraient.
    imputation_mois       = models.JSONField(default=dict, blank=True,
                                             help_text='Répartition manuelle du payé par mois')
    # Montant DÛ pour un mois donné, quand il diffère de la mensualité
    # standard : {"7": 30000}. Vide = tarif normal.
    # Deux usages du terrain, indissociables du mois d'entrée :
    #   - un élève entré le 16 juillet à qui l'école accorde une réduction
    #     sur juillet, qu'il n'aura vécu qu'à moitié ;
    #   - un mois déjà réglé dans les frais d'inscription, donc à 0.
    # Zéro est une valeur légitime et distincte de « pas de montant saisi » :
    # d'où un dict, où seule la présence de la clé compte.
    montants_mois         = models.JSONField(default=dict, blank=True,
                                             help_text='Montant dû par mois quand il diffère du tarif')
    statut                = models.CharField(max_length=20, choices=STATUT_CHOICES, default='INSCRIT')
    # Date de départ de l'établissement (diplôme, transfert, abandon). Arrête
    # l'horloge des arriérés : sans elle, un abandon de mars continue
    # d'accumuler des mois de retard jusqu'en décembre et la fiche annonce
    # CRITIQUE pour une scolarité que l'enfant n'a jamais suivie.
    date_sortie           = models.DateField(null=True, blank=True,
                                             help_text="Date de sortie de l'établissement")
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

    # ── Frais d'entrée de l'année : inscription ou renouvellement ────────
    # Un daara n'inscrit un ndongo qu'UNE fois, à son arrivée. Les années
    # suivantes il ne paie plus l'inscription mais un renouvellement, souvent
    # moins cher et parfois nommé autrement selon l'établissement.
    #
    # Le système réclamait l'inscription à tout le monde, chaque année. Les
    # écoles s'en sortaient en inscrivant sur CHAQUE ancien élève une fausse
    # prise en charge égale à l'inscription, pour que le total annuel dû reste
    # juste : une donnée fausse, recopiée à la main tous les ans, qui faisait
    # passer une école entière pour prise en charge.
    @property
    def est_renouvelant(self):
        """L'élève a UNE ANNÉE RÉVOLUE dans l'établissement.

        Ce n'est pas « entré lors d'un exercice précédent » : un élève inscrit
        le 20 octobre 2025 ne doit pas de renouvellement en 2026, il n'a pas
        encore fait son année. C'est l'ancienneté qui compte, pas le calendrier
        de l'école — et elle se mesure à la date d'entrée, figée à vie.

        Trois sources, dans cet ordre :

          1. `date_entree` — figée à vie, recopiée à chaque réinscription. C'est
             la bonne réponse dès que l'école a une année d'historique dans
             l'application, ou qu'elle a passé le rebasage des matricules.
          2. `annee_entree`, la promo, quand seule elle est renseignée.
          3. `date_inscription` en dernier recours. Le formulaire de création
             l'intitule « Date d'entrée » : c'est là que les écoles migrées ont
             saisi la vraie date d'arrivée. Repositionnée au début de l'exercice
             elle dira « nouveau », ce qui est le repli sûr.

        Aucune de ces sources ne peut inventer un renouvellement : sans donnée,
        l'élève est un nouvel entrant et doit son inscription. On ne retire pas
        un dû sur une absence d'information."""
        if not self.exercice_id:
            return False
        if self.annee_entree and not self.date_entree:
            return self.annee_entree.strip() != (self.exercice.annee_scolaire or '').strip()
        reference = self.date_entree or self.date_inscription
        if not reference:
            return False
        # L'ancienneté exigée est un RÉGLAGE de l'école : Shoumoul retient
        # 9 mois, une école qui raisonne en années pleines en retiendra 12.
        # Mesurée au premier jour de l'exercice, pour qu'un élève ne change pas
        # de statut en cours d'année. Un élève entré pendant l'exercice en cours
        # en est forcément exclu : sa date d'entrée est postérieure au début.
        from dateutil.relativedelta import relativedelta
        mois = int(getattr(self.tenant, 'anciennete_renouvellement_mois', 12) or 12)
        return reference <= self.exercice.date_debut - relativedelta(months=mois)

    @property
    def renouvellement_du(self):
        """L'école pratique le renouvellement ET cet élève y est soumis."""
        return bool(getattr(self.tenant, 'renouvellement_actif', False)
                    and self.est_renouvelant)

    @property
    def frais_entree(self):
        """Ce que l'élève doit à l'entrée de l'année, avant prise en charge :
        son inscription s'il arrive, son renouvellement s'il était déjà là."""
        if not self.section:
            return 0.0
        return float(self.section.frais_renouvellement if self.renouvellement_du
                     else self.section.frais_inscription)

    @property
    def libelle_frais_entree(self):
        """« Inscription », ou le mot que l'école donne au renouvellement."""
        if not self.renouvellement_du:
            return 'Inscription'
        return getattr(self.tenant, 'libelle_renouvellement', '') or 'Renouvellement'

    # ── Prise en charge ──────────────────────────────────────────────────
    @property
    def montant_pec_inscription(self):
        """Montant pris en charge sur les frais d'entrée — le champ fait foi.

        Plus de repli sur l'ancien taux : il rendait 0 INSAISISSABLE. Une école
        qui retirait une prise en charge en remettant le montant à zéro voyait
        le taux reprendre la main et la réduction revenir intacte. Les taux ont
        été matérialisés en montants par la migration 0024, ils ne servent plus
        qu'à l'historique.

        Plafonné aux frais d'entrée RÉELLEMENT dus : chez un ancien élève, c'est
        le renouvellement. Plafonner sur l'inscription laisserait une prise en
        charge dépasser le dû et rendrait un reste négatif."""
        if not self.section:
            return 0.0
        return round(min(float(self.pec_inscription or 0), self.frais_entree), 2)

    @property
    def montant_pec_mensualite_mensuel(self):
        """Réduction sur une mensualité (montant mensuel) — voir ci-dessus.
        Celle du mois en cours quand la formule de l'enfant a changé."""
        return self.pec_du_mois(None)

    # ── Formule (crèche : 08H-13H, 08H-17H…) ─────────────────────────────
    # Une section peut proposer plusieurs formules, chacune avec sa mensualité.
    # L'enfant en change en cours d'année : le changement est DATÉ
    # (`FormuleEleve.mois_debut`), et chaque mois est facturé au tarif de la
    # formule en vigueur ce mois-là. Changer la section d'un élève recalculait
    # toute l'année, mois passés compris : c'est exactement ce qu'on évite.
    def _formules_datees(self):
        """Les formules de la fiche, dans l'ordre de l'année scolaire."""
        cache = getattr(self, '_formules_cache', None)
        if cache is None:
            if not self.pk or not self.section_id:
                cache = []
            else:
                lignes = [f for f in self.formules_eleve.all()
                          if f.formule.section_id == self.section_id]
                debut = self.exercice.date_debut.month if self.exercice_id else 1
                cache = sorted(lignes, key=lambda f: (f.mois_debut - debut) % 12)
            self._formules_cache = cache
        return cache

    def formule_du_mois(self, mois=None):
        """La formule en vigueur pour le mois `mois` (None : aujourd'hui)."""
        lignes = self._formules_datees()
        if not lignes:
            return None
        debut = self.exercice.date_debut.month if self.exercice_id else 1
        if mois is None:
            import datetime as _dt
            aujourdhui = _dt.date.today()
            if self.exercice_id and aujourdhui > self.exercice.date_fin:
                return lignes[-1].formule
            mois = aujourdhui.month
            if self.exercice_id and aujourdhui < self.exercice.date_debut:
                mois = debut
        rang = (int(mois) - debut) % 12
        choisie = lignes[0]
        for ligne in lignes:
            if (ligne.mois_debut - debut) % 12 <= rang:
                choisie = ligne
        return choisie.formule

    @property
    def formule_actuelle(self):
        return self.formule_du_mois(None)

    def mensualite_brute_du_mois(self, mois=None):
        """Tarif du mois avant prise en charge : celui de la formule en vigueur,
        sinon la mensualité de la section."""
        if not self.section:
            return 0.0
        formule = self.formule_du_mois(mois)
        if formule is not None:
            return float(formule.frais_mensualite)
        return float(self.section.frais_mensualite)

    def pec_du_mois(self, mois=None):
        """Prise en charge du mois, plafonnée au tarif de ce mois."""
        if not self.section:
            return 0.0
        return round(min(float(self.pec_mensualite or 0), self.mensualite_brute_du_mois(mois)), 2)

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
        """Total annuel pris en charge (inscription + mensualités dues × réduction mensualité).
        Mois par mois quand la formule a changé : la réduction se plafonne au tarif du mois."""
        if self._formules_datees():
            return round(self.montant_pec_inscription
                         + sum(self.pec_du_mois(m) for m in self.mois_factures), 2)
        return round(self.montant_pec_inscription +
                     self.montant_pec_mensualite_mensuel * self.nb_mensualites_dues, 2)

    @property
    def total_theorique(self):
        """Total annuel brut sans prise en charge (mensualité × nb de mensualités dues)."""
        if not self.section:
            return 0.0
        if self._formules_datees():
            fixes = (self.frais_entree + float(self.section.frais_uniforme)
                     + float(self.section.frais_fournitures))
            return round(fixes + sum(self.mensualite_brute_du_mois(m) for m in self.mois_factures), 2)
        return float(self.section.total_annuel_pour(self.nb_mensualites_dues,
                                                    frais_entree=self.frais_entree))

    @property
    def frais_mensualite_effectif(self):
        """Mensualité réelle après prise en charge (formule du mois en cours)."""
        if not self.section:
            return 0.0
        return round(max(self.mensualite_brute_du_mois(None) - self.pec_du_mois(None), 0.0), 2)

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
        total += sum(a['montant'] for a in self.adhesions_services())
        return round(total, 2)

    def adhesions_services(self):
        """Frais d'adhésion dus pour les services choisis : droit d'inscription au
        service, équipement… Un élément « première adhésion seulement » (le
        kimono) n'est dû que si l'enfant n'avait pas suivi ce service une année
        précédente (`EleveService.premiere_adhesion`)."""
        dus = []
        for ab in self.abonnements.all():
            s = ab.service
            for el in s.composition_adhesion or []:
                if el.get('premiere_fois') and not ab.premiere_adhesion:
                    continue
                montant = float(el.get('montant') or 0)
                if montant <= 0:
                    continue
                libelle = str(el.get('libelle') or '').strip()
                dus.append({'service_id': str(s.id), 'service': s.nom, 'libelle': libelle,
                            'montant': montant, 'cle': f'{s.id}:{libelle}',
                            'premiere_fois': bool(el.get('premiere_fois'))})
        return dus

    @property
    def premier_mois_a_inscription(self):
        """Le premier mois se règle à l'inscription : réglage de l'école, ou
        exigence d'un service choisi (« premier mois payé d'avance »)."""
        if getattr(self.tenant, 'premier_mois_a_inscription', False):
            return True
        return any(ab.service.premier_mois_a_inscription for ab in self.abonnements.all())

    # ── Montants attendus / payés ─────────────────────────────────────────
    @property
    def total_attendu(self):
        """Total annuel réel attendu : frais section − prise en charge + services optionnels.

        Une fiche de créance ne doit RIEN au titre de l'année : l'enfant a
        quitté l'établissement, la fiche n'existe que pour porter son ardoise
        (qui, elle, est dans reliquat_anterieur). Lui compter la scolarité
        reviendrait à facturer une année qu'il ne fera pas.

        Le total est la somme du hors-mensualité et de CHAQUE mois facturé,
        et non plus « mensualité × nombre de mois » : un montant saisi pour un
        mois particulier (réduction d'entrée en cours de mois, mois inclus dans
        les frais d'inscription) doit se retrouver dans le total. Le calculer
        autrement ferait diverger la fiche de son propre échéancier."""
        if self.fiche_creance:
            return 0.0
        total = self.du_hors_mensualite
        for mois in self.mois_factures:
            total += self.du_du_mois(mois)
        return round(total, 2)

    @property
    def du_hors_mensualite(self):
        """Frais d'entrée nets de prise en charge, uniforme, fournitures et
        services à paiement unique. Rien de mensuel ici.

        Les frais d'entrée sont l'inscription pour un nouvel élève, le
        renouvellement pour un ancien quand l'école en pratique un."""
        adhesions = sum(a['montant'] for a in self.adhesions_services())
        if not self.section:
            return round(sum(float(ab.service.montant or 0)
                             for ab in self.abonnements.all()
                             if ab.service.periodicite != 'MENSUEL') + adhesions, 2)
        total = max(self.frais_entree - self.montant_pec_inscription, 0.0)
        total += float(self.section.frais_uniforme)
        total += float(self.section.frais_fournitures)
        total += sum(float(ab.service.montant or 0) for ab in self.abonnements.all()
                     if ab.service.periodicite != 'MENSUEL')
        total += adhesions
        return round(total, 2)

    @property
    def du_mensuel_standard(self):
        """Ce que coûte un mois ordinaire : mensualité nette + services mensuels."""
        mensuel = sum(float(ab.service.montant or 0) for ab in self.abonnements.all()
                      if ab.service.periodicite == 'MENSUEL')
        return round(self.frais_mensualite_effectif + mensuel, 2)

    @property
    def mois_factures(self):
        """Les numéros de mois facturés, saisis ou déduits du prorata."""
        from .echeancier import mois_factures
        return mois_factures(self)

    def du_du_mois(self, mois):
        """Montant dû pour UN mois : celui saisi par l'école s'il existe,
        sinon le tarif ordinaire. Zéro saisi vaut zéro, pas « non saisi ».

        Enfant gardé à la journée : le tarif ordinaire du mois est la somme de
        ses jours de présence, plus ses services mensuels."""
        saisis = self.montants_mois or {}
        cle = str(int(mois))
        if cle in saisis:
            return round(float(saisis[cle] or 0), 2)
        if self.a_la_journee:
            from .garderie import du_presences_du_mois
            return round(du_presences_du_mois(self, int(mois)) + self.du_mensuel_standard, 2)
        if self._formules_datees():
            mensuel = sum(float(ab.service.montant or 0) for ab in self.abonnements.all()
                          if ab.service.periodicite == 'MENSUEL')
            net = max(self.mensualite_brute_du_mois(mois) - self.pec_du_mois(mois), 0.0)
            return round(net + mensuel, 2)
        return self.du_mensuel_standard

    @property
    def a_la_journee(self):
        """Facturé selon ses jours de présence plutôt qu'au mois."""
        return bool(self.section and self.section.a_la_journee)

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

    # ── Répartition du dû entre l'organisme et la famille ──────────────────
    # Une bourse ne fait pas disparaître le dû, elle en change le débiteur.
    # Tout ce qui suit sépare donc ce que doit un tiers de ce que doit la
    # famille — sans quoi l'école croirait avoir encaissé ce qu'un organisme
    # lui doit encore, ou réclamerait à des parents la part de l'État.
    @property
    def pec_organisme(self):
        """La prise en charge par un organisme sur l'exercice de la fiche."""
        if not self.exercice_id:
            return None
        for pec in self.prises_en_charge_organisme.all():
            if pec.exercice_id == self.exercice_id:
                return pec
        return None

    @property
    def part_organisme(self):
        """Montant que l'organisme doit à l'école pour cet élève.

        Plafonné au dû réel : une convention qui couvre plus que la scolarité
        ne crée pas une créance sur la différence."""
        pec = self.pec_organisme
        if not pec:
            return 0.0
        return round(min(pec.montant_annuel, float(self.total_attendu)), 2)

    @property
    def part_famille(self):
        """Ce qui reste à la charge de la famille."""
        return round(max(float(self.total_attendu) - self.part_organisme, 0.0), 2)

    @property
    def paye_organisme(self):
        # Annotation quand elle existe (liste, dashboard) : sinon une requête
        # par élève, et la liste de 300 fiches redevient injouable.
        if hasattr(self, 'paye_organisme_sql'):
            return round(float(self.paye_organisme_sql), 2)
        from django.db.models import Sum
        agg = self.paiements.filter(statut='ACTIF', organisme__isnull=False).aggregate(
            t=Sum('montant_inscription') + Sum('montant_mensualite') +
              Sum('montant_uniforme')    + Sum('montant_fournitures') +
              Sum('montant_cantine')     + Sum('montant_divers'))
        return round(float(agg['t'] or 0), 2)

    @property
    def reste_organisme(self):
        return round(max(self.part_organisme - self.paye_organisme, 0.0), 2)

    @property
    def reste_famille(self):
        """Ce que la famille doit encore. C'est CE montant qu'on lui réclame,
        jamais le dû global : une famille n'a pas à être relancée parce que
        l'État tarde à verser sa subvention."""
        paye_famille = round(float(self.total_paye) - self.paye_organisme, 2)
        return round(max(self.part_famille - paye_famille, 0.0), 2)

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
        pour EXERCICE, durée convenue pour PASSAGER (qui peut dépasser l'exercice).

        L'horloge S'ARRÊTE à la date de sortie : un élève parti en mars ne doit
        pas voir ses arriérés grossir jusqu'en décembre. Sans ce plafond, une
        fiche d'abandon finit toujours en CRITIQUE, pour une scolarité que
        l'enfant n'a pas suivie — et l'alerte cesse alors de vouloir dire
        quoi que ce soit."""
        from django.utils import timezone
        if not self.exercice_id:
            return 0
        today = today or timezone.now().date()
        if self.date_sortie and self.date_sortie < today:
            today = self.date_sortie
        debut = self.exercice.date_debut
        insc  = self.date_inscription or debut
        mois_avant = max(0, (insc.year - debut.year) * 12 + (insc.month - debut.month)) if insc > debut else 0
        elapsed_incl = (today.year - debut.year) * 12 + (today.month - debut.month) + 1
        return max(0, min(elapsed_incl - mois_avant, self.nb_mensualites_dues))

    def situation_alerte(self, today=None):
        """Source de vérité unique des alertes paiement.

        Rend {niveau, nb_mois, montant, mois} — voir
        `echeancier.alerte_depuis_echeancier` pour les niveaux.

        Tout vient de l'ÉCHÉANCIER, le même que celui affiché sur la fiche.
        Le calcul précédent multipliait les mois écoulés depuis l'inscription
        par une mensualité uniforme : il ignorait les mois réellement
        facturés, le montant saisi pour un mois donné, le réglage
        d'exigibilité de l'école et les imputations corrigées à la main. Un
        tableau de bord qui réclame ce que la fiche ne réclame pas fait
        appeler des familles qui ne doivent rien — le pire défaut possible
        pour cet écran.

        Pour parcourir une école entière, précharger le queryset avec
        `echeancier.precharger` : sinon, une requête de paiements par fiche.
        """
        from .echeancier import alerte_depuis_echeancier, construire_echeancier
        return alerte_depuis_echeancier(construire_echeancier(self, today=today))

    def niveau_alerte_detail(self, total_paye=None, mensualites_payees=None, today=None):
        """(niveau, nb_mois_arrieres) — conservé pour les appelants existants.

        Les deux premiers arguments ne servent plus : les montants sont lus
        dans l'échéancier, qui les impute mois par mois.
        """
        etat = self.situation_alerte(today)
        return (etat['niveau'], etat['nb_mois'])

    @property
    def niveau_alerte(self):
        return self.situation_alerte()['niveau']


class FormuleSection(TenantModel):
    """Une formule d'une section : même inscription, mensualité propre.

    Crèche : 08H-13H à 30 000, 08H-17H à 40 000, 08H-19H à 55 000, dans la même
    classe. Une section sans formule garde sa mensualité unique.
    """
    section          = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='formules')
    nom              = models.CharField(max_length=100)
    frais_mensualite = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    ordre            = models.IntegerField(default=0)
    actif            = models.BooleanField(default=True)

    class Meta:
        db_table = 'formules_section'
        ordering = ['ordre', 'nom']

    def __str__(self):
        return f"{self.section.nom} — {self.nom}"


class FormuleEleve(TenantModel):
    """La formule d'un enfant à partir d'un mois de l'année scolaire.

    La première ligne vaut depuis le début ; chaque ligne suivante est un
    changement, qui ne touche que les mois à partir du sien.
    """
    eleve      = models.ForeignKey(Eleve, on_delete=models.CASCADE, related_name='formules_eleve')
    formule    = models.ForeignKey(FormuleSection, on_delete=models.PROTECT, related_name='eleves')
    mois_debut = models.PositiveSmallIntegerField()     # 1..12
    saisi_par  = models.CharField(max_length=150, blank=True)

    class Meta:
        db_table = 'formules_eleve'
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'eleve', 'mois_debut'],
                                    name='uniq_formule_eleve_par_mois'),
        ]

    def __str__(self):
        return f"{self.eleve} → {self.formule.nom} (mois {self.mois_debut})"


class PresenceGarderie(TenantModel):
    """Un jour de garde d'un enfant facturé à la journée.

    **Le montant est figé à la saisie.** Un tarif révisé en cours d'année ne
    doit pas réécrire ce que la famille devait pour les jours déjà gardés —
    ni le reçu qu'elle a peut-être déjà entre les mains.

    Un seul enregistrement par enfant et par jour : l'appel se corrige en
    changeant la formule ou en retirant la présence, jamais en empilant.
    """
    FORMULE_CHOICES = [
        ('DEMI_JOURNEE', '½ journée'),
        ('JOURNEE',      'Journée'),
    ]
    eleve     = models.ForeignKey(Eleve, on_delete=models.CASCADE, related_name='presences_garderie')
    date      = models.DateField()
    formule   = models.CharField(max_length=12, choices=FORMULE_CHOICES)
    montant   = models.DecimalField(max_digits=12, decimal_places=2)
    saisi_par = models.CharField(max_length=150, blank=True)

    class Meta:
        db_table = 'presences_garderie'
        ordering = ['date']
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'eleve', 'date'],
                                    name='uniq_presence_garderie_par_jour'),
        ]
        indexes = [models.Index(fields=['tenant', 'date'], name='idx_garderie_jour')]

    def __str__(self):
        return f"{self.eleve} — {self.date:%d/%m/%Y} ({self.get_formule_display()})"


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
    # Frais d'adhésion au service, dus à l'inscription de l'enfant au service :
    # [{"libelle": "Droit d'inscription", "montant": 12000, "premiere_fois": false},
    #  {"libelle": "Kimono", "montant": 10000, "premiere_fois": true}]
    # `premiere_fois` : seulement si l'enfant n'a pas suivi ce service une
    # année précédente (l'équipement déjà acheté ne se rachète pas).
    composition_adhesion = models.JSONField(default=list, blank=True)
    # Le premier mois du service se paie d'avance, avec l'inscription.
    premier_mois_a_inscription = models.BooleanField(default=False)

    class Meta:
        db_table = 'services'
        ordering = ['nom']

    def __str__(self):
        return self.nom


class EleveService(TenantModel):
    """Abonnement d'un élève à un service optionnel."""
    eleve   = models.ForeignKey(Eleve, on_delete=models.CASCADE, related_name='abonnements')
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='abonnements')
    # Première fois que l'enfant suit ce service : décidé à l'abonnement d'après
    # ses fiches des années précédentes, corrigeable par l'école. Figé, pour
    # qu'une fiche ancienne supprimée ne fasse pas réapparaître un kimono dû.
    premiere_adhesion = models.BooleanField(default=True)

    class Meta:
        db_table = 'eleve_services'
        unique_together = ['tenant', 'eleve', 'service']

    def __str__(self):
        return f"{self.eleve} → {self.service}"


class RappelEnvoye(TenantModel):
    """Trace d'un rappel de paiement envoyé à une famille.

    Sert d'abord de garde-fou : on n'écrit ici qu'une fois par élève et par
    mois, et l'envoi refuse tout doublon. Harceler une famille avec le même
    message trois fois dans la journée abîme la relation bien plus qu'un
    rappel oublié — et une école qui s'est fait ce reproche une fois
    n'utilisera plus jamais la fonction.

    C'est ensuite l'historique : qui a été prévenu, quand, sur quel numéro, et
    ce que le fournisseur a répondu. Un parent qui affirme n'avoir rien reçu
    se vérifie ici.
    """
    STATUT_CHOICES = [
        ('ENVOYE',    'Envoyé'),
        ('ECHEC',     'Échec'),
        ('SIMULE',    'Simulé (aucun envoi réel)'),
    ]
    eleve      = models.ForeignKey(Eleve, on_delete=models.CASCADE,
                                   related_name='rappels')
    # Période couverte : « 2026-07 ». C'est la clé d'unicité, pas la date
    # d'envoi — relancer le 3 puis le 28 du même mois reste UN rappel.
    periode    = models.CharField(max_length=7)
    canal      = models.CharField(max_length=10, default='SMS')
    destinataire = models.CharField(max_length=40)
    message    = models.TextField()
    montant    = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    statut     = models.CharField(max_length=10, choices=STATUT_CHOICES,
                                  default='ENVOYE')
    detail     = models.TextField(blank=True, help_text='Réponse du fournisseur')

    class Meta:
        db_table = 'rappels_envoyes'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'eleve', 'periode'],
                                    name='uniq_rappel_par_mois'),
        ]

    def __str__(self):
        return f"{self.eleve} — {self.periode} ({self.statut})"


class MouvementEleve(TenantModel):
    """Sorties et retours d'un élève — la mémoire des allers-retours.

    Réintégrer un enfant efface la date de sortie de sa fiche (elle redevient
    celle d'un élève présent). Sans cette table, l'abandon de mars et le retour
    de juin ne laisseraient aucune trace : ni pour la direction qui doit juger
    une deuxième demande, ni pour expliquer pourquoi avril et mai ne sont pas
    facturés.
    """
    TYPE_CHOICES = [
        ('SORTIE',        'Sortie'),
        ('REINTEGRATION', 'Réintégration'),
    ]
    eleve         = models.ForeignKey(Eleve, on_delete=models.CASCADE,
                                      related_name='mouvements')
    type_mouvement = models.CharField(max_length=15, choices=TYPE_CHOICES)
    date_mouvement = models.DateField()
    statut_avant  = models.CharField(max_length=20, blank=True, default='')
    statut_apres  = models.CharField(max_length=20, blank=True, default='')
    motif         = models.CharField(max_length=300, blank=True, default='')
    # Réintégration : mois d'absence retirés de la facturation, dette
    # reconnue au retour, fiche d'origine quand le retour change d'exercice.
    mois_retires  = models.JSONField(default=list, blank=True)
    dette_reconnue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    fiche_origine = models.ForeignKey(Eleve, null=True, blank=True,
                                      on_delete=models.SET_NULL, related_name='+')
    utilisateur   = models.CharField(max_length=150, blank=True, default='')

    class Meta:
        db_table = 'mouvements_eleves'
        ordering = ['-date_mouvement', '-created_at']

    def __str__(self):
        return f"{self.eleve} — {self.type_mouvement} {self.date_mouvement}"


class Organisme(TenantModel):
    """Tiers qui prend en charge la scolarité d'élèves : État, collectivité,
    ONG, fondation, entreprise.

    À NE PAS confondre avec `Eleve.prise_en_charge`, qui est une REMISE : là,
    l'école renonce à la somme et personne ne la paie. Ici, un tiers DOIT cet
    argent à l'établissement. Confondre les deux ferait disparaître des
    créances réelles du suivi financier — pour un centre de formation dont la
    moitié des étudiants sont boursiers de l'État, c'est la moitié de ses
    recettes qui deviendrait invisible.
    """
    TYPE_CHOICES = [
        ('ETAT',         'État / Ministère'),
        ('COLLECTIVITE', 'Collectivité territoriale'),
        ('ONG',          'ONG'),
        ('FONDATION',    'Fondation'),
        ('ENTREPRISE',   'Entreprise'),
        ('AUTRE',        'Autre'),
    ]
    nom          = models.CharField(max_length=200)
    type         = models.CharField(max_length=20, choices=TYPE_CHOICES, default='AUTRE')
    # Référence de la convention ou de l'arrêté : c'est ce que l'école cite
    # quand elle relance, et ce qu'un contrôleur demande en premier.
    reference    = models.CharField(max_length=100, blank=True,
                                    help_text='Convention, arrêté, marché…')
    contact_nom  = models.CharField(max_length=150, blank=True)
    telephone    = models.CharField(max_length=20, blank=True)
    email        = models.EmailField(blank=True)
    adresse      = models.TextField(blank=True)
    observations = models.TextField(blank=True)
    actif        = models.BooleanField(default=True)

    class Meta:
        db_table = 'organismes'
        ordering = ['nom']
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'nom'],
                                    name='uniq_organisme_par_tenant'),
        ]

    def __str__(self):
        return self.nom


class PriseEnChargeOrganisme(TenantModel):
    """Ce qu'un organisme prend en charge pour un élève, sur un exercice.

    Les montants ont la même forme que la prise en charge sociale de la fiche
    (une part sur l'inscription, une part par mensualité) : l'école raisonne
    déjà ainsi, et le calcul du dû reste lisible.

    La différence tient à la conséquence : ces montants ne DISPARAISSENT pas
    du dû, ils CHANGENT de débiteur. La famille ne les doit plus, l'organisme
    les doit.
    """
    eleve      = models.ForeignKey(Eleve, on_delete=models.CASCADE,
                                   related_name='prises_en_charge_organisme')
    organisme  = models.ForeignKey(Organisme, on_delete=models.PROTECT,
                                   related_name='prises_en_charge')
    # L'exercice est porté explicitement : une bourse se renouvelle année par
    # année, et un boursier peut perdre sa bourse en cours de parcours.
    exercice   = models.ForeignKey('paiements.Exercice', on_delete=models.CASCADE,
                                   related_name='prises_en_charge_organisme')
    montant_inscription = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    montant_mensualite  = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                              help_text='Par mensualité')
    # Couvre les services optionnels (cantine, internat…) à 100 % ou pas du
    # tout : les organismes raisonnent rarement au prorata sur ces postes.
    couvre_services = models.BooleanField(default=False)
    reference  = models.CharField(max_length=100, blank=True,
                                  help_text="Numéro de bourse, décision d'attribution…")
    observations = models.TextField(blank=True)

    class Meta:
        db_table = 'prises_en_charge_organisme'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'eleve', 'exercice'],
                                    name='uniq_pec_organisme_par_eleve_exercice'),
        ]

    def __str__(self):
        return f"{self.eleve} — {self.organisme}"

    @property
    def montant_annuel(self):
        """Total pris en charge sur l'exercice, services compris."""
        eleve = self.eleve
        total = float(self.montant_inscription or 0)
        total += float(self.montant_mensualite or 0) * eleve.nb_mensualites_dues
        if self.couvre_services:
            total += eleve.montant_services_annuel
        return round(total, 2)


class ModeleCertificat(TenantModel):
    """Certificat de scolarité rédigé par l'établissement dans Word.

    Le .docx est gardé en base (base64), comme le logo : il suit l'école en
    local comme en cloud, et dans ses sauvegardes. Pas sur le Tenant lui-même,
    relu à chaque requête : un modèle avec en-tête illustré pèse des centaines
    de Ko. Un seul modèle par établissement.
    """
    nom_fichier = models.CharField(max_length=255)
    contenu_b64 = models.TextField()
    codes       = models.JSONField(default=list, blank=True,
                                   help_text='Codes trouvés dans le modèle au téléversement')

    class Meta:
        db_table = 'modeles_certificat'
        constraints = [
            models.UniqueConstraint(fields=['tenant'], name='uniq_modele_certificat_par_ecole'),
        ]

    def __str__(self):
        return f"{self.tenant} — {self.nom_fichier}"
