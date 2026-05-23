import uuid
from django.db import models
from core.models import TenantModel


class AuditLog(models.Model):
    """Journal d'audit admin-only — actions sur les données critiques."""
    ACTION_CHOICES = [
        ('CREATE',   'Création'),
        ('UPDATE',   'Modification'),
        ('DELETE',   'Suppression'),
        ('VALIDATE', 'Validation'),
        ('ANNULER',  'Annulation'),
    ]
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant      = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, null=True, blank=True)
    utilisateur = models.CharField(max_length=200, blank=True)
    action      = models.CharField(max_length=20, choices=ACTION_CHOICES)
    modele      = models.CharField(max_length=100)
    objet_id    = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'audit_logs'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.action} {self.modele} par {self.utilisateur}"
