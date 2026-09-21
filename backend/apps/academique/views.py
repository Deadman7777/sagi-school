from rest_framework import viewsets, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from django.db.models import Avg, Max, Min, Count, Q
from .models import NiveauScolaire, Classe, TypeEvaluation, Matiere, Evaluation, Note, BulletinCache
from .serializers import (NiveauScolaireSerializer, ClasseSerializer,
                           TypeEvaluationSerializer, MatiereSerializer,
                           EvaluationSerializer, NoteSerializer, erreur_bareme)
from django.http import HttpResponse
from django.template.loader import render_to_string
from apps.eleves.models import Eleve
from core.tenant import get_tenant
from .resultats import (fiche_pedagogique, lignes_cache, moyenne_generale, numero_periode,
                        note_max_reference, points_matiere, poids_ligne, programme_valide, ramener,
                        resultat_matiere, arrondir, mode_arrondi,
                        situation_periode)


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

    @action(detail=True, methods=['post'], url_path='copier-matieres')
    def copier_matieres(self, request, pk=None):
        """Recopie les matières de cette classe vers d'autres classes.

        Attend {"cibles": ["<id>", ...], "ecraser": false}.

        Un établissement à filières partage presque toujours un tronc commun :
        les matières se saisissaient classe par classe, soit plusieurs centaines
        de saisies identiques au paramétrage d'un centre de formation. La même
        matière recopiée à la main finit d'ailleurs avec des coefficients
        divergents d'une classe à l'autre.

        Une matière déjà présente dans la cible, reconnue à son NOM, n'est pas
        dupliquée : soit on la laisse telle quelle, soit on aligne son
        coefficient et sa note maximale sur la source quand `ecraser` est
        demandé. Relancer l'opération ne crée donc jamais de doublon.
        """
        from django.db import transaction

        tenant = get_tenant(request)
        try:
            source = Classe.objects.get(id=pk, tenant=tenant)
        except Classe.DoesNotExist:
            return Response({'error': 'Classe source introuvable.'}, status=404)

        cibles_ids = request.data.get('cibles') or []
        if not isinstance(cibles_ids, list) or not cibles_ids:
            return Response({'cibles': 'Attendu : une liste de classes cibles.'},
                            status=400)
        ecraser = bool(request.data.get('ecraser'))

        cibles = list(Classe.objects.filter(tenant=tenant, id__in=cibles_ids)
                      .exclude(id=source.id))
        if not cibles:
            return Response({'cibles': 'Aucune classe cible valide.'}, status=400)

        matieres = list(Matiere.objects.filter(tenant=tenant, classe=source,
                                               est_active=True).order_by('ordre', 'nom'))
        if not matieres:
            return Response({'error': "Cette classe n'a aucune matière à recopier."},
                            status=400)

        rapport = []
        with transaction.atomic():
            for cible in cibles:
                existantes = {(m.programme, m.nom.strip().lower()): m for m in
                              Matiere.objects.filter(tenant=tenant, classe=cible)}
                creees = alignees = 0
                for m in matieres:
                    cle = (m.programme, m.nom.strip().lower())
                    if cle in existantes:
                        if ecraser:
                            deja = existantes[cle]
                            deja.coefficient, deja.note_max = m.coefficient, m.note_max
                            deja.ordre, deja.est_active = m.ordre, True
                            deja.save(update_fields=['coefficient', 'note_max',
                                                     'ordre', 'est_active'])
                            alignees += 1
                        continue
                    Matiere.objects.create(
                        tenant=tenant, classe=cible, nom=m.nom, code=m.code,
                        programme=m.programme, coefficient=m.coefficient, note_max=m.note_max,
                        ordre=m.ordre, est_active=True)
                    creees += 1
                rapport.append({'classe': cible.nom, 'creees': creees,
                                'alignees': alignees,
                                'inchangees': len(matieres) - creees - alignees})

        from core.models import log_audit
        log_audit(request, 'CREATE', 'Matiere', str(source.id),
                  f"{len(matieres)} matière(s) de « {source.nom} » recopiées "
                  f"vers {len(cibles)} classe(s)")

        return Response({'source': source.nom, 'matieres': len(matieres),
                         'rapport': rapport})

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
        if programme := self.request.query_params.get('programme'):
            qs = qs.filter(programme=programme)
        return qs

    def perform_create(self, serializer):
        serializer.save(tenant=get_tenant(self.request))


class EvaluationViewSet(viewsets.ModelViewSet):
    serializer_class   = EvaluationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Evaluation.objects.filter(
            tenant=get_tenant(self.request)
        ).select_related('matiere', 'type_eval').annotate(
            # Le nombre de notes déjà saisies, en une requête plutôt qu'une
            # par évaluation : la liste en affiche une dizaine.
            nb_notes_annote=Count('notes'))
        if matiere := self.request.query_params.get('matiere'):
            qs = qs.filter(matiere_id=matiere)
        if trimestre := self.request.query_params.get('trimestre'):
            qs = qs.filter(trimestre=trimestre)
        return qs

    def perform_create(self, serializer):
        serializer.save(tenant=get_tenant(self.request))

    def _perimer_moyennes(self, evaluation):
        """Jette les moyennes calculées qui dépendaient de cette évaluation.

        Elles sont dans BulletinCache, et rien ne les invalidait : supprimer
        une évaluation ou changer son barème laissait le bulletin afficher
        les moyennes d'avant, justes en apparence. Une moyenne absente se
        voit (« Lancez d'abord le calcul »), une moyenne périmée ne se voit
        pas — c'est la seule raison de préférer l'effacement au silence.
        """
        BulletinCache.objects.filter(
            tenant=evaluation.tenant,
            matiere=evaluation.matiere,
            trimestre=evaluation.trimestre,
        ).delete()

    def perform_update(self, serializer):
        ancienne_matiere   = serializer.instance.matiere
        ancien_trimestre   = serializer.instance.trimestre
        evaluation = serializer.save()
        # La modification a pu déplacer l'évaluation : périmer des deux côtés.
        self._perimer_moyennes(evaluation)
        if (ancienne_matiere != evaluation.matiere
                or ancien_trimestre != evaluation.trimestre):
            BulletinCache.objects.filter(
                tenant=evaluation.tenant, matiere=ancienne_matiere,
                trimestre=ancien_trimestre).delete()

    def destroy(self, request, *args, **kwargs):
        """Supprime l'évaluation ET ses notes, en disant combien.

        Le CASCADE est voulu : une évaluation créée par erreur n'a pas à
        laisser des notes orphelines derrière elle. Mais la réponse annonce
        le nombre de notes emportées, pour que l'écran puisse le confirmer
        avant, et le rappeler après.
        """
        evaluation = self.get_object()
        nb_notes   = evaluation.notes.count()
        libelle    = f"{evaluation.type_eval.nom} — {evaluation.matiere.nom}"
        self._perimer_moyennes(evaluation)
        evaluation.delete()
        return Response({'supprimee': libelle, 'notes_supprimees': nb_notes,
                         'recalcul_necessaire': True})


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

        # Barèmes des évaluations concernées, en une requête : la grille peut
        # porter sur plusieurs évaluations de barèmes différents.
        # Clés en CHAÎNE : la requête envoie des UUID sous forme de texte, et
        # un dictionnaire indexé par UUID ne les retrouve jamais — le barème
        # ressortait None et la note hors barème passait quand même.
        eval_ids  = {item.get('evaluation') for item in notes_data if item.get('evaluation')}
        baremes   = {str(i): nm for i, nm in
                     Evaluation.objects.filter(tenant=tenant, id__in=eval_ids)
                                       .values_list('id', 'note_max')}

        created = updated = errors = 0
        refusees = []
        with transaction.atomic():
            for item in notes_data:
                try:
                    # Une note hors barème est refusée NOMMÉMENT. Elle passait
                    # avant, et faussait ensuite moyenne, rang et mention sans
                    # que rien ne le signale.
                    if not item.get('absent', False):
                        message = erreur_bareme(item.get('valeur', 0),
                                                baremes.get(str(item['evaluation'])))
                        if message:
                            refusees.append({'eleve': item.get('eleve'), 'message': message})
                            errors += 1
                            continue
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

        return Response({'created': created, 'updated': updated, 'errors': errors,
                         'refusees': refusees})


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

        matieres_qs = Matiere.objects.filter(classe=classe, tenant=tenant, est_active=True)
        # Établissement hybride : chaque programme a sa moyenne et son rang
        programme = programme_valide(request.data.get('programme'))
        if programme:
            matieres_qs = matieres_qs.filter(programme=programme)
        matieres = list(matieres_qs)
        from apps.eleves.models import Eleve
        from apps.paiements.models import Exercice as _Exercice
        exercice_actif = _Exercice.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()
        # La classe de l'élève fait foi. Le rapprochement se faisait par nom de
        # section : il ne tombait juste que pour une école dont une section
        # porte le nom d'une classe. Dès que les sections sont les niveaux
        # tarifaires (Maternelle, Élémentaire…) et les classes les vraies
        # classes (CI, CE2, CM2…), aucun élève ne ressortait — moyennes vides
        # puis bulletins « Aucune note calculée » malgré des notes en base.
        # Le repli par nom reste pour les fiches anciennes sans classe posée.
        eleves_qs = Eleve.objects.filter(tenant=tenant, classe=classe)
        if exercice_actif:
            eleves_qs = eleves_qs.filter(exercice=exercice_actif)
        eleves = list(eleves_qs)
        if not eleves:
            secours = Eleve.objects.filter(tenant=tenant, classe__isnull=True,
                                           section__nom__iexact=classe.nom)
            if exercice_actif:
                secours = secours.filter(exercice=exercice_actif)
            eleves = list(secours)

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

        note_max_niveau = note_max_reference(classe, matieres)
        arrondi         = mode_arrondi(tenant)
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

                # Moyenne sur TOUTES les évaluations définies (une note
                # manquante compte zéro), selon le calcul choisi par l'école.
                resultat = resultat_matiere(
                    [(ev, notes_idx.get((str(eleve.id), str(ev.id)))) for ev in evaluations],
                    matiere, note_max_niveau, tenant.calcul_moyenne)

                # Si aucune note saisie du tout → absent
                if resultat is None:
                    detail_matieres.append({
                        'matiere': matiere.nom,
                        'coefficient': float(matiere.coefficient),
                        'moyenne': None,
                        'points': None,
                        'appreciation': 'Absent',
                    })
                    continue

                # La moyenne reste sur le barème de la matière (affichage),
                # les points sont ramenés à celui du niveau (addition).
                moyenne, points, poids = resultat
                poids_effectif = poids if poids is not None else float(matiere.coefficient)
                total_points += points
                total_coef   += poids_effectif
                appreciation  = self.get_appreciation(moyenne, matiere.note_max)

                cache_to_upsert.append((eleve, matiere, arrondir(moyenne, arrondi), round(points, 2),
                                        None if poids is None else round(poids, 3), appreciation))
                matieres_classement[str(matiere.id)].append((str(eleve.id), arrondir(moyenne, arrondi)))

                detail_matieres.append({
                    'matiere_id':   str(matiere.id),
                    'matiere':      matiere.nom,
                    'coefficient':  float(matiere.coefficient),
                    # Poids réel dans la moyenne générale : le coefficient, ou
                    # en calcul « total des points » coef × barème / barème du niveau.
                    'poids':        round(poids_effectif, 3),
                    'note_max':     float(matiere.note_max),
                    'moyenne':      arrondir(moyenne, arrondi),
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
                'moy_generale':          arrondir(moy_generale, arrondi),
                'appreciation_generale': appr_generale,
                'rang':                  0,  # calculé après
            })

        # ── Upsert BulletinCache en bloc atomique ─────────────────────────
        with transaction.atomic():
            for eleve, matiere, moyenne, points, poids, appreciation in cache_to_upsert:
                BulletinCache.objects.update_or_create(
                    tenant=tenant, eleve=eleve, matiere=matiere,
                    trimestre=trimestre, annee_scolaire=annee,
                    defaults={'moyenne': moyenne, 'points': points, 'poids': poids,
                              'appreciation': appreciation}
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
            'moy_classe':   arrondir(sum(moyennes)/len(moyennes), arrondi) if moyennes else 0,
            'moy_max':      max(moyennes) if moyennes else 0,
            'moy_min':      min(moyennes) if moyennes else 0,
            'nb_eleves':    len(resultats),
            'taux_reussite': round(len([m for m in moyennes if m >= seuil_reussite])/len(moyennes)*100, 1) if moyennes else 0,
        }

        return Response({
            'classe':    classe.nom,
            'trimestre': trimestre,
            'programme': programme,
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

        programme = programme_valide(request.query_params.get('programme'))
        situation = situation_periode(tenant, eleve, trimestre, annee, programme)
        if situation is None:
            return Response({'error': 'Aucune note calculée. Lancez d\'abord le calcul.'}, status=404)

        data = {
            'eleve': {
                'nom_complet':    eleve.nom_complet,
                'matricule':      eleve.numero,
                'date_naissance': str(eleve.date_naissance) if eleve.date_naissance else '',
                # La CLASSE de l'élève, pas sa section. La section est un niveau
                # tarifaire : l'imprimer ici affiche « Élémentaire » là où le
                # bulletin doit dire « CM2 ». Chez un centre de formation dont
                # les grilles distinguent les auditeurs par nationalité, cela
                # imprimait « 1re année — Étranger » sur le bulletin d'un
                # auditeur, à la place de sa filière. La section ne sert plus
                # que de repli pour les fiches anciennes sans classe posée.
                'classe':         (eleve.classe.nom if eleve.classe_id
                                   else (eleve.section.nom if eleve.section else '')),
            },
            'tenant':    {'nom': tenant.nom, 'ville': tenant.ville},
            'trimestre': trimestre,
            'annee':     annee,
            'programme': programme,
            'matieres': [{
                'nom':         b.matiere.nom,
                'coefficient': float(b.matiere.coefficient),
                'note_max':    float(b.matiere.note_max),
                'moyenne':     float(b.moyenne) if b.moyenne is not None else None,
                'points':      float(b.points) if b.points is not None else None,
                'rang':        b.rang_matiere,
                'appreciation':b.appreciation,
            } for b in situation['lignes']],
            'stats': {
                'moy_generale': situation['moy_generale'],
                # Moyenne des moyennes générales de la classe — la même que le
                # PDF. C'était la moyenne de toutes les notes de matière de la
                # classe, un autre chiffre sous le même nom.
                'moy_classe':   situation['moy_classe'],
                'rang':         situation['rang'],
                'effectif':     situation['effectif'],
            }
        }
        return Response(data)


def _appreciation(moy, note_max):
    ratio = float(moy) / float(note_max) * 20
    if ratio >= 18: return 'Excellent'
    if ratio >= 16: return 'Très Bien'
    if ratio >= 14: return 'Bien'
    if ratio >= 12: return 'Assez Bien'
    if ratio >= 10: return 'Passable'
    if ratio >= 8:  return 'Insuffisant'
    return 'Très Insuffisant'


def _decision(moy, note_max, trimestre='T1', est_finale=None):
    return BulletinPDFView().get_decision(moy, note_max, trimestre, est_finale)


def contexte_bulletin(tenant, eleve, trimestre, annee, programme):
    """Contexte de rendu d'UN bulletin, ou None si l'élève n'a aucune note.

    Extrait de la vue le 19/09/2026 pour servir aussi à l'édition par
    classe. Deux constructions séparées du même bulletin auraient fini par
    diverger : l'école aurait imprimé deux documents différents pour un même
    élève selon le bouton utilisé.
    """
    situation = situation_periode(tenant, eleve, trimestre, annee, programme)
    if situation is None:
        return None

    bulletins_list = situation['lignes']
    total_points   = situation['total_points']
    total_coef     = situation['total_coef']
    moy_generale   = situation['moy_generale']
    # Barème de la moyenne générale — la MÊME déduction que le moteur de
    # calcul, avec les mêmes arguments (cf. note_max_reference).
    note_max = note_max_reference(bulletins_list[0].matiere.classe,
                                  [b.matiere for b in bulletins_list])

    from collections import defaultdict

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

    eval_columns = []   # [{'key': (tnom, idx), 'label': str, 'width': int}]
    for tnom, info in sorted(type_info.items(), key=lambda x: (x[1]['poids'], x[0])):
        for i in range(1, info['max'] + 1):
            label = f"{tnom} {i}" if info['max'] > 1 else tnom
            eval_columns.append({'key': (tnom, i), 'label': label})

    # Largeur des colonnes d'évaluation : 37% partagé, en ENTIERS.
    # xhtml2pdf (table-layout:fixed) gère mal les % fractionnaires → colonnes écrasées.
    # On distribue 37 en entiers (reliquat sur les 1ères). Template fixe : 20+6+37+12+8+6+11=100.
    ESPACE_EVAL = 34
    nb = max(1, len(eval_columns))
    base_w = ESPACE_EVAL // nb
    extra  = ESPACE_EVAL - base_w * nb
    for j, col in enumerate(eval_columns):
        col['width'] = base_w + (1 if j < extra else 0)

    def build_notes_cells(matiere_id, note_max_matiere):
        """Les notes du détail, ramenées au barème de la matière.

        La ligne annonce « 15,5/20 » : il faut que les notes affichées à sa
        gauche s'en approchent, sinon le parent ne retrouve pas la moyenne.
        Une interro notée sur /10 s'imprime donc sur /20 comme le reste de la
        ligne. Le professeur retrouve sa note telle qu'il l'a saisie dans
        l'écran de saisie, qui affiche le barème de l'évaluation.
        """
        ordered = matiere_evals_ordered.get(str(matiere_id), [])
        by_key: dict = {}
        for ev, t, idx in ordered:
            n = notes_par_eval.get(str(ev.id))
            if n:
                valeur = ramener(n.valeur, ev.note_max, note_max_matiere)
                by_key[(t, idx)] = 'ABS' if n.absent else f"{valeur:g}".replace('.', ',')
            else:
                by_key[(t, idx)] = '—'
        return [by_key.get(col['key'], '—') for col in eval_columns]

    def _fmt(val):
        """Nombre court, avec la virgule décimale du document.

        Les totaux de la ligne du bas sont rendus par Django, qui applique la
        locale et écrit « 140,67 ». Ces cellules-ci étaient formatées à la
        main en `%g` et écrivaient « 58.67 » : deux séparateurs dans la même
        colonne du même tableau.
        """
        if val is None:
            return '—'
        return f"{float(val):g}".replace('.', ',')

    matieres_ctx = []
    for b in bulletins_list:
        matieres_ctx.append({
            'nom':          b.matiere.nom,
            # Le coefficient DE L'ÉCOLE, toujours. En calcul « total des
            # points », le poids du barème (0,5 pour /5, 2 pour /20) reste
            # interne : imprimé, il contredisait les coefficients que l'école
            # a saisis.
            'coefficient':  _fmt(b.matiere.coefficient),
            'note_max':     int(b.matiere.note_max) if float(b.matiere.note_max) == int(b.matiere.note_max) else float(b.matiere.note_max),
            'moyenne':      _fmt(b.moyenne),
            'points':       _fmt(b.points),
            'rang':         b.rang_matiere,
            'appreciation': b.appreciation,
            'notes_cells':  build_notes_cells(b.matiere_id, b.matiere.note_max),
        })
    # ─────────────────────────────────────────────────────────────────

    context = {
        'tenant':    tenant,
        'annee':     annee,
        'trimestre': trimestre,
        'note_max':  int(note_max) if note_max == int(note_max) else note_max,
        'eval_columns':   eval_columns,
        'eleve': {
            'nom_complet':    eleve.nom_complet,
            'matricule':      eleve.numero or '—',
            'date_naissance': str(eleve.date_naissance) if eleve.date_naissance else '—',
            # La classe de l'élève, pas sa section — voir le commentaire
            # de la vue bulletin plus haut.
            'classe':         (eleve.classe.nom if eleve.classe_id
                               else (eleve.section.nom if eleve.section else '—')),
            'rang':           situation['rang'],
        },
        'matieres':            matieres_ctx,
        'total_coef':          round(total_coef, 1),
        'total_points':        round(total_points, 2),
        # Calcul « total des points » : le total se lit « 125 / 150 », comme la
        # feuille de l'enseignant. Points possibles = Σ poids × barème de la
        # moyenne (voir resultats.resultat_matiere).
        'total_bareme':        (round(total_coef * note_max, 2)
                                if any(b.poids is not None for b in bulletins_list) else None),
        'stats': {
            'moy_generale': moy_generale,
            'moy_classe':   situation['moy_classe'],
            'moy_max':      situation['moy_max'],
            'moy_min':      situation['moy_min'],
            'nb_eleves':    situation['effectif'],
        },
        'appreciation_generale': _appreciation(moy_generale, note_max),
        'decision':              _decision(moy_generale, note_max, trimestre, est_finale=_est_periode_finale(tenant, trimestre)),
        'is_final':              _est_periode_finale(tenant, trimestre),
        'decision_positive':     moy_generale >= (note_max * 10 / 20),
    }

    context['programme'] = programme
    context['hybride'] = getattr(tenant, 'programmes_hybrides', False)
    context['_lignes'] = bulletins_list
    return context


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

        programme = programme_valide(request.query_params.get('programme'))
        context = contexte_bulletin(tenant, eleve, trimestre, annee, programme)
        if context is None:
            return HttpResponse('Aucune note calculée', status=404)
        bulletins_list = context.pop('_lignes')
        if programme == 'AR':
            # Bulletin du programme arabe : tout en arabe, de droite à gauche
            from .libelles import contexte_bulletin_ar
            from core.arabe import font_link_callback
            from xhtml2pdf import pisa
            html_str = render_to_string('pdf/bulletin_ar.html',
                                        contexte_bulletin_ar(context, tenant, bulletins_list))
            buffer = BytesIO()
            result = pisa.CreatePDF(html_str, dest=buffer, encoding='utf-8',
                                    link_callback=font_link_callback)
            if result.err:
                return HttpResponse('Erreur génération bulletin PDF.', status=500)
            response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="bulletin_ar_{eleve.nom_complet}_{trimestre}.pdf"'
            return response

        import logging, traceback as _tb
        _logger = logging.getLogger('django')
        html_str = render_to_string('pdf/bulletin.html', context)
        buffer   = BytesIO()
        try:
            import weasyprint
            weasyprint.HTML(string=html_str).write_pdf(buffer)
        except Exception as e_weasy:
            try:
                from xhtml2pdf import pisa
                buffer = BytesIO()
                result = pisa.CreatePDF(html_str, dest=buffer, encoding='utf-8')
                if result.err:
                    _logger.error('Bulletin PDF — xhtml2pdf err=%s (weasy: %s)', result.err, e_weasy)
                    return HttpResponse('Erreur génération bulletin PDF.', status=500)
            except Exception as e:
                _logger.error('Bulletin PDF — échec rendu :\n%s', _tb.format_exc())
                return HttpResponse(f'Erreur PDF : {e}', status=500)

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="bulletin_{eleve.nom_complet}_{trimestre}.pdf"'
        return response


class AnalysePerformanceView(APIView):
    """Statistiques académiques : top élèves, top classes, évolution par trimestre."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.paiements.models import Exercice
        from django.db.models import Sum
        from django.db.models.functions import Coalesce
        from collections import defaultdict

        tenant   = get_tenant(request)
        exercice = Exercice.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()
        annee    = exercice.annee_scolaire if exercice else ''
        arrondi  = mode_arrondi(tenant)

        bulletins = BulletinCache.objects.filter(tenant=tenant, annee_scolaire=annee)
        if programme := programme_valide(request.query_params.get('programme')):
            bulletins = bulletins.filter(matiere__programme=programme)

        # BulletinCache est PAR MATIÈRE → la moyenne générale d'un élève = Σpoints / Σcoef.
        def moyennes_par_eleve(periode):
            """Retourne [{eleve_id, nom, classe, moyenne}] pour une période donnée."""
            rows = bulletins.filter(trimestre=periode).values(
                'eleve_id', 'eleve__nom_complet',
                'eleve__classe__nom', 'eleve__section__nom',
            ).annotate(pts=Sum('points'),
                       # Même poids que resultats.poids_ligne, en SQL.
                       coef=Sum(Coalesce('poids', 'matiere__coefficient')))
            res = []
            for r in rows:
                c = float(r['coef'] or 0)
                if c <= 0:
                    continue
                res.append({
                    'eleve_id': r['eleve_id'],
                    'nom':      r['eleve__nom_complet'] or '—',
                    'classe':   r['eleve__classe__nom'] or r['eleve__section__nom'] or '—',
                    'moyenne':  arrondir(float(r['pts'] or 0) / c, arrondi),
                })
            return res

        # Périodes réellement présentes, triées par numéro (T1<T2<T3 ou S1<S2 ou P1..)
        def _num(p):
            digits = ''.join(ch for ch in (p or '') if ch.isdigit())
            return int(digits) if digits else 0
        periodes = sorted(
            {b for b in bulletins.values_list('trimestre', flat=True).distinct() if b},
            key=_num
        )

        # ── Évolution des moyennes par période ────────────────────────────
        evolution = []
        for p in periodes:
            avgs = moyennes_par_eleve(p)
            moy = arrondir(sum(a['moyenne'] for a in avgs) / len(avgs), arrondi) if avgs else 0
            evolution.append({'trimestre': p, 'moyenne': moy, 'nb_eleves': len(avgs)})

        # Période de référence = la dernière disponible
        tri_ref = periodes[-1] if periodes else ''
        ref_avgs = moyennes_par_eleve(tri_ref) if tri_ref else []

        # ── Top 10 élèves ─────────────────────────────────────────────────
        top_eleves = [{
            'rang':      i + 1,
            'nom':       a['nom'],
            'classe':    a['classe'],
            'moyenne':   a['moyenne'],
            'trimestre': tri_ref,
        } for i, a in enumerate(sorted(ref_avgs, key=lambda x: x['moyenne'], reverse=True)[:10])]

        # ── Top classes (moyenne des moyennes générales des élèves) ───────
        par_classe = defaultdict(list)
        for a in ref_avgs:
            par_classe[a['classe']].append(a['moyenne'])
        classes_calc = [
            {'classe': nom, 'moyenne': arrondir(sum(v) / len(v), arrondi), 'nb': len(v)}
            for nom, v in par_classe.items() if v
        ]
        top_classes = [
            {**c, 'rang': i + 1}
            for i, c in enumerate(sorted(classes_calc, key=lambda x: x['moyenne'], reverse=True)[:10])
        ]

        # ── Distribution des mentions (période de référence) ──────────────
        distribution = {'excellent': 0, 'bien': 0, 'assez_bien': 0, 'passable': 0, 'insuffisant': 0}
        for a in ref_avgs:
            m = a['moyenne']
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
        arrondi = mode_arrondi(tenant)

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
            # Même règle que partout ailleurs : la classe de l'élève d'abord,
            # le nom de section en repli pour les fiches sans classe posée.
            qs = qs.filter(Q(eleve__classe__nom__iexact=classe_nom)
                           | Q(eleve__classe__isnull=True,
                               eleve__section__nom__iexact=classe_nom))
        if search:
            qs = qs.filter(eleve__nom_complet__icontains=search)
        if programme := programme_valide(request.query_params.get('programme')):
            qs = qs.filter(matiere__programme=programme)

        zero = Value(Decimal('0'), output_field=DecimalField())
        # Un bulletin par programme : un élève d'établissement hybride en a deux
        groupes = list(
            qs.values('eleve_id', 'trimestre', 'annee_scolaire', 'matiere__programme')
            .annotate(
                nb_matieres=Count('id'),
                total_points=Coalesce(Sum('points'), zero),
                # Même poids que resultats.poids_ligne, en SQL.
                total_coef=Coalesce(Sum(Coalesce('poids', 'matiere__coefficient')), zero),
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
            moy  = arrondir(pts / coef, arrondi) if coef > 0 else 0
            result.append({
                'eleve_id':      str(g['eleve_id']),
                'eleve_nom':     e.nom_complet,
                'classe':        (e.classe.nom if e.classe_id
                                  else (e.section.nom if e.section else '—')),
                'trimestre':     g['trimestre'],
                'annee_scolaire':g['annee_scolaire'],
                'programme':     g['matiere__programme'],
                'moy_generale':  moy,
                'nb_matieres':   g['nb_matieres'],
            })

        result.sort(key=lambda x: (
            -(int(x['annee_scolaire'][:4]) if x['annee_scolaire'] and x['annee_scolaire'][:4].isdigit() else 0),
            x['trimestre'],
            x['eleve_nom'],
            x['programme'],
        ))

        # Années disponibles pour le filtre
        annees = sorted(
            BulletinCache.objects.filter(tenant=tenant)
            .values_list('annee_scolaire', flat=True)
            .distinct(),
            reverse=True,
        )

        return Response({'bulletins': result, 'annees': annees})


class FichePedagogiqueView(APIView):
    """Suivi pédagogique d'un élève sur l'année : évolution, points forts,
    points faibles et points d'amélioration, pour un programme.

    GET fiche-pedagogique/<eleve_id>/?programme=FR|AR&annee=… → JSON
    GET fiche-pedagogique-pdf/<eleve_id>/?…                   → PDF (en arabe pour AR)
    """
    permission_classes = [IsAuthenticated]
    pdf = False

    def get(self, request, eleve_id):
        tenant = get_tenant(request)
        from django.core.exceptions import ValidationError
        try:
            eleve = Eleve.objects.select_related('classe', 'section').get(id=eleve_id, tenant=tenant)
        except (Eleve.DoesNotExist, ValidationError, ValueError):
            return Response({'error': 'Élève introuvable'}, status=404)
        annee = request.query_params.get('annee') or _get_annee_scolaire(tenant)
        programme = programme_valide(request.query_params.get('programme'))
        fiche = fiche_pedagogique(tenant, eleve, annee, programme)
        classe_nom = (eleve.classe.nom if eleve.classe_id
                      else (eleve.section.nom if eleve.section else '—'))

        if not self.pdf:
            return Response({**fiche, 'eleve': {'id': str(eleve.id), 'nom_complet': eleve.nom_complet,
                                                 'classe': classe_nom}})

        from io import BytesIO
        from django.utils import timezone
        from xhtml2pdf import pisa
        from core.arabe import font_link_callback
        from .libelles import contexte_fiche
        langue = 'ar' if programme == 'AR' else 'fr'
        context = contexte_fiche(fiche, tenant, eleve, classe_nom, langue)
        context['date_edition'] = timezone.localdate()
        html_str = render_to_string('pdf/fiche_pedagogique.html', context)
        buffer = BytesIO()
        result = pisa.CreatePDF(html_str, dest=buffer, encoding='utf-8', link_callback=font_link_callback)
        if result.err:
            return HttpResponse('Erreur génération fiche pédagogique.', status=500)
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        nom = eleve.nom_complet.replace(' ', '_').replace('/', '-')
        response['Content-Disposition'] = f'inline; filename="fiche_pedagogique_{nom}_{langue}.pdf"'
        return response


def _imposer_deux_par_feuille(pdfs_bulletins):
    """Empile deux bulletins par feuille A4 et trace le trait de découpe.

    L'assemblage se fait sur les PDF finis, pas dans le gabarit : xhtml2pdf
    ignore « page-break-inside: avoid », et deux bulletins empilés dans une
    page A4 se coupaient en plein milieu dès qu'une classe avait dix
    matières. Ici chaque bulletin arrive sur sa ou ses demi-pages.

    Un bulletin qui déborde sa demi-page (une classe à quinze matières)
    prend la feuille entière, sans trait : mieux vaut une feuille de plus
    qu'un bulletin déchiré en deux au ciseau.
    """
    from io import BytesIO
    from pypdf import PageObject, PdfReader, PdfWriter, Transformation

    A4_L, A4_H = 595.276, 841.89          # points PDF
    demi = A4_H / 2

    # Composition des feuilles : (demi-pages, trait de découpe ou non).
    feuilles = []
    en_attente = None                      # demi-page du haut, sans voisin encore
    for donnees in pdfs_bulletins:
        pages = PdfReader(BytesIO(donnees)).pages
        if len(pages) == 1:
            if en_attente is None:
                en_attente = pages[0]
            else:
                feuilles.append(([en_attente, pages[0]], True))
                en_attente = None
            continue
        if en_attente is not None:         # on ne mélange pas un long et un court
            feuilles.append(([en_attente], False))
            en_attente = None
        for i in range(0, len(pages), 2):
            feuilles.append((list(pages[i:i + 2]), False))
    if en_attente is not None:
        feuilles.append(([en_attente], False))

    ecrivain = PdfWriter()
    repere = _repere_decoupe(A4_L, A4_H)
    for demi_pages, trait in feuilles:
        feuille = PageObject.create_blank_page(width=A4_L, height=A4_H)
        # L'origine PDF est en bas à gauche : la première demi-page est celle
        # du haut, donc c'est elle qu'on remonte d'une demi-feuille.
        feuille.merge_transformed_page(demi_pages[0], Transformation().translate(0, demi))
        if len(demi_pages) > 1:
            feuille.merge_transformed_page(demi_pages[1], Transformation())
        # Pas de repère quand il n'y a rien à séparer : un trait inutile
        # invite à couper un bulletin en deux.
        if trait:
            feuille.merge_page(repere)
        ecrivain.add_page(feuille)

    sortie = BytesIO()
    ecrivain.write(sortie)
    return sortie.getvalue()


def _repere_decoupe(largeur, hauteur):
    """Calque d'une feuille : pointillés et ciseaux à mi-hauteur.

    Le trait doit se voir d'un coup d'œil sur une pile de feuilles, sinon
    l'école coupe de travers.
    """
    from io import BytesIO
    from pypdf import PdfReader
    from reportlab.pdfgen import canvas

    tampon = BytesIO()
    c = canvas.Canvas(tampon, pagesize=(largeur, hauteur))
    y = hauteur / 2
    c.setStrokeColorRGB(0.47, 0.56, 0.61)
    c.setDash(3, 3)
    c.setLineWidth(0.6)
    c.line(14, y, largeur - 14, y)
    c.setDash()
    c.setFillColorRGB(0.47, 0.56, 0.61)
    from reportlab.pdfbase.pdfmetrics import stringWidth

    police, corps, espacement = 'Helvetica', 6, 1.5
    texte = '\u2702  DÉCOUPER ICI'
    # Centrage à la main : stringWidth ignore l'espacement des lettres, et le
    # repère se retrouverait décalé d'un centimètre vers la gauche.
    largeur_texte = stringWidth(texte, police, corps) + espacement * len(texte)
    ligne = c.beginText((largeur - largeur_texte) / 2, y + 2.5)
    ligne.setFont(police, corps)
    ligne.setCharSpace(espacement)      # lettres espacées : le repère se lit de loin
    ligne.textOut(texte)
    c.drawText(ligne)
    c.showPage()
    c.save()
    tampon.seek(0)
    return PdfReader(tampon).pages[0]


class BulletinsClassePDFView(APIView):
    """Tous les bulletins d'une classe, deux par feuille A4.

    Une classe de 40 élèves consommait 40 feuilles, éditées une par une. On
    les édite en un seul document, deux par page, séparés par un trait de
    découpe : autant de bulletins, moitié moins de papier, et plus personne
    ne clique 40 fois.

    GET /api/academique/bulletins-classe/<classe_id>/<trimestre>/?programme=FR
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, classe_id, trimestre):
        from io import BytesIO

        tenant = get_tenant(request)
        annee = request.query_params.get('annee') or _get_annee_scolaire(tenant)
        programme = programme_valide(request.query_params.get('programme'))

        try:
            classe = Classe.objects.get(id=classe_id, tenant=tenant)
        except Classe.DoesNotExist:
            return HttpResponse('Classe introuvable', status=404)

        from apps.eleves.tri import cle_nom
        eleves = sorted(
            Eleve.objects.filter(tenant=tenant, classe=classe).select_related('section', 'classe'),
            key=lambda e: cle_nom(e.nom_complet))

        # Un élève sans aucune note n'a pas de bulletin : on l'ignore plutôt
        # que d'imprimer une feuille vide à son nom.
        corps = []
        sans_notes = []
        for eleve in eleves:
            contexte = contexte_bulletin(tenant, eleve, trimestre, annee, programme)
            if contexte is None:
                sans_notes.append(eleve.nom_complet)
                continue
            contexte.pop('_lignes', None)
            corps.append(render_to_string('pdf/_bulletin_corps.html', contexte))

        if not corps:
            return HttpResponse(
                "Aucun bulletin à éditer : aucun élève de cette classe n'a de note "
                f"sur la période {trimestre}.", status=404)

        # xhtml2pdf et lui seul : c'est le moteur embarqué chez l'école (il
        # arrive avec les dépendances du backend, weasyprint non). S'en
        # remettre à weasyprint quand il est là ferait voir en développement
        # une mise en page que personne n'imprime.
        from xhtml2pdf import pisa

        documents = []
        for corps_bulletin in corps:
            html_str = render_to_string('pdf/bulletins_classe.html',
                                        {'bulletins': [corps_bulletin],
                                         'classe': classe, 'tenant': tenant})
            buffer = BytesIO()
            if pisa.CreatePDF(html_str, dest=buffer, encoding='utf-8').err:
                return HttpResponse('Erreur génération des bulletins.', status=500)
            documents.append(buffer.getvalue())

        pdf = _imposer_deux_par_feuille(documents)

        reponse = HttpResponse(pdf, content_type='application/pdf')
        reponse['Content-Disposition'] = (
            f'inline; filename="bulletins_{classe.nom}_{trimestre}.pdf"')
        # L'école doit savoir qui manque, sans ouvrir les 40 bulletins.
        if sans_notes:
            reponse['X-Sans-Notes'] = str(len(sans_notes))
        return reponse
