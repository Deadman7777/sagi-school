"""API : exercices multiples, continuité (à-nouveaux), écritures diverses,
import de balance, dossier ETAFI. Règles : exercices.py, etats.py, etafi.py."""
import datetime

from django.http import HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.paiements.models import Exercice
from core.tenant import get_tenant

from . import etafi, exercices
from .models import EtafiArchive, JournalEntry
from .views import get_exercice, get_exercice_ecriture


def _exercice(tenant, ex_id):
    return Exercice.objects.filter(tenant=tenant, id=ex_id).first() if ex_id else None


class SituationExercicesView(APIView):
    """GET — tous les exercices, leur état et la continuité de l'un à l'autre."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({'exercices': exercices.situation_exercices(get_tenant(request))})


class ANouveauxView(APIView):
    """À-nouveaux d'un exercice vers le suivant.

    GET ?source=<id>&cible=<id> — aperçu (lignes, trésorerie, écarts de
    continuité si déjà générés). POST {source, cible?} — (re)génération.
    """
    permission_classes = [IsAuthenticated]

    def _couple(self, request, donnees):
        tenant = get_tenant(request)
        source = _exercice(tenant, donnees.get('source'))
        if source is None:
            return None, None, Response({'error': 'Exercice source introuvable.'}, status=404)
        cible = _exercice(tenant, donnees.get('cible')) or exercices.exercice_suivant(source)
        if cible is None:
            return None, None, Response({'error': "Aucun exercice après celui-ci : créez d'abord "
                                                  "l'exercice suivant."}, status=400)
        return source, cible, None

    def get(self, request):
        source, cible, err = self._couple(request, request.query_params)
        if err:
            return err
        calcul = exercices.calculer_a_nouveaux(source, cible)
        deja = exercices.a_nouveaux_existants(cible).exists()
        return Response({
            'source': source.annee_scolaire, 'cible': cible.annee_scolaire,
            'source_cloture': source.cloture, 'cible_cloture': cible.cloture,
            'lignes': [{**l, 'debit': float(l['debit']), 'credit': float(l['credit'])}
                       for l in calcul['lignes']],
            'tresorerie': {k: float(v) for k, v in calcul['tresorerie'].items()},
            'reliquats_reportes': float(calcul['reliquats_reportes']),
            'deja_generes': deja,
            'ecarts': exercices.controle_continuite(source, cible) if deja else [],
        })

    def post(self, request):
        source, cible, err = self._couple(request, request.data)
        if err:
            return err
        try:
            res = exercices.generer_a_nouveaux(source, cible)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
        from core.models import log_audit
        log_audit(request, 'CREATE', 'ANouveaux', str(cible.id),
                  f"À-nouveaux {source.annee_scolaire} → {cible.annee_scolaire}")
        return Response(res, status=201)


class EcrituresDiversesView(APIView):
    """Écritures diverses (OD) : GET ?exercice= · POST {exercice_id?, date,
    libelle, lignes} · POST <no_piece>/extourner/."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = get_tenant(request)
        exercice = get_exercice(tenant, request)
        if exercice is None:
            return Response({'pieces': []})
        pieces = {}
        for e in (JournalEntry.objects.filter(tenant=tenant, exercice=exercice,
                                              source__in=(exercices.SOURCE_OD, exercices.SOURCE_ANNUL_OD,
                                                          exercices.SOURCE_BALANCE))
                  .select_related('activite').order_by('date_ecriture', 'no_piece', 'ordre')):
            p = pieces.setdefault(e.no_piece, {'no_piece': e.no_piece, 'date': str(e.date_ecriture),
                                               'source': e.source, 'lignes': [], 'total': 0.0})
            p['lignes'].append({'no_compte': e.no_compte, 'libelle': e.libelle, 'debit': float(e.debit),
                                'credit': float(e.credit),
                                'activite': e.activite.libelle if e.activite_id else ''})
            p['total'] += float(e.debit)
        extournees = {p[1:] for p in pieces if p.startswith('X')}
        for p in pieces.values():
            p['extournee'] = p['no_piece'] in extournees
        return Response({'exercice': exercice.annee_scolaire, 'cloture': exercice.cloture,
                         'pieces': list(pieces.values())})

    def post(self, request, no_piece=None):
        tenant = get_tenant(request)
        try:
            if no_piece:
                return Response({'no_piece': exercices.extourner_ecriture_diverse(tenant, no_piece)},
                                status=201)
            exercice = get_exercice_ecriture(tenant, request)
            if exercice is None:
                return Response({'error': 'Aucun exercice ouvert.'}, status=400)
            date = request.data.get('date') or str(datetime.date.today())
            if not (str(exercice.date_debut) <= date <= str(exercice.date_fin)):
                return Response({'error': f"La date doit appartenir à l'exercice {exercice.annee_scolaire} "
                                          f"({exercice.date_debut:%d/%m/%Y} – {exercice.date_fin:%d/%m/%Y})."},
                                status=400)
            no = exercices.saisir_ecriture_diverse(tenant, exercice, date,
                                                    request.data.get('libelle') or 'Écriture diverse',
                                                    request.data.get('lignes') or [])
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
        from core.models import log_audit
        log_audit(request, 'CREATE', 'EcritureDiverse', no, f"OD {no} — {exercice.annee_scolaire}")
        return Response({'no_piece': no}, status=201)


class ImportBalanceView(APIView):
    """POST multipart : fichier (.xlsx/.csv), exercice_id, nature
    (OUVERTURE|CLOTURE), apercu=1 pour contrôler sans rien écrire."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        tenant = get_tenant(request)
        try:
            exercice = get_exercice_ecriture(tenant, request)
            if exercice is None:
                return Response({'error': 'Aucun exercice ouvert.'}, status=400)
            if 'fichier' in request.FILES:
                lignes = exercices.lire_balance(request.FILES['fichier'])
            else:
                lignes = request.data.get('lignes') or []
            nature = (request.data.get('nature') or 'CLOTURE').upper()
            propres = exercices.verifier_lignes(lignes)
            total_d = float(sum(l['debit'] for l in propres))
            if str(request.data.get('apercu', '')).lower() in ('1', 'true', 'oui'):
                return Response({'apercu': True, 'exercice': exercice.annee_scolaire, 'nature': nature,
                                 'nb_lignes': len(propres), 'total_debit': total_d,
                                 'lignes': [{**l, 'debit': float(l['debit']), 'credit': float(l['credit'])}
                                            for l in propres[:500]]})
            res = exercices.importer_balance(exercice, propres, nature)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
        from core.models import log_audit
        log_audit(request, 'CREATE', 'ImportBalance', str(exercice.id),
                  f"Balance {nature.lower()} importée — {exercice.annee_scolaire} ({res['nb_lignes']} lignes)")
        return Response(res, status=201)


# ── ETAFI ─────────────────────────────────────────────────────────────────────
def _archive_meta(a):
    return {'id': str(a.id), 'version': a.version, 'statut': a.statut, 'systeme': a.systeme,
            'taille': a.taille, 'empreinte': a.empreinte, 'resume': a.resume,
            'observations': a.observations, 'cree_le': a.created_at.isoformat(),
            'genere_par': (f"{a.genere_par.prenom} {a.genere_par.nom}".strip()
                           if a.genere_par_id else '')}


class EtafiView(APIView):
    """GET ?exercice=&systeme= — le dossier ETAFI en données (aperçu à l'écran),
    les documents disponibles et les archives de l'exercice."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = get_tenant(request)
        exercice = get_exercice(tenant, request)
        if exercice is None:
            return Response({'error': 'Aucun exercice.'}, status=404)
        systeme = request.query_params.get('systeme') or None
        d = etafi.construire(tenant, exercice, systeme)
        d.pop('profil', None)
        return Response({
            'exercice': {'id': str(exercice.id), 'annee_scolaire': exercice.annee_scolaire,
                         'cloture': exercice.cloture},
            'systeme_conseille': etafi.systeme_par_defaut(tenant, exercice),
            'documents': [{'code': c, 'fichier': f, 'titre': t} for c, f, t in etafi.documents(d['systeme'])],
            'archives': [_archive_meta(a) for a in EtafiArchive.objects.filter(tenant=tenant, exercice=exercice)
                         .select_related('genere_par')],
            **d,
        })


class EtafiDocumentView(APIView):
    """GET <code>/?exercice=&systeme= — un document du dossier, en PDF."""
    permission_classes = [IsAuthenticated]

    def get(self, request, code):
        tenant = get_tenant(request)
        exercice = get_exercice(tenant, request)
        if exercice is None:
            return HttpResponse('Aucun exercice.', status=404)
        d = etafi.construire(tenant, exercice, request.query_params.get('systeme') or None)
        doc = next(((c, f) for c, f, _t in etafi.documents(d['systeme']) if c == code), None)
        if doc is None:
            return HttpResponse('Document inconnu.', status=404)
        pdf = etafi.rendre_pdf(code, tenant, exercice, d, 'DEFINITIF' if exercice.cloture else 'PROVISOIRE')
        r = HttpResponse(pdf, content_type='application/pdf')
        r['Content-Disposition'] = f'inline; filename="ETAFI_{exercice.annee_scolaire}_{doc[1]}.pdf"'
        return r


class EtafiArchiverView(APIView):
    """POST {exercice_id?, systeme?, observations?} — génère le dossier complet
    (ZIP) et l'archive. Une nouvelle version à chaque génération."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        tenant = get_tenant(request)
        exercice = _exercice(tenant, request.data.get('exercice_id')) or get_exercice(tenant)
        if exercice is None:
            return Response({'error': 'Aucun exercice.'}, status=404)
        a = etafi.archiver(tenant, exercice, request.user if request.user.is_authenticated else None,
                           request.data.get('systeme') or None, request.data.get('observations', ''))
        from core.models import log_audit
        log_audit(request, 'CREATE', 'EtafiArchive', str(a.id),
                  f"ETAFI {exercice.annee_scolaire} v{a.version} ({a.statut})")
        return Response(_archive_meta(a), status=201)


class EtafiArchiveView(APIView):
    """GET <id>/ — télécharge le ZIP archivé · DELETE <id>/ — supprime une
    version PROVISOIRE (un dossier définitif ne se supprime pas)."""
    permission_classes = [IsAuthenticated]

    def _archive(self, request, pk):
        return EtafiArchive.objects.filter(tenant=get_tenant(request), id=pk).select_related('exercice').first()

    def get(self, request, pk):
        a = self._archive(request, pk)
        if a is None:
            return HttpResponse('Archive introuvable.', status=404)
        r = HttpResponse(bytes(a.contenu_zip), content_type='application/zip')
        r['Content-Disposition'] = (f'attachment; filename="ETAFI_{a.exercice.annee_scolaire}'
                                    f'_v{a.version}_{a.statut.lower()}.zip"')
        r['X-Empreinte-SHA256'] = a.empreinte
        return r

    def delete(self, request, pk):
        a = self._archive(request, pk)
        if a is None:
            return Response({'error': 'Archive introuvable.'}, status=404)
        if a.statut == 'DEFINITIF':
            return Response({'error': 'Un dossier définitif ne se supprime pas.'}, status=409)
        a.delete()
        return Response(status=204)
