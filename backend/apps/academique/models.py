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
    """Un groupe d'élèves, rangé sous une section, elle-même sous un niveau.

    « Niveau élémentaire → section CI → classe CIA. » Une école qui gère
    plusieurs niveaux, plusieurs sections et beaucoup de classes s'y retrouve ;
    sans ce rangement, l'utilisateur lit une liste plate de dizaines de classes.

    ⚠️ Jusqu'en septembre 2026, le lien classe→section n'existait pas : le
    front rapprochait les deux par leur NOM (`c.niveau_nom === secNom`).
    Renommer une section détachait silencieusement ses classes. `section` est
    désormais une vraie clé étrangère, et `niveau` en découle — on ne saisit
    plus deux fois la même information.
    """
    section    = models.ForeignKey('eleves.Section', on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='classes')
    # Dérivé de la section (voir save()). Conservé en colonne : le barème
    # note_max du niveau est lu sur la classe à chaque bulletin, et une classe
    # peut encore exister sans section le temps qu'une école se range.
    niveau     = models.ForeignKey(NiveauScolaire, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='classes')
    nom        = models.CharField(max_length=100)
    code       = models.CharField(max_length=20, blank=True)
    effectif   = models.IntegerField(default=0)
    ordre      = models.IntegerField(default=0)

    class Meta:
        db_table = 'classes'
        ordering = ['ordre', 'nom']

    def save(self, *args, **kwargs):
        # La section fait foi : deux chemins vers le niveau finiraient par
        # diverger, et le bulletin lirait un barème que l'écran ne montre pas.
        if self.section_id and self.section.niveau_id:
            self.niveau_id = self.section.niveau_id
        super().save(*args, **kwargs)

    def __str__(self):
        parent = self.section.nom if self.section_id else (
            self.niveau.nom if self.niveau_id else 'sans section')
        return f"{self.nom} ({parent})"


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
    # Poids de la matière dans la moyenne générale quand il n'est pas son
    # coefficient : en calcul « total des points », une matière pèse autant que
    # son barème (une matière sur /20 compte 2 sur un bulletin sur /10). Vide :
    # le coefficient de la matière. Lu par `resultats.poids_ligne`, seul lecteur.
    poids         = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    rang_matiere  = models.IntegerField(null=True)
    appreciation  = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = 'bulletins_cache'
        unique_together = ['tenant', 'eleve', 'matiere', 'trimestre', 'annee_scolaire']
