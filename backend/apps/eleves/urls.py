from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import (ChampFicheViewSet, EleveViewSet, FamilleViewSet, FormuleSectionViewSet, OrganismeViewSet, PriseEnChargeOrganismeViewSet,
                    SectionViewSet, ServiceViewSet, SuiviMensuelView,
                    CertificatScolariteView, PriseEnChargeStatsView,
                    ElevesListePDFView, SituationElevePDFView, FicheElevePDFView,
                    ParcoursElevePDFView, ModeleCertificatView,
                    GarderieAppelView, GarderieRecapView, GarderieRepriseView,
                    GardeSoirView)

router = DefaultRouter()
router.register('sections', SectionViewSet, basename='section')
router.register('services', ServiceViewSet, basename='service')
router.register('formules', FormuleSectionViewSet, basename='formule-section')
router.register('champs', ChampFicheViewSet, basename='champ-fiche')
router.register('organismes', OrganismeViewSet, basename='organisme')
# Avant la route racine, qui capte tout ce qui n'est pas déclaré au-dessus.
router.register('familles', FamilleViewSet, basename='famille')
router.register('bourses', PriseEnChargeOrganismeViewSet, basename='bourse')
router.register('liste', EleveViewSet, basename='eleve')
router.register('', EleveViewSet, basename='eleve-root')

urlpatterns = [
    # Avant les routes « <eleve_id>/… » : « garderie » n'est pas un élève.
    path('garderie/appel/', GarderieAppelView.as_view()),
    path('garderie/recap/', GarderieRecapView.as_view()),
    path('garderie/reprise/', GarderieRepriseView.as_view()),
    path('garde-soir/', GardeSoirView.as_view()),
    path('suivi-mensuel/', SuiviMensuelView.as_view()),
    path('export-pdf/', ElevesListePDFView.as_view()),
    path('prises-en-charge/stats/', PriseEnChargeStatsView.as_view()),
    path('certificat-modele/', ModeleCertificatView.as_view()),
    path('<str:eleve_id>/certificat/', CertificatScolariteView.as_view()),
    path('<str:eleve_id>/situation-pdf/', SituationElevePDFView.as_view()),
    path('<str:eleve_id>/fiche-pdf/', FicheElevePDFView.as_view()),
    path('<str:eleve_id>/parcours-pdf/', ParcoursElevePDFView.as_view()),
] + router.urls