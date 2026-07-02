"""Génération PDF du module GMRF (fiche + tableau d'amortissement / suivi NATT)."""
from io import BytesIO

from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from core.tenant import get_tenant
from apps.paiements.models import Exercice
from .models import Pret, NattCycle
from .views import _pret_to_dict, _cycle_to_dict, _echeance_to_dict, _cotis_to_dict


def _exercice(tenant):
    return Exercice.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()


def _render_pdf(template, context, filename):
    try:
        from xhtml2pdf import pisa
    except ImportError:
        return HttpResponse('xhtml2pdf non installé', status=500)
    html_str = render_to_string(template, context)
    buffer = BytesIO()
    result = pisa.CreatePDF(html_str, dest=buffer, encoding='utf-8')
    if result.err:
        return HttpResponse('Erreur génération PDF.', status=500)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


class PretPDFView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        tenant = get_tenant(request)
        try:
            pret = Pret.objects.prefetch_related('echeances').get(tenant=tenant, id=pk)
        except Pret.DoesNotExist:
            return HttpResponse('Prêt introuvable', status=404)
        data = _pret_to_dict(pret, detail=True)
        ctx = {
            'tenant': tenant, 'exercice': _exercice(tenant),
            'date_edition': timezone.now(), 'pret': data,
            'echeances': data['echeances'],
        }
        return _render_pdf('pdf/gmrf_pret.html', ctx, f"pret_{pret.reference}.pdf")


class NattPDFView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        tenant = get_tenant(request)
        try:
            cycle = NattCycle.objects.prefetch_related('cotisations', 'reception').get(tenant=tenant, id=pk)
        except NattCycle.DoesNotExist:
            return HttpResponse('NATT introuvable', status=404)
        data = _cycle_to_dict(cycle, detail=True)
        ctx = {
            'tenant': tenant, 'exercice': _exercice(tenant),
            'date_edition': timezone.now(), 'natt': data,
            'cotisations': data['cotisations'], 'reception': data['reception'],
        }
        return _render_pdf('pdf/gmrf_natt.html', ctx, f"natt_{cycle.reference}.pdf")
