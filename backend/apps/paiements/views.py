from rest_framework.views import APIView
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Count
from apps.eleves.models import Eleve
from core.permissions import IsTenantMember
from .models import Paiement, Exercice
from .serializers import PaiementSerializer, ExerciceSerializer


class ExerciceViewSet(viewsets.ModelViewSet):
    serializer_class   = ExerciceSerializer
    permission_classes = [IsTenantMember]

    def get_queryset(self):
        tenant = self.request.tenant
        if not tenant and self.request.user.role == 'SUPER_ADMIN':
            from apps.tenants.models import Tenant
            tenant = Tenant.objects.first()
        return Exercice.objects.filter(tenant=tenant)

    def perform_create(self, serializer):
        tenant = self.request.tenant
        if not tenant and self.request.user.role == 'SUPER_ADMIN':
            from apps.tenants.models import Tenant
            tenant = Tenant.objects.first()
        serializer.save(tenant=tenant)


class PaiementViewSet(viewsets.ModelViewSet):
    serializer_class   = PaiementSerializer
    permission_classes = [IsAuthenticated]

    def get_tenant(self):
        if self.request.tenant:
            return self.request.tenant
        if self.request.user.role == 'SUPER_ADMIN':
            from apps.tenants.models import Tenant
            return Tenant.objects.first()
        return None

    def get_queryset(self):
        tenant = self.get_tenant()
        if not tenant:
            return Paiement.objects.none()
        qs = Paiement.objects.filter(tenant=tenant).select_related('eleve', 'exercice')
        if eleve_id := self.request.query_params.get('eleve'):
            qs = qs.filter(eleve_id=eleve_id)
        if mode := self.request.query_params.get('mode'):
            qs = qs.filter(mode_paiement=mode)
        return qs

    def perform_create(self, serializer):
        tenant = self.get_tenant()
        serializer.save(tenant=tenant, saisi_par=self.request.user)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        tenant   = self.get_tenant()
        exercice = Exercice.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()
        if not exercice:
            return Response({'total': 0, 'nb_transactions': 0, 'par_mode': []})

        paiements = Paiement.objects.filter(tenant=tenant, exercice=exercice)

        def total(qs):
            a = qs.aggregate(
                t=Sum('montant_inscription') + Sum('montant_mensualite') +
                  Sum('montant_uniforme')    + Sum('montant_fournitures') +
                  Sum('montant_cantine')     + Sum('montant_divers')
            )
            return float(a['t'] or 0)

        par_mode = []
        for m in paiements.values('mode_paiement').annotate(nb=Count('id')):
            par_mode.append({
                'mode':  m['mode_paiement'],
                'nb':    m['nb'],
                'total': total(paiements.filter(mode_paiement=m['mode_paiement']))
            })

        return Response({
            'total':           total(paiements),
            'nb_transactions': paiements.count(),
            'par_mode':        sorted(par_mode, key=lambda x: x['total'], reverse=True),
        })

    @action(detail=True, methods=['get'])
    def recu(self, request, pk=None):
        """Génère les données du reçu pour impression."""
        p = self.get_object()
        return Response({
            'no_piece':      p.no_piece,
            'date':          p.date_paiement,
            'eleve':         p.eleve.nom_complet,
            'section':       p.eleve.section.nom if p.eleve.section else '',
            'inscription':   float(p.montant_inscription),
            'mensualite':    float(p.montant_mensualite),
            'uniforme':      float(p.montant_uniforme),
            'fournitures':   float(p.montant_fournitures),
            'cantine':       float(p.montant_cantine),
            'divers':        float(p.montant_divers),
            'total':         float(p.total),
            'mode_paiement': p.mode_paiement,
            'saisi_par':     p.saisi_par.nom if p.saisi_par else '',
        })


class CloturerExerciceView(APIView):
    permission_classes = [IsAuthenticated]

    def get_tenant(self):
        if self.request.tenant:
            return self.request.tenant
        if hasattr(self.request.user, 'tenant') and self.request.user.tenant:
            return self.request.user.tenant
        return None

    def get(self, request):
        """Vérifie si l'exercice peut être clôturé."""
        from .cloturer import verifier_avant_cloture
        tenant   = self.get_tenant()
        exercice = Exercice.objects.filter(
            tenant=tenant, cloture=False
        ).order_by('-date_debut').first()

        if not exercice:
            return Response({'error': 'Aucun exercice actif'}, status=404)

        verification = verifier_avant_cloture(exercice)
        verification['exercice'] = {
            'id':             str(exercice.id),
            'annee_scolaire': exercice.annee_scolaire,
            'date_debut':     str(exercice.date_debut),
            'date_fin':       str(exercice.date_fin),
        }
        return Response(verification)

    def post(self, request):
        """Clôture l'exercice."""
        from .cloturer import verifier_avant_cloture, cloturer_exercice
        from core.permissions import IsAdminEcole

        tenant   = self.get_tenant()
        exercice = Exercice.objects.filter(
            tenant=tenant, cloture=False
        ).order_by('-date_debut').first()

        if not exercice:
            return Response({'error': 'Aucun exercice actif'}, status=404)

        # Vérification finale
        verif = verifier_avant_cloture(exercice)
        if not verif['peut_cloturer']:
            return Response({
                'error':     'Clôture impossible',
                'problemes': verif['problemes']
            }, status=400)

        # Confirmation requise
        if not request.data.get('confirme'):
            return Response({
                'error': 'Confirmation requise',
                'message': 'Envoyez {"confirme": true} pour confirmer la clôture'
            }, status=400)

        creer_suivant = request.data.get('creer_suivant', True)
        result        = cloturer_exercice(exercice, creer_suivant)

        return Response({
            'success': True,
            'message': f"Exercice {result['exercice_cloture']} clôturé ✅",
            **result
        })
