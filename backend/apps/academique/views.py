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
from core.tenant import get_tenant


def _est_periode_finale(tenant, periode):
    """True si la période (ex. 'T3', 'S2', 'P4') est la dernière de l'année,
    selon le nombre de périodes configuré pour l'école."""
    try:
        idx = int(''.join(ch for ch in (periode or '') if ch.isdigit()))
    except ValueError:
        return False
    nb = getattr(tenant, 'nb_periodes', 3) or 3
    return idx >= nb


class NiveauScolaireViewSet(viewsets.ModelViewSet):
    serializer_class   = NiveauScolaireSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        tenant = get_tenant(self.request)
        # Auto-synchronisation : chaque section (Paramètres → Frais Sections) devient
        # un NIVEAU. On crée ensuite les classes (CI A, CI B…) à l'intérieur d'une section.
        if tenant:
            from apps.eleves.models import Section
            existants = set(
                NiveauScolaire.objects.filter(tenant=tenant).values_list('nom', flat=True)
            )
            nouveaux = [
                NiveauScolaire(tenant=tenant, nom=s.nom, code='', ordre=s.ordre, note_max=20)
                for s in Section.objects.filter(tenant=tenant)
                if s.nom not in existants
            ]
            if nouveaux:
                NiveauScolaire.objects.bulk_create(nouveaux)
        return NiveauScolaire.objects.filter(tenant=tenant)

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

        # Élèves explicitement affectés à cette classe
        qs = Eleve.objects.filter(
            tenant=tenant, exercice=exercice, classe=classe
        ).select_related('section').order_by('numero')

        # Fallback (données anciennes non affectées) : élèves sans classe dont
        # la section porte le nom de la classe.
        if not qs.exists():
            qs = Eleve.objects.filter(
                tenant=tenant, exercice=exercice, classe__isnull=True,
                section__nom__iexact=classe.nom
            ).select_related('section').order_by('numero')

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

    @action(detail=False, methods=['post'])
    def bulk_save(self, request):
        """Enregistre toutes les notes d'une évaluation en une seule transaction."""
        from django.db import transaction
        tenant = get_tenant(request)
        notes_data = request.data.get('notes', [])
        if not notes_data:
            return Response({'error': 'Aucune note fournie.'}, status=400)

        created = updated = errors = 0
        with transaction.atomic():
            for item in notes_data:
                try:
                    _, was_created = Note.objects.update_or_create(
                        tenant=tenant,
                        eleve_id=item['eleve'],
                        evaluation_id=item['evaluation'],
                        defaults={
                            'valeur': item.get('valeur', 0),
                            'absent': item.get('absent', False),
                        },
                    )
                    if was_created:
                        created += 1
                    else:
                        updated += 1
                except Exception:
                    errors += 1

        return Response({'created': created, 'updated': updated, 'errors': errors})


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
        from django.db import transaction
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
            classe = Classe.objects.select_related('niveau').get(id=classe_id, tenant=tenant)
        except Classe.DoesNotExist:
            return Response({'error': 'Classe introuvable'}, status=404)

        matieres = list(Matiere.objects.filter(classe=classe, tenant=tenant, est_active=True))
        from apps.eleves.models import Eleve
        from apps.paiements.models import Exercice as _Exercice
        exercice_actif = _Exercice.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()
        eleves_qs = Eleve.objects.filter(tenant=tenant, section__nom__iexact=classe.nom)
        if exercice_actif:
            eleves_qs = eleves_qs.filter(exercice=exercice_actif)
        eleves = list(eleves_qs)

        # ── Prefetch toutes les évaluations en 1 requête ──────────────────
        all_evaluations = list(Evaluation.objects.filter(
            matiere__in=matieres, trimestre=trimestre, tenant=tenant
        ).select_related('type_eval'))

        evals_by_matiere: dict = {}
        for ev in all_evaluations:
            evals_by_matiere.setdefault(str(ev.matiere_id), []).append(ev)

        # ── Prefetch toutes les notes en 1 requête ────────────────────────
        all_notes = list(Note.objects.filter(
            eleve__in=eleves, evaluation__in=all_evaluations, tenant=tenant
        ))
        notes_idx: dict = {}
        for n in all_notes:
            notes_idx[(str(n.eleve_id), str(n.evaluation_id))] = n
        # ─────────────────────────────────────────────────────────────────

        note_max_niveau = float(classe.niveau.note_max) if classe.niveau else 20
        seuil_reussite  = note_max_niveau / 2

        resultats = []
        matieres_classement: dict = {str(m.id): [] for m in matieres}
        cache_to_upsert = []

        for eleve in eleves:
            total_points = 0
            total_coef   = 0
            detail_matieres = []

            for matiere in matieres:
                evaluations = evals_by_matiere.get(str(matiere.id), [])

                if not evaluations:
                    detail_matieres.append({
                        'matiere': matiere.nom,
                        'coefficient': float(matiere.coefficient),
                        'moyenne': None,
                        'points': None,
                        'appreciation': '—',
                    })
                    continue

                # Moyenne pondérée sur TOUTES les évaluations définies
                sum_note_poids = 0.0
                sum_poids      = 0.0
                has_any_note   = False
                for ev in evaluations:
                    poids = float(ev.type_eval.poids)
                    sum_poids += poids
                    note = notes_idx.get((str(eleve.id), str(ev.id)))
                    if note:
                        has_any_note = True
                        if not note.absent:
                            sum_note_poids += float(note.valeur) * poids

                # Si aucune note saisie du tout → absent
                if not has_any_note:
                    detail_matieres.append({
                        'matiere': matiere.nom,
                        'coefficient': float(matiere.coefficient),
                        'moyenne': None,
                        'points': None,
                        'appreciation': 'Absent',
                    })
                    continue

                moyenne = sum_note_poids / sum_poids if sum_poids > 0 else 0
                points  = moyenne * float(matiere.coefficient)
                total_points += points
                total_coef   += float(matiere.coefficient)
                appreciation  = self.get_appreciation(moyenne, matiere.note_max)

                cache_to_upsert.append((eleve, matiere, round(moyenne, 2), round(points, 2), appreciation))
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

            moy_generale  = total_points / total_coef if total_coef > 0 else 0
            appr_generale = self.get_appreciation(moy_generale, note_max_niveau)

            resultats.append({
                'eleve_id':              str(eleve.id),
                'eleve_nom':             eleve.nom_complet,
                'matieres':              detail_matieres,
                'total_points':          round(total_points, 2),
                'total_coef':            total_coef,
                'moy_generale':          round(moy_generale, 2),
                'appreciation_generale': appr_generale,
                'rang':                  0,  # calculé après
            })

        # ── Upsert BulletinCache en bloc atomique ─────────────────────────
        with transaction.atomic():
            for eleve, matiere, moyenne, points, appreciation in cache_to_upsert:
                BulletinCache.objects.update_or_create(
                    tenant=tenant, eleve=eleve, matiere=matiere,
                    trimestre=trimestre, annee_scolaire=annee,
                    defaults={'moyenne': moyenne, 'points': points, 'appreciation': appreciation}
                )
        # ─────────────────────────────────────────────────────────────────

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
            'taux_reussite': round(len([m for m in moyennes if m >= seuil_reussite])/len(moyennes)*100, 1) if moyennes else 0,
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
        ).select_related('matiere', 'matiere__classe', 'matiere__classe__niveau')

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

    def get_decision(self, moy, note_max, trimestre='T1', est_finale=None):
        ratio = float(moy) / float(note_max) * 20
        # Période finale (passage en classe supérieure). Compat : T3/S2 si non précisé.
        if est_finale is None:
            est_finale = trimestre in ('T3', 'S2')
        if est_finale:
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

        tenant = get_tenant(request)
        annee = request.query_params.get('annee') or self._get_annee(request)

        try:
            eleve = Eleve.objects.get(id=eleve_id, tenant=tenant)
        except Eleve.DoesNotExist:
            return HttpResponse('Élève introuvable', status=404)

        bulletins = BulletinCache.objects.filter(
            tenant=tenant, eleve=eleve,
            trimestre=trimestre, annee_scolaire=annee
        ).select_related('matiere', 'matiere__classe', 'matiere__classe__niveau')

        if not bulletins.exists():
            return HttpResponse('Aucune note calculée', status=404)

        bulletins_list = list(bulletins.order_by('matiere__ordre'))

        # Calcul moyenne générale
        total_points = sum(float(b.points or 0) for b in bulletins_list)
        total_coef   = sum(float(b.matiere.coefficient) for b in bulletins_list)
        moy_generale = round(total_points / total_coef, 2) if total_coef > 0 else 0
        # note_max de référence : niveau si défini, sinon note_max de la matière (niveau nullable)
        note_max = 20.0
        if bulletins_list:
            m0 = bulletins_list[0].matiere
            niv = getattr(m0.classe, 'niveau', None) if m0.classe_id else None
            note_max = float(niv.note_max) if niv else float(m0.note_max or 20)

        # Stats classe — 1 seule requête
        from collections import defaultdict
        classe = bulletins_list[0].matiere.classe if bulletins_list else None
        tous_bulletins_classe = list(BulletinCache.objects.filter(
            tenant=tenant, trimestre=trimestre,
            annee_scolaire=annee, matiere__classe=classe
        ).select_related('matiere'))

        bulletins_par_eleve: dict = defaultdict(list)
        for b in tous_bulletins_classe:
            bulletins_par_eleve[str(b.eleve_id)].append(b)

        moyennes_classe = []
        rang_eleve = 1
        for e_bulletins in bulletins_par_eleve.values():
            e_pts  = sum(float(b.points or 0) for b in e_bulletins)
            e_coef = sum(float(b.matiere.coefficient) for b in e_bulletins)
            e_moy  = round(e_pts / e_coef, 2) if e_coef > 0 else 0
            moyennes_classe.append(e_moy)
            if e_moy > moy_generale:
                rang_eleve += 1

        moy_classe = round(sum(moyennes_classe)/len(moyennes_classe), 2) if moyennes_classe else 0

        # ── Détail des notes individuelles par matière ────────────────────
        matiere_ids = [b.matiere_id for b in bulletins_list]
        # Devoirs (poids faible) en premier, Composition (poids fort) en dernier
        evals_for_pdf = list(Evaluation.objects.filter(
            matiere_id__in=matiere_ids, trimestre=trimestre, tenant=tenant
        ).select_related('type_eval').order_by('type_eval__poids', 'id'))

        evals_par_matiere: dict = defaultdict(list)
        for ev in evals_for_pdf:
            evals_par_matiere[str(ev.matiere_id)].append(ev)

        notes_eleve = list(Note.objects.filter(
            eleve=eleve, evaluation__in=evals_for_pdf, tenant=tenant
        ))
        notes_par_eval: dict = {str(n.evaluation_id): n for n in notes_eleve}

        # ── Colonnes d'évaluation dynamiques (union, ordonnées par poids) ──
        # Ex. 2 Devoirs + 1 Composition → colonnes [Devoir 1, Devoir 2, Composition].
        # Chaque matière remplit les cases qu'elle possède, les autres = «—».
        type_info: dict = {}            # tnom -> {'poids': float, 'max': int}
        matiere_evals_ordered: dict = {}  # matiere_id -> [(ev, tnom, idx)]
        for mid, evs in evals_par_matiere.items():
            counts: dict = {}
            ordered = []
            for ev in evs:
                t = ev.type_eval.nom
                counts[t] = counts.get(t, 0) + 1
                ordered.append((ev, t, counts[t]))
                info = type_info.setdefault(t, {'poids': float(ev.type_eval.poids), 'max': 0})
                info['max']   = max(info['max'], counts[t])
                info['poids'] = min(info['poids'], float(ev.type_eval.poids))
            matiere_evals_ordered[mid] = ordered

        eval_columns = []   # [{'key': (tnom, idx), 'label': str}]
        for tnom, info in sorted(type_info.items(), key=lambda x: (x[1]['poids'], x[0])):
            for i in range(1, info['max'] + 1):
                label = f"{tnom} {i}" if info['max'] > 1 else tnom
                eval_columns.append({'key': (tnom, i), 'label': label})

        # Largeur des colonnes notes : ~40% réparti, le reste pour les colonnes fixes
        n_cols = max(1, len(eval_columns))
        note_col_width = round(40 / n_cols, 2)

        def build_notes_cells(matiere_id):
            ordered = matiere_evals_ordered.get(str(matiere_id), [])
            by_key: dict = {}
            for ev, t, idx in ordered:
                n = notes_par_eval.get(str(ev.id))
                if n:
                    by_key[(t, idx)] = 'ABS' if n.absent else f"{float(n.valeur):g}"
                else:
                    by_key[(t, idx)] = '—'
            return [by_key.get(col['key'], '—') for col in eval_columns]

        def _fmt(val):
            if val is None:
                return '—'
            f = float(val)
            return f"{f:g}"

        matieres_ctx = []
        for b in bulletins_list:
            matieres_ctx.append({
                'nom':          b.matiere.nom,
                'coefficient':  float(b.matiere.coefficient),
                'note_max':     int(b.matiere.note_max) if float(b.matiere.note_max) == int(b.matiere.note_max) else float(b.matiere.note_max),
                'moyenne':      _fmt(b.moyenne),
                'points':       _fmt(b.points),
                'rang':         b.rang_matiere,
                'appreciation': b.appreciation,
                'notes_cells':  build_notes_cells(b.matiere_id),
            })
        # ─────────────────────────────────────────────────────────────────

        context = {
            'tenant':    tenant,
            'annee':     annee,
            'trimestre': trimestre,
            'note_max':  int(note_max) if note_max == int(note_max) else note_max,
            'eval_columns':   eval_columns,
            'note_col_width': note_col_width,
            'eleve': {
                'nom_complet':    eleve.nom_complet,
                'matricule':      eleve.numero or '—',
                'date_naissance': str(eleve.date_naissance) if eleve.date_naissance else '—',
                'classe':         eleve.section.nom if eleve.section else '—',
                'rang':           rang_eleve,
            },
            'matieres':            matieres_ctx,
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
            'decision':              self.get_decision(moy_generale, note_max, trimestre, est_finale=_est_periode_finale(tenant, trimestre)),
            'is_final':              _est_periode_finale(tenant, trimestre),
            'decision_positive':     moy_generale >= (note_max * 10 / 20),
        }

        html_str = render_to_string('pdf/bulletin.html', context)
        buffer   = BytesIO()
        try:
            import weasyprint
            weasyprint.HTML(string=html_str).write_pdf(buffer)
        except Exception:
            try:
                from xhtml2pdf import pisa
                buffer = BytesIO()
                result = pisa.CreatePDF(html_str, dest=buffer, encoding='utf-8')
                if result.err:
                    return HttpResponse('Erreur génération bulletin PDF.', status=500)
            except Exception as e:
                return HttpResponse(f'Erreur PDF : {e}', status=500)

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="bulletin_{eleve.nom_complet}_{trimestre}.pdf"'
        return response


class AnalysePerformanceView(APIView):
    """Statistiques académiques : top élèves, top classes, évolution par trimestre."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.paiements.models import Exercice
        tenant   = get_tenant(request)
        exercice = Exercice.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()
        annee    = exercice.annee_scolaire if exercice else ''

        bulletins = BulletinCache.objects.filter(tenant=tenant, annee_scolaire=annee)

        # ── Évolution moyennes par trimestre ──────────────────────────────
        evolution = []
        for tri in ['T1', 'T2', 'T3']:
            agg = bulletins.filter(trimestre=tri).aggregate(
                moy=Avg('moyenne_generale'), nb=Count('id', distinct=True)
            )
            evolution.append({
                'trimestre': tri,
                'moyenne':   round(float(agg['moy'] or 0), 2),
                'nb_eleves': agg['nb'],
            })

        # ── Top 10 élèves (T3 si dispo, sinon T2, sinon T1) ──────────────
        tri_ref = 'T3' if bulletins.filter(trimestre='T3').exists() else \
                  'T2' if bulletins.filter(trimestre='T2').exists() else 'T1'
        top_eleves_qs = (
            bulletins.filter(trimestre=tri_ref)
            .select_related('eleve', 'classe')
            .order_by('-moyenne_generale')[:10]
        )
        top_eleves = [{
            'rang':          i + 1,
            'nom':           b.eleve.nom_complet if b.eleve else '—',
            'classe':        b.classe.nom if b.classe else '—',
            'moyenne':       round(float(b.moyenne_generale or 0), 2),
            'trimestre':     tri_ref,
        } for i, b in enumerate(top_eleves_qs)]

        # ── Top classes par moyenne (tri_ref) ─────────────────────────────
        from django.db.models import FloatField
        from django.db.models.functions import Cast
        classes_qs = (
            bulletins.filter(trimestre=tri_ref, classe__isnull=False)
            .values('classe__id', 'classe__nom')
            .annotate(moy=Avg('moyenne_generale'), nb=Count('id', distinct=True))
            .order_by('-moy')[:10]
        )
        top_classes = [{
            'rang':    i + 1,
            'classe':  c['classe__nom'] or '—',
            'moyenne': round(float(c['moy'] or 0), 2),
            'nb':      c['nb'],
        } for i, c in enumerate(classes_qs)]

        # ── Distribution mentions (tri_ref) ───────────────────────────────
        distribution = {'excellent': 0, 'bien': 0, 'assez_bien': 0, 'passable': 0, 'insuffisant': 0}
        for b in bulletins.filter(trimestre=tri_ref).values_list('moyenne_generale', flat=True):
            m = float(b or 0)
            if m >= 16:   distribution['excellent']   += 1
            elif m >= 14: distribution['bien']         += 1
            elif m >= 12: distribution['assez_bien']   += 1
            elif m >= 10: distribution['passable']      += 1
            else:         distribution['insuffisant']   += 1

        return Response({
            'annee_scolaire': annee,
            'trimestre_ref':  tri_ref,
            'evolution':      evolution,
            'top_eleves':     top_eleves,
            'top_classes':    top_classes,
            'distribution':   distribution,
        })

class BulletinsHistoriqueView(APIView):
    """Liste de tous les bulletins déjà calculés, groupés par (élève, trimestre, année)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.db.models import Sum, Count, DecimalField, Value
        from django.db.models.functions import Coalesce
        from decimal import Decimal
        from apps.eleves.models import Eleve

        tenant = get_tenant(request)

        # Filtres optionnels
        classe_nom  = request.query_params.get('classe')
        trimestre   = request.query_params.get('trimestre')
        annee       = request.query_params.get('annee')
        search      = request.query_params.get('search', '').strip()

        qs = BulletinCache.objects.filter(tenant=tenant)
        if trimestre:
            qs = qs.filter(trimestre=trimestre)
        if annee:
            qs = qs.filter(annee_scolaire=annee)
        if classe_nom:
            qs = qs.filter(eleve__section__nom__iexact=classe_nom)
        if search:
            qs = qs.filter(eleve__nom_complet__icontains=search)

        zero = Value(Decimal('0'), output_field=DecimalField())
        groupes = list(
            qs.values('eleve_id', 'trimestre', 'annee_scolaire')
            .annotate(
                nb_matieres=Count('id'),
                total_points=Coalesce(Sum('points'), zero),
                total_coef=Coalesce(Sum('matiere__coefficient'), zero),
            )
            .order_by('-annee_scolaire', 'trimestre')
        )

        eleve_ids = list({str(g['eleve_id']) for g in groupes})
        eleves_map = {
            str(e.id): e
            for e in Eleve.objects.filter(id__in=eleve_ids).select_related('section')
        }

        result = []
        for g in groupes:
            e = eleves_map.get(str(g['eleve_id']))
            if not e:
                continue
            coef = float(g['total_coef'] or 0)
            pts  = float(g['total_points'] or 0)
            moy  = round(pts / coef, 2) if coef > 0 else 0
            result.append({
                'eleve_id':      str(g['eleve_id']),
                'eleve_nom':     e.nom_complet,
                'classe':        e.section.nom if e.section else '—',
                'trimestre':     g['trimestre'],
                'annee_scolaire':g['annee_scolaire'],
                'moy_generale':  moy,
                'nb_matieres':   g['nb_matieres'],
            })

        result.sort(key=lambda x: (
            -(int(x['annee_scolaire'][:4]) if x['annee_scolaire'] and x['annee_scolaire'][:4].isdigit() else 0),
            x['trimestre'],
            x['eleve_nom'],
        ))

        # Années disponibles pour le filtre
        annees = sorted(
            BulletinCache.objects.filter(tenant=tenant)
            .values_list('annee_scolaire', flat=True)
            .distinct(),
            reverse=True,
        )

        return Response({'bulletins': result, 'annees': annees})
