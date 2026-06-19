from rest_framework import serializers
from .models import NiveauScolaire, Classe, TypeEvaluation, Matiere, Evaluation, Note, BulletinCache


class NiveauScolaireSerializer(serializers.ModelSerializer):
    class Meta:
        model = NiveauScolaire
        fields = '__all__'
        extra_kwargs = {'tenant': {'required': False, 'read_only': True}}


class ClasseSerializer(serializers.ModelSerializer):
    niveau_nom = serializers.SerializerMethodField()
    note_max   = serializers.SerializerMethodField()

    class Meta:
        model = Classe
        fields = '__all__'
        extra_kwargs = {
            'tenant': {'required': False, 'read_only': True},
            'niveau': {'required': False, 'allow_null': True},
        }

    def get_niveau_nom(self, obj):
        return obj.niveau.nom if obj.niveau_id else ''

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

    class Meta:
        model = Evaluation
        fields = '__all__'
        extra_kwargs = {'tenant': {'required': False, 'read_only': True}}


class NoteSerializer(serializers.ModelSerializer):
    eleve_nom      = serializers.CharField(source='eleve.nom_complet', read_only=True)
    evaluation_nom = serializers.CharField(source='evaluation.matiere.nom', read_only=True)

    class Meta:
        model = Note
        fields = '__all__'
        extra_kwargs = {'tenant': {'required': False, 'read_only': True}}
