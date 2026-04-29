from django.db import models
from core.models import TenantModel
import uuid

class Employe(TenantModel):
    TYPE_CHOICES = [
        ('ENSEIGNANT',    'Enseignant'),
        ('ADMINISTRATION','Administration'),
        ('APPUI',         'Personnel d\'appui'),
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

    matricule       = models.CharField(max_length=20, blank=True)
    nom_complet     = models.CharField(max_length=200)
    type_employe    = models.CharField(max_length=20, choices=TYPE_CHOICES)
    poste           = models.CharField(max_length=100)
    type_contrat    = models.CharField(max_length=20, choices=CONTRAT_CHOICES, default='CDI')
    date_embauche   = models.DateField()
    date_fin_contrat= models.DateField(null=True, blank=True)
    salaire_base    = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    telephone       = models.CharField(max_length=20, blank=True)
    email           = models.EmailField(blank=True)
    statut          = models.CharField(max_length=20, choices=STATUT_CHOICES, default='ACTIF')

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
    employe         = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='paies')
    mois            = models.CharField(max_length=7)  # YYYY-MM
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
