from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import (NiveauScolaireViewSet, ClasseViewSet, TypeEvaluationViewSet,
                    MatiereViewSet, EvaluationViewSet, NoteViewSet,
                    MoteurCalculView, BulletinView)

router = DefaultRouter()
router.register('niveaux',     NiveauScolaireViewSet, basename='niveau')
router.register('classes',     ClasseViewSet,         basename='classe')
router.register('types-eval',  TypeEvaluationViewSet, basename='type-eval')
router.register('matieres',    MatiereViewSet,        basename='matiere')
router.register('evaluations', EvaluationViewSet,     basename='evaluation')
router.register('notes',       NoteViewSet,           basename='note')

urlpatterns = router.urls + [
    path('calculer/',                        MoteurCalculView.as_view()),
    path('bulletin/<str:eleve_id>/<str:trimestre>/', BulletinView.as_view()),
]
