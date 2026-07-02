"""
Gestion de la Mobilisation des Ressources Financières (GMRF).

Module métier permettant de centraliser toutes les ressources financières de
l'établissement autres que la scolarité : dons, subventions (investissement /
exploitation), partenariats, financements participatifs, revenus exceptionnels,
prêts et financements traditionnels africains (NATT / Tontine).

Principe d'intégration comptable : ce module NE fait aucune saisie comptable
manuelle. Chaque opération génère automatiquement des écritures dans
`comptabilite.JournalEntry` (taggées `source='GMRF_*'`) via `services.py`. Le
Grand Livre, la Balance, le Bilan, le compte de résultat et le tableau de flux
lisent ces écritures : la synchronisation compta / trésorerie / états financiers
est donc automatique. Les numéros de comptes sont entièrement paramétrables par
établissement afin de s'adapter aux recommandations de son expert-comptable.
"""
from django.db import models
from core.models import TenantModel


# ── Type de financement (entièrement paramétrable) ───────────────────────────
class TypeFinancement(TenantModel):
    """Catégorie de ressource financière paramétrable par établissement.

    Générique : de nouveaux mécanismes peuvent être ajoutés sans modifier le
    code. Porte le compte de ressource crédité lors d'une réception de fonds et
    sa nature comptable (produit, capitaux propres ou dette)."""

    CATEGORIE_CHOICES = [
        ('DON',           'Don'),
        ('SUBV_INVEST',   "Subvention d'investissement"),
        ('SUBV_EXPLOIT',  "Subvention d'exploitation"),
        ('PARTENARIAT',   'Partenariat financier'),
        ('CROWDFUNDING',  'Financement participatif (crowdfunding)'),
        ('REVENU_EXCEPT', 'Revenu exceptionnel'),
        ('PRET',          'Prêt / crédit'),
        ('NATT',          'NATT / Tontine'),
        ('AUTRE',         'Autre source de financement'),
    ]
    # Sens comptable de la ressource (compte crédité à la réception)
    NATURE_CHOICES = [
        ('PRODUIT',  'Produit'),           # classe 7 — impacte le résultat
        ('CAPITAUX', 'Capitaux propres'),  # classe 1 (ex. subvention d'investissement 14)
        ('DETTE',    'Dette / financement'),  # classe 1/4 — ni charge ni produit
    ]

    code            = models.CharField(max_length=30)
    libelle         = models.CharField(max_length=150)
    categorie       = models.CharField(max_length=20, choices=CATEGORIE_CHOICES, default='DON')
    nature_comptable = models.CharField(max_length=10, choices=NATURE_CHOICES, default='PRODUIT')
    # Compte crédité lors de la réception des fonds (paramétrable)
    compte_ressource        = models.CharField(max_length=10, default='7588')
    compte_tresorerie_defaut = models.CharField(max_length=10, default='571')
    description     = models.TextField(blank=True, default='')
    est_actif       = models.BooleanField(default=True)
    est_systeme     = models.BooleanField(default=False)  # type par défaut, non supprimable

    class Meta:
        db_table = 'gmrf_types_financement'
        unique_together = ['tenant', 'code']
        ordering = ['libelle']

    def __str__(self):
        return f"{self.libelle} ({self.get_categorie_display()})"


# ── Financement simple (dons, subventions, partenariats, revenus…) ───────────
class Financement(TenantModel):
    """Opération de mobilisation de ressources à réception unique (hors NATT et
    prêts, qui ont leur propre cycle de vie). Comptabilisation à la réception :
    D compte_tresorerie / C compte_ressource."""

    STATUT_CHOICES = [
        ('ATTENDU', 'Attendu / promis'),
        ('RECU',    'Reçu'),
        ('ANNULE',  'Annulé'),
    ]
    TYPE_SOURCE_CHOICES = [
        ('ASSOCIATION', 'Association / ONG'),
        ('PARTICULIER', 'Particulier'),
        ('GROUPEMENT',  'Groupement / coopérative'),
        ('ENTREPRISE',  'Entreprise'),
        ('ETAT',        'État / collectivité'),
        ('AUTRE',       'Autre'),
    ]

    reference       = models.CharField(max_length=30)
    type_financement = models.ForeignKey(TypeFinancement, on_delete=models.PROTECT, related_name='financements')
    libelle         = models.CharField(max_length=200)
    source          = models.CharField(max_length=150, blank=True, default='')   # bailleur / donateur
    type_source     = models.CharField(max_length=15, choices=TYPE_SOURCE_CHOICES, default='AUTRE')
    coordonnees     = models.TextField(blank=True, default='')
    montant         = models.DecimalField(max_digits=15, decimal_places=2)
    devise          = models.CharField(max_length=5, default='XOF')
    date_reception  = models.DateField(null=True, blank=True)
    compte_tresorerie = models.CharField(max_length=10, default='571')
    compte_ressource  = models.CharField(max_length=10, default='7588')
    statut          = models.CharField(max_length=10, choices=STATUT_CHOICES, default='ATTENDU')
    observations    = models.TextField(blank=True, default='')
    documents       = models.JSONField(default=list, blank=True)  # [{nom, url|data}]

    class Meta:
        db_table = 'gmrf_financements'
        unique_together = ['tenant', 'reference']
        ordering = ['-date_reception', 'reference']

    def __str__(self):
        return f"{self.reference} — {self.libelle}"


# ── NATT / Tontine — l'établissement est PARTICIPANT (pas organisateur) ───────
class NattCycle(TenantModel):
    """Participation à un NATT / Tontine organisé par un tiers.

    L'établissement souscrit et cotise ; il reçoit la cagnotte une fois durant le
    cycle. Traitement comptable (ni charge ni produit) :
      • cotisation avant réception : D compte_creance / C trésorerie
      • réception de la cagnotte   : D trésorerie / C compte_creance (cotisations
        déjà versées) + C compte_dette (avance du groupe à rembourser)
      • cotisation après réception : D compte_dette / C trésorerie
    En fin de cycle, créance = dette = 0 : le NATT est un financement temporaire.
    Tous les comptes sont paramétrables."""

    TYPE_ORGANISATEUR_CHOICES = [
        ('ASSOCIATION', 'Association'),
        ('PARTICULIER', 'Particulier'),
        ('GROUPEMENT',  'Groupement'),
        ('ENTREPRISE',  'Entreprise'),
        ('AUTRE',       'Autre'),
    ]
    PERIODICITE_CHOICES = [
        ('HEBDOMADAIRE', 'Hebdomadaire'),
        ('MENSUELLE',    'Mensuelle'),
        ('TRIMESTRIELLE', 'Trimestrielle'),
    ]
    MODE_ATTRIBUTION_CHOICES = [
        ('TIRAGE',    'Tirage au sort'),
        ('ORDRE',     'Ordre prédéfini'),
        ('CONSENSUS', 'Consensus'),
        ('AUTRE',     'Autre'),
    ]
    STATUT_CHOICES = [
        ('EN_COURS', 'En cours'),
        ('CLOTURE',  'Clôturé'),
        ('ANNULE',   'Annulé'),
    ]

    reference        = models.CharField(max_length=30)
    nom              = models.CharField(max_length=200)
    organisateur     = models.CharField(max_length=200, blank=True, default='')
    type_organisateur = models.CharField(max_length=15, choices=TYPE_ORGANISATEUR_CHOICES, default='AUTRE')
    coordonnees      = models.TextField(blank=True, default='')
    nb_participants  = models.IntegerField(default=0)
    duree            = models.IntegerField(help_text="Nombre d'échéances du cycle")
    periodicite      = models.CharField(max_length=15, choices=PERIODICITE_CHOICES, default='MENSUELLE')
    montant_cotisation = models.DecimalField(max_digits=15, decimal_places=2)
    mode_attribution = models.CharField(max_length=12, choices=MODE_ATTRIBUTION_CHOICES, default='TIRAGE')
    date_debut       = models.DateField()
    date_fin         = models.DateField(null=True, blank=True)
    compte_tresorerie = models.CharField(max_length=10, default='571')
    compte_creance   = models.CharField(max_length=10, default='4718')  # créances sur tontine
    compte_dette     = models.CharField(max_length=10, default='4798')  # dettes sur tontine
    devise           = models.CharField(max_length=5, default='XOF')
    observations     = models.TextField(blank=True, default='')
    documents        = models.JSONField(default=list, blank=True)
    statut           = models.CharField(max_length=10, choices=STATUT_CHOICES, default='EN_COURS')

    class Meta:
        db_table = 'gmrf_natt_cycles'
        unique_together = ['tenant', 'reference']
        ordering = ['-date_debut', 'reference']

    def __str__(self):
        return f"{self.reference} — {self.nom}"

    @property
    def montant_cagnotte(self):
        """Montant reçu par le bénéficiaire à chaque échéance = cotisation × participants."""
        return round(float(self.montant_cotisation) * (self.nb_participants or 0), 2)

    @property
    def total_a_cotiser(self):
        """Total que l'établissement versera sur tout le cycle = cotisation × durée."""
        return round(float(self.montant_cotisation) * (self.duree or 0), 2)


class NattCotisation(TenantModel):
    """Une échéance de cotisation de l'établissement sur un cycle NATT."""

    STATUT_CHOICES = [
        ('A_PAYER',   'À payer'),
        ('PAYE',      'Payée'),
        ('EN_RETARD', 'En retard'),
    ]

    cycle         = models.ForeignKey(NattCycle, on_delete=models.CASCADE, related_name='cotisations')
    numero        = models.IntegerField(help_text="Numéro d'échéance (1..durée)")
    date_echeance = models.DateField()
    montant       = models.DecimalField(max_digits=15, decimal_places=2)
    statut        = models.CharField(max_length=10, choices=STATUT_CHOICES, default='A_PAYER')
    date_paiement = models.DateField(null=True, blank=True)
    compte_tresorerie = models.CharField(max_length=10, blank=True, default='')  # renseigné au paiement

    class Meta:
        db_table = 'gmrf_natt_cotisations'
        unique_together = ['tenant', 'cycle', 'numero']
        ordering = ['cycle', 'numero']

    def __str__(self):
        return f"{self.cycle.reference} — cotisation {self.numero}"


class NattReception(TenantModel):
    """Réception de la cagnotte par l'établissement (une seule fois par cycle)."""

    cycle           = models.OneToOneField(NattCycle, on_delete=models.CASCADE, related_name='reception')
    numero_echeance = models.IntegerField(help_text="Échéance à laquelle la cagnotte est perçue")
    date_reception  = models.DateField()
    montant_recu    = models.DecimalField(max_digits=15, decimal_places=2)
    compte_tresorerie = models.CharField(max_length=10, default='571')
    # Ventilation calculée à la comptabilisation (traçabilité)
    montant_creance_soldee = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    montant_dette          = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    observations    = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'gmrf_natt_receptions'
        ordering = ['-date_reception']

    def __str__(self):
        return f"{self.cycle.reference} — réception échéance {self.numero_echeance}"
