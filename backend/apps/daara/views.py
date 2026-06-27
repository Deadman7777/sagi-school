import os
from io import BytesIO

from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string

from core.tenant import get_tenant
from .models import Sourate, Subdivision, NiveauDaara, ParcoursNongo, SuiviQuotidien
from .serializers import (SourateSerializer, SubdivisionSerializer,
                          NiveauDaaraSerializer, ParcoursNongoSerializer,
                          SuiviQuotidienSerializer)

# Niveaux fournis par défaut à chaque Daara (configurables ensuite).
NIVEAUX_DEFAUT = [
    {'nom_fr': 'Idjie (alphabet arabe)', 'nom_ar': 'الهجائية', 'categorie': 'IDJIE',        'ordre': 0},
    {'nom_fr': 'Mémorisation',           'nom_ar': 'الحفظ',     'categorie': 'MEMORISATION', 'ordre': 1},
    {'nom_fr': 'Révision / Consolidation','nom_ar': 'المراجعة', 'categorie': 'AUTRE',        'ordre': 2},
]


# ───────────────────────── Référence (lecture seule, globale) ─────────────────────────

class SourateViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class   = SourateSerializer
    permission_classes = [IsAuthenticated]
    queryset           = Sourate.objects.all()
    pagination_class   = None


class SubdivisionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class   = SubdivisionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = None

    def get_queryset(self):
        qs = Subdivision.objects.select_related('sourate_debut').all()
        riwaya = self.request.query_params.get('riwaya')
        type_  = self.request.query_params.get('type')
        if riwaya:
            qs = qs.filter(riwaya=riwaya)
        if type_:
            qs = qs.filter(type=type_)
        return qs


# ───────────────────────── Suivi (multi-tenant) ─────────────────────────

class NiveauDaaraViewSet(viewsets.ModelViewSet):
    serializer_class   = NiveauDaaraSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = None

    def get_queryset(self):
        tenant = get_tenant(self.request)
        if tenant and not NiveauDaara.objects.filter(tenant=tenant).exists():
            NiveauDaara.objects.bulk_create(
                [NiveauDaara(tenant=tenant, **d) for d in NIVEAUX_DEFAUT]
            )
        return NiveauDaara.objects.filter(tenant=tenant)

    def perform_create(self, serializer):
        serializer.save(tenant=get_tenant(self.request))


class ParcoursNongoViewSet(viewsets.ModelViewSet):
    serializer_class   = ParcoursNongoSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = None

    def get_queryset(self):
        qs = ParcoursNongo.objects.filter(
            tenant=get_tenant(self.request)
        ).select_related('eleve', 'niveau')
        eleve = self.request.query_params.get('eleve')
        if eleve:
            qs = qs.filter(eleve_id=eleve)
        return qs

    def perform_create(self, serializer):
        serializer.save(tenant=get_tenant(self.request))


class SuiviQuotidienViewSet(viewsets.ModelViewSet):
    serializer_class   = SuiviQuotidienSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = None

    def get_queryset(self):
        qs = SuiviQuotidien.objects.filter(
            tenant=get_tenant(self.request)
        ).select_related('sourate_debut', 'sourate_fin')
        parcours = self.request.query_params.get('parcours')
        if parcours:
            qs = qs.filter(parcours_id=parcours)
        return qs

    def perform_create(self, serializer):
        serializer.save(tenant=get_tenant(self.request))


# ───────────────────────── Progression (calculée) ─────────────────────────

def _offsets(riwaya):
    """index global cumulé de début de chaque sourate (numero -> offset versets avant elle)."""
    offset, cumul = {}, 0
    for s in Sourate.objects.all().order_by('numero'):
        offset[s.numero] = cumul
        cumul += s.nb_versets(riwaya)
    return offset, cumul


def _merge(intervals):
    """Union d'intervalles [debut, fin] inclusifs ; renvoie le nombre de versets distincts."""
    if not intervals:
        return 0, []
    intervals = sorted(intervals)
    fusion = [list(intervals[0])]
    for d, f in intervals[1:]:
        if d <= fusion[-1][1] + 1:
            fusion[-1][1] = max(fusion[-1][1], f)
        else:
            fusion.append([d, f])
    total = sum(f - d + 1 for d, f in fusion)
    return total, fusion


def compute_progression(parcours):
    """% mémorisé (versets distincts couverts / total riwaaya) + couverture par Juz."""
    riwaya = parcours.riwaya
    offset, total = _offsets(riwaya)

    intervals = []
    for s in parcours.suivis.select_related('sourate_debut', 'sourate_fin').all():
        if not s.sourate_debut_id or not s.sourate_fin_id:
            continue
        g1 = offset[s.sourate_debut.numero] + s.verset_debut
        g2 = offset[s.sourate_fin.numero] + s.verset_fin
        intervals.append((min(g1, g2), max(g1, g2)))

    couverts, fusion = _merge(intervals)
    pct = round(100 * couverts / total, 1) if total else 0

    juzs = list(Subdivision.objects.filter(riwaya=riwaya, type='JUZ')
                .select_related('sourate_debut').order_by('numero'))
    bornes = [offset[j.sourate_debut.numero] + j.verset_debut for j in juzs]
    par_juz = []
    for i, j in enumerate(juzs):
        debut = bornes[i]
        fin   = (bornes[i + 1] - 1) if i + 1 < len(bornes) else total
        taille = fin - debut + 1
        couv = sum(max(0, min(f, fin) - max(d, debut) + 1) for d, f in fusion)
        par_juz.append({'juz': j.numero, 'pct': round(100 * couv / taille, 0) if taille else 0})

    return {
        'parcours': str(parcours.id),
        'riwaya': riwaya,
        'total_versets': total,
        'versets_memorises': couverts,
        'pct': pct,
        'nb_suivis': parcours.suivis.count(),
        'par_juz': par_juz,
    }


class ProgressionView(APIView):
    """GET ?parcours=<id> → progression de mémorisation d'un NONGO."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = get_tenant(request)
        parcours_id = request.query_params.get('parcours')
        if not parcours_id:
            return Response({'detail': 'Paramètre parcours requis.'}, status=400)
        try:
            parcours = ParcoursNongo.objects.get(id=parcours_id, tenant=tenant)
        except ParcoursNongo.DoesNotExist:
            return Response({'detail': 'Parcours introuvable.'}, status=404)
        return Response(compute_progression(parcours))


# ───────────────────────── Rapport parent (PDF bilingue AR/FR) ─────────────────────────

FONT_DIR = os.path.join(settings.BASE_DIR, 'templates', 'pdf', 'fonts')


def shape_ar(text):
    """Pré-forme l'arabe (ligatures + ordre visuel RTL) pour xhtml2pdf/ReportLab,
    qui ne savent ni façonner ni inverser. Échoue en douceur sur le texte brut."""
    if not text:
        return ''
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


def _font_link_callback(uri, rel):
    """Résout url('xxx.ttf') du @font-face vers le fichier embarqué."""
    if uri.endswith('.ttf'):
        return os.path.join(FONT_DIR, os.path.basename(uri))
    return uri


class RapportParentPDFView(APIView):
    """GET /rapport-pdf/<parcours_id>/ → rapport de progression bilingue (PDF)."""
    permission_classes = [IsAuthenticated]

    def get(self, request, parcours_id):
        tenant = get_tenant(request)
        try:
            parcours = ParcoursNongo.objects.select_related('eleve', 'niveau').get(
                id=parcours_id, tenant=tenant)
        except ParcoursNongo.DoesNotExist:
            return HttpResponse('Parcours introuvable', status=404)

        prog = compute_progression(parcours)

        suivis = []
        for s in parcours.suivis.select_related('sourate_debut', 'sourate_fin')[:25]:
            suivis.append({
                'date': s.date,
                'deb_fr': s.sourate_debut.nom_fr if s.sourate_debut_id else '—',
                'deb_ar': shape_ar(s.sourate_debut.nom_ar) if s.sourate_debut_id else '',
                'vd': s.verset_debut,
                'fin_fr': s.sourate_fin.nom_fr if s.sourate_fin_id else '—',
                'fin_ar': shape_ar(s.sourate_fin.nom_ar) if s.sourate_fin_id else '',
                'vf': s.verset_fin,
                'qualite': s.get_qualite_display(),
                'present': s.present,
                'observation': s.observation,
            })

        context = {
            'ecole': tenant.nom if tenant else '',
            'eleve': parcours.eleve.nom_complet,
            'riwaya': parcours.riwaya,
            'niveau_fr': parcours.niveau.nom_fr if parcours.niveau_id else '—',
            'niveau_ar': shape_ar(parcours.niveau.nom_ar) if parcours.niveau_id else '',
            'date_debut': parcours.date_debut,
            'date_sortie': parcours.date_sortie,
            'statut': parcours.get_statut_display(),
            'prog': prog,
            'suivis': suivis,
            'titre_ar': shape_ar('تقرير حفظ القرآن الكريم'),
            'sous_titre_ar': shape_ar('متابعة النونغو'),
            'ar': {k: shape_ar(v) for k, v in {
                'infos': 'المعلومات', 'riwaya': 'الرواية', 'niveau': 'المستوى',
                'statut': 'الحالة', 'progression': 'التقدّم', 'memorise': 'محفوظ',
                'juz': 'جزء', 'suivi': 'المتابعة اليومية', 'portion': 'المقدار',
            }.items()},
            'font_body': 'DejaVuSans.ttf',
            'font_ar':   'KacstOne.ttf',
        }

        html_str = render_to_string('pdf/rapport_daara.html', context)
        buffer = BytesIO()
        try:
            from xhtml2pdf import pisa
            result = pisa.CreatePDF(html_str, dest=buffer, encoding='utf-8',
                                    link_callback=_font_link_callback)
            if result.err:
                return HttpResponse('Erreur génération rapport PDF.', status=500)
        except Exception as e:
            return HttpResponse(f'Erreur PDF : {e}', status=500)

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="rapport_{parcours.eleve.nom_complet}.pdf"'
        return response
