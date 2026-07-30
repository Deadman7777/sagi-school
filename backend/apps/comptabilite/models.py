from django.db import models
from core.models import TenantModel


class JournalEntry(TenantModel):
    exercice      = models.ForeignKey('paiements.Exercice', on_delete=models.CASCADE, related_name='journal')
    no_piece      = models.CharField(max_length=30)
    date_ecriture = models.DateField()
    no_compte     = models.CharField(max_length=20)
    libelle       = models.TextField()
    debit         = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    credit        = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    source        = models.CharField(max_length=20, blank=True)
    source_id     = models.UUIDField(null=True, blank=True)
    ordre         = models.IntegerField(default=0)
    # Dimension analytique (Lot 0 gouvernance) : rattache la ligne à un projet.
    # Nullable — toutes les écritures existantes et non ventilées restent valides.
    # La traçabilité « par projet » se lit par agrégation sur ce champ, sans
    # dupliquer les montants ailleurs (une seule source de vérité : le ledger).
    projet        = models.ForeignKey('gouvernance.Projet', null=True, blank=True,
                                      on_delete=models.SET_NULL, related_name='ecritures')
    # Dimension analytique (Lot 2) : rattache la ligne à une ressource financière.
    # Nullable — la consommation d'une ressource = agrégation des débits taggés ici
    # (comptes 6xx/2xx), sans dupliquer les montants. Une seule source : le ledger.
    ressource     = models.ForeignKey('gouvernance.Ressource', null=True, blank=True,
                                      on_delete=models.SET_NULL, related_name='ecritures')
    # Imputation budgétaire explicite : à QUELLE ligne de budget cette charge
    # se rattache. Le suivi ne pouvait s'appuyer que sur le numéro de compte,
    # or une école utilise le même 6xx pour des dépenses budgétées et d'autres
    # qui ne le sont pas — toutes comptaient comme du réalisé. Nullable :
    # « hors budget » reste le cas normal, et rien n'oblige à imputer.
    budget_ligne  = models.ForeignKey('comptabilite.BudgetLigne', null=True, blank=True,
                                      on_delete=models.SET_NULL, related_name='ecritures')

    class Meta:
        db_table = 'journal_entries'
        ordering = ['date_ecriture', 'no_piece', 'ordre']

    def __str__(self):
        return f"{self.no_piece} — {self.libelle}"


class CompteComptable(TenantModel):
    """Plan comptable SYSCOHADA Révisé paramétrable par établissement."""
    TYPE_CHOICES = [
        ('BILAN',   'Compte de bilan'),
        ('CHARGE',  'Compte de charge'),
        ('PRODUIT', 'Compte de produit'),
    ]

    no_compte   = models.CharField(max_length=10)
    libelle     = models.CharField(max_length=200)
    type        = models.CharField(max_length=10, choices=TYPE_CHOICES, default='CHARGE')
    classe      = models.IntegerField()          # 1 à 9
    est_actif   = models.BooleanField(default=True)
    est_systeme = models.BooleanField(default=False)  # comptes non supprimables

    class Meta:
        db_table = 'comptes_comptables'
        unique_together = ['tenant', 'no_compte']
        ordering = ['no_compte']

    def __str__(self):
        return f"{self.no_compte} — {self.libelle}"


class BudgetLigne(TenantModel):
    """Budget prévisionnel mensuel par compte et par exercice."""
    TYPE_CHOICES = [
        ('FIXE',     'Charge fixe'),
        ('VARIABLE', 'Charge variable'),
    ]

    # D'où vient le RÉALISÉ de cette ligne. Le budget ne savait faire que
    # « tout le compte » : une école qui passe sur son 658 une dépense budgétée
    # et trois qui ne le sont pas voyait les quatre consommer son budget.
    #
    #   COMPTE     — tout ce qui passe sur le compte (comportement d'origine,
    #                conservé par défaut : personne ne voit ses chiffres bouger)
    #   IMPUTATION — seulement les charges rattachées explicitement à la ligne
    #   PAIE       — seulement les écritures de paie. Une charge de personnel
    #                saisie à la main À CÔTÉ du bulletin ne la compte pas deux
    #                fois. Vaut pour tout poste alimenté par un module dédié.
    REALISE_CHOICES = [
        ('COMPTE',     'Tout ce qui passe sur ce compte'),
        ('IMPUTATION', 'Seulement les charges rattachées à cette ligne'),
        ('PAIE',       'Seulement la paie'),
    ]

    exercice    = models.ForeignKey('paiements.Exercice', on_delete=models.CASCADE, related_name='budget_lignes')
    no_compte   = models.CharField(max_length=10)
    libelle     = models.CharField(max_length=200)
    type_charge = models.CharField(max_length=10, choices=TYPE_CHOICES, default='FIXE')
    # Montants mensuels (FCFA)
    m01 = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    m02 = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    m03 = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    m04 = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    m05 = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    m06 = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    m07 = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    m08 = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    m09 = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    m10 = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    m11 = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    m12 = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    # Dimensions analytiques (gouvernance) : budget ventilable par projet et
    # rattachable à une ressource de financement. Le réalisé se compare par
    # projet via le tag `projet` du grand livre. Nullables → budget « général ».
    projet    = models.ForeignKey('gouvernance.Projet', null=True, blank=True,
                                  on_delete=models.SET_NULL, related_name='budget_lignes')
    ressource = models.ForeignKey('gouvernance.Ressource', null=True, blank=True,
                                  on_delete=models.SET_NULL, related_name='budget_lignes')

    mode_realise = models.CharField(max_length=12, choices=REALISE_CHOICES, default='COMPTE')

    class Meta:
        db_table = 'budget_lignes'
        # PLUS d'unicité sur (compte, projet). Une école budgète plusieurs
        # postes sur un même compte — « Loyer école » et « Loyer internat » sont
        # tous deux du 622. La contrainte faisait écraser la ligne précédente
        # par update_or_create : dix postes saisis, six lignes affichées, et
        # chaque ajout suivant gonflait un total sans jamais créer de ligne.
        # Une ligne budgétaire est identifiée par son id, décrite par son
        # libellé, et le compte n'est plus qu'une imputation comptable.
        ordering = ['no_compte', 'libelle']

    def __str__(self):
        return f"Budget {self.no_compte} — {self.exercice.annee_scolaire}"

    @property
    def total_prevu(self):
        return sum(getattr(self, f'm{i:02d}') for i in range(1, 13))

    def to_dict_montants(self):
        return {i: float(getattr(self, f'm{i:02d}')) for i in range(1, 13)}


class Immobilisation(TenantModel):
    """Gestion des immobilisations et calcul des amortissements (SYSCOHADA Révisé)."""
    MODE_CHOICES = [
        ('LINEAIRE',  'Linéaire'),
        ('DEGRESSIF', 'Dégressif'),
    ]

    COMPTES_IMMO = [
        ('211', '211 — Terrains'),
        ('221', '221 — Bâtiments'),
        ('231', '231 — Matériel et outillage'),
        ('241', '241 — Mobilier'),
        ('244', '244 — Matériel informatique'),
        ('245', '245 — Matériel de transport'),
        ('248', '248 — Autres immobilisations corporelles'),
    ]
    COMPTES_AMORT = [
        ('2811', '2811 — Amort. Terrains'),
        ('2821', '2821 — Amort. Bâtiments'),
        ('2831', '2831 — Amort. Matériel et outillage'),
        ('2841', '2841 — Amort. Mobilier'),
        ('2844', '2844 — Amort. Matériel informatique'),
        ('2845', '2845 — Amort. Matériel de transport'),
        ('2848', '2848 — Amort. Autres immo. corporelles'),
    ]

    COMPTE_FOURN_CHOICES = [
        ('404', '404 — Fournisseurs d\'immobilisations'),
        ('481', '481 — Fournisseurs d\'immo. (autre tiers)'),
    ]
    MODE_REGLEMENT_CHOICES = [
        ('',            'Non réglé (à payer)'),
        ('ESPECE',      'Espèce'),
        ('WAVE',        'Wave'),
        ('ORANGE_MONEY','Orange Money'),
        ('FREE_MONEY',  'Free Money'),
        ('VIREMENT',    'Virement'),
        ('CHEQUE',      'Chèque'),
    ]

    no_bien                  = models.CharField(max_length=20, unique=False)
    libelle                  = models.CharField(max_length=200)
    date_entree              = models.DateField()
    valeur_entree            = models.DecimalField(max_digits=15, decimal_places=2)
    duree_utilisation        = models.IntegerField(help_text='Années')
    mode_amortissement       = models.CharField(max_length=10, choices=MODE_CHOICES, default='LINEAIRE')
    no_compte_immobilisation = models.CharField(max_length=10, default='231')
    no_compte_amortissement  = models.CharField(max_length=10, default='2831')
    cumul_amortissements     = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    est_cede                 = models.BooleanField(default=False)
    # Règlement
    compte_fournisseur       = models.CharField(max_length=5, choices=COMPTE_FOURN_CHOICES, default='404')
    mode_reglement           = models.CharField(max_length=20, choices=MODE_REGLEMENT_CHOICES, blank=True, default='')
    compte_tresorerie        = models.CharField(max_length=10, blank=True, default='')
    # Financement (Lot 3 gouvernance) : l'immobilisation « connaît » sa ressource
    # et son projet. Les écritures d'acquisition sont déjà taggées de la même
    # dimension (traçabilité ledger) ; ces FK portent l'info sur le bien lui-même.
    ressource                = models.ForeignKey('gouvernance.Ressource', null=True, blank=True,
                                                 on_delete=models.SET_NULL, related_name='immobilisations')
    projet                   = models.ForeignKey('gouvernance.Projet', null=True, blank=True,
                                                 on_delete=models.SET_NULL, related_name='immobilisations')

    class Meta:
        db_table = 'immobilisations'
        ordering = ['date_entree', 'no_bien']

    @property
    def taux_amortissement(self):
        if not self.duree_utilisation:
            return 0
        return round(100 / self.duree_utilisation, 4)

    @property
    def annuite_amortissement(self):
        return round(float(self.valeur_entree) / self.duree_utilisation, 2)

    @property
    def valeur_nette_comptable(self):
        return round(float(self.valeur_entree) - float(self.cumul_amortissements), 2)

    @property
    def est_amorti(self):
        return float(self.cumul_amortissements) >= float(self.valeur_entree)

    def __str__(self):
        return f"{self.no_bien} — {self.libelle}"
