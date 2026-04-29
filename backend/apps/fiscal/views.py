from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum
import datetime


def get_tenant(request):
    if request.tenant:
        return request.tenant
    if request.user.role == 'SUPER_ADMIN':
        from apps.tenants.models import Tenant
        return Tenant.objects.first()
    return None


class DeclarationsFiscalesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.paiements.models import Exercice
        from apps.comptabilite.models import JournalEntry

        tenant   = get_tenant(request)
        exercice = Exercice.objects.filter(
            tenant=tenant, cloture=False
        ).order_by('-date_debut').first()

        if not exercice:
            return Response([])

        # Salaires réels par mois depuis le journal
        salaires_mensuels = JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice,
            no_compte='661', source='CHARGE'
        ).extra(
            select={'mois': "DATE_TRUNC('month', date_ecriture)"}
        ).values('mois').annotate(
            total=Sum('debit')
        ).order_by('mois')

        # Indexer par mois
        salaires_par_mois = {}
        for s in salaires_mensuels:
            if s['mois']:
                key = s['mois'].strftime('%Y-%m') if hasattr(s['mois'], 'strftime') else str(s['mois'])[:7]
                salaires_par_mois[key] = float(s['total'] or 0)

        # Total salaires pour fallback
        total_salaires = float(JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice,
            no_compte='661', source='CHARGE'
        ).aggregate(t=Sum('debit'))['t'] or 0)

        # Générer déclarations par mois
        declarations = []
        debut = exercice.date_debut
        fin   = exercice.date_fin
        today = datetime.date.today()
        mois_actuel = datetime.date(debut.year, debut.month, 1)

        while mois_actuel <= fin and mois_actuel <= today:
            key   = mois_actuel.strftime('%Y-%m')
            masse = salaires_par_mois.get(key, total_salaires / 12 if total_salaires else 0)

            # Calculs fiscaux sénégalais
            brs    = round(masse * 0.05, 2)      # BRS 5%
            ipres  = round(masse * 0.056, 2)     # IPRES 5.6% part patronale
            css    = round(masse * 0.007, 2)     # CSS 0.7%
            ir     = round(max(masse - 500000, 0) * 0.20, 2)  # IR simplifié 20% au-delà de 500k
            cfce   = round(masse * 0.01, 2)      # CFCE 1%

            # Date limite : 15 du mois suivant
            next_month = mois_actuel.month % 12 + 1
            next_year  = mois_actuel.year + (1 if mois_actuel.month == 12 else 0)
            limite = datetime.date(next_year, next_month, 15)

            if limite > today:
                statut = 'A_VENIR'
            elif mois_actuel.month == today.month and mois_actuel.year == today.year:
                statut = 'EN_REGLE'
            else:
                statut = 'EN_RETARD' if masse == 0 else 'EN_REGLE'

            declarations.append({
                'mois':            mois_actuel.strftime('%B %Y'),
                'masse_salariale': masse,
                'brs':             brs,
                'ipres':           ipres,
                'css':             css,
                'ir':              ir,
                'cfce':            cfce,
                'montant_brs':     brs,  # compatibilité frontend
                'total_impots':    round(brs + ipres + css + ir + cfce, 2),
                'date_limite':     str(limite),
                'statut':          statut,
            })

            # Mois suivant
            if mois_actuel.month == 12:
                mois_actuel = datetime.date(mois_actuel.year + 1, 1, 1)
            else:
                mois_actuel = datetime.date(mois_actuel.year, mois_actuel.month + 1, 1)

        return Response(declarations)
