from django.urls import path
from rest_framework.routers import DefaultRouter
from .relais import EtatDistantView, RelaisRenouvellementView
from .views import LicenceViewSet

router = DefaultRouter()
router.register('', LicenceViewSet)
# Avant le routeur : sa route de détail (^<pk>/$) avalerait ce chemin.
urlpatterns = [
    path('relais-renouvellement/', RelaisRenouvellementView.as_view()),
    path('etat-distant/', EtatDistantView.as_view()),
] + router.urls
