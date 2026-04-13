from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from core.permissions import IsSuperAdmin
from apps.tenants.models import Tenant
from apps.eleves.models import Eleve
from apps.paiements.models import Exercice
from .models import Licence
from .serializers import LicenceSerializer


class LicenceViewSet(viewsets.ModelViewSet):
    queryset = Licence.objects.all()
    serializer_class = LicenceSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update',
                           'destroy', 'creer_ecole', 'stats_globales']:
            return [IsSuperAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'SUPER_ADMIN':
            return Licence.objects.select_related('tenant').all()
        if self.request.tenant:
            return Licence.objects.filter(
                tenant=self.request.tenant
            ).select_related('tenant')
        return Licence.objects.none()

    @action(detail=False, methods=['post'], permission_classes=[])
    def verifier(self, request):
        cle = request.data.get('cle_licence')
        try:
            licence = Licence.objects.get(cle_licence=cle)
            return Response({
                'valide':         licence.est_active,
                'type':           licence.type,
                'jours_restants': licence.jours_restants,
                'tenant':         licence.tenant.nom,
                'tenant_id':      str(licence.tenant.id),
            })
        except Licence.DoesNotExist:
            return Response({'valide': False, 'message': 'Clé invalide'}, status=400)

    @action(detail=True, methods=['post'])
    def renouveler(self, request, pk=None):
        licence = self.get_object()
        mois    = int(request.data.get('mois', 12))
        from dateutil.relativedelta import relativedelta
        base             = max(licence.date_fin, timezone.now().date())
        licence.date_fin = base + relativedelta(months=mois)
        licence.statut   = 'ACTIVE'
        licence.save()
        return Response(LicenceSerializer(licence).data)

    @action(detail=False, methods=['get'])
    def stats_globales(self, request):
        total_tenants = Tenant.objects.count()
        actives       = Licence.objects.filter(statut='ACTIVE').count()
        expirees      = Licence.objects.filter(statut='EXPIREE').count()
        essai         = Licence.objects.filter(statut='ESSAI').count()
        total_eleves  = Eleve.objects.count()

        TARIFS  = {'PRO': 150000, 'BASIC': 75000, 'ESSAI': 0, 'ENTERPRISE': 300000}
        revenus = sum(
            TARIFS.get(l.type, 0)
            for l in Licence.objects.filter(statut='ACTIVE')
        )
        dans_30j = [
            l for l in Licence.objects.filter(statut='ACTIVE')
            if 0 <= l.jours_restants <= 30
        ]
        return Response({
            'total_ecoles':    total_tenants,
            'actives':         actives,
            'expirees':        expirees,
            'essai':           essai,
            'total_eleves':    total_eleves,
            'revenus_annuels': revenus,
            'alertes_expiration': [{
                'ecole':          l.tenant.nom,
                'jours_restants': l.jours_restants,
                'date_fin':       str(l.date_fin),
                'type':           l.type,
            } for l in dans_30j],
        })

    @action(detail=False, methods=['post'])
    def creer_ecole(self, request):
        data = request.data
        tenant = Tenant.objects.create(
            nom=data.get('nom'), ville=data.get('ville', ''),
            adresse=data.get('adresse', ''), telephone=data.get('telephone', ''),
            email=data.get('email', ''), rccm=data.get('rccm', ''),
            ninea=data.get('ninea', ''),
        )
        from datetime import date
        from dateutil.relativedelta import relativedelta
        mois     = int(data.get('mois_licence', 12))
        type_lic = data.get('type_licence', 'ESSAI')
        cle      = Licence.generer_cle(tenant.rccm or tenant.nom[:6].upper())
        licence  = Licence.objects.create(
            tenant=tenant, cle_licence=cle, type=type_lic,
            statut='ACTIVE' if type_lic != 'ESSAI' else 'ESSAI',
            date_debut=date.today(),
            date_fin=date.today() + relativedelta(months=mois),
        )
        Exercice.objects.create(
            tenant=tenant,
            annee_scolaire=data.get('annee_scolaire', '2025-2026'),
            date_debut=data.get('date_debut', '2025-10-01'),
            date_fin=data.get('date_fin', '2026-09-30'),
            devise='FCFA',
        )
        return Response({
            'tenant_id': str(tenant.id), 'nom': tenant.nom,
            'cle_licence': cle, 'type': type_lic,
            'date_fin': str(licence.date_fin),
        }, status=status.HTTP_201_CREATED)
