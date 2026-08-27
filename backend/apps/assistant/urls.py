from django.urls import path

from .views import EtatView, MessageView

urlpatterns = [
    path('etat/',    EtatView.as_view()),
    path('message/', MessageView.as_view()),
]
