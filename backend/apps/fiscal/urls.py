from django.urls import path
from .views import DeclarationsFiscalesView
from .views_parametrage import ParametresFiscauxView, ProfilFiscalView, ReferentielObligationsView
from .etablissement import (ObligationsEtablissementView,
                            ComptabiliserObligationView, ConseilsView)

urlpatterns = [
    path('declarations/',  DeclarationsFiscalesView.as_view()),
    path('obligations/',   ObligationsEtablissementView.as_view()),
    path('comptabiliser/', ComptabiliserObligationView.as_view()),
    path('conseils/',      ConseilsView.as_view()),
    path('profil/',        ProfilFiscalView.as_view()),
    path('parametres/',    ParametresFiscauxView.as_view()),
    path('referentiel/',   ReferentielObligationsView.as_view()),
]
