from django.urls import path
from .views import (JournalView, GrandLivreView, BalanceView,
                    CompteResultatView, BilanView,
                    TableauFluxView, HistoriqueExercicesView, ChargeView,
                    NotesAnnexesView, PlanComptableView, BudgetView,
                    BudgetComptabiliserView, ImmobilisationView, AmortirView,
                    ReglerImmobilisationView)
from .pdf_views import ExportPDFView

urlpatterns = [
    path('journal/',            JournalView.as_view()),
    path('grand-livre/',        GrandLivreView.as_view()),
    path('balance/',            BalanceView.as_view()),
    path('compte-resultat/',    CompteResultatView.as_view()),
    path('bilan/',              BilanView.as_view()),
    path('tableau-flux/',       TableauFluxView.as_view()),
    path('historique/',         HistoriqueExercicesView.as_view()),
    path('notes-annexes/',      NotesAnnexesView.as_view()),
    path('export-pdf/<str:type_doc>/', ExportPDFView.as_view()),
    path('charges/',            ChargeView.as_view()),
    path('charges/<str:pk>/',   ChargeView.as_view()),
    # Plan comptable paramétrable
    path('plan-comptable/',                  PlanComptableView.as_view()),
    path('plan-comptable/<str:no_compte>/', PlanComptableView.as_view()),
    # Budget prévisionnel
    path('budget/',                              BudgetView.as_view()),
    path('budget/<str:pk>/',                     BudgetView.as_view()),
    path('budget/<str:pk>/comptabiliser/',       BudgetComptabiliserView.as_view()),
    # Investissements / Immobilisations
    path('immobilisations/',              ImmobilisationView.as_view()),
    path('immobilisations/<str:pk>/',     ImmobilisationView.as_view()),
    path('immobilisations/<str:pk>/amortir/', AmortirView.as_view()),
    path('immobilisations/<str:pk>/regler/',  ReglerImmobilisationView.as_view()),
]
