from django.db import models
from core.models import TimeStampedModel


class Tenant(TimeStampedModel):
    nom       = models.CharField(max_length=200)
    ville     = models.CharField(max_length=100, blank=True)
    adresse   = models.TextField(blank=True)
    rccm      = models.CharField(max_length=50, blank=True)
    ninea     = models.CharField(max_length=20, blank=True)
    # Numéro d'autorisation d'ouverture délivré par l'autorité de tutelle —
    # figure sur les documents officiels (certificat, bulletins, reçus).
    numero_autorisation = models.CharField(max_length=100, blank=True)
    # Personnalisation du certificat de scolarité : dict {element: bool} +
    # textes libres. Vide = version standard complète (tous les éléments).
    config_certificat = models.JSONField(default=dict, blank=True)
    telephone = models.CharField(max_length=20, blank=True)
    email     = models.EmailField(blank=True)
    code_etablissement = models.CharField(max_length=10, default='ETB')
    # Logo de l'établissement en data URI base64 (ex. "data:image/png;base64,...").
    # Stocké en base pour fonctionner identiquement en local (Electron) et en cloud,
    # et s'embarquer directement dans les PDF (xhtml2pdf gère les data URIs).
    logo      = models.TextField(blank=True, default='')
    # Régime de paie : COMPLET (affilié IPRES/CSS/IR) ou SIMPLIFIE (non affilié, sans cotisations)
    REGIME_PAIE_CHOICES = [('COMPLET', 'Complet (affilié)'), ('SIMPLIFIE', 'Simplifié (non affilié)')]
    regime_paie = models.CharField(max_length=10, choices=REGIME_PAIE_CHOICES, default='COMPLET')
    # Découpage de l'année scolaire — libre : type (mot) + nombre de périodes
    PERIODE_CHOICES = [('TRIMESTRE', 'Trimestre'), ('SEMESTRE', 'Semestre'), ('PERIODE', 'Période')]
    periode_scolaire = models.CharField(max_length=10, choices=PERIODE_CHOICES, default='TRIMESTRE')
    nb_periodes      = models.IntegerField(default=3)

    # ── Quand une mensualité devient-elle exigible ? ──────────────────────
    # Les écoles ne collectent pas au même moment, et la réponse décide de tout
    # ce qui est présenté comme « en retard » à une famille :
    #   ANTICIPE   : on paie AVANT le mois (cas de Shoumoul — l'élève règle
    #                juillet avant de commencer juillet) ;
    #   DEBUT_MOIS : exigible dès le mois commencé ;
    #   FIN_MOIS   : exigible une fois le mois consommé.
    # DEBUT_MOIS est le défaut : c'est le comportement d'avant ce réglage,
    # aucune école existante ne voit ses chiffres changer sans y toucher.
    ECHEANCE_CHOICES = [
        ('ANTICIPE',   'Avant le mois (paiement d\'avance)'),
        ('DEBUT_MOIS', 'Dès le début du mois'),
        ('FIN_MOIS',   'À la fin du mois (paiement à terme échu)'),
    ]
    echeance_mensualite = models.CharField(max_length=12, choices=ECHEANCE_CHOICES,
                                           default='DEBUT_MOIS')
    # Jour du mois de référence où l'échéance tombe. Plafonné à 28 : un 30 ou
    # un 31 n'existe pas tous les mois, et une échéance qui saute février
    # serait pire qu'inutile.
    jour_echeance = models.PositiveSmallIntegerField(
        default=1, help_text="Jour du mois de l'échéance (1 à 28)")
    # Mensualités encaissées dès l'inscription — pratique fréquente pour
    # sécuriser l'entrée et la sortie. Ces mois sont exigibles à la date
    # d'entrée de l'élève, pas à leur tour dans le calendrier.
    premier_mois_a_inscription = models.BooleanField(
        default=False, help_text="La 1re mensualité est encaissée à l'inscription")
    dernier_mois_a_inscription = models.BooleanField(
        default=False, help_text="La dernière mensualité est encaissée à l'inscription")

    # ── Renouvellement annuel (daaras) ────────────────────────────────────
    # Un daara n'inscrit un ndongo qu'UNE fois, à son arrivée. Les années
    # suivantes, il ne paie plus l'inscription mais un renouvellement — souvent
    # moins cher, et qui porte le nom que l'école lui donne.
    #
    # Sans ce réglage, le système réclamait l'inscription chaque année à tout le
    # monde. Les écoles s'en sortaient en inscrivant une fausse prise en charge
    # égale à l'inscription sur CHAQUE ancien élève, pour que le total annuel dû
    # reste juste — une donnée fausse recopiée à la main tous les ans, qui faisait
    # passer une école entière pour prise en charge.
    #
    # Désactivé par défaut : une école classique, qui réinscrit et refacture
    # l'inscription tous les ans, ne voit rien changer.
    renouvellement_actif = models.BooleanField(
        default=False,
        help_text="Les anciens élèves doivent un renouvellement, pas l'inscription")
    libelle_renouvellement = models.CharField(
        max_length=60, default='Renouvellement',
        help_text="Le mot de l'école : Renouvellement, Réinscription, Droit de rentrée…")
    # Mois calendaire à partir duquel le renouvellement est réclamable. VIDE =
    # exigible dès le début de l'exercice, comme l'inscription. Les daaras
    # ouvrent souvent la campagne bien après la rentrée (« à partir de
    # janvier ») : sans ce réglage, tous leurs anciens élèves apparaîtraient en
    # retard dès le premier jour et la liste de relance serait inexploitable.
    mois_renouvellement = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text='Mois (1-12) où le renouvellement devient exigible — vide = dès la rentrée')
    # Ancienneté à partir de laquelle un élève est un ANCIEN. Chaque chef
    # d'établissement fixe son seuil : Shoumoul retient 9 mois, une école qui
    # raisonne en années scolaires pleines en retiendra 12. Mesurée au premier
    # jour de l'exercice, pour qu'un élève ne change pas de statut en cours
    # d'année.
    anciennete_renouvellement_mois = models.PositiveSmallIntegerField(
        default=12,
        help_text="Mois de présence à partir desquels l'élève doit un renouvellement")

    # ── Rappels de paiement ───────────────────────────────────────────────
    # Fenêtre mensuelle de relance : à partir de quel jour l'école commence à
    # rappeler, et jusqu'à quel jour la famille a pour régler.
    rappel_actif      = models.BooleanField(default=True)
    rappel_jour_debut = models.PositiveSmallIntegerField(
        default=1, help_text='Jour du mois où commencent les rappels (1 à 28)')
    rappel_jour_limite = models.PositiveSmallIntegerField(
        default=10, help_text='Dernier délai de paiement dans le mois (1 à 28)')

    # ── Envoi automatique des rappels (SMS) ───────────────────────────────
    # Rien ne part tant que l'école n'a pas explicitement activé l'envoi ET
    # renseigné un fournisseur : un message envoyé par erreur à des centaines
    # de familles ne se rattrape pas. Le défaut est donc « simulation », qui
    # journalise tout sans rien émettre — l'école vérifie ses textes d'abord.
    sms_actif = models.BooleanField(
        default=False, help_text='Envoyer réellement les rappels par SMS')
    # Transport volontairement générique : une URL, une méthode, un gabarit de
    # corps. N'importe quel agrégateur se branche sans toucher au code, et
    # aucun opérateur n'est imposé à l'école.
    sms_url = models.URLField(blank=True, help_text='URL de l\'API SMS du fournisseur')
    sms_methode = models.CharField(max_length=6, default='POST',
                                   choices=[('POST', 'POST'), ('GET', 'GET')])
    sms_entetes = models.JSONField(default=dict, blank=True,
                                   help_text='En-têtes HTTP (autorisation, etc.)')
    # Gabarit du corps envoyé au fournisseur. {destinataire} et {message} y
    # sont remplacés. Ex. {"to": "{destinataire}", "text": "{message}"}
    sms_gabarit = models.JSONField(default=dict, blank=True,
                                   help_text='Corps de la requête ({destinataire}, {message})')
    # Texte du rappel. Variables : {eleve} {montant} {ecole} {mois} {limite}
    rappel_message = models.TextField(
        blank=True,
        help_text='Message envoyé. Variables : {eleve} {montant} {ecole} {mois} {limite}')
    actif     = models.BooleanField(default=True)

    class Meta:
        db_table = 'tenants'
        verbose_name = 'École'

    def __str__(self):
        return self.nom
