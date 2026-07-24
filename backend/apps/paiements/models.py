from django.db import models
from core.models import TenantModel


class Exercice(TenantModel):
    annee_scolaire         = models.CharField(max_length=20)
    date_debut             = models.DateField()
    date_fin               = models.DateField()
    nb_mensualites         = models.IntegerField(default=10)
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
    # Règlement réparti sur plusieurs modes à la fois (voir modes_reglement).
    # mode_paiement vaut 'MIXTE' à titre indicatif ; le détail fait foi.
    ('MIXTE',        'Multi-mode'),
    # Migration : montants réglés avant la bascule sur SAGI SCHOOL.
    # Comptabilisé au 890 (bilan d'ouverture), jamais en trésorerie —
    # ne doit pas apparaître dans les formulaires de saisie de paiement.
    ('REPRISE',      'Reprise (migration)'),
]


class Paiement(TenantModel):
    STATUT_CHOICES = [('ACTIF', 'Actif'), ('ANNULE', 'Annulé')]

    eleve               = models.ForeignKey('eleves.Eleve', on_delete=models.CASCADE, related_name='paiements')
    exercice            = models.ForeignKey(Exercice, on_delete=models.CASCADE, related_name='paiements')
    no_piece            = models.CharField(max_length=30)
    date_paiement       = models.DateField(auto_now_add=True)
    statut              = models.CharField(max_length=10, choices=STATUT_CHOICES, default='ACTIF')
    montant_inscription = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    montant_mensualite  = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    montant_uniforme    = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    montant_fournitures = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    montant_cantine     = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    montant_divers      = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # Mois scolaires couverts par la mensualité (numéros 1-12), pour le suivi mensuel
    # et la gestion des paiements anticipés. Ex. [10, 11, 12].
    mois_regles         = models.JSONField(default=list, blank=True)
    # Détail des services optionnels réglés dans ce paiement (itemisation reçu).
    # Ex. [{"nom": "Cantine", "montant": 10000}]. Le montant est inclus dans montant_divers.
    services_regles     = models.JSONField(default=list, blank=True)
    mode_paiement       = models.CharField(max_length=20, choices=MODE_CHOICES, default='ESPECE')
    # Ventilation du règlement sur plusieurs modes (multi-mode). Vide → règlement
    # simple via mode_paiement. Ex. [{"mode": "ESPECE", "montant": 30000},
    # {"mode": "WAVE", "montant": 20000}, {"mode": "ORANGE_MONEY", "montant": 10000}].
    modes_reglement     = models.JSONField(default=list, blank=True)
    observations        = models.TextField(blank=True)
    saisi_par           = models.ForeignKey('users.User', null=True, on_delete=models.SET_NULL)

    class Meta:
        db_table = 'paiements'
        ordering = ['-date_paiement']
        # no_piece est séquentiel PAR école (généré via filter(tenant=...)),
        # il doit donc être unique par tenant, jamais globalement, sinon
        # le 1er reçu d'une nouvelle école (REC-0001) entre en collision avec
        # celui d'une école existante → IntegrityError 500.
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'no_piece'],
                                    name='uniq_no_piece_par_tenant'),
        ]

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
