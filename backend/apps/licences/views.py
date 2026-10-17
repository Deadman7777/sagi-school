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
                           'renouveler', 'confirmer_demande']:
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

    def destroy(self, request, *args, **kwargs):
        """Supprime DÉFINITIVEMENT l'école de cette licence et toutes ses données.

        Supprimer seulement la licence laissait l'école active en base (voir
        apps/tenants/suppression.py). Le nom exact doit être renvoyé dans
        `confirmation` : un clic égaré ne doit pas effacer une école.
        """
        from apps.dashboard.models import AuditLog
        from apps.tenants.suppression import supprimer_ecole
        licence = self.get_object()
        tenant = licence.tenant
        tenant_id = str(tenant.pk)
        confirmation = (request.data.get('confirmation')
                        or request.query_params.get('confirmation') or '').strip()
        if confirmation != tenant.nom.strip():
            return Response({'error': "Confirmation incorrecte : retapez exactement le nom de l'école."},
                            status=status.HTTP_400_BAD_REQUEST)
        bilan = supprimer_ecole(tenant)
        # Journal SANS école : celle-ci n'existe plus (log_audit rattacherait
        # l'entrée à l'école impersonée, effacée à l'instant).
        AuditLog.objects.create(
            tenant=None, utilisateur=str(request.user), action='DELETE', modele='Tenant',
            objet_id=tenant_id,
            description=f"Suppression définitive de l'école {bilan['ecole']} — {bilan['eleves']} élèves, "
                        f"{bilan['paiements']} paiements, {bilan['utilisateurs']} utilisateurs")
        return Response(bilan)

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
        from .renouvellement import prolonger
        licence = prolonger(self.get_object(), int(request.data.get('mois', 12)))
        return Response(LicenceSerializer(licence).data)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def alerte(self, request):
        """L'alerte de fin de licence de l'école courante — voir apps/licences/alertes.py.

        `?actualiser=1` relit tout de suite le cloud (installation locale) :
        c'est le bouton « J'ai renouvelé, actualiser ».
        """
        from .alertes import config, etat
        tenant = get_tenant(request)
        licence = Licence.objects.filter(tenant=tenant).select_related('tenant').first() if tenant else None
        if licence is None:
            return Response({'licence': None, 'alerte': False, 'phase': 'AUCUNE'})
        from apps.users.serializers import modules_utilisateur
        cfg = config(licence, forcer=request.query_params.get('actualiser') == '1')
        donnees = etat(licence, cfg=cfg)
        # Les modules de CET utilisateur (ceux du jeton) : l'écran les reprend
        # dès que la licence est renouvelée, sans reconnexion.
        donnees['modules'] = ([] if request.user.role == 'SUPER_ADMIN'
                              else modules_utilisateur(request.user, licence)[0])
        return Response(donnees)

    @action(detail=True, methods=['post'])
    def demander_renouvellement(self, request, pk=None):
        """Demande de renouvellement — enregistrée, puis courriel ou relais cloud.

        Voir apps/licences/renouvellement.py. `recue` ne vaut True que si
        HADY GESMAN a réellement la demande (courriel parti ou cloud qui en
        accuse réception) : l'écran ne doit plus jamais dire « envoyé » à tort.
        L'isolation tenant est assurée par get_queryset.
        """
        from .renouvellement import composer, demander, destinataire, formule_demandee
        licence = self.get_object()
        demande, recue = demander(licence, request.user, request.data.get('message') or '',
                                  formule=formule_demandee(licence, request.data))
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
            'licence': str(d.licence_id) if d.licence_id else None,
            'type_demande': d.type_demande, 'mois': d.mois, 'montant': d.montant,
            'moyen_paiement': d.moyen_paiement, 'reference_paiement': d.reference_paiement,
            'confirmee': d.confirmee,
        } for d in qs])

    @action(detail=False, methods=['post'], url_path=r'demandes-renouvellement/(?P<demande_id>[^/.]+)/confirmer',
            permission_classes=[IsSuperAdmin])
    def confirmer_demande(self, request, demande_id=None):
        """Paiement reçu : prolonge la licence de la formule demandée et clôt la demande.

        L'école voit son statut à jour à la consultation suivante (au plus
        quelques minutes ; en local, via `etat-distant`).
        """
        from .models import DemandeRenouvellement
        from .renouvellement import prolonger
        d = DemandeRenouvellement.objects.select_related('licence').filter(id=demande_id).first()
        if d is None:
            return Response({'error': 'Demande introuvable.'}, status=404)
        if d.licence is None:
            return Response({'error': "Cette école n'a pas de licence sur ce serveur : "
                                      "renouvelez-la depuis son installation."}, status=400)
        if d.confirmee:
            return Response({'error': 'Demande déjà confirmée.'}, status=400)
        try:
            mois = int(request.data.get('mois') or d.mois or 0)
        except (TypeError, ValueError):
            mois = 0
        if not 1 <= mois <= 36:
            return Response({'error': 'Durée invalide (1 à 36 mois).'}, status=400)
        licence = prolonger(d.licence, mois, d.type_demande or None)
        d.traitee, d.confirmee, d.traitee_le = True, True, timezone.now()
        d.save(update_fields=['traitee', 'confirmee', 'traitee_le', 'updated_at'])
        return Response({'confirmee': True, 'licence': LicenceSerializer(licence).data})

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

    @action(detail=False, methods=['get'], permission_classes=[IsSuperAdmin])
    def relances(self, request):
        """Échéances dans 7 jours ou moins (et expirées en sursis), relances faites."""
        from apps.prospects.models import ParametresFacturation
        from apps.prospects.messagerie import smtp_configure
        from .relances import tableau
        return Response({'lignes': tableau(),
                         'relances_auto': ParametresFacturation.actuels().relances_auto,
                         'smtp': smtp_configure()})

    @action(detail=True, methods=['post'], permission_classes=[IsSuperAdmin])
    def relancer(self, request, pk=None):
        """Envoie tout de suite la relance du palier courant (même déjà faite)."""
        from .relances import relancer
        r = relancer(self.get_object(), auteur=str(request.user))
        if not r.succes:
            return Response({'error': r.erreur}, status=400)
        return Response({'succes': True, 'destinataires': r.destinataires})

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
        """École + licence + exercice, tout ou rien (voir creation_ecole.py)."""
        from .creation_ecole import CreationEcoleErreur, creer_ecole
        try:
            tenant, licence = creer_ecole(request.data)
        except CreationEcoleErreur as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'tenant_id': str(tenant.id), 'nom': tenant.nom,
            'cle_licence': licence.cle_licence, 'type': licence.type,
            'date_fin': str(licence.date_fin),
        }, status=status.HTTP_201_CREATED)
