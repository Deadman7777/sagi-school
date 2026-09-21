from django.db import models
from django.utils import timezone
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
    # Date du RÈGLEMENT, pas de la saisie. Longtemps déclarée `auto_now_add`,
    # elle était de ce fait impossible à corriger : un encaissement noté le
    # lendemain portait la date du lendemain, la rectification d'une vieille
    # pièce la ramenait à aujourd'hui (le `date_paiement=` passé à
    # `Paiement.objects.create` était silencieusement ignoré), et un import
    # d'école réécrivait l'année entière à la date de la bascule — `bulk_create`
    # applique `auto_now_add` comme n'importe quel INSERT. Le défaut reste
    # « aujourd'hui » : la saisie courante ne change pas.
    date_paiement       = models.DateField(default=timezone.localdate)
    statut              = models.CharField(max_length=10, choices=STATUT_CHOICES, default='ACTIF')
    montant_inscription = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    montant_mensualite  = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    montant_uniforme    = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    montant_fournitures = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    montant_cantine     = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    montant_divers      = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # Part du règlement affectée au reliquat de l'exercice précédent. Elle est
    # encaissée (trésorerie) mais ne constate AUCUN produit 706 : le produit a
    # déjà été comptabilisé l'année d'origine, seule la créance 411 reportée
    # en à-nouveaux se solde. C'est pourquoi elle est volontairement absente de
    # toutes les sommes « recettes de l'exercice » (les 6 catégories ci-dessus)
    # et n'apparaît que dans Paiement.total, le montant réellement encaissé.
    montant_reliquat    = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # Mois scolaires couverts par la mensualité (numéros 1-12), pour le suivi mensuel
    # et la gestion des paiements anticipés. Ex. [10, 11, 12].
    mois_regles         = models.JSONField(default=list, blank=True)
    # Qui a payé. NULL = la famille. Renseigné = un organisme règle la part
    # qu'il prend en charge — c'est ce qui permet de distinguer « la famille
    # est à jour » de « l'État a versé », deux situations qu'un même total
    # confondrait.
    organisme           = models.ForeignKey('eleves.Organisme', null=True, blank=True,
                                            on_delete=models.PROTECT,
                                            related_name='paiements')
    # Détail des services optionnels réglés dans ce paiement (itemisation reçu).
    # Ex. [{"nom": "Cantine", "montant": 10000}]. Le montant est inclus dans montant_divers.
    services_regles     = models.JSONField(default=list, blank=True)
    # Part du règlement qui porte sur des SERVICES EXTRA (garderie, garde du
    # soir, cantine, activités). Elle ne s'ajoute pas au total : c'est une
    # ventilation du montant déjà saisi, qui décide du compte de produit —
    # 758 « Produits divers » au lieu du 706, réservé au service éducatif.
    part_accessoire     = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # Caisse qui reçoit les espèces de ce règlement (garderie, cantine…).
    # Vide = la caisse principale (571). Les autres modes gardent leur compte :
    # un versement Wave n'entre pas dans une caisse en espèces.
    caisse              = models.ForeignKey('comptabilite.CaisseEncaissement', null=True, blank=True,
                                            on_delete=models.PROTECT, related_name='paiements')
    mode_paiement       = models.CharField(max_length=20, choices=MODE_CHOICES, default='ESPECE')
    # Ventilation du règlement sur plusieurs modes (multi-mode). Vide → règlement
    # simple via mode_paiement. Ex. [{"mode": "ESPECE", "montant": 30000},
    # {"mode": "WAVE", "montant": 20000}, {"mode": "ORANGE_MONEY", "montant": 10000}].
    modes_reglement     = models.JSONField(default=list, blank=True)
    observations        = models.TextField(blank=True)
    # ── Règlement groupé d'une famille ────────────────────────────────────
    # Un père règle 150 000 F pour ses cinq enfants. Le paiement reste PAR
    # ÉLÈVE — l'échéancier, l'imputation par mois, le grand livre et le suivi
    # en dépendent tous — mais les N règlements issus du même versement
    # portent la même référence, ce qui permet d'imprimer UN reçu pour la
    # famille au lieu de cinq.
    reference_groupe    = models.UUIDField(null=True, blank=True, db_index=True,
                                           help_text="Versement groupé d'une famille")
    # Qui a effectivement payé, quand la famille compte plusieurs
    # responsables : le père règle pour trois enfants, la mère pour deux.
    # C'est la question que l'école pose en premier quand un parent conteste.
    payeur              = models.ForeignKey('eleves.ResponsableFamille', null=True, blank=True,
                                            on_delete=models.SET_NULL, related_name='paiements')
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
    def total_exercice(self):
        """Part du règlement qui porte sur les frais de l'année en cours
        (= produits 706 de l'exercice). Exclut le reliquat reporté."""
        return (self.montant_inscription + self.montant_mensualite +
                self.montant_uniforme    + self.montant_fournitures +
                self.montant_cantine     + self.montant_divers)

    @property
    def total(self):
        """Montant réellement encaissé (ce qui figure sur le reçu et se
        ventile en trésorerie) : frais de l'année + reliquat antérieur."""
        return self.total_exercice + self.montant_reliquat

    def save(self, *args, **kwargs):
        if not self.no_piece:
            # Un COMPTE de lignes ne donne pas un numéro libre : une annulation
            # ou une pièce migrée le fait retomber sur un rang déjà pris. Même
            # séquence que la vue, et vérifiée libre (voir numerotation.py).
            from .numerotation import prochain_no_piece
            self.no_piece = prochain_no_piece(self.tenant, 'REC')
        super().save(*args, **kwargs)


class Proforma(TenantModel):
    """Facture proforma de scolarité remise à une famille.

    Deux usages : le parent qui veut régler toute l'année d'un coup demande
    combien, et le parent qui se renseigne avant d'inscrire son enfant veut
    savoir ce que coûtera l'année, et quand payer.

    Une proforma n'est PAS une pièce comptable : elle n'écrit rien au grand
    livre, ne crée aucune créance et ne se règle pas en l'état — le paiement
    passe par l'encaissement normal, qui produit le reçu. Elle est FIGÉE à
    l'émission (lignes, échéancier, totaux) : réimprimée dans trois mois, elle
    doit dire ce qu'elle disait le jour où le parent l'a emportée, même si les
    tarifs ont changé depuis. Le calcul vit dans `proformas.py`.
    """
    STATUT_CHOICES = [('EMISE', 'Émise'), ('ANNULEE', 'Annulée')]

    # PF-2026-0001 : séquence propre à l'école et à l'année d'émission.
    numero          = models.CharField(max_length=30)
    exercice        = models.ForeignKey(Exercice, on_delete=models.PROTECT, related_name='proformas')
    # L'année scolaire chiffrée. Celle de l'exercice, ou la suivante pour une
    # famille qui se renseigne avant la rentrée.
    annee_scolaire  = models.CharField(max_length=20)
    # Élève déjà inscrit ; vide pour un futur élève.
    eleve           = models.ForeignKey('eleves.Eleve', null=True, blank=True,
                                        on_delete=models.SET_NULL, related_name='proformas')
    # Recopiés : une proforma se relit sans la fiche, qui peut changer ou disparaître.
    beneficiaire    = models.CharField(max_length=200, blank=True)
    matricule       = models.CharField(max_length=30, blank=True)
    section_nom     = models.CharField(max_length=100, blank=True)
    formule_nom     = models.CharField(max_length=100, blank=True)
    parent_nom      = models.CharField(max_length=200, blank=True)
    parent_telephone = models.CharField(max_length=60, blank=True)
    date_emission   = models.DateField(default=timezone.localdate)
    date_validite   = models.DateField()
    # [{designation, detail, quantite, prix_unitaire, montant, nature}]
    lignes          = models.JSONField(default=list)
    # [{libelle, date, montant}] — règlement échelonné proposé à la famille.
    echeancier      = models.JSONField(default=list, blank=True)
    total_du        = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deja_regle      = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    part_organisme  = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    organisme_nom   = models.CharField(max_length=200, blank=True)
    remise_libelle  = models.CharField(max_length=150, blank=True)
    remise_montant  = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_a_payer     = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # Ce que l'école a demandé (portée, options) : de quoi refaire la même
    # proforma à jour, sans ressaisir.
    parametres      = models.JSONField(default=dict, blank=True)
    observations    = models.TextField(blank=True)
    conditions      = models.TextField(blank=True)
    statut          = models.CharField(max_length=10, choices=STATUT_CHOICES, default='EMISE')
    motif_annulation = models.CharField(max_length=255, blank=True)
    emise_par       = models.CharField(max_length=150, blank=True)

    class Meta:
        db_table = 'proformas_scolarite'
        ordering = ['-date_emission', '-created_at']
        # Séquence PAR école : la première proforma d'une nouvelle école ne
        # doit pas entrer en collision avec celle d'une autre.
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'numero'],
                                    name='uniq_proforma_par_tenant'),
        ]

    def __str__(self):
        return f"{self.numero} — {self.beneficiaire}"
