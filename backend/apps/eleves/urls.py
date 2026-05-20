from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import EleveViewSet, SectionViewSet, SuiviMensuelView

router = DefaultRouter()
router.register('sections', SectionViewSet, basename='section')
router.register('liste', EleveViewSet, basename='eleve')
router.register('', EleveViewSet, basename='eleve-root')

# IMPORTANT : les paths explicites doivent précéder router.urls
# sinon le pattern ^(?P<pk>[^/.]+)/$ du router intercepte 'suivi-mensuel'
urlpatterns = [
    path('suivi-mensuel/', SuiviMensuelView.as_view()),
] + router.urls