from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import EleveViewSet, SectionViewSet, SuiviMensuelView, CertificatScolariteView, PriseEnChargeStatsView

router = DefaultRouter()
router.register('sections', SectionViewSet, basename='section')
router.register('liste', EleveViewSet, basename='eleve')
router.register('', EleveViewSet, basename='eleve-root')

urlpatterns = [
    path('suivi-mensuel/', SuiviMensuelView.as_view()),
    path('prises-en-charge/stats/', PriseEnChargeStatsView.as_view()),
    path('<str:eleve_id>/certificat/', CertificatScolariteView.as_view()),
] + router.urls