from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import EleveViewSet, SectionViewSet, SuiviMensuelView

router = DefaultRouter()
router.register('sections', SectionViewSet, basename='section')
router.register('liste', EleveViewSet, basename='eleve')
router.register('', EleveViewSet, basename='eleve-root')

urlpatterns = router.urls + [
    path('suivi-mensuel/', SuiviMensuelView.as_view()),
]