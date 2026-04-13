from django.urls import path
from .views import DashboardKPIView, DashboardAlerteView, DashboardSuperAdminView

urlpatterns = [
    path('kpis/',       DashboardKPIView.as_view()),
    path('alertes/',    DashboardAlerteView.as_view()),
    path('superadmin/', DashboardSuperAdminView.as_view()),
]
