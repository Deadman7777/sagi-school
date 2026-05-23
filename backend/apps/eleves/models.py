from django.db import models
from core.models import TenantModel


class Section(TenantModel):
    nom                = models.CharField(max_length=100)
    frais_inscription  = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    frais_mensualite   = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    frais_uniforme     = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    frais_fournitures  = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    frais_yendu        = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    ordre              = models.IntegerField(default=0)

    class Meta:
        db_table = 'sections'
        ordering = ['ordre', 'nom']

    def __str__(self):
        return self.nom

    @property
    def total_annuel(self):
        return (self.frais_inscription + self.frais_uniforme +
                self.frais_fournitures + (self.frais_mensualite * 10) +
                self.frais_yendu)


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
    # Prise en charge sociale
    prise_en_charge       = models.CharField(max_length=20, choices=PRISE_EN_CHARGE_CHOICES, blank=True, null=True)
    taux_prise_en_charge  = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text='% de réduction appliquée')
    obs_prise_en_charge   = models.TextField(blank=True)

    class Meta:
        db_table = 'eleves'
        ordering = ['numero', 'nom_complet']

    def __str__(self):
        return self.nom_complet

    @property
    def total_attendu(self):
        return self.section.total_annuel if self.section else 0

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

        mensualite = float(self.section.frais_mensualite) if self.section else 0

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
