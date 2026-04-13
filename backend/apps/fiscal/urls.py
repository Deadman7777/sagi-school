from django.urls import path
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum


class DeclarationsFiscalesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.paiements.models import Exercice, Paiement
        from apps.dashboard.views import get_tenant
        import datetime

        tenant   = get_tenant(request)
        exercice = Exercice.objects.filter(
            tenant=tenant, cloture=False
        ).order_by('-date_debut').first()

        if not exercice:
            return Response([])

        # Calcule BRS depuis les charges salariales du journal
        from apps.comptabilite.models import JournalEntry
        salaires = JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice,
            no_compte='661'
        ).aggregate(t=Sum('debit'))['t'] or 0

        # Génère une déclaration par mois de l'exercice
        declarations = []
        debut = exercice.date_debut
        fin   = exercice.date_fin
        mois_actuel = datetime.date(debut.year, debut.month, 1)

        while mois_actuel <= fin:
            masse    = float(salaires) / 12  # simplifié
            montant  = masse * 0.05
            limite   = datetime.date(
                mois_actuel.year if mois_actuel.month < 12 else mois_actuel.year + 1,
                mois_actuel.month % 12 + 1, 15
            )
            today    = datetime.date.today()
            statut   = 'A_VENIR' if limite > today else (
                       'EN_REGLE' if mois_actuel.month == today.month else 'EN_RETARD'
            )
            declarations.append({
                'mois':            mois_actuel.strftime('%B %Y'),
                'masse_salariale': masse,
                'montant_brs':     montant,
                'date_limite':     str(limite),
                'statut':          statut,
            })
            # Mois suivant
            if mois_actuel.month == 12:
                mois_actuel = datetime.date(mois_actuel.year + 1, 1, 1)
            else:
                mois_actuel = datetime.date(mois_actuel.year, mois_actuel.month + 1, 1)

        return Response(declarations)


urlpatterns = [
    path('declarations/', DeclarationsFiscalesView.as_view()),
]
