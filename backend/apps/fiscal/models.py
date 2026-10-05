"""Fiscalité de l'établissement — paramétrable, datée, par profil.

Rien n'est codé en dur : un taux, un seuil ou une obligation qui change avec
une loi de finances se met à jour ici, avec sa date d'effet, sans
redéploiement. Trois objets :

- ParametreFiscal : une valeur datée (taux d'IS, TVA, plancher de l'IMF…).
  Sans école : la valeur nationale (tenue par HADY GESMAN) ; avec école : une
  surcharge propre à cet établissement (régime particulier, convention).
- ObligationFiscale : une obligation décrite en données — sa base, sa
  formule, les paramètres qu'elle lit, ses comptes SYSCOHADA, et les profils
  d'établissement auxquels elle s'applique.
- ProfilFiscal : ce qu'est l'établissement au regard de l'impôt — forme
  juridique, statut (laïc, confessionnel, franco-arabe, daara…), but lucratif,
  régime, TVA, exonérations datées et motivées.

Le moteur (apps/fiscal/moteur.py) croise les trois : chaque obligation est
applicable ou non selon le profil, exonérée ou non sur la période, et
calculée avec les paramètres en vigueur à la date de clôture de l'exercice.
Les montants restent des ESTIMATIONS à confirmer avec un expert-comptable ou
la DGID.
"""
from django.db import models

from core.models import TenantModel, TimeStampedModel


class ParametreFiscal(TimeStampedModel):
    UNITE_CHOICES = [('%', 'Pourcentage'), ('FCFA', 'Montant en FCFA'), ('MOIS', 'Mois'),
                     ('JOUR', 'Jour du mois'), ('NOMBRE', 'Nombre')]
    tenant      = models.ForeignKey('tenants.Tenant', null=True, blank=True, on_delete=models.CASCADE,
                                    related_name='parametres_fiscaux')
    code        = models.CharField(max_length=40)
    libelle     = models.CharField(max_length=200)
    valeur      = models.DecimalField(max_digits=18, decimal_places=4)
    unite       = models.CharField(max_length=6, choices=UNITE_CHOICES, default='%')
    date_effet  = models.DateField()
    date_fin    = models.DateField(null=True, blank=True)
    reference   = models.CharField(max_length=250, blank=True, default='')
    # Valeur reprise sans certitude du texte en vigueur : à confirmer.
    a_verifier  = models.BooleanField(default=False)
    observations = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'fiscal_parametres'
        ordering = ['code', '-date_effet']
        constraints = [models.UniqueConstraint(fields=['tenant', 'code', 'date_effet'],
                                               name='uniq_param_fiscal_date')]

    def __str__(self):
        return f"{self.code} = {self.valeur} ({self.date_effet})"


class ObligationFiscale(TimeStampedModel):
    BASE_CHOICES = [
        ('RESULTAT', 'Résultat fiscal estimé'),
        ('PRODUITS', "Chiffre d'affaires / produits"),
        ('TVA_NETTE', 'TVA collectée − TVA déductible'),
        ('MASSE_SALARIALE', 'Masse salariale brute'),
        ('SAISIE', "Montant de l'avis (saisi)"),
        ('AUCUNE', 'Information'),
    ]
    FORMULE_CHOICES = [
        ('TAUX', 'Base × taux'),
        ('IS_IMF', 'Plus élevé de IS (taux × résultat) et IMF (minimum forfaitaire)'),
        ('MASSE_SALARIALE', 'Masse salariale × taux (bulletins de paie si disponibles)'),
        ('TVA', 'TVA nette du journal'),
        ('SAISIE', 'Montant saisi'),
        ('RH', 'Calculée par le module RH'),
        ('INFO', 'Information seulement'),
    ]
    code         = models.CharField(max_length=20, unique=True)
    libelle      = models.CharField(max_length=200)
    description  = models.TextField(blank=True, default='')
    base         = models.CharField(max_length=20, choices=BASE_CHOICES, default='AUCUNE')
    formule      = models.CharField(max_length=20, choices=FORMULE_CHOICES, default='INFO')
    # Codes des ParametreFiscal lus : {"taux": "IS_TAUX", "minimum_taux": "IMF_TAUX", …}
    parametres   = models.JSONField(default=dict, blank=True)
    periodicite  = models.CharField(max_length=60, blank=True, default='')
    echeance     = models.CharField(max_length=250, blank=True, default='')
    compte_debit = models.CharField(max_length=10, blank=True, default='')
    compte_credit = models.CharField(max_length=10, blank=True, default='')
    # À qui elle s'applique. Clés possibles, toutes facultatives :
    # formes, exclure_formes, regimes, statuts, but_lucratif (true/false),
    # assujetti_tva (true/false), proprietaire_locaux (true), employeur (true).
    conditions   = models.JSONField(default=dict, blank=True)
    # Message quand le profil n'est pas concerné (association sans but
    # lucratif devant l'IS, établissement non assujetti à la TVA…).
    message_non_applicable = models.TextField(blank=True, default='')
    reference    = models.CharField(max_length=250, blank=True, default='')
    a_verifier   = models.BooleanField(default=False)
    ordre        = models.IntegerField(default=0)
    actif        = models.BooleanField(default=True)

    class Meta:
        db_table = 'fiscal_obligations'
        ordering = ['ordre', 'code']

    def __str__(self):
        return self.libelle


class ProfilFiscal(TenantModel):
    FORME_CHOICES = [
        ('SA', 'Société anonyme (SA)'), ('SARL', 'SARL'), ('SUARL', 'SUARL'), ('SAS', 'SAS'),
        ('SNC', 'Société en nom collectif'), ('EI', 'Entreprise individuelle'),
        ('GIE', "Groupement d'intérêt économique"), ('ASSOCIATION', 'Association'),
        ('FONDATION', 'Fondation'), ('ONG', 'ONG'), ('CONGREGATION', 'Congrégation / institution religieuse'),
        ('COOPERATIVE', 'Coopérative'), ('AUTRE', 'Autre'),
    ]
    STATUT_CHOICES = [
        ('PRIVE_LAIC', 'Privé laïc'), ('PRIVE_CATHOLIQUE', 'Privé catholique'),
        ('FRANCO_ARABE', 'Franco-arabe'), ('DAARA', 'Daara (école coranique)'),
        ('COMMUNAUTAIRE', 'Communautaire / associatif'), ('FORMATION_PRO', 'Formation professionnelle'),
        ('SUPERIEUR', 'Enseignement supérieur privé'), ('AUTRE', 'Autre'),
    ]
    REGIME_CHOICES = [
        ('REEL_NORMAL', 'Régime du réel normal'), ('REEL_SIMPLIFIE', 'Régime du réel simplifié'),
        ('CGU', 'Contribution globale unique (CGU)'), ('NON_ASSUJETTI', 'Non assujetti (exonéré total)'),
    ]
    tenant          = models.OneToOneField('tenants.Tenant', on_delete=models.CASCADE,
                                           related_name='profil_fiscal')
    forme_juridique = models.CharField(max_length=15, choices=FORME_CHOICES, default='AUTRE')
    statut          = models.CharField(max_length=20, choices=STATUT_CHOICES, default='PRIVE_LAIC')
    but_lucratif    = models.BooleanField(default=True)
    regime          = models.CharField(max_length=15, choices=REGIME_CHOICES, default='REEL_NORMAL')
    assujetti_tva   = models.BooleanField(default=False)
    proprietaire_locaux = models.BooleanField(default=False)
    centre_fiscal   = models.CharField(max_length=150, blank=True, default='')
    date_debut_activite = models.DateField(null=True, blank=True)
    numero_agrement = models.CharField(max_length=100, blank=True, default='')
    # [{"obligation": "IS", "motif": "Agrément Code des investissements",
    #   "reference": "Arrêté n°…", "date_debut": "2025-01-01", "date_fin": "2029-12-31"}]
    exonerations    = models.JSONField(default=list, blank=True)
    observations    = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'fiscal_profils'

    def __str__(self):
        return f"Profil fiscal — {self.tenant}"
