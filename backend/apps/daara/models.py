"""
Module Taxawu Daara — suivi de mémorisation coranique du NONGO (élève).

Deux familles de modèles :
- Référence (faits coraniques, partagés, non multi-tenant, seedés par
  `init_coran`) : Sourate, Subdivision.
- Suivi (multi-tenant, propre à chaque Daara/NONGO) : NiveauDaara,
  ParcoursNongo, SuiviQuotidien.
"""
from django.db import models
from core.models import TenantModel


# ───────────────────────── Référence (non-tenant) ─────────────────────────

class Sourate(models.Model):
    """Une des 114 sourates du Coran (donnée de référence partagée)."""
    TYPE_CHOICES = [
        ('MECQUOISE', 'Mecquoise'),
        ('MEDINOISE', 'Médinoise'),
    ]
    numero            = models.PositiveSmallIntegerField(unique=True)   # 1..114
    nom_ar            = models.CharField(max_length=100)
    nom_fr            = models.CharField(max_length=100)                # translittération
    type_revelation   = models.CharField(max_length=10, choices=TYPE_CHOICES)
    nb_versets_hafs   = models.PositiveSmallIntegerField()
    nb_versets_warsh  = models.PositiveSmallIntegerField()
    ordre_revelation  = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        db_table = 'coran_sourates'
        ordering = ['numero']

    def __str__(self):
        return f"{self.numero}. {self.nom_fr}"

    def nb_versets(self, riwaya):
        return self.nb_versets_warsh if riwaya == 'WARSH' else self.nb_versets_hafs


class Subdivision(models.Model):
    """
    Subdivision du Coran (Juz / Hizb / Nisf / Rub') selon la riwaaya.
    Situe une position par sa borne de début (sourate:verset).
    """
    RIWAYA_CHOICES = [('HAFS', 'Hafs'), ('WARSH', 'Warsh')]
    TYPE_CHOICES   = [
        ('JUZ',  'Juz'),
        ('HIZB', 'Hizb'),
        ('NISF', 'Nisf'),
        ('RUB',  "Rub'"),
    ]
    riwaya         = models.CharField(max_length=6, choices=RIWAYA_CHOICES)
    type           = models.CharField(max_length=5, choices=TYPE_CHOICES)
    numero         = models.PositiveSmallIntegerField()
    sourate_debut  = models.ForeignKey(Sourate, on_delete=models.CASCADE,
                                       related_name='subdivisions')
    verset_debut   = models.PositiveSmallIntegerField(default=1)

    class Meta:
        db_table = 'coran_subdivisions'
        ordering = ['riwaya', 'type', 'numero']
        unique_together = [('riwaya', 'type', 'numero')]

    def __str__(self):
        return f"{self.get_type_display()} {self.numero} ({self.riwaya})"


# ───────────────────────── Suivi (multi-tenant) ─────────────────────────

class NiveauDaara(TenantModel):
    """Niveau configurable d'un Daara (dont IDJIE = alphabet arabe)."""
    CATEGORIE_CHOICES = [
        ('IDJIE',        'Idjie (alphabet arabe)'),
        ('MEMORISATION', 'Mémorisation'),
        ('AUTRE',        'Autre'),
    ]
    nom_fr     = models.CharField(max_length=100)
    nom_ar     = models.CharField(max_length=100, blank=True)
    categorie  = models.CharField(max_length=15, choices=CATEGORIE_CHOICES,
                                  default='MEMORISATION')
    ordre      = models.IntegerField(default=0)

    class Meta:
        db_table = 'daara_niveaux'
        ordering = ['ordre', 'nom_fr']

    def __str__(self):
        return self.nom_fr


class ParcoursNongo(TenantModel):
    """
    Parcours coranique d'un NONGO (élève) dans le Daara, de l'inscription
    à la sortie. Un seul parcours actif par élève.
    """
    RIWAYA_CHOICES = [('HAFS', 'Hafs'), ('WARSH', 'Warsh')]
    SENS_CHOICES   = [
        ('FIN',   'Depuis la fin (An-Nas → Al-Baqara)'),
        ('DEBUT', 'Depuis le début (Al-Baqara → An-Nas)'),
    ]
    STATUT_CHOICES = [
        ('EN_COURS', 'En cours'),
        ('SORTI',    'Sorti'),
        ('KHATMA',   'Khatma (Coran terminé)'),
    ]
    # Niveau IDJIE (apprentissage de l'alphabet arabe) : on ne modélise pas la
    # pédagogie fine (assemblage des lettres 2 à 2, masques…), on suit seulement
    # le palier atteint par le NONGO. N'a de sens que si niveau.categorie == IDJIE.
    NIVEAU_IDJIE_CHOICES = [
        ('DEBUTANT', 'Débutant'),
        ('MOYEN',    'Moyen'),
        ('AVANCE',   'Avancé'),
    ]
    eleve       = models.ForeignKey('eleves.Eleve', on_delete=models.CASCADE,
                                    related_name='parcours_coranique')
    riwaya      = models.CharField(max_length=6, choices=RIWAYA_CHOICES, default='WARSH')
    niveau      = models.ForeignKey(NiveauDaara, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='parcours')
    niveau_idjie = models.CharField(max_length=10, choices=NIVEAU_IDJIE_CHOICES,
                                    blank=True, null=True)
    sens        = models.CharField(max_length=5, choices=SENS_CHOICES, default='FIN')
    date_debut  = models.DateField(null=True, blank=True)
    date_sortie = models.DateField(null=True, blank=True)
    statut      = models.CharField(max_length=10, choices=STATUT_CHOICES, default='EN_COURS')

    class Meta:
        db_table = 'daara_parcours'
        ordering = ['-created_at']
        unique_together = [('tenant', 'eleve')]

    def __str__(self):
        return f"Parcours {self.eleve} ({self.riwaya})"


def bornes_hizb(riwaya, hizb_debut, hizb_fin):
    """Bornes (sourate_debut, verset_debut, sourate_fin, verset_fin) couvrant
    les hizb hizb_debut..hizb_fin inclus, pour une riwaaya donnée.
    La fin d'un hizb = le verset précédant le début du hizb suivant
    (dernier verset du Coran pour le hizb 60)."""
    subs = {s.numero: s for s in Subdivision.objects
            .filter(riwaya=riwaya, type='HIZB')
            .select_related('sourate_debut')}
    deb = subs.get(hizb_debut)
    if deb is None or hizb_fin not in subs:
        raise ValueError(f'Hizb {hizb_debut}..{hizb_fin} hors bornes ({riwaya}) '
                         f'— vérifier la saisie ou lancer init_coran.')
    suivant = subs.get(hizb_fin + 1)
    if suivant is None:                                  # hizb 60 → fin du Coran
        s_fin = Sourate.objects.get(numero=114)
        v_fin = s_fin.nb_versets(riwaya)
    elif suivant.verset_debut > 1:
        s_fin, v_fin = suivant.sourate_debut, suivant.verset_debut - 1
    else:                                                # hizb suivant en tête de sourate
        s_fin = Sourate.objects.get(numero=suivant.sourate_debut.numero - 1)
        v_fin = s_fin.nb_versets(riwaya)
    return deb.sourate_debut, deb.verset_debut, s_fin, v_fin


class SuiviQuotidien(TenantModel):
    """Entrée de suivi quotidien : portion travaillée + qualité + présence.

    Deux méthodes de saisie selon la pédagogie du Daara : par sourate
    (bornes sourate:verset saisies) ou par hizb (hizb_debut..hizb_fin ; les
    bornes sourate:verset sont alors dérivées de la table Subdivision à
    l'enregistrement, si bien que la progression — versets couverts, juz,
    hizb complets — reste exacte même en mélangeant les deux méthodes)."""
    QUALITE_CHOICES = [
        ('BIEN',     'Bien'),
        ('MOYEN',    'Moyen'),
        ('A_REVOIR', 'À revoir'),
    ]
    MODE_CHOICES = [
        ('SOURATE', 'Par sourate'),
        ('HIZB',    'Par hizb'),
    ]
    parcours       = models.ForeignKey(ParcoursNongo, on_delete=models.CASCADE,
                                       related_name='suivis')
    date           = models.DateField()
    mode           = models.CharField(max_length=8, choices=MODE_CHOICES, default='SOURATE')
    hizb_debut     = models.PositiveSmallIntegerField(null=True, blank=True)   # 1..60
    hizb_fin       = models.PositiveSmallIntegerField(null=True, blank=True)
    sourate_debut  = models.ForeignKey(Sourate, on_delete=models.SET_NULL,
                                       null=True, blank=True, related_name='+')
    verset_debut   = models.PositiveSmallIntegerField(default=1)
    sourate_fin    = models.ForeignKey(Sourate, on_delete=models.SET_NULL,
                                       null=True, blank=True, related_name='+')
    verset_fin     = models.PositiveSmallIntegerField(default=1)
    qualite        = models.CharField(max_length=10, choices=QUALITE_CHOICES, default='MOYEN')
    present        = models.BooleanField(default=True)
    observation    = models.TextField(blank=True)

    class Meta:
        db_table = 'daara_suivi_quotidien'
        ordering = ['-date', '-created_at']
        indexes = [models.Index(fields=['parcours', 'date'])]

    def __str__(self):
        return f"{self.date} — {self.parcours.eleve}"
