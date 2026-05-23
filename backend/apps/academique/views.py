from rest_framework import viewsets, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from django.db.models import Avg, Max, Min, Count
from .models import NiveauScolaire, Classe, TypeEvaluation, Matiere, Evaluation, Note, BulletinCache
from .serializers import (NiveauScolaireSerializer, ClasseSerializer,
                           TypeEvaluationSerializer, MatiereSerializer,
                           EvaluationSerializer, NoteSerializer)
from django.http import HttpResponse
from django.template.loader import render_to_string
from apps.eleves.models import Eleve


def get_tenant(request):
    if request.tenant:
        return request.tenant
    if request.user.role == 'SUPER_ADMIN':
        from apps.tenants.models import Tenant
        return Tenant.objects.first()
    return None


class NiveauScolaireViewSet(viewsets.ModelViewSet):
    serializer_class   = NiveauScolaireSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return NiveauScolaire.objects.filter(tenant=get_tenant(self.request))

    def perform_create(self, serializer):
        serializer.save(tenant=get_tenant(self.request))


class ClasseViewSet(viewsets.ModelViewSet):
    serializer_class   = ClasseSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Classe.objects.filter(tenant=get_tenant(self.request)).select_related('niveau')
        if niveau := self.request.query_params.get('niveau'):
            qs = qs.filter(niveau_id=niveau)
        return qs

    def perform_create(self, serializer):
        serializer.save(tenant=get_tenant(self.request))

    @action(detail=True, methods=['get'])
    def eleves(self, request, pk=None):
        """Retourne les élèves inscrits dans la section dont le nom correspond à cette classe."""
        tenant = get_tenant(request)
        try:
            classe = Classe.objects.get(id=pk, tenant=tenant)
        except Classe.DoesNotExist:
            return Response([], status=200)

        from apps.eleves.models import Eleve
        from apps.paiements.models import Exercice
        from django.db.models import Sum, Value, DecimalField
        from django.db.models.functions import Coalesce

        exercice = Exercice.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()
        if not exercice:
            return Response([])

        # Chercher par nom de section = nom de classe (convention)
        qs = Eleve.objects.filter(
            tenant=tenant, exercice=exercice
        ).filter(
            section__nom__iexact=classe.nom
        ).select_related('section').order_by('numero')

        # Si aucun résultat, renvoyer tous les élèves de l'exercice (fallback)
        if not qs.exists():
            qs = Eleve.objects.filter(tenant=tenant, exercice=exercice).select_related('section').order_by('numero')

        return Response([{
            'id':          str(e.id),
            'numero':      e.numero,
            'matricule':   e.matricule,
            'nom_complet': e.nom_complet,
            'section_nom': e.section.nom if e.section else '—',
        } for e in qs])


class TypeEvaluationViewSet(viewsets.ModelViewSet):
    serializer_class   = TypeEvaluationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return TypeEvaluation.objects.filter(tenant=get_tenant(self.request))

    def perform_create(self, serializer):
        serializer.save(tenant=get_tenant(self.request))


class MatiereViewSet(viewsets.ModelViewSet):
    serializer_class   = MatiereSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Matiere.objects.filter(
            tenant=get_tenant(self.request), est_active=True
        ).select_related('classe')
        if classe := self.request.query_params.get('classe'):
            qs = qs.filter(classe_id=classe)
        return qs

    def perform_create(self, serializer):
        serializer.save(tenant=get_tenant(self.request))


class EvaluationViewSet(viewsets.ModelViewSet):
    serializer_class   = EvaluationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Evaluation.objects.filter(
            tenant=get_tenant(self.request)
        ).select_related('matiere', 'type_eval')
        if matiere := self.request.query_params.get('matiere'):
            qs = qs.filter(matiere_id=matiere)
        if trimestre := self.request.query_params.get('trimestre'):
            qs = qs.filter(trimestre=trimestre)
        return qs

    def perform_create(self, serializer):
        serializer.save(tenant=get_tenant(self.request))


class NoteViewSet(viewsets.ModelViewSet):
    serializer_class   = NoteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Note.objects.filter(
            tenant=get_tenant(self.request)
        ).select_related('eleve', 'evaluation')
        if eleve := self.request.query_params.get('eleve'):
            qs = qs.filter(eleve_id=eleve)
        if evaluation := self.request.query_params.get('evaluation'):
            qs = qs.filter(evaluation_id=evaluation)
        return qs

    def perform_create(self, serializer):
        serializer.save(tenant=get_tenant(self.request))


class MoteurCalculView(APIView):
    """Moteur de calcul des moyennes et rangs."""
    permission_classes = [IsAuthenticated]

    def get_appreciation(self, moyenne, note_max):
        ratio = float(moyenne) / float(note_max) * 20
        if ratio >= 18:   return 'Excellent'
        if ratio >= 16:   return 'Très Bien'
        if ratio >= 14:   return 'Bien'
        if ratio >= 12:   return 'Assez Bien'
        if ratio >= 10:   return 'Passable'
        if ratio >= 8:    return 'Insuffisant'
        return 'Très Insuffisant'

    def get_appreciation_intelligente(self, moyenne, note_max, absences=0, progression=0):
        base = self.get_appreciation(moyenne, note_max)
        ratio = float(moyenne) / float(note_max) * 20
        if ratio >= 16 and absences <= 2:
            return f"Excellent trimestre. Élève sérieux et régulier."
        if 10 <= ratio < 12:
            return "Des efforts restent nécessaires."
        if progression < -1:
            return "Baisse de niveau constatée. Doit se ressaisir."
        if ratio >= 14:
            return "Bon travail. Continuez ainsi."
        if ratio < 10:
            return "Résultats insuffisants. Un soutien est recommandé."
        return base

    def post(self, request):
        """Calculer les moyennes pour une classe et un trimestre."""
        import datetime as _dt
        tenant    = get_tenant(request)
        classe_id = request.data.get('classe_id')
        trimestre = request.data.get('trimestre', 'T1')
        # Année scolaire : fournie par le frontend ou calculée depuis exercice actif
        annee = request.data.get('annee_scolaire')
        if not annee:
            from apps.paiements.models import Exercice as _Ex2
            ex = _Ex2.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()
            annee = ex.annee_scolaire if ex else f"{_dt.date.today().year-1}-{_dt.date.today().year}"

        try:
            classe = Classe.objects.get(id=classe_id, tenant=tenant)
        except Classe.DoesNotExist:
            return Response({'error': 'Classe introuvable'}, status=404)

        matieres = Matiere.objects.filter(classe=classe, tenant=tenant, est_active=True)
        from apps.eleves.models import Eleve
        from apps.paiements.models import Exercice as _Exercice
        exercice_actif = _Exercice.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()
        eleves_qs = Eleve.objects.filter(tenant=tenant, section__nom__iexact=classe.nom)
        if exercice_actif:
            eleves_qs = eleves_qs.filter(exercice=exercice_actif)
        eleves = eleves_qs

        resultats = []
        matieres_classement: dict = {str(m.id): [] for m in matieres}

        for eleve in eleves:
            total_points = 0
            total_coef   = 0
            detail_matieres = []

            for matiere in matieres:
                evaluations = Evaluation.objects.filter(
                    matiere=matiere, trimestre=trimestre, tenant=tenant
                )
                notes = Note.objects.filter(
                    eleve=eleve, evaluation__in=evaluations,
                    absent=False, tenant=tenant
                ).select_related('evaluation__type_eval')

                if not notes.exists():
                    detail_matieres.append({
                        'matiere': matiere.nom,
                        'coefficient': float(matiere.coefficient),
                        'moyenne': None,
                        'points': None,
                        'appreciation': 'Absent',
                    })
                    continue

                # Moyenne pondérée : Σ(note × poids) ÷ Σ(poids)
                sum_note_poids = sum(
                    float(n.valeur) * float(n.evaluation.type_eval.poids)
                    for n in notes
                )
                sum_poids = sum(float(n.evaluation.type_eval.poids) for n in notes)
                moyenne = sum_note_poids / sum_poids if sum_poids > 0 else 0

                points = moyenne * float(matiere.coefficient)
                total_points += points
                total_coef   += float(matiere.coefficient)

                appreciation = self.get_appreciation(moyenne, matiere.note_max)

                # Sauvegarder dans cache
                BulletinCache.objects.update_or_create(
                    tenant=tenant, eleve=eleve, matiere=matiere,
                    trimestre=trimestre, annee_scolaire=annee,
                    defaults={
                        'moyenne':      round(moyenne, 2),
                        'points':       round(points, 2),
                        'appreciation': appreciation,
                    }
                )

                matieres_classement[str(matiere.id)].append((str(eleve.id), round(moyenne, 2)))

                detail_matieres.append({
                    'matiere_id':   str(matiere.id),
                    'matiere':      matiere.nom,
                    'coefficient':  float(matiere.coefficient),
                    'note_max':     float(matiere.note_max),
                    'moyenne':      round(moyenne, 2),
                    'points':       round(points, 2),
                    'appreciation': appreciation,
                    'rang_matiere': None,  # rempli après
                })

            moy_generale = total_points / total_coef if total_coef > 0 else 0

            resultats.append({
                'eleve_id':      str(eleve.id),
                'eleve_nom':     eleve.nom_complet,
                'matieres':      detail_matieres,
                'total_points':  round(total_points, 2),
                'total_coef':    total_coef,
                'moy_generale':  round(moy_generale, 2),
                'rang':          0,  # calculé après
            })

        # Calcul des rangs
        resultats.sort(key=lambda x: x['moy_generale'], reverse=True)
        rang = 1
        for i, r in enumerate(resultats):
            if i > 0 and r['moy_generale'] == resultats[i-1]['moy_generale']:
                r['rang'] = resultats[i-1]['rang']  # égalité
            else:
                r['rang'] = rang
            rang += 1

        # Calcul des rangs par matière
        rang_par_matiere: dict = {}
        for matiere_id, liste in matieres_classement.items():
            if not liste:
                continue
            sorted_liste = sorted(liste, key=lambda x: -x[1])
            rang_map: dict = {}
            prev_moy: float = -1.0
            prev_rang = 0
            position = 0
            for eleve_id, moy in sorted_liste:
                position += 1
                if moy == prev_moy:
                    rang_map[eleve_id] = prev_rang
                else:
                    rang_map[eleve_id] = position
                    prev_rang = position
                    prev_moy = moy
            rang_par_matiere[matiere_id] = rang_map
            # Mettre à jour BulletinCache avec rang_matiere
            for eleve_id, _ in liste:
                r_mat = rang_map.get(eleve_id)
                if r_mat is not None:
                    BulletinCache.objects.filter(
                        tenant=tenant, eleve_id=eleve_id, matiere_id=matiere_id,
                        trimestre=trimestre, annee_scolaire=annee
                    ).update(rang_matiere=r_mat)

        # Injecter rang_matiere dans le détail de chaque résultat
        for r in resultats:
            for dm in r['matieres']:
                mat_id = dm.get('matiere_id')
                if mat_id:
                    dm['rang_matiere'] = rang_par_matiere.get(mat_id, {}).get(r['eleve_id'])

        # Statistiques classe
        moyennes = [r['moy_generale'] for r in resultats if r['moy_generale'] > 0]
        stats = {
            'moy_classe':   round(sum(moyennes)/len(moyennes), 2) if moyennes else 0,
            'moy_max':      max(moyennes) if moyennes else 0,
            'moy_min':      min(moyennes) if moyennes else 0,
            'nb_eleves':    len(resultats),
            'taux_reussite': round(len([m for m in moyennes if m >= 10])/len(moyennes)*100, 1) if moyennes else 0,
        }

        return Response({
            'classe':    classe.nom,
            'trimestre': trimestre,
            'resultats': resultats,
            'stats':     stats,
        })


def _get_annee_scolaire(tenant):
    """Retourne l'année scolaire de l'exercice actif, ou calcule depuis la date courante."""
    import datetime as _dt
    from apps.paiements.models import Exercice as _ExAnne
    ex = _ExAnne.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()
    if ex:
        return ex.annee_scolaire
    today = _dt.date.today()
    y = today.year if today.month >= 9 else today.year - 1
    return f"{y}-{y+1}"


class BulletinView(APIView):
    """Retourne les données du bulletin d'un élève (JSON)."""
    permission_classes = [IsAuthenticated]

    def _get_annee(self, request):
        return _get_annee_scolaire(get_tenant(request))

    def get(self, request, eleve_id, trimestre):
        tenant = get_tenant(request)
        annee = request.query_params.get('annee') or self._get_annee(request)

        try:
            eleve = Eleve.objects.get(id=eleve_id, tenant=tenant)
        except Eleve.DoesNotExist:
            return Response({'error': 'Élève introuvable'}, status=404)

        # Récupérer les données du cache bulletin
        bulletins = BulletinCache.objects.filter(
            tenant=tenant, eleve=eleve,
            trimestre=trimestre, annee_scolaire=annee
        ).select_related('matiere')

        if not bulletins.exists():
            return Response({'error': 'Aucune note calculée. Lancez d\'abord le calcul.'}, status=404)

        # Stats classe
        tous_bulletins = BulletinCache.objects.filter(
            tenant=tenant, trimestre=trimestre,
            annee_scolaire=annee,
            matiere__classe=bulletins.first().matiere.classe
        )
        moyennes_classe = [float(b.moyenne) for b in tous_bulletins if b.moyenne]

        data = {
            'eleve': {
                'nom_complet':    eleve.nom_complet,
                'matricule':      eleve.numero,
                'date_naissance': str(eleve.date_naissance) if eleve.date_naissance else '',
                'classe':         eleve.section.nom if eleve.section else '',
            },
            'tenant':    {'nom': tenant.nom, 'ville': tenant.ville},
            'trimestre': trimestre,
            'annee':     annee,
            'matieres': [{
                'nom':         b.matiere.nom,
                'coefficient': float(b.matiere.coefficient),
                'note_max':    float(b.matiere.note_max),
                'moyenne':     float(b.moyenne) if b.moyenne else None,
                'points':      float(b.points) if b.points else None,
                'rang':        b.rang_matiere,
                'appreciation':b.appreciation,
            } for b in bulletins.order_by('matiere__ordre')],
            'stats': {
                'moy_generale': round(sum(float(b.points or 0) for b in bulletins) /
                               sum(float(b.matiere.coefficient) for b in bulletins), 2)
                               if bulletins else 0,
                'moy_classe':  round(sum(moyennes_classe)/len(moyennes_classe), 2) if moyennes_classe else 0,
            }
        }
        return Response(data)

class BulletinPDFView(APIView):
    """Générer le bulletin PDF d'un élève."""
    permission_classes = [IsAuthenticated]

    def _get_annee(self, request):
        return _get_annee_scolaire(get_tenant(request))

    def get_appreciation(self, moy, note_max):
        ratio = float(moy) / float(note_max) * 20
        if ratio >= 18: return 'Excellent'
        if ratio >= 16: return 'Très Bien'
        if ratio >= 14: return 'Bien'
        if ratio >= 12: return 'Assez Bien'
        if ratio >= 10: return 'Passable'
        if ratio >= 8:  return 'Insuffisant'
        return 'Très Insuffisant'

    def get_decision(self, moy, note_max, trimestre='T1'):
        ratio = float(moy) / float(note_max) * 20
        if trimestre == 'T3':
            if ratio >= 16: return 'Admis(e) avec félicitations — Passage en classe supérieure'
            if ratio >= 14: return 'Admis(e) avec encouragements — Passage en classe supérieure'
            if ratio >= 10: return 'Admis(e) — Passage en classe supérieure'
            if ratio >= 8:  return 'Ajourné(e) — Décision soumise au Conseil de Classe'
            return 'Redoublement recommandé par le Conseil de Classe'
        else:  # T1, T2 — mentions
            if ratio >= 16: return 'Félicitations du Conseil de Classe'
            if ratio >= 14: return 'Encouragements du Conseil de Classe'
            if ratio >= 12: return 'Compliments du Conseil de Classe'
            if ratio >= 10: return 'Résultats satisfaisants'
            if ratio >= 8:  return 'Avertissement de travail'
            return 'Blâme de travail — Soutien scolaire recommandé'

    def get(self, request, eleve_id, trimestre):
        from io import BytesIO
        try:
            from xhtml2pdf import pisa
        except ImportError:
            return HttpResponse('xhtml2pdf non installé', status=500)

        tenant = get_tenant(request)
        annee = request.query_params.get('annee') or self._get_annee(request)

        try:
            eleve = Eleve.objects.get(id=eleve_id, tenant=tenant)
        except Eleve.DoesNotExist:
            return HttpResponse('Élève introuvable', status=404)

        bulletins = BulletinCache.objects.filter(
            tenant=tenant, eleve=eleve,
            trimestre=trimestre, annee_scolaire=annee
        ).select_related('matiere')

        if not bulletins.exists():
            return HttpResponse('Aucune note calculée', status=404)

        # Calcul moyenne générale
        total_points = sum(float(b.points or 0) for b in bulletins)
        total_coef   = sum(float(b.matiere.coefficient) for b in bulletins)
        moy_generale = round(total_points / total_coef, 2) if total_coef > 0 else 0
        note_max     = float(bulletins.first().matiere.note_max) if bulletins else 20

        # Stats classe
        from apps.eleves.models import Eleve as EleveModel
        classe = bulletins.first().matiere.classe if bulletins else None
        tous   = BulletinCache.objects.filter(
            tenant=tenant, trimestre=trimestre,
            annee_scolaire=annee, matiere__classe=classe
        ).values('eleve').distinct()

        moyennes_classe = []
        rang_eleve = 1
        for e_data in tous:
            e_bulletins = BulletinCache.objects.filter(
                tenant=tenant, eleve_id=e_data['eleve'],
                trimestre=trimestre, annee_scolaire=annee
            )
            e_pts  = sum(float(b.points or 0) for b in e_bulletins)
            e_coef = sum(float(b.matiere.coefficient) for b in e_bulletins)
            e_moy  = round(e_pts / e_coef, 2) if e_coef > 0 else 0
            moyennes_classe.append(e_moy)
            if e_moy > moy_generale:
                rang_eleve += 1

        moy_classe = round(sum(moyennes_classe)/len(moyennes_classe), 2) if moyennes_classe else 0

        context = {
            'tenant':    tenant,
            'annee':     annee,
            'trimestre': trimestre,
            'note_max':  note_max,
            'eleve': {
                'nom_complet':    eleve.nom_complet,
                'matricule':      eleve.numero or '—',
                'date_naissance': str(eleve.date_naissance) if eleve.date_naissance else '—',
                'classe':         eleve.section.nom if eleve.section else '—',
                'rang':           rang_eleve,
            },
            'matieres': [{
                'nom':         b.matiere.nom,
                'coefficient': float(b.matiere.coefficient),
                'note_max':    float(b.matiere.note_max),
                'moyenne':     float(b.moyenne) if b.moyenne else None,
                'points':      float(b.points) if b.points else None,
                'rang':        b.rang_matiere,
                'appreciation':b.appreciation,
            } for b in bulletins.order_by('matiere__ordre')],
            'total_coef':          round(total_coef, 1),
            'total_points':        round(total_points, 2),
            'stats': {
                'moy_generale': moy_generale,
                'moy_classe':   moy_classe,
                'moy_max':      max(moyennes_classe) if moyennes_classe else 0,
                'moy_min':      min(moyennes_classe) if moyennes_classe else 0,
                'nb_eleves':    len(moyennes_classe),
            },
            'appreciation_generale': self.get_appreciation(moy_generale, note_max),
            'decision':              self.get_decision(moy_generale, note_max, trimestre),
            'is_final':              trimestre == 'T3',
            'decision_positive':     moy_generale >= (note_max * 10 / 20),
        }

        html_str = render_to_string('pdf/bulletin.html', context)
        buffer   = BytesIO()
        result   = pisa.CreatePDF(html_str, dest=buffer, encoding='utf-8')
        if result.err:
            return HttpResponse('Erreur génération bulletin PDF.', status=500)

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="bulletin_{eleve.nom_complet}_{trimestre}.pdf"'
        return response