from django.db import models
from core.models import TenantModel


class Section(TenantModel):
    nom                = models.CharField(max_length=100)
    frais_inscription  = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    frais_mensualite   = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    frais_uniforme     = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    frais_fournitures  = models.DecimalField(max_digits=12, decimal_places=2, default=0)
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

    exercice              = models.ForeignKey('paiements.Exercice', on_delete=models.CASCADE, related_name='eleves')
    section               = models.ForeignKey(Section, null=True, on_delete=models.SET_NULL, related_name='eleves')
    numero                = models.IntegerField(null=True, blank=True)
    matricule             = models.CharField(max_length=20, blank=True, unique=True, null=True)
    nom_complet           = models.CharField(max_length=200)
    genre                 = models.CharField(max_length=1, choices=GENRE_CHOICES, blank=True)
    date_naissance        = models.DateField(null=True, blank=True)
    lieu_naissance        = models.CharField(max_length=200, blank=True)
    nom_pere              = models.CharField(max_length=200, blank=True)
    telephone_pere        = models.CharField(max_length=20, blank=True)
    nom_mere              = models.CharField(max_length=200, blank=True)
    telephone_mere        = models.CharField(max_length=20, blank=True)
    date_inscription      = models.DateField(auto_now_add=True)
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

    def __str__(self):
        return self.nom_complet

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
    def montant_pec_annuel(self):
        """Total annuel pris en charge (inscription + nb_mois × réduction mensualité)."""
        nb_mois = self.exercice.nb_mensualites if self.exercice_id else 10
        return round(self.montant_pec_inscription + self.montant_pec_mensualite_mensuel * nb_mois, 2)

    @property
    def total_theorique(self):
        """Total annuel brut sans prise en charge (mensualité × nb de mois de l'exercice)."""
        if not self.section:
            return 0.0
        nb_mois = self.exercice.nb_mensualites if self.exercice_id else 10
        return float(self.section.total_annuel_pour(nb_mois))

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
        Mensuel → montant × nb_mensualites ; Unique → montant une fois.
        Les services ne sont PAS soumis à la prise en charge."""
        nb_mois = self.exercice.nb_mensualites if self.exercice_id else 10
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

    @property
    def niveau_alerte(self):
        from django.utils import timezone
        from django.db.models import Sum

        total = float(self.total_attendu)
        paye  = float(self.total_paye)

        if total <= 0 or paye >= total:
            return 'A_JOUR'

        mensualite = self.frais_mensualite_effectif  # tient compte de la prise en charge

        if mensualite <= 0:
            ratio = paye / total if total > 0 else 0
            return 'URGENT' if ratio < 0.5 else 'ATTENTION'

        today  = timezone.now().date()
        debut  = self.exercice.date_debut
        months = max(0, min(
            (today.year - debut.year) * 12 + (today.month - debut.month),
            10
        ))

        mensualites_payees = float(
            self.paiements.aggregate(t=Sum('montant_mensualite'))['t'] or 0
        )
        arrieres = max(0.0, months * mensualite - mensualites_payees)

        if arrieres <= 0:
            return 'OK'

        nb_arrieres  = arrieres / mensualite
        jours_retard = nb_arrieres * 30

        if jours_retard >= 60 and nb_arrieres >= 2:
            return 'CRITIQUE'
        if jours_retard >= 30 and nb_arrieres >= 1:
            return 'URGENT'
        return 'ATTENTION'


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
