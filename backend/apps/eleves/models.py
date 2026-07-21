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
    statut                = models.CharField(max_length=20, choices=STATUT_CHOICES, default='INSCRIT')
    # Prise en charge sociale — motif
    prise_en_charge       = models.CharField(max_length=20, choices=PRISE_EN_CHARGE_CHOICES, blank=True, null=True)
    obs_prise_en_charge   = models.TextField(blank=True)
    # Prise en charge — type et taux détaillés
    type_pec              = models.CharField(max_length=20, choices=TYPE_PEC_CHOICES, blank=True, null=True)
    taux_pec_inscription  = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                                 help_text='% réduction sur frais inscription')
    taux_pec_mensualite   = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                                 help_text='% réduction sur mensualités')
    # Conservé pour compatibilité (ancienne valeur globale)
    taux_prise_en_charge  = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        db_table = 'eleves'
        ordering = ['numero', 'nom_complet']
        # Le matricule (AAAA-CODE-NNNNNN) est généré PAR école : son numéro est
        # séquentiel par tenant et le code établissement peut rester au défaut 'ETB'.
        # Il doit donc être unique par tenant, jamais globalement, sinon deux écoles
        # sur 'ETB' entrent en collision (2026-ETB-000001) → IntegrityError 500.
        # Les NULL restent autorisés en multiple (matricule optionnel).
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'matricule'],
                                    name='uniq_matricule_par_tenant'),
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
        if not self.section or not self.type_pec:
            return 0.0
        if self.type_pec in ('INSCRIPTION', 'TOTALE'):
            return round(float(self.section.frais_inscription) * float(self.taux_pec_inscription) / 100, 2)
        return 0.0

    @property
    def montant_pec_mensualite_mensuel(self):
        """Réduction sur une mensualité (montant mensuel)."""
        if not self.section or not self.type_pec:
            return 0.0
        if self.type_pec in ('MENSUALITES', 'TOTALE'):
            return round(float(self.section.frais_mensualite) * float(self.taux_pec_mensualite) / 100, 2)
        return 0.0

    @property
    def nb_mensualites_dues(self):
        """Nombre de mensualités réellement dues, au prorata de la date d'entrée.
        Ex. exercice débutant en octobre, élève inscrit en janvier → on ne compte
        pas oct/nov/déc. Plafonné à nb_mensualites de l'exercice.
        Régime PASSAGER (daara) : la durée convenue prime — le ndongo doit
        nb_mois_passager mensualités depuis son entrée, sans plafond de fin
        d'exercice (séjour à cheval → réinscrire avec les mois restants)."""
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
        if self.type_pec in ('MENSUALITES', 'TOTALE') and self.taux_pec_mensualite:
            return round(base * (1 - float(self.taux_pec_mensualite) / 100), 2)
        return base

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
        """Total annuel réel attendu : frais section − prise en charge + services optionnels."""
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
        return self.total_attendu - self.total_paye

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
