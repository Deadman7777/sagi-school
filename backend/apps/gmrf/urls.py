from django.urls import path
from .views import (TypeFinancementView, FinancementView, NattCycleView,
                    NattCotisationView, NattReceptionView, DashboardGMRFView,
                    PretView, PretEcheanceView)

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
    path('prets/',                    PretView.as_view()),
    path('prets/<uuid:pk>/',          PretView.as_view()),
    path('echeances/<uuid:pk>/',      PretEcheanceView.as_view()),
]
