from django.db import models
from core.models import TenantModel


class Exercice(TenantModel):
    annee_scolaire         = models.CharField(max_length=20)
    date_debut             = models.DateField()
    date_fin               = models.DateField()
    solde_initial_caisse   = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    solde_initial_banque   = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    solde_initial_mobile   = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    devise                 = models.CharField(max_length=10, default='FCFA')
    cloture                = models.BooleanField(default=False)
    date_cloture           = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'exercices'
        unique_together = ['tenant', 'annee_scolaire']

    def __str__(self):
        return f"{self.tenant} — {self.annee_scolaire}"


MODE_CHOICES = [
    ('ESPECE',       'Espèce'),
    ('WAVE',         'Wave'),
    ('ORANGE_MONEY', 'Orange Money'),
    ('FREE_MONEY',   'Free Money'),
    ('VIREMENT',     'Virement'),
    ('CHEQUE',       'Chèque'),
]


class Paiement(TenantModel):
    eleve               = models.ForeignKey('eleves.Eleve', on_delete=models.CASCADE, related_name='paiements')
    exercice            = models.ForeignKey(Exercice, on_delete=models.CASCADE, related_name='paiements')
    no_piece            = models.CharField(max_length=30, unique=True)
    date_paiement       = models.DateField(auto_now_add=True)
    montant_inscription = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    montant_mensualite  = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    montant_uniforme    = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    montant_fournitures = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    montant_cantine     = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    montant_divers      = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    mode_paiement       = models.CharField(max_length=20, choices=MODE_CHOICES, default='ESPECE')
    observations        = models.TextField(blank=True)
    saisi_par           = models.ForeignKey('users.User', null=True, on_delete=models.SET_NULL)

    class Meta:
        db_table = 'paiements'
        ordering = ['-date_paiement']

    @property
    def total(self):
        return (self.montant_inscription + self.montant_mensualite +
                self.montant_uniforme    + self.montant_fournitures +
                self.montant_cantine     + self.montant_divers)

    def save(self, *args, **kwargs):
        if not self.no_piece:
            last = Paiement.objects.filter(exercice=self.exercice).count()
            self.no_piece = f"REC-{str(last + 1).zfill(4)}"
        super().save(*args, **kwargs)
        # Génère automatiquement l'écriture comptable
        self._generer_ecriture()

    def _generer_ecriture(self):
        from apps.comptabilite.models import JournalEntry
        compte_tresorerie = {'WAVE': '5521', 'ORANGE_MONEY': '5522',
                             'FREE_MONEY': '5523', 'ESPECE': '571',
                             'VIREMENT': '521'}.get(self.mode_paiement, '571')
        JournalEntry.objects.get_or_create(
            exercice=self.exercice, no_piece=self.no_piece,
            no_compte=compte_tresorerie,
            defaults={'libelle': f"Encaissement - {self.eleve.nom_complet} ({self.mode_paiement})",
                      'debit': self.total, 'credit': 0, 'source': 'RECETTE', 'source_id': self.id,
                      'date_ecriture': self.date_paiement, 'tenant': self.tenant}
        )
