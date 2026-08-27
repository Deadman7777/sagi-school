from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views_devis import DevisViewSet

router = DefaultRouter()
router.register('', DevisViewSet, basename='devis')

urlpatterns = [path('', include(router.urls))]
