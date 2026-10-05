"""API du module multi-activité : activités, factures, règlements, résultats.

Voir apps/comptabilite/activites.py pour les règles comptables.
"""
from io import BytesIO

from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.serializers import TenantModelSerializer
from core.tenant import get_tenant

from . import activites as services
from .models import Activite, FactureActivite, ReglementFacture
from .views import get_exercice, get_exercice_ecriture


class ActiviteSerializer(TenantModelSerializer):
    nb_factures = serializers.SerializerMethodField()

    class Meta:
        model = Activite
        fields = '__all__'
        extra_kwargs = {'tenant': {'required': False, 'read_only': True}}

    def get_nb_factures(self, obj):
        return obj.factures.count()

    def validate(self, attrs):
        for champ, classe in (('compte_produit', '7'), ('compte_charge', '6'), ('compte_client', '41')):
            valeur = attrs.get(champ)
            if valeur and not str(valeur).startswith(classe):
                raise serializers.ValidationError(
                    {champ: f"Compte attendu en classe {classe} (SYSCOHADA)."})
        return attrs


class ActiviteViewSet(viewsets.ModelViewSet):
    """Activités de l'établissement. GET modeles/ : modèles proposés."""
    serializer_class = ActiviteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        tenant = get_tenant(self.request)
        services.activite_principale(tenant)          # toujours présente
        return Activite.objects.filter(tenant=tenant)

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        est_principale = serializer.validated_data.get('est_principale', False)
        act = serializer.save(tenant=tenant)
        if est_principale:
            Activite.objects.filter(tenant=tenant).exclude(id=act.id).update(est_principale=False)

    def perform_update(self, serializer):
        act = serializer.save()
        if act.est_principale:
            Activite.objects.filter(tenant=act.tenant).exclude(id=act.id).update(est_principale=False)
        elif not Activite.objects.filter(tenant=act.tenant, est_principale=True).exists():
            act.est_principale = True                   # il en faut toujours une
            act.save(update_fields=['est_principale'])

    def destroy(self, request, *args, **kwargs):
        act = self.get_object()
        if act.est_principale:
            return Response({'error': "L'activité principale ne se supprime pas."}, status=409)
        if act.ecritures.exists() or act.factures.exists():
            return Response({'error': "Cette activité a déjà des écritures : désactivez-la "
                                      "plutôt que de la supprimer."}, status=409)
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['get'])
    def modeles(self, request):
        return Response([{'type_activite': k, **v} for k, v in services.MODELES_ACTIVITES.items()])


class FactureActiviteSerializer(TenantModelSerializer):
    activite_libelle = serializers.CharField(source='activite.libelle', read_only=True)
    reste_a_regler = serializers.ReadOnlyField()
    reglements = serializers.SerializerMethodField()

    class Meta:
        model = FactureActivite
        fields = '__all__'
        read_only_fields = ('tenant', 'numero', 'montant_ht', 'taux_tva', 'montant_tva',
                            'montant_ttc', 'montant_regle', 'statut', 'date_validation',
                            'exercice')

    def get_reglements(self, obj):
        return [{'id': str(r.id), 'date': str(r.date_reglement), 'montant': float(r.montant),
                 'mode': r.mode, 'reference': r.reference, 'no_piece': r.no_piece,
                 'annule': r.annule} for r in obj.reglements.all()]

    def validate_lignes(self, lignes):
        if not isinstance(lignes, list) or not lignes:
            raise serializers.ValidationError('Au moins une ligne de facture.')
        for i, l in enumerate(lignes, start=1):
            if not str(l.get('libelle') or '').strip():
                raise serializers.ValidationError(f'Ligne {i} : libellé manquant.')
            try:
                if float(l.get('quantite') or 0) <= 0 or float(l.get('prix_unitaire') or 0) < 0:
                    raise ValueError
            except (TypeError, ValueError):
                raise serializers.ValidationError(f'Ligne {i} : quantité ou prix invalide.')
        return lignes


class FactureActiviteViewSet(viewsets.ModelViewSet):
    """Factures d'activité.

    POST/PATCH : brouillon (montants recalculés depuis les lignes).
    POST {id}/valider/ · {id}/regler/ · {id}/annuler/ · GET {id}/pdf/
    POST reglements/{id}/annuler/ : extourne d'un règlement.
    """
    serializer_class = FactureActiviteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        tenant = get_tenant(self.request)
        qs = (FactureActivite.objects.filter(tenant=tenant)
              .select_related('activite', 'exercice').prefetch_related('reglements'))
        p = self.request.query_params
        if p.get('exercice'):
            qs = qs.filter(exercice_id=p['exercice'])
        elif self.action == 'list':
            ex = get_exercice(tenant)
            qs = qs.filter(exercice=ex) if ex else qs.none()
        if p.get('activite'):
            qs = qs.filter(activite_id=p['activite'])
        if p.get('statut'):
            qs = qs.filter(statut=p['statut'])
        return qs

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        ex = get_exercice_ecriture(tenant, self.request)
        if ex is None:
            raise serializers.ValidationError({'exercice': 'Aucun exercice ouvert.'})
        facture = serializer.save(tenant=tenant, exercice=ex)
        services.calculer_montants(facture)
        facture.save()

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)

    def update(self, request, *args, **kwargs):
        if self.get_object().statut != 'BROUILLON':
            return Response({'error': "Une facture validée ne se modifie plus : annulez-la "
                                      "et émettez-en une nouvelle."}, status=409)
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        facture = serializer.save()
        services.calculer_montants(facture)
        facture.save()

    def destroy(self, request, *args, **kwargs):
        facture = self.get_object()
        if facture.statut != 'BROUILLON':
            return Response({'error': 'Une facture validée ne se supprime pas : annulez-la.'},
                            status=409)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def valider(self, request, pk=None):
        try:
            facture = services.valider_facture(self.get_object())
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
        return Response(self.get_serializer(facture).data)

    @action(detail=True, methods=['post'])
    def regler(self, request, pk=None):
        facture = self.get_object()
        d = request.data
        try:
            exercice = get_exercice_ecriture(facture.tenant, request) if d.get('exercice_id') else None
            services.regler_facture(facture, d.get('montant') or facture.reste_a_regler,
                                    d.get('date') or str(timezone.localdate()),
                                    d.get('mode') or 'ESPECE', d.get('reference') or '', exercice)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
        facture.refresh_from_db()
        return Response(self.get_serializer(facture).data)

    @action(detail=True, methods=['post'])
    def annuler(self, request, pk=None):
        try:
            facture = services.annuler_facture(self.get_object(), request.data.get('motif', ''))
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
        if facture is None:
            return Response(status=204)
        return Response(self.get_serializer(facture).data)

    @action(detail=False, methods=['post'], url_path=r'reglements/(?P<reglement_id>[^/.]+)/annuler')
    def annuler_reglement(self, request, reglement_id=None):
        reg = ReglementFacture.objects.filter(tenant=get_tenant(request), id=reglement_id).first()
        if reg is None:
            return Response({'error': 'Règlement introuvable.'}, status=404)
        try:
            services.annuler_reglement(reg)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
        return Response(self.get_serializer(reg.facture).data)

    @action(detail=True, methods=['get'])
    def pdf(self, request, pk=None):
        from xhtml2pdf import pisa
        facture = self.get_object()
        lignes = [{**l, 'montant': float(l.get('quantite') or 0) * float(l.get('prix_unitaire') or 0)}
                  for l in facture.lignes]
        html = render_to_string('pdf/facture_activite.html', {
            'facture': facture, 'tenant': facture.tenant, 'lignes': lignes,
            'date_edition': timezone.localdate()})
        tampon = BytesIO()
        if pisa.CreatePDF(html, dest=tampon, encoding='utf-8').err:
            return HttpResponse('Erreur génération PDF.', status=500)
        reponse = HttpResponse(tampon.getvalue(), content_type='application/pdf')
        reponse['Content-Disposition'] = (
            f'inline; filename="facture_{facture.numero or "brouillon"}.pdf"')
        return reponse


class ResultatsActivitesView(APIView):
    """GET /comptabilite/activites-resultats/?exercice= — résultat par activité."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = get_tenant(request)
        exercice = get_exercice(tenant, request)
        if exercice is None:
            return Response({'activites': []})
        return Response({'exercice': exercice.annee_scolaire,
                         **services.resultats_par_activite(tenant, exercice)})
