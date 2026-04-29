from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import EmployeViewSet, PaieViewSet, RHStatsView

router = DefaultRouter()
router.register('employes', EmployeViewSet, basename='employe')
router.register('paies',    PaieViewSet,    basename='paie')

urlpatterns = router.urls + [
    path('stats/', RHStatsView.as_view()),
]
