import datetime
from decimal import Decimal

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone

from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.db.models import Sum

from core.permissions import IsSuperAdmin, CanAccessRH
from .models import Employe, Paie, ParametresFiscaux, AvanceSalaire, BulletinPaie
from .serializers import (
    EmployeSerializer, PaieSerializer, ParametresFiscauxSerializer,
    AvanceSalaireSerializer, BulletinPaieSerializer, BulletinPaieCreateSerializer,
)
from .services import PaieCalculateur, generer_ecriture_avance, generer_ecritures_paie

NOMS_MOIS = {
    1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril',
    5: 'Mai', 6: 'Juin', 7: 'Juillet', 8: 'Août',
    9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre',
}


def get_tenant(request):
    if request.tenant:
        return request.tenant
    if request.user.role == 'SUPER_ADMIN':
        from apps.tenants.models import Tenant
        return Tenant.objects.first()
    return None


class EmployeViewSet(viewsets.ModelViewSet):
    serializer_class   = EmployeSerializer
    permission_classes = [CanAccessRH]
    filter_backends    = [filters.SearchFilter]
    search_fields      = ['nom_complet', 'poste', 'matricule']

    def get_queryset(self):
        tenant = get_tenant(self.request)
        qs = Employe.objects.filter(tenant=tenant)
        if type_e := self.request.query_params.get('type'):
            qs = qs.filter(type_employe=type_e)
        if statut := self.request.query_params.get('statut'):
            qs = qs.filter(statut=statut)
        return qs

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        count  = Employe.objects.filter(tenant=tenant).count() + 1
        serializer.save(tenant=tenant, matricule=f"EMP-{count:04d}")

    @action(detail=True, methods=['post'])
    def avance(self, request, pk=None):
        employe = self.get_object()
        tenant  = get_tenant(request)

        montant_raw = request.data.get('montant')
        if not montant_raw:
            return Response({'error': 'montant requis'}, status=status.HTTP_400_BAD_REQUEST)

        mode       = request.data.get('mode_paiement', 'CAISSE')
        date_raw   = request.data.get('date_avance', datetime.date.today().isoformat())
        try:
            date_avance = datetime.date.fromisoformat(str(date_raw))
        except ValueError:
            return Response({'error': 'date_avance invalide (YYYY-MM-DD)'}, status=status.HTTP_400_BAD_REQUEST)

        count    = AvanceSalaire.objects.filter(tenant=tenant).count() + 1
        no_piece = f"AVA-{employe.matricule}-{count:04d}"

        avance = AvanceSalaire.objects.create(
            tenant=tenant, employe=employe,
            montant=Decimal(str(montant_raw)),
            date_avance=date_avance,
            mode_paiement=mode,
            no_piece=no_piece,
            observations=request.data.get('observations', ''),
        )
        generer_ecriture_avance(avance, tenant)
        return Response(AvanceSalaireSerializer(avance).data, status=status.HTTP_201_CREATED)


class PaieViewSet(viewsets.ModelViewSet):
    serializer_class   = PaieSerializer
    permission_classes = [CanAccessRH]

    def get_queryset(self):
        tenant = get_tenant(self.request)
        qs = Paie.objects.filter(tenant=tenant).select_related('employe')
        if mois := self.request.query_params.get('mois'):
            qs = qs.filter(mois=mois)
        if employe := self.request.query_params.get('employe'):
            qs = qs.filter(employe_id=employe)
        return qs

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        paie   = serializer.save(tenant=tenant)
        self._enregistrer_journal(paie, tenant)

    def _enregistrer_journal(self, paie, tenant):
        from apps.comptabilite.models import JournalEntry
        from apps.paiements.models import Exercice
        exercice = Exercice.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()
        if not exercice:
            return
        date = datetime.date.today()
        ref  = f"PAIE-{paie.mois}-{paie.employe.matricule}"
        JournalEntry.objects.create(
            tenant=tenant, exercice=exercice, no_piece=ref, date_ecriture=date,
            no_compte='661', libelle=f"Salaire {paie.employe.nom_complet} - {paie.mois}",
            debit=float(paie.salaire_brut), credit=0, source='CHARGE',
        )
        JournalEntry.objects.create(
            tenant=tenant, exercice=exercice, no_piece=ref, date_ecriture=date,
            no_compte='571', libelle=f"Paiement salaire {paie.employe.nom_complet} - {paie.mois}",
            debit=0, credit=float(paie.salaire_net), source='CHARGE',
        )


class ParametresFiscauxViewSet(viewsets.ModelViewSet):
    queryset         = ParametresFiscaux.objects.all()
    serializer_class = ParametresFiscauxSerializer
    lookup_field     = 'annee'

    def get_permissions(self):
        if self.action in ('update', 'partial_update', 'create', 'destroy'):
            return [IsSuperAdmin()]
        return [CanAccessRH()]


class BulletinPaieViewSet(viewsets.ModelViewSet):
    serializer_class   = BulletinPaieSerializer
    permission_classes = [CanAccessRH]

    def get_queryset(self):
        tenant = get_tenant(self.request)
        qs = BulletinPaie.objects.filter(tenant=tenant).select_related('employe', 'parametres_fiscaux')
        if employe := self.request.query_params.get('employe'):
            qs = qs.filter(employe_id=employe)
        if mois := self.request.query_params.get('mois'):
            qs = qs.filter(mois=mois)
        if annee := self.request.query_params.get('annee'):
            qs = qs.filter(annee=annee)
        if statut := self.request.query_params.get('statut'):
            qs = qs.filter(statut=statut)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = BulletinPaieCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        tenant  = get_tenant(request)
        employe = get_object_or_404(Employe, id=vd['employe_id'], tenant=tenant)

        kwargs_paie = {k: vd[k] for k in (
            'indemnite_sujetion', 'indemnite_logement', 'primes_diverses',
            'avantages_nature', 'opposition_saisie', 'autres_retenues',
            'avance_ids', 'inclure_avances',
        )}
        if 'mode_paiement_effectif' in vd:
            kwargs_paie['mode_paiement_effectif'] = vd['mode_paiement_effectif']

        try:
            bulletin = PaieCalculateur.creer_bulletin(
                employe, vd['mois'], vd['annee'],
                float(vd['nb_heures_effectuees']), **kwargs_paie
            )
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(BulletinPaieSerializer(bulletin).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'])
    def calculer(self, request):
        """Prévisualisation sans persistance."""
        serializer = BulletinPaieCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        tenant  = get_tenant(request)
        employe = get_object_or_404(Employe, id=vd['employe_id'], tenant=tenant)

        kwargs_paie = {k: vd[k] for k in (
            'indemnite_sujetion', 'indemnite_logement', 'primes_diverses',
            'avantages_nature', 'opposition_saisie', 'autres_retenues',
            'avance_ids', 'inclure_avances',
        )}
        if 'mode_paiement_effectif' in vd:
            kwargs_paie['mode_paiement_effectif'] = vd['mode_paiement_effectif']

        try:
            data = PaieCalculateur.calculer_bulletin(
                employe, vd['mois'], vd['annee'],
                float(vd['nb_heures_effectuees']), **kwargs_paie
            )
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        data.pop('_avances_qs', None)
        params = data.pop('parametres_fiscaux', None)

        result = {k: str(v) for k, v in data.items() if not k.startswith('_')}
        result['employe_nom']     = employe.nom_complet
        result['employe_matricule'] = employe.matricule
        result['parametres_annee'] = params.annee if params else None
        return Response(result)

    @action(detail=True, methods=['post'])
    def valider(self, request, pk=None):
        bulletin = self.get_object()
        if bulletin.statut != 'BROUILLON':
            return Response(
                {'error': 'Seul un bulletin en statut BROUILLON peut être validé.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        bulletin.statut          = 'VALIDE'
        bulletin.date_validation = timezone.now()
        bulletin.save()
        generer_ecritures_paie(bulletin, bulletin.tenant)
        return Response(BulletinPaieSerializer(bulletin).data)

    @action(detail=True, methods=['post'])
    def payer(self, request, pk=None):
        bulletin = self.get_object()
        if bulletin.statut != 'VALIDE':
            return Response(
                {'error': 'Seul un bulletin en statut VALIDE peut être marqué payé.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        bulletin.statut        = 'PAYE'
        bulletin.date_paiement = timezone.now()
        if mode := request.data.get('mode_paiement_effectif'):
            bulletin.mode_paiement_effectif = mode
        bulletin.save()
        return Response(BulletinPaieSerializer(bulletin).data)

    @action(detail=True, methods=['get'])
    def pdf(self, request, pk=None):
        bulletin = self.get_object()
        try:
            from weasyprint import HTML
        except ImportError:
            return HttpResponse('WeasyPrint non installé.', status=500)

        context = {
            'bulletin':     bulletin,
            'employe':      bulletin.employe,
            'tenant':       bulletin.tenant,
            'date_edition': timezone.now(),
            'nom_mois':     NOMS_MOIS.get(bulletin.mois, str(bulletin.mois)),
        }
        html_str = render_to_string('pdf/bulletin_paie.html', context)
        pdf_bytes = HTML(string=html_str, base_url=request.build_absolute_uri()).write_pdf()

        filename = f"bulletin_{bulletin.employe.matricule}_{bulletin.mois:02d}_{bulletin.annee}.pdf"
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response


class AvanceSalaireViewSet(viewsets.ModelViewSet):
    serializer_class   = AvanceSalaireSerializer
    permission_classes = [CanAccessRH]

    def get_queryset(self):
        tenant = get_tenant(self.request)
        qs = AvanceSalaire.objects.filter(tenant=tenant).select_related('employe')
        if employe := self.request.query_params.get('employe'):
            qs = qs.filter(employe_id=employe)
        if statut := self.request.query_params.get('statut'):
            qs = qs.filter(statut=statut)
        return qs

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        avance = serializer.save(tenant=tenant)
        generer_ecriture_avance(avance, tenant)


class RHStatsView(APIView):
    permission_classes = [CanAccessRH]

    def get(self, request):
        tenant   = get_tenant(request)
        employes = Employe.objects.filter(tenant=tenant)
        masse    = float(
            employes.filter(statut='ACTIF').aggregate(t=Sum('salaire_base'))['t'] or 0
        )
        return Response({
            'total_employes':  employes.count(),
            'actifs':          employes.filter(statut='ACTIF').count(),
            'enseignants':     employes.filter(type_employe='ENSEIGNANT').count(),
            'administration':  employes.filter(type_employe='ADMINISTRATION').count(),
            'appui':           employes.filter(type_employe='APPUI').count(),
            'masse_salariale': masse,
            'ipres_patronal':  round(masse * 0.084, 2),
            'css_patronal':    round(masse * 0.070, 2),
        })
