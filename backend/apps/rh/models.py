from decimal import Decimal
from django.db import models
from core.models import TenantModel
import uuid


TRANCHES_IR_DEFAULT = [
    {"min": 0,       "max": 630000,  "taux": 0},
    {"min": 630001,  "max": 1500000, "taux": 20},
    {"min": 1500001, "max": 4000000, "taux": 30},
    {"min": 4000001, "max": 8000000, "taux": 35},
    {"min": 8000001, "max": None,    "taux": 40},
]


class Employe(TenantModel):
    TYPE_CHOICES = [
        ('ENSEIGNANT',    'Enseignant'),
        ('ADMINISTRATION', 'Administration'),
        ('APPUI',         "Personnel d'appui"),
    ]
    CONTRAT_CHOICES = [
        ('CDI',       'CDI'),
        ('CDD',       'CDD'),
        ('VACATAIRE', 'Vacataire'),
        ('STAGIAIRE', 'Stagiaire'),
    ]
    STATUT_CHOICES = [
        ('ACTIF',    'Actif'),
        ('CONGE',    'En congé'),
        ('SUSPENDU', 'Suspendu'),
        ('QUITTE',   'A quitté'),
    ]
    NIVEAU_CHOICES = [
        ('PRESCOLAIRE', 'Préscolaire'),
        ('ELEMENTAIRE', 'Élémentaire'),
        ('MOYEN',       'Moyen'),
        ('SECONDAIRE',  'Secondaire'),
        ('SUPERIEUR',   'Supérieur'),
    ]
    SITUATION_CHOICES = [
        ('CELIBATAIRE', 'Célibataire'),
        ('MARIE',       'Marié(e)'),
        ('DIVORCE',     'Divorcé(e)'),
        ('VEUF',        'Veuf/Veuve'),
    ]
    MODE_PAIEMENT_CHOICES = [
        ('BANQUE',       'Banque (virement)'),
        ('CAISSE',       'Caisse (espèces)'),
        ('WAVE',         'Wave'),
        ('ORANGE_MONEY', 'Orange Money'),
        ('FREE_MONEY',   'Free Money'),
        ('WIZALL',       'Wizall'),
        ('AUTRE',        'Autre'),
    ]

    matricule              = models.CharField(max_length=20, blank=True)
    nom_complet            = models.CharField(max_length=200)
    type_employe           = models.CharField(max_length=20, choices=TYPE_CHOICES)
    poste                  = models.CharField(max_length=100)
    type_contrat           = models.CharField(max_length=20, choices=CONTRAT_CHOICES, default='CDI')
    date_embauche          = models.DateField()
    date_fin_contrat       = models.DateField(null=True, blank=True)
    salaire_base           = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    telephone              = models.CharField(max_length=20, blank=True)
    email                  = models.EmailField(blank=True)
    statut                 = models.CharField(max_length=20, choices=STATUT_CHOICES, default='ACTIF')
    # Champs paie
    niveau_enseignement    = models.CharField(max_length=15, choices=NIVEAU_CHOICES, blank=True, default='')
    nb_enfants             = models.IntegerField(default=0)
    situation_matrimoniale = models.CharField(max_length=15, choices=SITUATION_CHOICES, default='CELIBATAIRE')
    est_cadre              = models.BooleanField(default=False)
    mode_paiement          = models.CharField(max_length=15, choices=MODE_PAIEMENT_CHOICES, default='CAISSE')
    numero_compte          = models.CharField(max_length=50, blank=True)

    class Meta:
        db_table = 'employes'
        ordering = ['nom_complet']

    def __str__(self):
        return f"{self.matricule} - {self.nom_complet}"

    @property
    def salaire_net(self):
        brut = float(self.salaire_base)
        ipres = brut * 0.056
        css   = brut * 0.007
        ir    = max(brut - 500000, 0) * 0.20
        return brut - ipres - css - ir


class Paie(TenantModel):
    """Modèle historique — conservé pour compatibilité données existantes."""
    employe         = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='paies')
    mois            = models.CharField(max_length=7)
    salaire_brut    = models.DecimalField(max_digits=12, decimal_places=2)
    ipres           = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    css             = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    ir              = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    autres_retenues = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    salaire_net     = models.DecimalField(max_digits=12, decimal_places=2)
    statut          = models.CharField(max_length=20, default='PAYE')
    observations    = models.TextField(blank=True)

    class Meta:
        db_table = 'paies'
        ordering = ['-mois']
        unique_together = ['tenant', 'employe', 'mois']

    def __str__(self):
        return f"{self.employe.nom_complet} - {self.mois}"


class ParametresFiscaux(models.Model):
    """Paramètres fiscaux nationaux Sénégal — non lié à un tenant."""
    id                             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    annee                          = models.IntegerField(unique=True)
    taux_ipres_general_salarie     = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal('5.6'))
    taux_ipres_general_patronal    = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal('8.4'))
    plafond_ipres_general          = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('300000'))
    taux_ipres_cadre_salarie       = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal('2.4'))
    taux_ipres_cadre_patronal      = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal('3.6'))
    plafond_ipres_cadre            = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('900000'))
    taux_css_prestations_familiales = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal('7.0'))
    plafond_css                    = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('63000'))
    taux_atmp                      = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal('1.0'))
    taux_cfce                      = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal('1.0'))
    prime_transport                = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('20800'))
    allocation_salaire_unique_base = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('5000'))
    allocation_par_enfant          = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('800'))
    plafond_allocation             = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('6400'))
    tranches_ir                    = models.JSONField(default=list)

    class Meta:
        db_table = 'parametres_fiscaux'
        ordering = ['-annee']
        verbose_name = 'Paramètres fiscaux'
        verbose_name_plural = 'Paramètres fiscaux'

    def __str__(self):
        return f"Paramètres fiscaux {self.annee}"

    def save(self, *args, **kwargs):
        if not self.tranches_ir:
            self.tranches_ir = TRANCHES_IR_DEFAULT
        super().save(*args, **kwargs)


class AvanceSalaire(TenantModel):
    MODE_CHOICES = [
        ('BANQUE',       'Banque'),
        ('WAVE',         'Wave'),
        ('ORANGE_MONEY', 'Orange Money'),
        ('FREE_MONEY',   'Free Money'),
        ('WIZALL',       'Wizall'),
        ('CAISSE',       'Caisse'),
    ]
    STATUT_CHOICES = [
        ('EN_ATTENTE', 'En attente'),
        ('IMPUTE',     'Imputé sur bulletin'),
        ('ANNULE',     'Annulé'),
    ]

    employe       = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='avances')
    montant       = models.DecimalField(max_digits=12, decimal_places=2)
    date_avance   = models.DateField()
    mode_paiement = models.CharField(max_length=15, choices=MODE_CHOICES, default='CAISSE')
    no_piece      = models.CharField(max_length=30, blank=True)
    statut        = models.CharField(max_length=15, choices=STATUT_CHOICES, default='EN_ATTENTE')
    observations  = models.TextField(blank=True)

    class Meta:
        db_table = 'avances_salaire'
        ordering = ['-date_avance']

    def __str__(self):
        return f"Avance {self.employe.nom_complet} — {self.montant} FCFA ({self.date_avance})"


class BulletinPaie(TenantModel):
    STATUT_CHOICES = [
        ('BROUILLON', 'Brouillon'),
        ('VALIDE',    'Validé'),
        ('PAYE',      'Payé'),
    ]
    MODE_PAIEMENT_CHOICES = [
        ('BANQUE',       'Banque (virement)'),
        ('CAISSE',       'Caisse (espèces)'),
        ('WAVE',         'Wave'),
        ('ORANGE_MONEY', 'Orange Money'),
        ('FREE_MONEY',   'Free Money'),
        ('WIZALL',       'Wizall'),
        ('AUTRE',        'Autre'),
    ]

    employe            = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='bulletins')
    mois               = models.IntegerField()
    annee              = models.IntegerField()
    parametres_fiscaux = models.ForeignKey(
        ParametresFiscaux, on_delete=models.SET_NULL, null=True, blank=True
    )

    # GAINS
    salaire_base              = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    nb_heures_sup             = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    heures_sup_montant        = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    indemnite_sujetion        = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    indemnite_logement        = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    allocation_salaire_unique = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    prime_transport           = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    primes_diverses           = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    avantages_nature          = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    salaire_brut              = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # RETENUES SALARIALES
    ipres_general_salarie     = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    ipres_cadre_salarie       = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    ir_retenu                 = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    avance_sur_salaire        = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    opposition_saisie         = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    autres_retenues           = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_retenues_salariales = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # CHARGES PATRONALES
    ipres_general_patronal     = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    ipres_cadre_patronal       = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    css_prestations_familiales = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    atmp                       = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cfce                       = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_charges_patronales   = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # RÉSULTAT
    net_a_payer            = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cout_total_employeur   = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    statut                 = models.CharField(max_length=15, choices=STATUT_CHOICES, default='BROUILLON')
    date_validation        = models.DateTimeField(null=True, blank=True)
    date_paiement          = models.DateTimeField(null=True, blank=True)
    mode_paiement_effectif = models.CharField(max_length=15, choices=MODE_PAIEMENT_CHOICES, default='CAISSE')

    avances = models.ManyToManyField(AvanceSalaire, blank=True, related_name='bulletins')

    class Meta:
        db_table = 'bulletins_paie'
        ordering = ['-annee', '-mois']
        unique_together = ['tenant', 'employe', 'mois', 'annee']

    def __str__(self):
        return f"Bulletin {self.employe.nom_complet} — {self.mois:02d}/{self.annee}"

    @property
    def periode(self):
        MOIS = {
            1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril',
            5: 'Mai', 6: 'Juin', 7: 'Juillet', 8: 'Août',
            9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre',
        }
        return f"{MOIS[self.mois]} {self.annee}"
