from django.db import models
from core.models import TenantModel
import uuid


class NiveauScolaire(TenantModel):
    # Le post-bac manquait : un centre de formation professionnelle qui prépare
    # un BTS n'avait aucun code juste à poser sur ses promotions, et devait se
    # déclarer « Lycée ». Le module RH, lui, connaissait déjà le niveau
    # Supérieur pour ses enseignants (apps/rh/models.py) — c'était un oubli, pas
    # une décision.
    NIVEAU_CHOICES = [
        ('PRESCOLAIRE',  'Préscolaire'),
        ('ELEMENTAIRE',  'Élémentaire'),
        ('COLLEGE',      'Collège'),
        ('LYCEE',        'Lycée'),
        ('SUPERIEUR',    'Supérieur / BTS'),
    ]
    nom        = models.CharField(max_length=50)
    code       = models.CharField(max_length=20, choices=NIVEAU_CHOICES)
    note_max   = models.DecimalField(max_digits=4, decimal_places=1, default=20)
    ordre      = models.IntegerField(default=0)

    class Meta:
        db_table = 'niveaux_scolaires'
        ordering = ['ordre']

    def __str__(self):
        return self.nom


class Classe(TenantModel):
    niveau     = models.ForeignKey(NiveauScolaire, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='classes')
    nom        = models.CharField(max_length=100)
    code       = models.CharField(max_length=20, blank=True)
    effectif   = models.IntegerField(default=0)
    ordre      = models.IntegerField(default=0)

    class Meta:
        db_table = 'classes'
        ordering = ['ordre', 'nom']

    def __str__(self):
        return f"{self.nom} ({self.niveau.nom})"


class TypeEvaluation(TenantModel):
    nom        = models.CharField(max_length=50)  # Devoir, Composition, Interro...
    # Libellé sur le bulletin du programme arabe (فرض، امتحان…). Vide : une
    # traduction des noms courants, sinon le nom tel quel.
    nom_ar     = models.CharField(max_length=50, blank=True)
    poids      = models.DecimalField(max_digits=4, decimal_places=2, default=1)
    description= models.TextField(blank=True)

    class Meta:
        db_table = 'types_evaluations'
        ordering = ['nom']

    def __str__(self):
        return f"{self.nom} (poids {self.poids})"


class Matiere(TenantModel):
    # Établissement hybride : une même classe suit le programme français ET le
    # programme arabe. Chaque matière appartient à l'un des deux ; chacun a son
    # bulletin, sa moyenne générale et son rang. Une école à un seul programme
    # garde tout en FR sans jamais voir ce champ.
    PROGRAMME_CHOICES = [('FR', 'Programme français'), ('AR', 'Programme arabe')]
    classe       = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name='matieres')
    programme    = models.CharField(max_length=2, choices=PROGRAMME_CHOICES, default='FR')
    nom          = models.CharField(max_length=100)
    code         = models.CharField(max_length=20, blank=True)
    coefficient  = models.DecimalField(max_digits=4, decimal_places=1, default=1)
    note_max     = models.DecimalField(max_digits=4, decimal_places=1, default=20)
    ordre        = models.IntegerField(default=0)
    est_active   = models.BooleanField(default=True)

    class Meta:
        db_table = 'matieres'
        ordering = ['ordre', 'nom']

    def __str__(self):
        return f"{self.nom} — {self.classe.nom}"


class Evaluation(TenantModel):
    # Période : T1/T2/T3 (trimestres) ou S1/S2 (semestres) selon le réglage de l'école.
    # Pas de choices figés pour supporter les deux découpages.
    matiere       = models.ForeignKey(Matiere, on_delete=models.CASCADE, related_name='evaluations')
    type_eval     = models.ForeignKey(TypeEvaluation, on_delete=models.CASCADE)
    trimestre     = models.CharField(max_length=2)
    date_eval     = models.DateField()
    titre         = models.CharField(max_length=100, blank=True)
    note_max      = models.DecimalField(max_digits=4, decimal_places=1, default=20)

    class Meta:
        db_table = 'evaluations'
        ordering = ['date_eval']

    def __str__(self):
        return f"{self.matiere.nom} — {self.type_eval.nom} — {self.trimestre}"


class Note(TenantModel):
    eleve         = models.ForeignKey('eleves.Eleve', on_delete=models.CASCADE, related_name='notes')
    evaluation    = models.ForeignKey(Evaluation, on_delete=models.CASCADE, related_name='notes')
    valeur        = models.DecimalField(max_digits=5, decimal_places=2)
    absent        = models.BooleanField(default=False)
    observations  = models.TextField(blank=True)

    class Meta:
        db_table = 'notes'
        unique_together = ['tenant', 'eleve', 'evaluation']

    def __str__(self):
        return f"{self.eleve.nom_complet} — {self.evaluation} — {self.valeur}"


class BulletinCache(TenantModel):
    """Cache des moyennes calculées pour performance."""
    eleve         = models.ForeignKey('eleves.Eleve', on_delete=models.CASCADE)
    matiere       = models.ForeignKey(Matiere, on_delete=models.CASCADE)
    trimestre     = models.CharField(max_length=2)
    annee_scolaire= models.CharField(max_length=10)
    moyenne       = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    points        = models.DecimalField(max_digits=8, decimal_places=2, null=True)
    rang_matiere  = models.IntegerField(null=True)
    appreciation  = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = 'bulletins_cache'
        unique_together = ['tenant', 'eleve', 'matiere', 'trimestre', 'annee_scolaire']
