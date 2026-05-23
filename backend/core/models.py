import uuid
from django.db import models


def log_audit(request, action: str, modele: str, objet_id: str = '', description: str = ''):
    """Crée une entrée AuditLog depuis une vue Django."""
    from apps.dashboard.models import AuditLog
    tenant = getattr(request, 'tenant', None)
    user   = getattr(request, 'user', None)
    AuditLog.objects.create(
        tenant=tenant,
        utilisateur=str(user) if user else '',
        action=action,
        modele=modele,
        objet_id=str(objet_id),
        description=description,
    )


class TimeStampedModel(models.Model):
    """Classe de base avec UUID + timestamps automatiques."""
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TenantModel(TimeStampedModel):
    """Classe de base pour tous les modèles liés à une école (tenant)."""
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='%(app_label)s_%(class)s_set'
    )

    class Meta:
        abstract = True
