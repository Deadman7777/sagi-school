from rest_framework.routers import DefaultRouter
from django.urls import path

from .views import (SourateViewSet, SubdivisionViewSet, NiveauDaaraViewSet,
                    ParcoursNongoViewSet, SuiviQuotidienViewSet, ProgressionView,
                    RapportParentPDFView)

router = DefaultRouter()
router.register('sourates',     SourateViewSet,        basename='sourate')
router.register('subdivisions', SubdivisionViewSet,    basename='subdivision')
router.register('niveaux',      NiveauDaaraViewSet,    basename='niveau-daara')
router.register('parcours',     ParcoursNongoViewSet,  basename='parcours')
router.register('suivi',        SuiviQuotidienViewSet, basename='suivi')

urlpatterns = router.urls + [
    path('progression/', ProgressionView.as_view()),
    path('rapport-pdf/<str:parcours_id>/', RapportParentPDFView.as_view()),
]
