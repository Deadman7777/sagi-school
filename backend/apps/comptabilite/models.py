from django.db import models
from core.models import TenantModel


class JournalEntry(TenantModel):
    exercice      = models.ForeignKey('paiements.Exercice', on_delete=models.CASCADE, related_name='journal')
    no_piece      = models.CharField(max_length=30)
    date_ecriture = models.DateField()
    no_compte     = models.CharField(max_length=20)
    libelle       = models.TextField()
    debit         = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    credit        = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    source        = models.CharField(max_length=20, blank=True)
    source_id     = models.UUIDField(null=True, blank=True)
    ordre         = models.IntegerField(default=0)

    class Meta:
        db_table = 'journal_entries'
        ordering = ['date_ecriture', 'no_piece', 'ordre']

    def __str__(self):
        return f"{self.no_piece} — {self.libelle}"


class CompteComptable(TenantModel):
    """Plan comptable SYSCOHADA Révisé paramétrable par établissement."""
    TYPE_CHOICES = [
        ('BILAN',   'Compte de bilan'),
        ('CHARGE',  'Compte de charge'),
        ('PRODUIT', 'Compte de produit'),
    ]

    no_compte   = models.CharField(max_length=10)
    libelle     = models.CharField(max_length=200)
    type        = models.CharField(max_length=10, choices=TYPE_CHOICES, default='CHARGE')
    classe      = models.IntegerField()          # 1 à 9
    est_actif   = models.BooleanField(default=True)
    est_systeme = models.BooleanField(default=False)  # comptes non supprimables

    class Meta:
        db_table = 'comptes_comptables'
        unique_together = ['tenant', 'no_compte']
        ordering = ['no_compte']

    def __str__(self):
        return f"{self.no_compte} — {self.libelle}"


class BudgetLigne(TenantModel):
    """Budget prévisionnel mensuel par compte et par exercice."""
    TYPE_CHOICES = [
        ('FIXE',     'Charge fixe'),
        ('VARIABLE', 'Charge variable'),
    ]

    exercice    = models.ForeignKey('paiements.Exercice', on_delete=models.CASCADE, related_name='budget_lignes')
    no_compte   = models.CharField(max_length=10)
    libelle     = models.CharField(max_length=200)
    type_charge = models.CharField(max_length=10, choices=TYPE_CHOICES, default='FIXE')
    # Montants mensuels (FCFA)
    m01 = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    m02 = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    m03 = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    m04 = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    m05 = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    m06 = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    m07 = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    m08 = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    m09 = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    m10 = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    m11 = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    m12 = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        db_table = 'budget_lignes'
        unique_together = ['tenant', 'exercice', 'no_compte']
        ordering = ['no_compte']

    def __str__(self):
        return f"Budget {self.no_compte} — {self.exercice.annee_scolaire}"

    @property
    def total_prevu(self):
        return sum(getattr(self, f'm{i:02d}') for i in range(1, 13))

    def to_dict_montants(self):
        return {i: float(getattr(self, f'm{i:02d}')) for i in range(1, 13)}
