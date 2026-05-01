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
        tenant    = get_tenant(request)
        classe_id = request.data.get('classe_id')
        trimestre = request.data.get('trimestre', 'T1')
        annee     = request.data.get('annee_scolaire', '2025-2026')

        try:
            classe = Classe.objects.get(id=classe_id, tenant=tenant)
        except Classe.DoesNotExist:
            return Response({'error': 'Classe introuvable'}, status=404)

        matieres = Matiere.objects.filter(classe=classe, tenant=tenant, est_active=True)
        from apps.eleves.models import Eleve
        eleves = Eleve.objects.filter(tenant=tenant, section__nom=classe.nom)

        resultats = []

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

                detail_matieres.append({
                    'matiere':      matiere.nom,
                    'coefficient':  float(matiere.coefficient),
                    'note_max':     float(matiere.note_max),
                    'moyenne':      round(moyenne, 2),
                    'points':       round(points, 2),
                    'appreciation': appreciation,
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


class BulletinView(APIView):
    """Générer le bulletin PDF d'un élève."""
    permission_classes = [IsAuthenticated]

    def get(self, request, eleve_id, trimestre):
        tenant = get_tenant(request)
        annee  = request.query_params.get('annee', '2025-2026')

        from apps.eleves.models import Eleve
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
