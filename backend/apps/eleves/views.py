from rest_framework import viewsets, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Count, Value, DecimalField
from django.db.models.functions import Coalesce, TruncMonth
from core.permissions import IsTenantMember
from .models import Eleve, Section
from .serializers import EleveSerializer, SectionSerializer


def get_tenant(request):
    if request.tenant:
        return request.tenant
    if hasattr(request.user, 'tenant') and request.user.tenant:
        return request.user.tenant
    if request.user.role == 'SUPER_ADMIN':
        from apps.tenants.models import Tenant
        return Tenant.objects.first()
    return None


class SectionViewSet(viewsets.ModelViewSet):
    serializer_class   = SectionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Section.objects.filter(tenant=get_tenant(self.request))

    def perform_create(self, serializer):
        serializer.save(tenant=get_tenant(self.request))


class EleveViewSet(viewsets.ModelViewSet):
    serializer_class   = EleveSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [filters.SearchFilter, filters.OrderingFilter]
    search_fields      = ['nom_complet', 'telephone_parent']
    ordering_fields    = ['nom_complet', 'date_inscription', 'numero']

    def get_queryset(self):
        tenant = get_tenant(self.request)
        if not tenant:
            return Eleve.objects.none()

        qs = Eleve.objects.filter(tenant=tenant).select_related(
            'section'
        ).prefetch_related('paiements').annotate(
            total_paye_sql=Coalesce(
                Sum('paiements__montant_inscription') +
                Sum('paiements__montant_mensualite')  +
                Sum('paiements__montant_uniforme')    +
                Sum('paiements__montant_fournitures') +
                Sum('paiements__montant_cantine')     +
                Sum('paiements__montant_divers'),
                Value(0), output_field=DecimalField()
            )
        )

        if section := self.request.query_params.get('section'):
            qs = qs.filter(section__nom=section)
        if exercice := self.request.query_params.get('exercice'):
            qs = qs.filter(exercice_id=exercice)

        return qs.order_by('numero')

    def perform_create(self, serializer):
        serializer.save(tenant=get_tenant(self.request))


class SuiviMensuelView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.paiements.models import Exercice, Paiement

        tenant   = get_tenant(request)
        exercice = Exercice.objects.filter(
            tenant=tenant, cloture=False
        ).order_by('-date_debut').first()

        if not exercice:
            return Response({'global': [], 'eleve': None})

        eleve_id = request.query_params.get('eleve_id')

        # ── Suivi détaillé d'un élève ────────────────────────
        eleve_data = None
        if eleve_id:
            try:
                eleve = Eleve.objects.get(id=eleve_id, tenant=tenant)
                paiements_eleve = Paiement.objects.filter(
                    tenant=tenant, exercice=exercice, eleve=eleve
                ).order_by('date_paiement')

                eleve_data = {
                    'nom':      eleve.nom_complet,
                    'section':  eleve.section.nom if eleve.section else '',
                    'attendu':  float(eleve.total_attendu),
                    'paiements': [{
                        'no_piece':    p.no_piece,
                        'date':        str(p.date_paiement),
                        'inscription': float(p.montant_inscription),
                        'mensualite':  float(p.montant_mensualite),
                        'uniforme':    float(p.montant_uniforme),
                        'fournitures': float(p.montant_fournitures),
                        'cantine':     float(p.montant_cantine),
                        'divers':      float(p.montant_divers),
                        'total':       float(p.total),
                        'mode':        p.mode_paiement,
                    } for p in paiements_eleve]
                }
                # Cumul progressif
                cumul = 0
                for p in eleve_data['paiements']:
                    cumul += p['total']
                    p['cumul'] = cumul
                eleve_data['total_paye'] = cumul
                eleve_data['reste']      = eleve_data['attendu'] - cumul
            except Eleve.DoesNotExist:
                pass

        # ── Suivi global mensuel ─────────────────────────────
        mensuel = Paiement.objects.filter(
            tenant=tenant, exercice=exercice
        ).annotate(mois=TruncMonth('date_paiement')).values('mois').annotate(
            total       = Sum('montant_inscription') + Sum('montant_mensualite') +
                          Sum('montant_uniforme')    + Sum('montant_fournitures') +
                          Sum('montant_cantine')     + Sum('montant_divers'),
            nb          = Count('id'),
            inscription = Sum('montant_inscription'),
            mensualite  = Sum('montant_mensualite'),
            uniforme    = Sum('montant_uniforme'),
            fournitures = Sum('montant_fournitures'),
            cantine     = Sum('montant_cantine'),
        ).order_by('mois')

        global_data = [{
            'mois':        m['mois'].strftime('%B %Y'),
            'mois_court':  m['mois'].strftime('%b'),
            'total':       float(m['total']       or 0),
            'nb':          m['nb'],
            'inscription': float(m['inscription'] or 0),
            'mensualite':  float(m['mensualite']  or 0),
            'uniforme':    float(m['uniforme']    or 0),
            'fournitures': float(m['fournitures'] or 0),
            'cantine':     float(m['cantine']     or 0),
        } for m in mensuel if m['mois']]

        return Response({'global': global_data, 'eleve': eleve_data})
