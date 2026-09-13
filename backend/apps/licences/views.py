from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.conf import settings
from django.utils import timezone
from core.permissions import IsSuperAdmin
from core.tenant import get_tenant
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
                           'destroy', 'creer_ecole', 'stats_globales',
                           'renouveler']:
            return [IsSuperAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'SUPER_ADMIN':
            return Licence.objects.select_related('tenant').all()
        tenant = get_tenant(self.request)
        if tenant:
            return Licence.objects.filter(tenant=tenant).select_related('tenant')
        return Licence.objects.none()

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def catalogue(self, request):
        """La grille tarifaire officielle, servie par le serveur.

        Les tarifs vivaient jusqu'ici en dur dans l'écran Licences, alors que
        les devis les lisent désormais dans `apps.licences.catalogue`. Deux
        sources finissent toujours par diverger — et ici la divergence se
        verrait sur une pièce signée.
        """
        from .catalogue import catalogue_public
        return Response(catalogue_public())

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

    @action(detail=True, methods=['post'])
    def demander_renouvellement(self, request, pk=None):
        """Demande de renouvellement — enregistrée, puis courriel ou relais cloud.

        Voir apps/licences/renouvellement.py. `recue` ne vaut True que si
        HADY GESMAN a réellement la demande (courriel parti ou cloud qui en
        accuse réception) : l'écran ne doit plus jamais dire « envoyé » à tort.
        L'isolation tenant est assurée par get_queryset.
        """
        from .renouvellement import composer, demander, destinataire
        licence = self.get_object()
        demande, recue = demander(licence, request.user, request.data.get('message') or '')
        sujet, corps = composer(demande)
        return Response({
            'recue':        recue,
            # Compatibilité avec les écrans déjà déployés.
            'envoye':       recue,
            'enregistree':  True,
            'reference':    str(demande.id),
            'origine':      demande.origine,
            'erreur':       demande.erreur if not recue else '',
            'destinataire': destinataire(),
            'sujet':        sujet,
            'corps':        corps,
        })

    @action(detail=False, methods=['get'], url_path='demandes-renouvellement',
            permission_classes=[IsSuperAdmin])
    def demandes_renouvellement(self, request):
        """Toutes les demandes reçues — y compris celles dont le courriel a échoué."""
        from .models import DemandeRenouvellement
        qs = DemandeRenouvellement.objects.all()[:200]
        return Response([{
            'id': str(d.id), 'created_at': d.created_at, 'ecole_nom': d.ecole_nom,
            'type_licence': d.type_licence, 'date_fin': d.date_fin,
            'demandeur': d.demandeur, 'email_demandeur': d.email_demandeur,
            'telephone': d.telephone, 'message': d.message,
            'origine': d.origine, 'origine_libelle': d.get_origine_display(),
            'courriel_envoye': d.courriel_envoye, 'erreur': d.erreur,
            'traitee': d.traitee, 'traitee_le': d.traitee_le,
        } for d in qs])

    @action(detail=False, methods=['post'], url_path=r'demandes-renouvellement/(?P<demande_id>[^/.]+)/traiter',
            permission_classes=[IsSuperAdmin])
    def traiter_demande(self, request, demande_id=None):
        from .models import DemandeRenouvellement
        d = DemandeRenouvellement.objects.filter(id=demande_id).first()
        if d is None:
            return Response({'error': 'Demande introuvable.'}, status=404)
        d.traitee = True
        d.traitee_le = timezone.now()
        d.save(update_fields=['traitee', 'traitee_le', 'updated_at'])
        return Response({'traitee': True})

    @action(detail=True, methods=['post'], permission_classes=[IsSuperAdmin])
    def suspendre(self, request, pk=None):
        licence = self.get_object()
        licence.statut = 'SUSPENDUE'
        licence.save()
        return Response(LicenceSerializer(licence).data)

    @action(detail=True, methods=['post'], permission_classes=[IsSuperAdmin])
    def activer(self, request, pk=None):
        licence = self.get_object()
        licence.statut = 'ACTIVE'
        licence.save()
        return Response(LicenceSerializer(licence).data)

    @action(detail=True, methods=['post'], permission_classes=[IsSuperAdmin])
    def changer_type(self, request, pk=None):
        licence = self.get_object()
        nouveau_type = request.data.get('type')
        if nouveau_type not in ['ESSAI', 'BASIC', 'PRO', 'AVANCE', 'TAXAWU_DAARA']:
            return Response({'error': 'Type invalide'}, status=400)
        licence.type = nouveau_type
        licence.date_debut = timezone.now().date()
        licence.save()
        return Response(LicenceSerializer(licence).data)

    @action(detail=False, methods=['get'])
    def stats_globales(self, request):
        total_tenants = Tenant.objects.count()
        actives       = Licence.objects.filter(statut='ACTIVE').count()
        expirees      = Licence.objects.filter(statut='EXPIREE').count()
        essai         = Licence.objects.filter(statut='ESSAI').count()
        total_eleves  = Eleve.objects.count()

        # Annuel = tarif mensuel × 12 − 10% (aligné sur TARIFS_MENSUEL du frontend)
        TARIFS  = {'ESSAI': 0, 'BASIC': 270000, 'PRO': 540000, 'AVANCE': 972000, 'TAXAWU_DAARA': 216000}
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
            code_etablissement=data.get('code_etablissement', 'ETB'),
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
