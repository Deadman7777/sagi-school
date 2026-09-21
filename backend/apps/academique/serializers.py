from rest_framework import serializers
from .models import NiveauScolaire, Classe, TypeEvaluation, Matiere, Evaluation, Note, BulletinCache


class NiveauScolaireSerializer(serializers.ModelSerializer):
    class Meta:
        model = NiveauScolaire
        fields = '__all__'
        extra_kwargs = {'tenant': {'required': False, 'read_only': True}}


class ClasseSerializer(serializers.ModelSerializer):
    niveau_nom  = serializers.SerializerMethodField()
    section_nom = serializers.SerializerMethodField()
    note_max    = serializers.SerializerMethodField()

    class Meta:
        model = Classe
        fields = '__all__'
        extra_kwargs = {
            'tenant':  {'required': False, 'read_only': True},
            'niveau':  {'required': False, 'allow_null': True},
            'section': {'required': False, 'allow_null': True},
        }

    def get_niveau_nom(self, obj):
        return obj.niveau.nom if obj.niveau_id else ''

    def get_section_nom(self, obj):
        return obj.section.nom if obj.section_id else ''

    def get_note_max(self, obj):
        return float(obj.niveau.note_max) if obj.niveau_id else 20.0


class TypeEvaluationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TypeEvaluation
        fields = '__all__'
        extra_kwargs = {'tenant': {'required': False, 'read_only': True}}


class MatiereSerializer(serializers.ModelSerializer):
    classe_nom = serializers.CharField(source='classe.nom', read_only=True)

    class Meta:
        model = Matiere
        fields = '__all__'
        extra_kwargs = {'tenant': {'required': False, 'read_only': True}}


class EvaluationSerializer(serializers.ModelSerializer):
    matiere_nom   = serializers.CharField(source='matiere.nom', read_only=True)
    type_eval_nom = serializers.CharField(source='type_eval.nom', read_only=True)
    type_eval_poids = serializers.FloatField(source='type_eval.poids', read_only=True)
    # Combien de notes cette évaluation porte déjà. Sert à prévenir AVANT de
    # supprimer : les notes partent avec elle (CASCADE). Annoté par la vue,
    # replié sur un COUNT quand l'objet arrive d'ailleurs (création, détail).
    nb_notes      = serializers.SerializerMethodField()

    class Meta:
        model = Evaluation
        fields = '__all__'
        extra_kwargs = {'tenant': {'required': False, 'read_only': True}}

    def get_nb_notes(self, obj):
        valeur = getattr(obj, 'nb_notes_annote', None)
        return valeur if valeur is not None else obj.notes.count()

    def validate(self, attrs):
        """Baisser le barème ne doit pas rendre des notes déjà saisies illégales.

        Le cas qui motive la modification : l'évaluation a été créée sur /20
        alors qu'elle était sur /10, et la saisie a commencé. On garde les
        valeurs telles quelles — le professeur a noté sur 10 dans sa tête, une
        conversion lui changerait ses notes sous les yeux. Mais si l'une
        dépasse le nouveau barème, on refuse en la nommant plutôt que de
        laisser en base une note hors barème.
        """
        if self.instance is None:
            return attrs
        note_max = attrs.get('note_max', self.instance.note_max)
        if note_max is None or float(note_max) >= float(self.instance.note_max):
            return attrs
        hors = list(self.instance.notes.filter(absent=False, valeur__gt=note_max)
                                       .select_related('eleve')[:5])
        if hors:
            noms = ', '.join(f"{n.eleve.nom_complet} ({float(n.valeur):g})" for n in hors)
            raise serializers.ValidationError({'note_max': (
                f"Des notes déjà saisies dépassent /{float(note_max):g} : {noms}. "
                f"Corrigez-les d'abord, ou supprimez l'évaluation.")})
        return attrs


def erreur_bareme(valeur, note_max):
    """Le message d'erreur si la note ne tient pas dans son barème, sinon None.

    Une seule définition, parce qu'il y a deux chemins d'écriture : le
    serializer (API unitaire, imports) et `NoteViewSet.bulk_save` (la grille
    de saisie, qui écrit en masse sans passer par DRF).
    """
    if valeur is None:
        return None
    try:
        valeur = float(valeur)
    except (TypeError, ValueError):
        return "Note illisible."
    if valeur < 0:
        return "Une note ne peut pas être négative."
    note_max = float(note_max or 0)
    if note_max > 0 and valeur > note_max:
        return (f"Note supérieure au barème de l'évaluation "
                f"({valeur:g} sur /{note_max:g}).")
    return None


class NoteSerializer(serializers.ModelSerializer):
    eleve_nom      = serializers.CharField(source='eleve.nom_complet', read_only=True)
    evaluation_nom = serializers.CharField(source='evaluation.matiere.nom', read_only=True)

    class Meta:
        model = Note
        fields = '__all__'
        extra_kwargs = {'tenant': {'required': False, 'read_only': True}}

    def validate(self, attrs):
        """Une note ne peut pas dépasser le barème de son évaluation.

        L'écran de saisie borne déjà le champ, l'API ne le faisait pas : un
        import ou un appel direct posait 18 sur une interrogation notée /10.
        La note entrait en base et tout le reste en découlait — moyenne,
        rang, mention — sans que rien ne signale l'anomalie.
        """
        evaluation = attrs.get('evaluation') or getattr(self.instance, 'evaluation', None)
        valeur     = attrs.get('valeur', getattr(self.instance, 'valeur', None))
        if evaluation is not None and not attrs.get('absent', False):
            if message := erreur_bareme(valeur, evaluation.note_max):
                raise serializers.ValidationError({'valeur': message})
        return attrs
