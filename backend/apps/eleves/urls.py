from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import (EleveViewSet, SectionViewSet, ServiceViewSet, SuiviMensuelView,
                    CertificatScolariteView, PriseEnChargeStatsView,
                    ElevesListePDFView, SituationElevePDFView, FicheElevePDFView,
                    ParcoursElevePDFView)

router = DefaultRouter()
router.register('sections', SectionViewSet, basename='section')
router.register('services', ServiceViewSet, basename='service')
router.register('liste', EleveViewSet, basename='eleve')
router.register('', EleveViewSet, basename='eleve-root')

urlpatterns = [
    path('suivi-mensuel/', SuiviMensuelView.as_view()),
    path('export-pdf/', ElevesListePDFView.as_view()),
    path('prises-en-charge/stats/', PriseEnChargeStatsView.as_view()),
    path('<str:eleve_id>/certificat/', CertificatScolariteView.as_view()),
    path('<str:eleve_id>/situation-pdf/', SituationElevePDFView.as_view()),
    path('<str:eleve_id>/fiche-pdf/', FicheElevePDFView.as_view()),
    path('<str:eleve_id>/parcours-pdf/', ParcoursElevePDFView.as_view()),
] + router.urls