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


class Immobilisation(TenantModel):
    """Gestion des immobilisations et calcul des amortissements (SYSCOHADA Révisé)."""
    MODE_CHOICES = [
        ('LINEAIRE',  'Linéaire'),
        ('DEGRESSIF', 'Dégressif'),
    ]

    COMPTES_IMMO = [
        ('211', '211 — Terrains'),
        ('221', '221 — Bâtiments'),
        ('231', '231 — Matériel et outillage'),
        ('241', '241 — Mobilier'),
        ('244', '244 — Matériel informatique'),
        ('245', '245 — Matériel de transport'),
        ('248', '248 — Autres immobilisations corporelles'),
    ]
    COMPTES_AMORT = [
        ('2811', '2811 — Amort. Terrains'),
        ('2821', '2821 — Amort. Bâtiments'),
        ('2831', '2831 — Amort. Matériel et outillage'),
        ('2841', '2841 — Amort. Mobilier'),
        ('2844', '2844 — Amort. Matériel informatique'),
        ('2845', '2845 — Amort. Matériel de transport'),
        ('2848', '2848 — Amort. Autres immo. corporelles'),
    ]

    no_bien                = models.CharField(max_length=20, unique=False)
    libelle                = models.CharField(max_length=200)
    date_entree            = models.DateField()
    valeur_entree          = models.DecimalField(max_digits=15, decimal_places=2)
    duree_utilisation      = models.IntegerField(help_text='Années')
    mode_amortissement     = models.CharField(max_length=10, choices=MODE_CHOICES, default='LINEAIRE')
    no_compte_immobilisation = models.CharField(max_length=10, default='231')
    no_compte_amortissement  = models.CharField(max_length=10, default='2831')
    cumul_amortissements   = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    est_cede               = models.BooleanField(default=False)

    class Meta:
        db_table = 'immobilisations'
        ordering = ['date_entree', 'no_bien']

    @property
    def taux_amortissement(self):
        if not self.duree_utilisation:
            return 0
        return round(100 / self.duree_utilisation, 4)

    @property
    def annuite_amortissement(self):
        return round(float(self.valeur_entree) / self.duree_utilisation, 2)

    @property
    def valeur_nette_comptable(self):
        return round(float(self.valeur_entree) - float(self.cumul_amortissements), 2)

    @property
    def est_amorti(self):
        return float(self.cumul_amortissements) >= float(self.valeur_entree)

    def __str__(self):
        return f"{self.no_bien} — {self.libelle}"
