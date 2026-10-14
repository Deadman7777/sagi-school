from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views_proposition import BibliothequeViewSet, PropositionViewSet

router = DefaultRouter()
router.register('propositions', PropositionViewSet, basename='proposition')
router.register('bibliotheque', BibliothequeViewSet, basename='bibliotheque')

urlpatterns = [path('', include(router.urls))]
