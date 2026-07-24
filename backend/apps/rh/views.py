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
from core.tenant import get_tenant
from .models import Employe, Paie, ParametresFiscaux, AvanceSalaire, BulletinPaie
from .serializers import (
    EmployeSerializer, PaieSerializer, ParametresFiscauxSerializer,
    AvanceSalaireSerializer, BulletinPaieSerializer, BulletinPaieCreateSerializer,
)
from .services import PaieCalculateur, generer_ecriture_avance, generer_ecritures_paie, annuler_ecriture_avance, annuler_ecritures_paie

NOMS_MOIS = {
    1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril',
    5: 'Mai', 6: 'Juin', 7: 'Juillet', 8: 'Août',
    9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre',
}


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

        mode       = request.data.get('mode_paiement', 'ESPECE')
        date_raw   = request.data.get('date_avance', datetime.date.today().isoformat())
        try:
            date_avance = datetime.date.fromisoformat(str(date_raw))
        except ValueError:
            return Response({'error': 'date_avance invalide (YYYY-MM-DD)'}, status=status.HTTP_400_BAD_REQUEST)

        count    = AvanceSalaire.objects.filter(tenant=tenant).count() + 1
        no_piece = f"AVA-{employe.matricule}-{count:04d}"

        montant_dec = Decimal(str(montant_raw))

        # Dimensions analytiques (gouvernance) + multi-mode. Une avance (D 421,
        # créance sur le salarié) n'est pas une charge → elle ne consomme pas la
        # ressource ; on garde le rattachement pour la traçabilité, sans contrôle.
        from apps.gouvernance.models import Projet, Ressource
        from .services import _ventiler_reglement
        projet = ressource = None
        pid = request.data.get('projet_id')
        rid = request.data.get('ressource_id')
        if pid:
            projet = Projet.objects.filter(tenant=tenant, id=pid).first()
        if rid:
            ressource = Ressource.objects.filter(tenant=tenant, id=rid).first()
            if ressource is None:
                return Response({'error': 'Ressource introuvable'}, status=status.HTTP_400_BAD_REQUEST)
        modes_reglement = request.data.get('modes_reglement') or []
        try:
            _ventiler_reglement(modes_reglement, montant_dec)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        avance = AvanceSalaire.objects.create(
            tenant=tenant, employe=employe,
            montant=montant_dec,
            date_avance=date_avance,
            mode_paiement=mode,
            no_piece=no_piece,
            observations=request.data.get('observations', ''),
            projet=projet, ressource=ressource, modes_reglement=modes_reglement,
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
        from django.db import IntegrityError

        serializer = BulletinPaieCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        tenant  = get_tenant(request)
        employe = get_object_or_404(Employe, id=vd['employe_id'], tenant=tenant)

        kwargs_paie = {}
        for k in ('prime_transport', 'indemnite_sujetion', 'indemnite_logement',
                  'primes_diverses', 'avantages_nature', 'opposition_saisie', 'autres_retenues'):
            kwargs_paie[k] = vd.get(k, 0)
        # avance_ids non vide = sélection explicite ; sinon auto (toutes EN_ATTENTE du mois)
        if vd.get('avance_ids'):
            kwargs_paie['avance_ids'] = vd['avance_ids']
        if 'mode_paiement_effectif' in vd:
            kwargs_paie['mode_paiement_effectif'] = vd['mode_paiement_effectif']

        try:
            bulletin = PaieCalculateur.creer_bulletin(
                employe, vd['mois'], vd['annee'],
                float(vd.get('nb_heures_effectuees', 0)), **kwargs_paie
            )
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except IntegrityError:
            return Response(
                {'error': f"Un bulletin existe déjà pour {employe.nom_complet} — "
                          f"{vd['mois']:02d}/{vd['annee']}. Supprimez-le d'abord ou modifiez la période."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            return Response({'error': f"Erreur interne : {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Dimensions analytiques (gouvernance) + multi-mode + contrôle du disponible.
        # Le coût employeur (661 + 6641) consomme la ressource → on le contrôle.
        from apps.gouvernance.models import Projet, Ressource
        from apps.gouvernance import services as gouv_services
        from .services import _ventiler_reglement
        pid = request.data.get('projet_id')
        rid = request.data.get('ressource_id')
        projet = Projet.objects.filter(tenant=tenant, id=pid).first() if pid else None
        ressource = None
        if rid:
            ressource = Ressource.objects.filter(tenant=tenant, id=rid).first()
            if ressource is None:
                bulletin.delete()
                return Response({'error': 'Ressource introuvable'}, status=status.HTTP_400_BAD_REQUEST)
            ok, msg, _ = gouv_services.verifier_disponibilite(
                tenant, ressource, bulletin.cout_total_employeur)
            if not ok:
                bulletin.delete()
                return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)
        modes_reglement = request.data.get('modes_reglement') or []
        try:
            _ventiler_reglement(modes_reglement, bulletin.net_a_payer)
        except ValueError as exc:
            bulletin.delete()
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        bulletin.projet = projet
        bulletin.ressource = ressource
        bulletin.modes_reglement = modes_reglement
        bulletin.save(update_fields=['projet', 'ressource', 'modes_reglement'])

        return Response(BulletinPaieSerializer(bulletin).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'])
    def calculer(self, request):
        """Prévisualisation sans persistance."""
        serializer = BulletinPaieCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        tenant  = get_tenant(request)
        employe = get_object_or_404(Employe, id=vd['employe_id'], tenant=tenant)

        kwargs_paie = {}
        for k in ('prime_transport', 'indemnite_sujetion', 'indemnite_logement',
                  'primes_diverses', 'avantages_nature', 'opposition_saisie', 'autres_retenues'):
            kwargs_paie[k] = vd.get(k, 0)
        # avance_ids non vide = sélection explicite ; sinon auto (toutes EN_ATTENTE du mois)
        if vd.get('avance_ids'):
            kwargs_paie['avance_ids'] = vd['avance_ids']
        if 'mode_paiement_effectif' in vd:
            kwargs_paie['mode_paiement_effectif'] = vd['mode_paiement_effectif']

        try:
            data = PaieCalculateur.calculer_bulletin(
                employe, vd['mois'], vd['annee'],
                float(vd.get('nb_heures_effectuees', 0)), **kwargs_paie
            )
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': f"Erreur calcul : {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        data.pop('_avances_qs', None)
        params = data.pop('parametres_fiscaux', None)

        result = {k: str(v) for k, v in data.items() if not k.startswith('_')}
        result['employe_nom']       = employe.nom_complet
        result['employe_matricule'] = employe.matricule
        result['parametres_annee']  = params.annee if params else None
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
        from core.models import log_audit
        log_audit(request, 'VALIDATE', 'BulletinPaie', str(bulletin.id),
                  f"{bulletin.employe.nom_complet} — {bulletin.mois:02d}/{bulletin.annee} — {float(bulletin.net_a_payer):,.0f} FCFA")
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
        from core.models import log_audit
        log_audit(request, 'CREATE', 'PaiementPaie', str(bulletin.id),
                  f"Paiement salaire {bulletin.employe.nom_complet} — {bulletin.mois:02d}/{bulletin.annee} — {float(bulletin.net_a_payer):,.0f} FCFA")
        return Response(BulletinPaieSerializer(bulletin).data)

    @action(detail=True, methods=['post'])
    def annuler(self, request, pk=None):
        """Annule un bulletin de paie : extourne toutes ses écritures SYSCOHADA."""
        bulletin = self.get_object()
        if bulletin.statut == 'ANNULE':
            return Response({'error': 'Ce bulletin est déjà annulé.'}, status=status.HTTP_400_BAD_REQUEST)
        if bulletin.statut == 'BROUILLON':
            return Response(
                {'error': 'Un bulletin BROUILLON n\'a pas d\'écritures comptables. Supprimez-le directement.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        tenant = get_tenant(request)
        annuler_ecritures_paie(bulletin, tenant)
        bulletin.statut = 'ANNULE'
        bulletin.save()
        from core.models import log_audit
        log_audit(request, 'ANNULER', 'BulletinPaie', str(bulletin.id),
                  f"Annulation bulletin {bulletin.employe.nom_complet} — {bulletin.mois:02d}/{bulletin.annee} — {float(bulletin.net_a_payer):,.0f} FCFA")
        return Response(BulletinPaieSerializer(bulletin).data)

    @action(detail=True, methods=['get'])
    def pdf(self, request, pk=None):
        bulletin = self.get_object()
        from io import BytesIO
        try:
            from xhtml2pdf import pisa
        except ImportError:
            return HttpResponse('xhtml2pdf non installé.', status=500)

        context = {
            'bulletin':     bulletin,
            'employe':      bulletin.employe,
            'tenant':       bulletin.tenant,
            'regime':       getattr(bulletin.tenant, 'regime_paie', 'COMPLET'),
            'date_edition': timezone.now(),
            'nom_mois':     NOMS_MOIS.get(bulletin.mois, str(bulletin.mois)),
        }
        html_str = render_to_string('pdf/bulletin_paie.html', context)
        buffer = BytesIO()
        result = pisa.CreatePDF(html_str, dest=buffer, encoding='utf-8')
        if result.err:
            return HttpResponse('Erreur génération PDF.', status=500)

        filename = f"bulletin_{bulletin.employe.matricule}_{bulletin.mois:02d}_{bulletin.annee}.pdf"
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
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

    @action(detail=True, methods=['post'])
    def annuler(self, request, pk=None):
        avance = self.get_object()
        if avance.statut != 'EN_ATTENTE':
            return Response(
                {'error': 'Seule une avance EN_ATTENTE peut être annulée.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        tenant = get_tenant(request)
        annuler_ecriture_avance(avance, tenant)
        avance.statut = 'ANNULE'
        avance.save()
        from core.models import log_audit
        log_audit(request, 'CANCEL', 'AvanceSalaire', str(avance.id),
                  f"Annulation avance {avance.employe.nom_complet} — {float(avance.montant):,.0f} FCFA")
        return Response(AvanceSalaireSerializer(avance).data)


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
