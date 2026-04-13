from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import PaiementViewSet, ExerciceViewSet, CloturerExerciceView

router = DefaultRouter()
router.register('paiements', PaiementViewSet, basename='paiement')
router.register('exercices', ExerciceViewSet, basename='exercice')

urlpatterns = router.urls + [
    path('cloturer-exercice/', CloturerExerciceView.as_view()),
    path('stats/', PaiementViewSet.as_view({'get': 'stats'})),
]