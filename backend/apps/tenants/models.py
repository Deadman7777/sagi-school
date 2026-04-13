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
    actif     = models.BooleanField(default=True)

    class Meta:
        db_table = 'tenants'
        verbose_name = 'École'

    def __str__(self):
        return self.nom
