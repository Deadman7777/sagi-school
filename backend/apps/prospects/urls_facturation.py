from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views_facturation import (DocumentCommercialViewSet, EncaissementViewSet, JustificatifViewSet,
                                ParametresFacturationView)

router = DefaultRouter()
router.register('documents', DocumentCommercialViewSet, basename='document-commercial')
router.register('encaissements', EncaissementViewSet, basename='encaissement')
router.register('justificatifs', JustificatifViewSet, basename='justificatif')

urlpatterns = [
    path('parametres/', ParametresFacturationView.as_view()),
    path('', include(router.urls)),
]
