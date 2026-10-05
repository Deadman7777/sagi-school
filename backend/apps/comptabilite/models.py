from django.db import models
from core.models import TenantModel


class JournalEntryQuerySet(models.QuerySet):
    def bulk_create(self, objs, *args, **kwargs):
        # bulk_create ne passe pas par save() : l'auteur est posé ici aussi,
        # sinon la plupart des écritures (paiements, extournes) en seraient privées.
        objs = list(objs)
        for e in objs:
            e._poser_auteur()
        return super().bulk_create(objs, *args, **kwargs)


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
    # Qui a passé l'écriture : le point de trésorerie de chaque chargé de
    # scolarité se lit là. Posé tout seul à l'enregistrement, d'après la
    # requête en cours (core/auteur.py) ; vide hors requête et avant octobre 2026
    # (sauf les encaissements, repris du saisi_par de leur reçu).
    saisi_par     = models.ForeignKey('users.User', null=True, blank=True,
                                      on_delete=models.SET_NULL, related_name='+')
    # Dimension « activité » (enseignement, transport, restauration…) : à
    # quelle activité de l'établissement la ligne appartient. Vide = l'activité
    # principale — toutes les écritures d'avant octobre 2026 y restent, sans
    # migration de données. Voir apps/comptabilite/activites.py.
    activite      = models.ForeignKey('comptabilite.Activite', null=True, blank=True,
                                      on_delete=models.SET_NULL, related_name='ecritures')

    objects = JournalEntryQuerySet.as_manager()

    class Meta:
        db_table = 'journal_entries'
        ordering = ['date_ecriture', 'no_piece', 'ordre']

    def __str__(self):
        return f"{self.no_piece} — {self.libelle}"

    def _poser_auteur(self):
        if self.saisi_par_id is None:
            from core.auteur import utilisateur_courant
            self.saisi_par = utilisateur_courant()

    def save(self, *args, **kwargs):
        self._poser_auteur()
        super().save(*args, **kwargs)


class CaisseEncaissement(TenantModel):
    """Une caisse de l'école, avec son compte de trésorerie.

    Les services extra (garderie, cantine, activités) sont encaissés à part de
    la caisse principale : chaque caisse a son compte 571x, donc son solde, son
    journal et son décompte. Sans cela, tout tombait sur « 571 Caisse » et il
    fallait décompter à la main.

    Le compte est créé dans le plan de l'école à l'enregistrement : les états,
    les soldes par canal et les transferts internes le reconnaissent alors
    comme les autres comptes de trésorerie.
    """
    nom       = models.CharField(max_length=100)
    no_compte = models.CharField(max_length=10)
    actif     = models.BooleanField(default=True)
    ordre     = models.IntegerField(default=0)

    class Meta:
        db_table = 'caisses_encaissement'
        ordering = ['ordre', 'nom']
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'no_compte'], name='uniq_caisse_compte_par_ecole'),
            models.UniqueConstraint(fields=['tenant', 'nom'], name='uniq_caisse_nom_par_ecole'),
        ]

    def __str__(self):
        return f"{self.nom} ({self.no_compte})"

    @staticmethod
    def prochain_compte(tenant):
        """Prochain sous-compte de caisse libre.

        571 est la caisse principale et 5715 la petite caisse du plan standard :
        les caisses de service prennent 5716, 5717, 5718, 5719, puis 57120,
        57121… Toutes restent des sous-comptes de 571, donc comptées dans la
        caisse de l'école.
        """
        pris = set(CaisseEncaissement.objects.filter(tenant=tenant)
                   .values_list('no_compte', flat=True))
        pris |= set(CompteComptable.objects.filter(tenant=tenant, no_compte__startswith='571')
                    .values_list('no_compte', flat=True))
        candidats = [f'571{n}' for n in range(6, 10)] + [f'571{n}' for n in range(20, 100)]
        for candidat in candidats:
            if candidat not in pris:
                return candidat
        raise ValueError('Plus de compte de caisse disponible.')

    def assurer_le_compte(self):
        """Crée (ou renomme) le compte de cette caisse dans le plan de l'école."""
        CompteComptable.objects.update_or_create(
            tenant=self.tenant, no_compte=self.no_compte,
            defaults={'libelle': self.nom, 'type': 'BILAN', 'classe': 5,
                      'est_actif': self.actif, 'est_systeme': False})


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


class Activite(TenantModel):
    """Une activité de l'établissement, suivie à part dans la comptabilité.

    L'enseignement est l'activité principale ; à côté, un établissement peut
    exploiter un transport (y compris pour des clients extérieurs, sans lien
    avec le ramassage des élèves), une restauration, un internat, des
    prestations externes (location de salles, formations…).

    Chaque activité porte son paramétrage comptable : le compte de produit
    crédité par ses factures, le compte de charge proposé pour ses dépenses,
    le compte client de ses débiteurs extérieurs, et son régime de TVA. Les
    écritures qu'elle génère sont marquées (`JournalEntry.activite`) : recettes,
    dépenses et résultat se lisent activité par activité, tout en alimentant
    la même comptabilité générale.
    """
    TYPE_CHOICES = [
        ('ENSEIGNEMENT', 'Enseignement'),
        ('TRANSPORT',    'Transport'),
        ('RESTAURATION', 'Restauration'),
        ('HEBERGEMENT',  'Hébergement / internat'),
        ('PRESTATION',   'Prestations externes'),
        ('FORMATION',    'Formation continue'),
        ('LOCATION',     'Location de locaux / matériel'),
        ('COMMERCE',     'Vente (librairie, uniformes…)'),
        ('AUTRE',        'Autre activité'),
    ]
    TVA_CHOICES = [
        ('EXONERE',  'Exonérée'),
        ('TAXABLE',  'Soumise à TVA'),
        ('HORS_CHAMP', 'Hors champ'),
    ]
    code            = models.CharField(max_length=20)
    libelle         = models.CharField(max_length=150)
    type_activite   = models.CharField(max_length=15, choices=TYPE_CHOICES, default='AUTRE')
    description     = models.TextField(blank=True, default='')
    est_principale  = models.BooleanField(default=False)
    compte_produit  = models.CharField(max_length=10, default='706')
    compte_charge   = models.CharField(max_length=10, blank=True, default='')
    compte_client   = models.CharField(max_length=10, default='4111')
    regime_tva      = models.CharField(max_length=10, choices=TVA_CHOICES, default='EXONERE')
    # Vide : le taux normal en vigueur (paramètre fiscal TVA_TAUX_NORMAL).
    taux_tva        = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    actif           = models.BooleanField(default=True)
    ordre           = models.IntegerField(default=0)

    class Meta:
        db_table = 'activites'
        ordering = ['ordre', 'libelle']
        constraints = [models.UniqueConstraint(fields=['tenant', 'code'],
                                               name='uniq_activite_code_tenant')]

    def __str__(self):
        return self.libelle


class FactureActivite(TenantModel):
    """Facture émise par une activité à un client (souvent extérieur).

    Brouillon modifiable ; validée, elle est numérotée et comptabilisée :
    client (D, TTC) / produit de l'activité (C, HT) / TVA facturée (C).
    Les règlements soldent la créance ; une facture validée ne se supprime
    pas, elle s'annule par extourne (traçabilité SYSCOHADA).
    """
    STATUT_CHOICES = [
        ('BROUILLON', 'Brouillon'),
        ('VALIDEE',   'Validée'),
        ('PARTIEL',   'Partiellement réglée'),
        ('PAYEE',     'Réglée'),
        ('ANNULEE',   'Annulée'),
    ]
    activite      = models.ForeignKey(Activite, on_delete=models.PROTECT, related_name='factures')
    exercice      = models.ForeignKey('paiements.Exercice', on_delete=models.PROTECT,
                                      related_name='factures_activite')
    numero        = models.CharField(max_length=30, blank=True, default='')
    date_facture  = models.DateField()
    date_echeance = models.DateField(null=True, blank=True)
    client_nom    = models.CharField(max_length=200)
    client_contact = models.CharField(max_length=200, blank=True, default='')
    client_ninea  = models.CharField(max_length=30, blank=True, default='')
    # [{"libelle": "Location bus — sortie", "quantite": 2, "prix_unitaire": 75000}]
    lignes        = models.JSONField(default=list, blank=True)
    montant_ht    = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    taux_tva      = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    montant_tva   = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    montant_ttc   = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    montant_regle = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    statut        = models.CharField(max_length=10, choices=STATUT_CHOICES, default='BROUILLON')
    observations  = models.TextField(blank=True, default='')
    date_validation = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'factures_activite'
        ordering = ['-date_facture', '-numero']
        constraints = [models.UniqueConstraint(
            fields=['tenant', 'numero'], condition=~models.Q(numero=''),
            name='uniq_facture_activite_numero_tenant')]

    def __str__(self):
        return f"{self.numero or 'Brouillon'} — {self.client_nom}"

    @property
    def reste_a_regler(self):
        return round(float(self.montant_ttc) - float(self.montant_regle), 2)


class ReglementFacture(TenantModel):
    """Encaissement (total ou partiel) d'une facture d'activité."""
    MODE_CHOICES = [
        ('ESPECE', 'Espèce'), ('WAVE', 'Wave'), ('ORANGE_MONEY', 'Orange Money'),
        ('FREE_MONEY', 'Free Money'), ('VIREMENT', 'Virement'), ('CHEQUE', 'Chèque'),
    ]
    facture       = models.ForeignKey(FactureActivite, on_delete=models.CASCADE,
                                      related_name='reglements')
    exercice      = models.ForeignKey('paiements.Exercice', on_delete=models.PROTECT,
                                      related_name='+')
    date_reglement = models.DateField()
    montant       = models.DecimalField(max_digits=15, decimal_places=2)
    mode          = models.CharField(max_length=15, choices=MODE_CHOICES, default='ESPECE')
    # N° de chèque, de bordereau de versement, référence de virement…
    reference     = models.CharField(max_length=80, blank=True, default='')
    no_piece      = models.CharField(max_length=30, blank=True, default='')
    annule        = models.BooleanField(default=False)

    class Meta:
        db_table = 'reglements_facture'
        ordering = ['date_reglement']
