from django.urls import path
from .views import DeclarationsFiscalesView
from .etablissement import (ObligationsEtablissementView,
                            ComptabiliserObligationView, ConseilsView)

urlpatterns = [
    path('declarations/',  DeclarationsFiscalesView.as_view()),
    path('obligations/',   ObligationsEtablissementView.as_view()),
    path('comptabiliser/', ComptabiliserObligationView.as_view()),
    path('conseils/',      ConseilsView.as_view()),
]
