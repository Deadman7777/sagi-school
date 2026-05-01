from rest_framework import serializers
from .models import NiveauScolaire, Classe, TypeEvaluation, Matiere, Evaluation, Note, BulletinCache


class NiveauScolaireSerializer(serializers.ModelSerializer):
    class Meta:
        model = NiveauScolaire
        fields = '__all__'
        extra_kwargs = {'tenant': {'required': False, 'read_only': True}}


class ClasseSerializer(serializers.ModelSerializer):
    niveau_nom = serializers.CharField(source='niveau.nom', read_only=True)
    note_max   = serializers.FloatField(source='niveau.note_max', read_only=True)

    class Meta:
        model = Classe
        fields = '__all__'
        extra_kwargs = {'tenant': {'required': False, 'read_only': True}}


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
