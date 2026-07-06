import hashlib, secrets
from datetime import timedelta
from django.db import models
from django.utils import timezone
from core.models import TimeStampedModel


class Licence(TimeStampedModel):
    TYPE_CHOICES = [
        ('ESSAI',        'Essai 30 jours'),
        ('BASIC',        'Basic'),
        ('PRO',          'Pro'),
        ('AVANCE',       'Avancé'),
        ('TAXAWU_DAARA', 'Taxawu Daara'),
    ]

    MODULES_PAR_TYPE = {
        'ESSAI':        ['/dashboard', '/eleves', '/paiements', '/comptabilite', '/suivi-mensuel'],
        'BASIC':        ['/dashboard', '/eleves', '/paiements', '/suivi-mensuel'],
        'PRO':          ['/dashboard', '/eleves', '/paiements', '/comptabilite', '/suivi-mensuel'],
        'AVANCE':       ['/dashboard', '/eleves', '/paiements', '/comptabilite', '/suivi-mensuel', '/academique', '/rh', '/fiscal', '/gmrf'],
        'TAXAWU_DAARA': ['/dashboard', '/eleves', '/paiements', '/comptabilite', '/academique', '/suivi-mensuel'],
    }
    STATUT_CHOICES = [
        ('ACTIVE',    'Active'),
        ('EXPIREE',   'Expirée'),
        ('SUSPENDUE', 'Suspendue'),
        ('ESSAI',     'Essai'),
    ]

    tenant      = models.OneToOneField('tenants.Tenant', on_delete=models.CASCADE, related_name='licence')
    cle_licence = models.CharField(max_length=100, unique=True)
    type        = models.CharField(max_length=20, choices=TYPE_CHOICES, default='ESSAI')
    statut      = models.CharField(max_length=20, choices=STATUT_CHOICES, default='ESSAI')
    date_debut  = models.DateField()
    date_fin    = models.DateField()
    version     = models.CharField(max_length=20, default='2.2.0')

    class Meta:
        db_table = 'licences'

    def __str__(self):
        return f"{self.tenant} — {self.type} ({self.statut})"

    # Délai de grâce après date_fin avant de couper l'accès aux modules
    GRACE_JOURS = 7

    @property
    def acces_expire(self):
        """True quand l'accès aux modules doit être coupé : licence
        suspendue, ou expirée au-delà de la période de grâce.
        Le statut ESSAI n'est pas concerné tant que date_fin + grâce
        n'est pas dépassée."""
        if self.statut == 'SUSPENDUE':
            return True
        if not self.date_fin:
            return True
        return timezone.now().date() > self.date_fin + timedelta(days=self.GRACE_JOURS)

    @property
    def modules(self):
        always = ['/ma-licence', '/parametres']
        if self.acces_expire:
            return always
        return self.MODULES_PAR_TYPE.get(self.type, []) + always

    @property
    def est_active(self):
        if not self.date_fin:
            return False
        return self.statut == 'ACTIVE' and self.date_fin >= timezone.now().date()

    @property
    def jours_restants(self):
        if not self.date_fin:
            return 0
        delta = self.date_fin - timezone.now().date()
        return max(delta.days, 0)

    @staticmethod
    def generer_cle(tenant_rccm: str) -> str:
        """Génère une clé de licence unique et signée."""
        token = secrets.token_hex(4).upper()
        payload = f"HG-PRO-{timezone.now().year}-{tenant_rccm}-{token}"
        signature = hashlib.sha256(payload.encode()).hexdigest()[:8].upper()
        return f"{payload}-{signature}"
