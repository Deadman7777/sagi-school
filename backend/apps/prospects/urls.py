from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ProspectViewSet

router = DefaultRouter()
router.register('', ProspectViewSet, basename='prospect')

urlpatterns = [path('', include(router.urls))]
