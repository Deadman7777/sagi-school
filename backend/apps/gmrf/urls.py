from django.urls import path
from .views import (TypeFinancementView, FinancementView, NattCycleView,
                    NattCotisationView, NattReceptionView, DashboardGMRFView)

urlpatterns = [
    path('dashboard/',                DashboardGMRFView.as_view()),
    path('types/',                    TypeFinancementView.as_view()),
    path('types/<uuid:pk>/',          TypeFinancementView.as_view()),
    path('financements/',             FinancementView.as_view()),
    path('financements/<uuid:pk>/',   FinancementView.as_view()),
    path('natt/',                     NattCycleView.as_view()),
    path('natt/<uuid:pk>/',           NattCycleView.as_view()),
    path('natt/<uuid:pk>/reception/', NattReceptionView.as_view()),
    path('cotisations/<uuid:pk>/',    NattCotisationView.as_view()),
]
