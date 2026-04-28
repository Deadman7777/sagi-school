from django.urls import path
from .views import (JournalView, GrandLivreView, BalanceView,
                    CompteResultatView, BilanView,
                    TableauFluxView, HistoriqueExercicesView, ChargeView)
from .pdf_views import ExportPDFView

urlpatterns = [
    path('journal/',            JournalView.as_view()),
    path('grand-livre/',        GrandLivreView.as_view()),
    path('balance/',            BalanceView.as_view()),
    path('compte-resultat/',    CompteResultatView.as_view()),
    path('bilan/',              BilanView.as_view()),
    path('tableau-flux/',       TableauFluxView.as_view()),
    path('historique/',         HistoriqueExercicesView.as_view()),
    path('export-pdf/<str:type_doc>/', ExportPDFView.as_view()),
    path('charges/',            ChargeView.as_view()),
    path('charges/<str:pk>/',   ChargeView.as_view()),
]
