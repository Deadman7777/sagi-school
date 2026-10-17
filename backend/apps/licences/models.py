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
        'AVANCE':       ['/dashboard', '/eleves', '/paiements', '/comptabilite', '/suivi-mensuel', '/academique', '/rh', '/fiscal', '/gmrf', '/gouvernance'],
        'TAXAWU_DAARA': ['/dashboard', '/eleves', '/paiements', '/comptabilite', '/academique', '/suivi-mensuel', '/rh', '/fiscal', '/gmrf', '/gouvernance'],
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


class DemandeRenouvellement(TimeStampedModel):
    """Demande de renouvellement de licence — enregistrée AVANT tout courriel.

    Suivi Shoumoul (septembre 2026) : « Demander un renouvellement » ne
    parvenait pas à hadygesman@gmail.com, et personne ne le savait. Le courriel
    était le seul dépôt et ses échecs étaient avalés en silence ; en local, le
    repli ouvrait un client de messagerie que le poste n'avait pas.

    Même règle que les demandes de démo du site : la base est la source de
    vérité, le courriel une commodité. Une demande dont l'envoi échoue reste
    visible dans l'écran Licences de HADY GESMAN, avec l'erreur.
    """
    ORIGINE_CHOICES = [
        ('CLOUD', 'Application cloud'),
        ('RELAIS', 'Installation locale (relayée au cloud)'),
        ('LOCAL', 'Installation locale (non relayée)'),
    ]
    tenant        = models.ForeignKey('tenants.Tenant', null=True, blank=True,
                                      on_delete=models.SET_NULL, related_name='demandes_renouvellement')
    licence       = models.ForeignKey(Licence, null=True, blank=True,
                                      on_delete=models.SET_NULL, related_name='demandes_renouvellement')
    ecole_nom     = models.CharField(max_length=200)
    cle_licence   = models.CharField(max_length=100, blank=True, default='')
    type_licence  = models.CharField(max_length=20, blank=True, default='')
    date_fin      = models.DateField(null=True, blank=True)
    demandeur     = models.CharField(max_length=200, blank=True, default='')
    email_demandeur = models.CharField(max_length=254, blank=True, default='')
    telephone     = models.CharField(max_length=60, blank=True, default='')  # = Tenant.telephone
    message       = models.TextField(blank=True, default='')
    origine       = models.CharField(max_length=10, choices=ORIGINE_CHOICES, default='CLOUD')
    courriel_envoye = models.BooleanField(default=False)
    relayee       = models.BooleanField(default=False)
    erreur        = models.TextField(blank=True, default='')
    traitee       = models.BooleanField(default=False)
    traitee_le    = models.DateTimeField(null=True, blank=True)
    # « Renouveler maintenant » : la formule choisie et le paiement déclaré.
    # La licence n'est prolongée qu'à la confirmation par HADY GESMAN.
    type_demande  = models.CharField(max_length=20, blank=True, default='')
    mois          = models.PositiveSmallIntegerField(null=True, blank=True)
    montant       = models.PositiveIntegerField(null=True, blank=True)
    moyen_paiement = models.CharField(max_length=60, blank=True, default='')
    reference_paiement = models.CharField(max_length=120, blank=True, default='')
    confirmee     = models.BooleanField(default=False)

    class Meta:
        db_table = 'demandes_renouvellement'
        ordering = ['-created_at']

    def __str__(self):
        return f"Renouvellement {self.ecole_nom} — {self.created_at:%d/%m/%Y}"


class RelanceLicence(TimeStampedModel):
    """Une relance de fin de licence, envoyée (ou tentée) à un palier.

    Paliers J-7, J-3, J-1 et J0 : jamais deux fois le même pour une même
    échéance. L'échéance (`date_fin`) fait partie de la clé : après un
    renouvellement, la date de fin change et un nouveau cycle de relances
    recommence de lui-même.
    """
    PALIERS = (7, 3, 1, 0)

    licence     = models.ForeignKey(Licence, on_delete=models.CASCADE, related_name='relances')
    date_fin    = models.DateField()
    palier      = models.PositiveSmallIntegerField()
    canal       = models.CharField(max_length=20, default='EMAIL')
    destinataires = models.CharField(max_length=500, blank=True)
    sujet       = models.CharField(max_length=250, blank=True)
    message     = models.TextField(blank=True)
    succes      = models.BooleanField(default=False)
    simulee     = models.BooleanField(default=False)
    erreur      = models.TextField(blank=True)
    declenchee_par = models.CharField(max_length=150, blank=True)   # vide : tâche planifiée

    class Meta:
        db_table = 'licences_relances'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['licence', 'date_fin', 'palier'])]

    def __str__(self):
        return f'{self.licence} — J-{self.palier} ({self.date_fin})'
