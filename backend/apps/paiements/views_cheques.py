"""Registre des chèques reçus (voir apps.paiements.cheques)."""
from django.db.models import Count, Prefetch, Q, Sum
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import log_audit
from core.tenant import get_tenant

from . import cheques as svc
from .models import AffectationCheque, ChequeRecu
from .serializers import ChequeRecuSerializer


class ChequeRecuViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                        mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Liste, détail et complément (numéro, banque, tireur, date d'émission,
    observations). Le cycle passe par les actions remettre / encaisser /
    impaye, qui écrivent au journal."""
    serializer_class   = ChequeRecuSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        tenant = get_tenant(self.request)
        if not tenant:
            return ChequeRecu.objects.none()
        qs = (ChequeRecu.objects.filter(tenant=tenant)
              .select_related('exercice', 'recu_par', 'remis_par', 'encaisse_par', 'impaye_par')
              .prefetch_related(Prefetch(
                  'affectations',
                  queryset=AffectationCheque.objects.select_related('paiement', 'paiement__eleve'))))
        p = self.request.query_params
        if statut := p.get('statut'):
            qs = qs.filter(statut__in=statut.split(','))
        if exercice := p.get('exercice'):
            qs = qs.filter(exercice_id=exercice)
        if q := (p.get('q') or '').strip():
            qs = qs.filter(Q(numero__icontains=q) | Q(banque__icontains=q) | Q(tireur__icontains=q)
                           | Q(bordereau__icontains=q)
                           | Q(affectations__paiement__eleve__nom_complet__icontains=q)
                           | Q(affectations__paiement__no_piece__icontains=q)).distinct()
        return qs

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        totaux = {r['statut']: {'nb': r['nb'], 'montant': float(r['m'] or 0)}
                  for r in ChequeRecu.objects.filter(id__in=qs.values('id')).values('statut').annotate(nb=Count('id'), m=Sum('montant'))}
        return Response({'results': self.get_serializer(qs, many=True).data, 'totaux': totaux})

    def _selection(self, request):
        ids = request.data.get('ids') or []
        cheques = list(self.get_queryset().filter(id__in=ids))
        if len(cheques) != len(set(ids)):
            raise ValueError("Chèque introuvable.")
        return cheques

    @action(detail=False, methods=['post'])
    def remettre(self, request):
        """Remise d'un lot de chèques en banque (bordereau)."""
        try:
            cheques = self._selection(request)
            no_piece = svc.remettre_en_banque(cheques, request.data.get('date'),
                                              (request.data.get('bordereau') or '').strip(),
                                              request.user)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        total = sum(float(c.montant) for c in cheques)
        log_audit(request, 'UPDATE', 'ChequeRecu', no_piece,
                  f"Remise en banque {no_piece} — {len(cheques)} chèque(s), {total:,.0f} FCFA")
        return Response({'no_piece': no_piece, 'nb': len(cheques), 'total': total})

    @action(detail=False, methods=['post'])
    def encaisser(self, request):
        """Crédit constaté sur le relevé bancaire."""
        try:
            cheques = self._selection(request)
            svc.confirmer_encaissement(cheques, request.data.get('date'), request.user)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        log_audit(request, 'UPDATE', 'ChequeRecu', '',
                  f"Encaissement confirmé — {len(cheques)} chèque(s)")
        return Response({'nb': len(cheques)})

    @action(detail=True, methods=['post'])
    def impaye(self, request, pk=None):
        """Chèque rejeté : retour banque, reçus annulés, la famille redoit."""
        cheque = self.get_object()
        motif = (request.data.get('motif') or '').strip()
        if not motif:
            return Response({'error': "Indiquez le motif du rejet (provision insuffisante…)."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            r = svc.declarer_impaye(cheque, request.data.get('date'), motif, request.user)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        log_audit(request, 'ANNULER', 'ChequeRecu', str(cheque.id),
                  f"Chèque impayé n° {cheque.numero or '?'} {cheque.banque} — {float(cheque.montant):,.0f} FCFA "
                  f"({motif}) — reçus annulés : {', '.join(x['no_piece'] for x in r['recus_annules']) or 'aucun'}")
        return Response(r)
