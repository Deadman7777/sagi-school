"""Le fichier prospects de HADY GESMAN.

Jusqu'ici, une demande de démonstration reçue depuis sagi-school.com partait
par courriel et n'existait nulle part ailleurs : un courriel perdu, une boîte
saturée, un commercial en congé, et la demande disparaissait sans trace. Ce
fichier renverse la charge — **la demande est d'abord enregistrée, le courriel
n'est plus qu'une notification.**

Deux conséquences à garder en tête en lisant ce module :

**Ces modèles ne sont pas cloisonnés par école.** Un prospect n'appartient à
aucun établissement client : il appartient à HADY GESMAN, comme les licences.
D'où `TimeStampedModel` et non `TenantModel`. Ils ne sont lisibles que par un
SUPER_ADMIN.

**Rien de ce qui est reçu n'est jeté.** Les champs typés servent au travail
commercial (filtrer, segmenter, relancer) ; `donnees_brutes` conserve la
soumission telle qu'elle est arrivée. Un formulaire du site qui gagne un champ
demain n'a pas besoin d'une migration pour que l'information soit gardée.
"""
from datetime import date

from django.db import models

from core.models import TimeStampedModel

# Les libellés proposés à la saisie — sur le site vitrine comme dans l'écran
# de suivi. Ce sont des LIBELLÉS, pas des codes : `type_organisation` accepte
# n'importe quel texte, parce qu'un prospect qui se décrit autrement doit être
# enregistré tel qu'il se décrit plutôt que rangé de force dans « Autre ».
TYPES_ORGANISATION = ('Daara', 'École privée', 'Franco-arabe',
                      'Centre de formation', 'PME', 'Autre')

# Idem pour l'origine du contact (section 3 de la fiche HG-COM-001).
ORIGINES = ('Site internet', 'WhatsApp', 'Facebook / Instagram', 'LinkedIn',
            'Recommandation client', 'Partenaire', 'Prospection terrain', 'Autre')


class Prospect(TimeStampedModel):
    """Un établissement qui s'est manifesté, et où en est la relation.

    L'ordre des champs suit la Fiche Prospect Commercial HG-COM-001, pour que
    la saisie manuelle et la fiche papier se lisent pareil.
    """

    STATUT_CHOICES = [
        ('NOUVEAU',  'Nouveau — à rappeler'),
        ('CONTACTE', 'Contacté'),
        ('QUALIFIE', 'Qualifié — besoin identifié'),
        ('DEVIS',    'Devis envoyé'),
        ('GAGNE',    'Gagné — devenu client'),
        ('PERDU',    'Perdu'),
    ]

    # D'où vient la fiche. `ASSISTANT` est réservé à SAMA : quand il mènera le
    # diagnostic sur le site vitrine, c'est ici qu'il déposera ce qu'il a
    # recueilli, et le commercial verra d'un coup d'œil ce qui vient de lui.
    SOURCE_CHOICES = [
        ('SITE',      'Formulaire du site'),
        ('ASSISTANT', 'Assistant SAMA'),
        ('MANUEL',    'Saisie manuelle'),
        ('IMPORT',    'Import'),
    ]

    # ── 1. Identification ────────────────────────────────────────────────
    etablissement     = models.CharField(max_length=200)
    type_organisation = models.CharField(max_length=30, blank=True)
    date_creation     = models.CharField(max_length=40, blank=True)
    adresse           = models.CharField(max_length=300, blank=True)
    ville             = models.CharField(max_length=120, blank=True)
    telephone         = models.CharField(max_length=60, blank=True)
    # Les numéros arrivent sous toutes les formes : « 77 123 45 67 »,
    # « +221771234567 », « 00221 77 123 45 67 ». Le rapprochement se fait sur
    # cette forme réduite, jamais sur le champ affiché.
    telephone_cle     = models.CharField(max_length=20, blank=True, db_index=True)
    # CharField et non EmailField : c'est un formulaire public. Une adresse
    # mal saisie doit être conservée telle quelle pour qu'on puisse rappeler
    # et la corriger, pas rejeter la demande.
    email             = models.CharField(max_length=254, blank=True)
    site_web          = models.CharField(max_length=200, blank=True)

    # ── 2. Contact principal ─────────────────────────────────────────────
    contact_nom         = models.CharField(max_length=200, blank=True)
    contact_fonction    = models.CharField(max_length=150, blank=True)
    contact_telephone   = models.CharField(max_length=60, blank=True)
    contact_email       = models.CharField(max_length=254, blank=True)
    pouvoir_decisionnel = models.CharField(max_length=80, blank=True)

    # ── 3. Origine ───────────────────────────────────────────────────────
    origines        = models.JSONField(default=list, blank=True)
    origine_details = models.TextField(blank=True)

    # ── 4. L'organisation ────────────────────────────────────────────────
    # Nuls et non zéro : « nous ne savons pas combien ils ont d'élèves » et
    # « ils n'en ont aucun » ne se traitent pas de la même façon en
    # segmentation commerciale.
    nb_eleves   = models.PositiveIntegerField(null=True, blank=True)
    nb_employes = models.PositiveIntegerField(null=True, blank=True)
    nb_classes  = models.PositiveIntegerField(null=True, blank=True)
    nb_sites    = models.PositiveIntegerField(null=True, blank=True)

    # ── La demande ───────────────────────────────────────────────────────
    disponibilites = models.CharField(max_length=300, blank=True)
    message        = models.TextField(blank=True)

    # ── Le suivi ─────────────────────────────────────────────────────────
    statut      = models.CharField(max_length=20, choices=STATUT_CHOICES,
                                   default='NOUVEAU', db_index=True)
    source      = models.CharField(max_length=20, choices=SOURCE_CHOICES,
                                   default='SITE')
    relance_le  = models.DateField(null=True, blank=True, db_index=True)
    notes       = models.TextField(blank=True)
    perdu_motif = models.CharField(max_length=250, blank=True)

    # Le jour où le prospect devient client, la fiche pointe vers son école :
    # c'est ce lien qui permettra de dire ce qu'a rapporté le site vitrine.
    tenant_converti = models.ForeignKey(
        'tenants.Tenant', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='prospects')
    date_conversion = models.DateField(null=True, blank=True)

    # ── Traçabilité ──────────────────────────────────────────────────────
    donnees_brutes  = models.JSONField(default=dict, blank=True)
    courriel_envoye = models.BooleanField(default=False)

    class Meta:
        db_table = 'prospects'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['statut', '-created_at']),
            models.Index(fields=['relance_le']),
        ]
        verbose_name = 'Prospect'
        verbose_name_plural = 'Prospects'

    def __str__(self):
        return f"{self.etablissement}" + (f" — {self.ville}" if self.ville else '')

    @property
    def anciennete_jours(self):
        return (date.today() - self.created_at.date()).days

    @property
    def en_cours(self):
        """Une affaire encore ouverte : ni gagnée, ni abandonnée."""
        return self.statut not in ('GAGNE', 'PERDU')

    @property
    def relance_en_retard(self):
        return bool(self.relance_le) and self.en_cours and self.relance_le < date.today()


class InteractionProspect(TimeStampedModel):
    """Un échange avec le prospect : l'historique de la relation.

    C'est ce qui manque le plus dans un suivi par courriel — savoir qu'on a
    déjà appelé deux fois sans réponse, et ce qui s'est dit la dernière fois.
    """

    CANAL_CHOICES = [
        ('SITE',      'Demande depuis le site'),
        ('ASSISTANT', 'Conversation avec SAMA'),
        ('APPEL',     'Appel téléphonique'),
        ('WHATSAPP',  'WhatsApp'),
        ('EMAIL',     'Courriel'),
        ('VISITE',    'Visite / rendez-vous'),
        ('DEMO',      'Démonstration'),
        ('AUTRE',     'Autre'),
    ]

    prospect = models.ForeignKey(Prospect, on_delete=models.CASCADE,
                                related_name='interactions')
    date     = models.DateField(default=date.today)
    canal    = models.CharField(max_length=20, choices=CANAL_CHOICES, default='APPEL')
    resume   = models.TextField()
    auteur   = models.CharField(max_length=150, blank=True)

    class Meta:
        db_table = 'prospects_interactions'
        ordering = ['-date', '-created_at']
        indexes = [models.Index(fields=['prospect', '-date'])]
        verbose_name = 'Interaction'
        verbose_name_plural = 'Interactions'

    def __str__(self):
        return f"{self.date:%d/%m/%Y} — {self.get_canal_display()}"
