from rest_framework import viewsets, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum
from .models import Employe, Paie
from .serializers import EmployeSerializer, PaieSerializer


def get_tenant(request):
    if request.tenant:
        return request.tenant
    if request.user.role == 'SUPER_ADMIN':
        from apps.tenants.models import Tenant
        return Tenant.objects.first()
    return None


class EmployeViewSet(viewsets.ModelViewSet):
    serializer_class   = EmployeSerializer
    permission_classes = [IsAuthenticated]
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
        # Générer matricule automatique
        count = Employe.objects.filter(tenant=tenant).count() + 1
        matricule = f"EMP-{count:04d}"
        serializer.save(tenant=tenant, matricule=matricule)


class PaieViewSet(viewsets.ModelViewSet):
    serializer_class   = PaieSerializer
    permission_classes = [IsAuthenticated]

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
        paie = serializer.save(tenant=tenant)
        # Enregistrer dans le journal comptable
        self._enregistrer_journal(paie, tenant)

    def _enregistrer_journal(self, paie, tenant):
        from apps.comptabilite.models import JournalEntry
        from apps.paiements.models import Exercice
        exercice = Exercice.objects.filter(
            tenant=tenant, cloture=False
        ).order_by('-date_debut').first()
        if not exercice:
            return
        import datetime
        date = datetime.date.today()
        ref = f"PAIE-{paie.mois}-{paie.employe.matricule}"
        # Débit 661 Salaires / Crédit 571 Caisse
        JournalEntry.objects.create(
            tenant=tenant, exercice=exercice,
            no_piece=ref, date_ecriture=date,
            no_compte='661',
            libelle=f"Salaire {paie.employe.nom_complet} - {paie.mois}",
            debit=float(paie.salaire_brut), credit=0,
            source='CHARGE',
        )
        JournalEntry.objects.create(
            tenant=tenant, exercice=exercice,
            no_piece=ref, date_ecriture=date,
            no_compte='571',
            libelle=f"Paiement salaire {paie.employe.nom_complet} - {paie.mois}",
            debit=0, credit=float(paie.salaire_net),
            source='CHARGE',
        )


class RHStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = get_tenant(request)
        employes = Employe.objects.filter(tenant=tenant)
        masse_salariale = float(
            employes.filter(statut='ACTIF').aggregate(
                t=Sum('salaire_base')
            )['t'] or 0
        )
        return Response({
            'total_employes':   employes.count(),
            'actifs':           employes.filter(statut='ACTIF').count(),
            'enseignants':      employes.filter(type_employe='ENSEIGNANT').count(),
            'administration':   employes.filter(type_employe='ADMINISTRATION').count(),
            'appui':            employes.filter(type_employe='APPUI').count(),
            'masse_salariale':  masse_salariale,
            'ipres_patronal':   round(masse_salariale * 0.086, 2),
            'css_patronal':     round(masse_salariale * 0.007, 2),
        })
