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
    source        = models.CharField(max_length=20, blank=True)  # 'RECETTE' | 'CHARGE'
    source_id     = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = 'journal_entries'
        ordering = ['date_ecriture', 'no_piece']

    def __str__(self):
        return f"{self.no_piece} — {self.libelle}"
