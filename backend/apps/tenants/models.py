from django.db import models
from core.models import TimeStampedModel


class Tenant(TimeStampedModel):
    nom       = models.CharField(max_length=200)
    ville     = models.CharField(max_length=100, blank=True)
    adresse   = models.TextField(blank=True)
    rccm      = models.CharField(max_length=50, blank=True)
    ninea     = models.CharField(max_length=20, blank=True)
    telephone = models.CharField(max_length=20, blank=True)
    email     = models.EmailField(blank=True)
    code_etablissement = models.CharField(max_length=10, default='ETB')
    # Logo de l'établissement en data URI base64 (ex. "data:image/png;base64,...").
    # Stocké en base pour fonctionner identiquement en local (Electron) et en cloud,
    # et s'embarquer directement dans les PDF (xhtml2pdf gère les data URIs).
    logo      = models.TextField(blank=True, default='')
    # Régime de paie : COMPLET (affilié IPRES/CSS/IR) ou SIMPLIFIE (non affilié, sans cotisations)
    REGIME_PAIE_CHOICES = [('COMPLET', 'Complet (affilié)'), ('SIMPLIFIE', 'Simplifié (non affilié)')]
    regime_paie = models.CharField(max_length=10, choices=REGIME_PAIE_CHOICES, default='COMPLET')
    actif     = models.BooleanField(default=True)

    class Meta:
        db_table = 'tenants'
        verbose_name = 'École'

    def __str__(self):
        return self.nom
