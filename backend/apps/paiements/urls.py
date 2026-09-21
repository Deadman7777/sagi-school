from rest_framework.routers import DefaultRouter
from django.urls import path
from .views_proformas import ProformaViewSet
from .views import (PaiementViewSet, ExerciceViewSet, CloturerExerciceView,
                    ReporterReliquatsView, CahierMensuelView, CahierMensuelPdfView)

router = DefaultRouter()
router.register('paiements', PaiementViewSet, basename='paiement')
router.register('exercices', ExerciceViewSet, basename='exercice')
router.register('proformas', ProformaViewSet, basename='proforma')

urlpatterns = router.urls + [
    path('cloturer-exercice/', CloturerExerciceView.as_view()),
    path('reporter-reliquats/', ReporterReliquatsView.as_view()),
    path('cahier-mensuel/', CahierMensuelView.as_view()),
    path('cahier-mensuel/pdf/', CahierMensuelPdfView.as_view()),
    path('stats/', PaiementViewSet.as_view({'get': 'stats'})),
]