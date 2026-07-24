"""
Socle de la gouvernance financière (Lot 0).

Deux briques transversales, fondations des lots suivants (ressources,
affectation, traçabilité, provisions, rapprochement bancaire) :

  • `Projet` — dimension analytique. Un projet regroupe des ressources et des
    emplois (charges, immobilisations, trésorerie). La consommation réelle n'est
    JAMAIS dupliquée ici : elle est portée par le grand livre
    (`comptabilite.JournalEntry.projet`) et lue par agrégation. Un seul point de
    vérité, zéro double comptage — cohérent avec l'architecture SYSCOHADA
    existante où tous les états financiers dérivent du ledger.

  • `PieceJustificative` — GED générique. Une pièce peut être rattachée à
    n'importe quel objet métier (charge, paiement, immobilisation, financement,
    prêt, projet, écriture…) via le couple typé (`objet_type`, `objet_id`), le
    même idiome que `JournalEntry.source` / `source_id`. Le fichier est stocké en
    base64 dans la base (comme le champ `documents` de GMRF) : il est ainsi
    capturé par les sauvegardes pg_dump, en local (Electron/Windows) comme en
    cloud, sans dépendance à un stockage de fichiers externe.
"""
from django.db import models
from core.models import TenantModel


class Projet(TenantModel):
    """Dimension analytique regroupant ressources et emplois d'un établissement.

    Le budget prévisionnel (`budget_prevu`) est une enveloppe de gestion, non
    comptable. La consommation effective se calcule en lisant les écritures
    taggées `JournalEntry.projet = self` (charges classe 6 + immobilisations
    classe 2), garantissant la cohérence avec la comptabilité."""

    STATUT_CHOICES = [
        ('PLANIFIE',  'Planifié'),
        ('EN_COURS',  'En cours'),
        ('SUSPENDU',  'Suspendu'),
        ('TERMINE',   'Terminé'),
        ('ANNULE',    'Annulé'),
    ]

    code         = models.CharField(max_length=30)
    libelle      = models.CharField(max_length=200)
    description  = models.TextField(blank=True, default='')
    responsable  = models.CharField(max_length=150, blank=True, default='')
    date_debut   = models.DateField(null=True, blank=True)
    date_fin     = models.DateField(null=True, blank=True)
    budget_prevu = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    statut       = models.CharField(max_length=10, choices=STATUT_CHOICES, default='PLANIFIE')
    observations = models.TextField(blank=True, default='')
    est_actif    = models.BooleanField(default=True)

    class Meta:
        db_table = 'gouvernance_projets'
        # `code` est séquentiel PAR école (PROJ-0001 généré via filter(tenant=…)) :
        # unicité par tenant, jamais globale, sinon collision 500 sur une nouvelle
        # école (cf. règle projet « unique par tenant »).
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'code'], name='uniq_projet_code_par_tenant'),
        ]
        ordering = ['-date_debut', 'code']

    def __str__(self):
        return f"{self.code} — {self.libelle}"


class Ressource(TenantModel):
    """Enveloppe unifiée de ressources financières (Lot 2).

    Registre transversal de toutes les origines de fonds : fonds propres, prêts,
    subventions, dons, partenariats, projets, cotisations exceptionnelles, avances
    de trésorerie, recettes scolaires… Une ressource peut refléter une opération
    déjà saisie dans GMRF (lien `financement`/`pret`) afin d'éviter toute double
    saisie ; dans ce cas l'encaissement est comptabilisé par GMRF, pas ici.

    Ce modèle est une COUCHE DE GESTION (affectation + suivi de consommation) :
    il ne génère AUCUNE écriture d'encaissement. La consommation réelle est lue
    par agrégation des débits taggés `JournalEntry.ressource = self` (comptes 6xx
    et 2xx) — une seule source de vérité, le ledger, comme pour la dimension
    `projet`. Zéro double comptage."""

    TYPE_CHOICES = [
        ('FONDS_PROPRES',      'Fonds propres'),
        ('PRET',               'Prêt'),
        ('SUBVENTION',         'Subvention'),
        ('DON',                'Don'),
        ('PARTENAIRE',         'Partenaire'),
        ('PROJET',             'Financement de projet'),
        ('COTISATION_EXCEPT',  'Cotisation exceptionnelle'),
        ('AVANCE_TRESO',       'Avance de trésorerie'),
        ('RECETTES_SCOLAIRES', 'Recettes scolaires'),
        ('AUTRE',              'Autre ressource'),
    ]
    STATUT_CHOICES = [
        ('ACTIVE',   'Active'),
        ('CLOTUREE', 'Clôturée'),
        ('ANNULEE',  'Annulée'),
    ]

    reference       = models.CharField(max_length=30)
    type_ressource  = models.CharField(max_length=20, choices=TYPE_CHOICES, default='AUTRE')
    libelle         = models.CharField(max_length=200)
    organisme       = models.CharField(max_length=200, blank=True, default='')  # financeur / origine
    montant         = models.DecimalField(max_digits=15, decimal_places=2)
    date_ressource  = models.DateField(null=True, blank=True)
    compte_tresorerie = models.CharField(max_length=10, blank=True, default='')  # informatif
    convention      = models.CharField(max_length=200, blank=True, default='')
    taux            = models.DecimalField(max_digits=6, decimal_places=3, default=0)  # si prêt
    statut          = models.CharField(max_length=10, choices=STATUT_CHOICES, default='ACTIVE')
    observations    = models.TextField(blank=True, default='')
    projet          = models.ForeignKey('gouvernance.Projet', null=True, blank=True,
                                        on_delete=models.SET_NULL, related_name='ressources')
    # Liens GMRF optionnels — la ressource reflète une opération déjà comptabilisée.
    financement     = models.ForeignKey('gmrf.Financement', null=True, blank=True,
                                        on_delete=models.SET_NULL, related_name='ressources_gouv')
    pret            = models.ForeignKey('gmrf.Pret', null=True, blank=True,
                                        on_delete=models.SET_NULL, related_name='ressources_gouv')

    class Meta:
        db_table = 'gouvernance_ressources'
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'reference'],
                                    name='uniq_ressource_ref_par_tenant'),
        ]
        ordering = ['-date_ressource', 'reference']

    def __str__(self):
        return f"{self.reference} — {self.libelle}"


class AffectationRessource(TenantModel):
    """Affectation prévisionnelle d'une part d'une ressource à un emploi (Lot 2).

    Acte de PLANIFICATION (« ce prêt servira à : 3M d'ordinateurs, 2M de
    travaux… ») : aucun mouvement de fonds, donc aucune écriture comptable. La
    dépense réelle correspondante est ensuite liée à la ressource au moment de la
    saisie (dimension `JournalEntry.ressource`), ce qui alimente la consommation."""

    TYPE_EMPLOI_CHOICES = [
        ('IMMOBILISATION', 'Immobilisation'),
        ('EQUIPEMENT',     'Équipement'),
        ('TRAVAUX',        'Travaux'),
        ('MOBILIER',       'Mobilier'),
        ('FONCTIONNEMENT', 'Fonctionnement'),
        ('SALAIRES',       'Salaires'),
        ('PROJET',         'Projet'),
        ('TRESORERIE',     'Trésorerie'),
        ('AUTRE',          'Autre emploi'),
    ]

    ressource     = models.ForeignKey(Ressource, on_delete=models.CASCADE, related_name='affectations')
    type_emploi   = models.CharField(max_length=15, choices=TYPE_EMPLOI_CHOICES, default='AUTRE')
    libelle       = models.CharField(max_length=200)
    montant_affecte = models.DecimalField(max_digits=15, decimal_places=2)
    projet        = models.ForeignKey('gouvernance.Projet', null=True, blank=True,
                                      on_delete=models.SET_NULL, related_name='affectations')
    date_affectation = models.DateField(null=True, blank=True)
    observations  = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'gouvernance_affectations'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.ressource.reference} → {self.libelle} ({self.montant_affecte})"


class CompteBancaire(TenantModel):
    """Compte bancaire de l'établissement (Lot 5).

    Chaque compte est rattaché à un compte comptable de trésorerie (521, 5211…),
    ce qui permet de gérer plusieurs banques et de rapprocher chacune avec son
    relevé."""

    libelle            = models.CharField(max_length=150)
    banque             = models.CharField(max_length=150, blank=True, default='')
    numero_compte      = models.CharField(max_length=50, blank=True, default='')  # RIB / IBAN
    no_compte_comptable = models.CharField(max_length=10, default='521')
    devise             = models.CharField(max_length=5, default='XOF')
    solde_initial      = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    actif              = models.BooleanField(default=True)

    class Meta:
        db_table = 'gouvernance_comptes_bancaires'
        ordering = ['libelle']

    def __str__(self):
        return f"{self.libelle} ({self.no_compte_comptable})"


class Rapprochement(TenantModel):
    """Session de rapprochement bancaire à une date donnée (Lot 5).

    Confronte le solde du relevé bancaire au solde comptable du compte (dérivé du
    ledger). L'écart est expliqué par les opérations non pointées de part et
    d'autre (chèques émis non débités, dépôts en transit, agios non comptabilisés…)."""

    STATUT_CHOICES = [
        ('EN_COURS', 'En cours'),
        ('VALIDE',   'Validé'),
    ]

    compte_bancaire   = models.ForeignKey(CompteBancaire, on_delete=models.CASCADE, related_name='rapprochements')
    exercice          = models.ForeignKey('paiements.Exercice', on_delete=models.CASCADE, related_name='rapprochements')
    reference         = models.CharField(max_length=30)
    date_rapprochement = models.DateField()
    solde_releve      = models.DecimalField(max_digits=15, decimal_places=2, default=0)  # solde final du relevé
    statut            = models.CharField(max_length=10, choices=STATUT_CHOICES, default='EN_COURS')
    observations      = models.TextField(blank=True, default='')
    date_validation   = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'gouvernance_rapprochements'
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'reference'],
                                    name='uniq_rapprochement_ref_par_tenant'),
        ]
        ordering = ['-date_rapprochement']

    def __str__(self):
        return f"{self.reference} — {self.compte_bancaire.libelle}"


class LigneReleve(TenantModel):
    """Ligne d'un relevé bancaire importé (Lot 5).

    `sens` selon l'effet sur la trésorerie de l'établissement :
      • ENTREE = encaissement (au débit du compte 521 dans nos livres)
      • SORTIE = décaissement (au crédit du compte 521)
    `journal_entry` pointe l'écriture du ledger à laquelle la ligne est rapprochée."""

    SENS_CHOICES = [
        ('ENTREE', 'Entrée (encaissement)'),
        ('SORTIE', 'Sortie (décaissement)'),
    ]
    STATUT_CHOICES = [
        ('NON_RAPPROCHEE', 'Non rapprochée'),
        ('RAPPROCHEE',     'Rapprochée'),
        ('REGULARISEE',    'Régularisée'),
    ]

    rapprochement  = models.ForeignKey(Rapprochement, on_delete=models.CASCADE, related_name='lignes')
    date_operation = models.DateField()
    libelle        = models.CharField(max_length=200)
    montant        = models.DecimalField(max_digits=15, decimal_places=2)  # positif
    sens           = models.CharField(max_length=6, choices=SENS_CHOICES)
    reference      = models.CharField(max_length=80, blank=True, default='')  # n° chèque / opération
    statut         = models.CharField(max_length=15, choices=STATUT_CHOICES, default='NON_RAPPROCHEE')
    journal_entry  = models.ForeignKey('comptabilite.JournalEntry', null=True, blank=True,
                                       on_delete=models.SET_NULL, related_name='+')

    class Meta:
        db_table = 'gouvernance_lignes_releve'
        ordering = ['date_operation', 'created_at']

    def __str__(self):
        return f"{self.date_operation} — {self.libelle} ({self.montant})"


class Provision(TenantModel):
    """Provision / dépréciation SYSCOHADA Révisé (Lot 4).

    Comptabilisation automatique via `services.py`, comptes paramétrables :
      • dotation : D compte_dotation (charge) / C compte_provision (bilan)
      • reprise  : D compte_provision / C compte_reprise (produit)
    Les états financiers (résultat, bilan) dérivant du ledger, l'intégration est
    automatique : les dotations d'exploitation (691) impactent le résultat
    d'exploitation, les provisions R&C (19x) et dépréciations (49x) le bilan ; les
    provisions réglementées (15x) figurent en capitaux propres (HAO 85/86)."""

    TYPE_CHOICES = [
        ('RISQUE',           'Provision pour risques'),
        ('LITIGE',           'Provision pour litiges'),
        ('CHARGE',           'Provision pour charges'),
        ('CREANCE_DOUTEUSE', 'Dépréciation de créances douteuses'),
        ('REGLEMENTEE',      'Provision réglementée'),
    ]
    STATUT_CHOICES = [
        ('ACTIVE', 'Active'),
        ('SOLDEE', 'Soldée'),
        ('ANNULEE', 'Annulée'),
    ]

    reference        = models.CharField(max_length=30)
    exercice         = models.ForeignKey('paiements.Exercice', on_delete=models.CASCADE,
                                         related_name='provisions')
    type_provision   = models.CharField(max_length=20, choices=TYPE_CHOICES, default='RISQUE')
    libelle          = models.CharField(max_length=200)
    montant          = models.DecimalField(max_digits=15, decimal_places=2)  # doté initial
    montant_repris   = models.DecimalField(max_digits=15, decimal_places=2, default=0)  # cumul reprises
    date_dotation    = models.DateField()
    compte_dotation  = models.CharField(max_length=10, default='6911')
    compte_provision = models.CharField(max_length=10, default='191')
    compte_reprise   = models.CharField(max_length=10, default='7911')
    tiers            = models.CharField(max_length=200, blank=True, default='')  # ex. client douteux
    observations     = models.TextField(blank=True, default='')
    statut           = models.CharField(max_length=10, choices=STATUT_CHOICES, default='ACTIVE')

    class Meta:
        db_table = 'gouvernance_provisions'
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'reference'],
                                    name='uniq_provision_ref_par_tenant'),
        ]
        ordering = ['-date_dotation', 'reference']

    def __str__(self):
        return f"{self.reference} — {self.libelle}"

    @property
    def montant_actuel(self):
        return self.montant - self.montant_repris


class TransfertTresorerie(TenantModel):
    """Transfert interne de fonds entre deux comptes de trésorerie (Lot 1).

    Ex. : Banque → Caisse, Caisse → Wave, Petite caisse → Banque… Ces mouvements
    ne changent PAS la trésorerie totale, seulement sa composition : ils doivent
    donc être neutres dans le tableau de flux. Traitement SYSCOHADA via le compte
    de virements internes (585) :
      • sortie  : D 585 / C compte_source
      • entrée  : D compte_destination / C 585
      • frais   : D compte_frais / C compte_source (le cas échéant)
    Les deux jambes 585 sont générées simultanément → 585 se solde à zéro, la
    variation de trésorerie de chaque canal est exacte, et le flux reste neutre.
    Comptes entièrement paramétrables. Écritures automatiques (source=TRANSFERT)."""

    STATUT_CHOICES = [
        ('ACTIF',  'Actif'),
        ('ANNULE', 'Annulé'),
    ]

    reference          = models.CharField(max_length=30)
    exercice           = models.ForeignKey('paiements.Exercice', on_delete=models.CASCADE,
                                           related_name='transferts')
    date_transfert     = models.DateField()
    compte_source      = models.CharField(max_length=10)
    compte_destination = models.CharField(max_length=10)
    montant            = models.DecimalField(max_digits=15, decimal_places=2)
    frais              = models.DecimalField(max_digits=13, decimal_places=2, default=0)
    compte_virement    = models.CharField(max_length=10, default='585')
    compte_frais       = models.CharField(max_length=10, default='6312')  # frais/commissions bancaires
    motif              = models.CharField(max_length=200, blank=True, default='')
    projet             = models.ForeignKey('gouvernance.Projet', null=True, blank=True,
                                           on_delete=models.SET_NULL, related_name='transferts')
    statut             = models.CharField(max_length=10, choices=STATUT_CHOICES, default='ACTIF')
    observations       = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'gouvernance_transferts'
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'reference'],
                                    name='uniq_transfert_ref_par_tenant'),
        ]
        ordering = ['-date_transfert', '-created_at']

    def __str__(self):
        return f"{self.reference} — {self.compte_source}→{self.compte_destination}"


class PieceJustificative(TenantModel):
    """Document justificatif rattaché à un objet métier (GED générique).

    Le rattachement polymorphe est typé (`objet_type` + `objet_id`) plutôt que via
    un GenericForeignKey Django, pour rester léger, sans dépendance à
    `contenttypes` et cohérent avec l'idiome `source`/`source_id` du ledger. Le
    contenu est un data URI base64 (`data:<mime>;base64,…`) stocké en base."""

    # Objets rattachables. Les valeurs postérieures au Lot 0 (RESSOURCE,
    # TRANSFERT, PROVISION, RAPPROCHEMENT) sont déclarées à l'avance pour éviter
    # une migration à chaque lot ; elles ne sont pas encore émises côté UI.
    OBJET_CHOICES = [
        ('CHARGE',         'Charge / dépense'),
        ('PAIEMENT',       'Paiement / recette'),
        ('IMMOBILISATION', 'Immobilisation'),
        ('BUDGET',         'Ligne de budget'),
        ('FINANCEMENT',    'Financement (GMRF)'),
        ('PRET',           'Prêt'),
        ('NATT',           'NATT / Tontine'),
        ('PROJET',         'Projet'),
        ('ECRITURE',       'Écriture comptable'),
        ('RESSOURCE',      'Ressource financière'),
        ('TRANSFERT',      'Transfert de trésorerie'),
        ('PROVISION',      'Provision'),
        ('RAPPROCHEMENT',  'Rapprochement bancaire'),
        ('AUTRE',          'Autre'),
    ]
    TYPE_CHOICES = [
        ('FACTURE',      'Facture'),
        ('DEVIS',        'Devis'),
        ('BON_COMMANDE', 'Bon de commande'),
        ('BON_LIVRAISON', 'Bon de livraison'),
        ('CONTRAT',      'Contrat'),
        ('CONVENTION',   'Convention'),
        ('RECU',         'Reçu'),
        ('RELEVE',       'Relevé bancaire'),
        ('PHOTO',        'Photo'),
        ('PDF',          'Document PDF'),
        ('WORD',         'Document Word'),
        ('AUTRE',        'Autre document'),
    ]

    objet_type   = models.CharField(max_length=20, choices=OBJET_CHOICES)
    objet_id     = models.UUIDField()
    type_piece   = models.CharField(max_length=15, choices=TYPE_CHOICES, default='AUTRE')
    nom          = models.CharField(max_length=200)
    mime_type    = models.CharField(max_length=100, blank=True, default='')
    taille       = models.IntegerField(default=0)  # octets (décodés)
    contenu      = models.TextField()              # data URI base64
    reference    = models.CharField(max_length=80, blank=True, default='')
    date_document = models.DateField(null=True, blank=True)
    observations = models.TextField(blank=True, default='')
    uploaded_par = models.ForeignKey('users.User', null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        db_table = 'gouvernance_pieces'
        indexes = [
            models.Index(fields=['tenant', 'objet_type', 'objet_id'],
                         name='idx_piece_objet'),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_type_piece_display()} — {self.nom}"
