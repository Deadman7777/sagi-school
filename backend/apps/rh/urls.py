from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import (
    EmployeViewSet, PaieViewSet, RHStatsView,
    ParametresFiscauxViewSet, BulletinPaieViewSet, AvanceSalaireViewSet,
)

router = DefaultRouter()
router.register('employes',           EmployeViewSet,          basename='employe')
router.register('paies',              PaieViewSet,             basename='paie')
router.register('parametres-fiscaux', ParametresFiscauxViewSet, basename='parametres-fiscaux')
router.register('bulletins',          BulletinPaieViewSet,     basename='bulletin')
router.register('avances',            AvanceSalaireViewSet,    basename='avance')

urlpatterns = router.urls + [
    path('stats/', RHStatsView.as_view()),
]
