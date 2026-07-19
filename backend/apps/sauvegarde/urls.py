from django.urls import path

from .views import (DeclencherSauvegardeView, RecevoirSauvegardeView,
                    StatutSauvegardeView)

urlpatterns = [
    path('statut/',     StatutSauvegardeView.as_view()),
    path('declencher/', DeclencherSauvegardeView.as_view()),
    path('recevoir/',   RecevoirSauvegardeView.as_view()),
]
