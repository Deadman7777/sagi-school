from django.urls import path
from .views import (DashboardKPIView, DashboardAlerteView,
                    DashboardSuperAdminView, DashboardTresorerieCanauView,
                    AuditLogView)

urlpatterns = [
    path('kpis/',               DashboardKPIView.as_view()),
    path('alertes/',            DashboardAlerteView.as_view()),
    path('superadmin/',         DashboardSuperAdminView.as_view()),
    path('tresorerie-canaux/',  DashboardTresorerieCanauView.as_view()),
    path('audit-log/',          AuditLogView.as_view()),
]
