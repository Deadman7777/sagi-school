from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Count, Value, DecimalField
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone
from django.core.cache import cache
from apps.eleves.models import Eleve
from apps.paiements.models import Paiement, Exercice
from apps.comptabilite.models import JournalEntry


def get_tenant(request):
    if request.tenant:
        return request.tenant
    if hasattr(request.user, 'tenant') and request.user.tenant:
        return request.user.tenant
    return None


def sum_paiements(qs):
    agg = qs.aggregate(
        t=Sum('montant_inscription') + Sum('montant_mensualite') +
          Sum('montant_uniforme')    + Sum('montant_fournitures') +
          Sum('montant_cantine')     + Sum('montant_divers')
    )
    return float(agg['t'] or 0)


class DashboardSuperAdminView(APIView):
    """Dashboard exclusif HADY GESMAN — stats globales sans détails écoles."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'SUPER_ADMIN':
            return Response({'error': 'Accès refusé'}, status=403)

        from apps.tenants.models import Tenant
        from apps.licences.models import Licence

        cache_key = 'dashboard_superadmin'
        cached    = cache.get(cache_key)
        if cached:
            return Response(cached)

        total_ecoles  = Tenant.objects.filter(actif=True).count()
        licences      = Licence.objects.select_related('tenant').all()
        actives       = licences.filter(statut='ACTIVE').count()
        expirees      = licences.filter(statut='EXPIREE').count()
        essai         = licences.filter(statut='ESSAI').count()

        TARIFS = {'PRO': 150000, 'BASIC': 75000, 'ESSAI': 0, 'ENTERPRISE': 300000}
        revenus_annuels = sum(
            TARIFS.get(l.type, 0) for l in licences.filter(statut='ACTIVE')
        )

        # Licences expirant dans 30 jours
        alertes = [{
            'ecole':          l.tenant.nom,
            'jours_restants': l.jours_restants,
            'date_fin':       str(l.date_fin),
            'type':           l.type,
        } for l in licences.filter(statut='ACTIVE') if 0 <= l.jours_restants <= 30]

        # Activité récente (nouvelles écoles ce mois)
        from django.utils import timezone
        debut_mois = timezone.now().replace(day=1, hour=0, minute=0, second=0)
        nouvelles  = Tenant.objects.filter(created_at__gte=debut_mois).count()

        result = {
            'ecoles': {
                'total':     total_ecoles,
                'actives':   actives,
                'expirees':  expirees,
                'essai':     essai,
                'nouvelles_ce_mois': nouvelles,
            },
            'finances': {
                'revenus_annuels':  revenus_annuels,
                'revenus_mensuels': revenus_annuels // 12,
            },
            'alertes_expiration': sorted(alertes, key=lambda x: x['jours_restants']),
        }
        cache.set(cache_key, result, 300)
        return Response(result)


class DashboardKPIView(APIView):
    """Dashboard école — données financières du tenant connecté."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Super admin redirigé vers son propre dashboard
        if request.user.role == 'SUPER_ADMIN':
            return Response({'error': 'Utilisez /api/dashboard/superadmin/'}, status=400)

        tenant = get_tenant(request)
        if not tenant:
            return Response({
                'exercice': None,
                'kpis': {'total_recettes': 0, 'total_charges': 0,
                         'resultat_net': 0, 'tresorerie': 0},
                'eleves': {'total': 0, 'urgent': 0, 'attention': 0, 'ok': 0},
                'modes_paiement': [], 'recettes_mensuelles': [],
            })

        cache_key = f'dashboard_kpis_{tenant.id}'
        cached    = cache.get(cache_key)
        if cached:
            return Response(cached)

        exercice = Exercice.objects.filter(
            tenant=tenant, cloture=False
        ).order_by('-date_debut').first()

        if not exercice:
            return Response({
                'exercice': None,
                'kpis': {'total_recettes': 0, 'total_charges': 0,
                         'resultat_net': 0, 'tresorerie': 0},
                'eleves': {'total': 0, 'urgent': 0, 'attention': 0, 'ok': 0},
                'modes_paiement': [], 'recettes_mensuelles': [],
                'message': 'Aucun exercice actif'
            })

        paiements      = Paiement.objects.filter(tenant=tenant, exercice=exercice)
        total_recettes = sum_paiements(paiements)
        total_charges  = float(JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice, source='CHARGE'
        ).aggregate(t=Sum('debit'))['t'] or 0)
        solde_initial  = float(exercice.solde_initial_caisse +
                               exercice.solde_initial_banque +
                               exercice.solde_initial_mobile)

        today  = timezone.now().date()
        eleves = Eleve.objects.filter(
            tenant=tenant, exercice=exercice
        ).annotate(
            total_paye_sql=Coalesce(
                Sum('paiements__montant_inscription') +
                Sum('paiements__montant_mensualite')  +
                Sum('paiements__montant_uniforme')    +
                Sum('paiements__montant_fournitures') +
                Sum('paiements__montant_cantine')     +
                Sum('paiements__montant_divers'),
                Value(0), output_field=DecimalField()
            )
        ).select_related('section')

        urgent = attention = ok = 0
        for e in eleves:
            reste = float(e.total_attendu) - float(e.total_paye_sql or 0)
            if reste <= 0:
                ok += 1; continue
            jours = (today - e.date_inscription).days
            if jours > 60:   urgent    += 1
            elif jours > 30: attention += 1
            else:            ok        += 1

        modes_raw = paiements.values('mode_paiement').annotate(
            nb=Count('id'),
            total=Sum('montant_inscription') + Sum('montant_mensualite') +
                  Sum('montant_uniforme')    + Sum('montant_fournitures') +
                  Sum('montant_cantine')     + Sum('montant_divers')
        ).order_by('-total')

        mensuel_raw = paiements.annotate(
            mois=TruncMonth('date_paiement')
        ).values('mois').annotate(
            total=Sum('montant_inscription') + Sum('montant_mensualite') +
                  Sum('montant_uniforme')    + Sum('montant_fournitures') +
                  Sum('montant_cantine')     + Sum('montant_divers')
        ).order_by('mois')
        
        # Calcul taux recouvrement et impayés
        total_attendu = sum(float(e.total_attendu) for e in eleves)
        total_paye    = sum(float(e.total_paye_sql or 0) for e in eleves)
        total_impayes = max(total_attendu - total_paye, 0)
        taux_recouvrement = round((total_paye / total_attendu * 100), 1) if total_attendu > 0 else 0

        result = {
            'exercice': {
                'annee_scolaire': exercice.annee_scolaire,
                'date_debut':     str(exercice.date_debut),
                'date_fin':       str(exercice.date_fin),
            },
            'kpis': {
                'total_recettes':      total_recettes,
                'total_charges':       total_charges,
                'resultat_net':        total_recettes - total_charges,
                'tresorerie':          solde_initial + total_recettes - total_charges,
                'total_attendu':       round(total_attendu, 2),
                'total_impayes':       round(total_impayes, 2),
                'taux_recouvrement':   taux_recouvrement,
            },
            'eleves': {
                'total': eleves.count(), 'urgent': urgent,
                'attention': attention, 'ok': ok,
            },
            'modes_paiement': [{'mode_paiement': m['mode_paiement'],
                                 'nb': m['nb'], 'total': float(m['total'] or 0)}
                                for m in modes_raw],
            'recettes_mensuelles': [{'mois': m['mois'].strftime('%b %Y'),
                                      'total': float(m['total'] or 0)}
                                     for m in mensuel_raw if m['mois']],
        }
        cache.set(cache_key, result, 300)
        return Response(result)


class DashboardAlerteView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = get_tenant(request)
        if not tenant or request.user.role == 'SUPER_ADMIN':
            return Response([])

        exercice = Exercice.objects.filter(
            tenant=tenant, cloture=False
        ).order_by('-date_debut').first()
        if not exercice:
            return Response([])

        today  = timezone.now().date()
        eleves = Eleve.objects.filter(
            tenant=tenant, exercice=exercice
        ).annotate(
            total_paye_sql=Coalesce(
                Sum('paiements__montant_inscription') +
                Sum('paiements__montant_mensualite')  +
                Sum('paiements__montant_uniforme')    +
                Sum('paiements__montant_fournitures') +
                Sum('paiements__montant_cantine')     +
                Sum('paiements__montant_divers'),
                Value(0), output_field=DecimalField()
            )
        ).select_related('section')

        data = []
        for e in eleves:
            reste = float(e.total_attendu) - float(e.total_paye_sql or 0)
            if reste <= 0: continue
            jours  = (today - e.date_inscription).days
            alerte = 'URGENT' if jours > 60 else 'ATTENTION' if jours > 30 else None
            if not alerte: continue
            data.append({
                'id': str(e.id), 'nom_complet': e.nom_complet,
                'section': e.section.nom if e.section else '',
                'telephone': e.telephone_parent,
                'reste_a_payer': reste, 'niveau_alerte': alerte, 'jours_retard': jours,
            })

        data.sort(key=lambda x: x['jours_retard'], reverse=True)
        return Response(data[:20])
