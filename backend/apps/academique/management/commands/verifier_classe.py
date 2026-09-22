"""Une classe passée au crible : anomalies de notes, puis relevé complet.

    python manage.py verifier_classe --ecole "Shoumoul" --classe "CE1" --periode S2

Imprime d'abord ce qui fausse les moyennes, puis le relevé de la classe tel que
le SYSTÈME le lit — une ligne par élève, une colonne par matière, la note sur
le barème de son évaluation, puis le total et la moyenne qu'imprime le
bulletin — pour le comparer, ligne à ligne, à la feuille de l'enseignant.

Anomalies cherchées (période donnée) :
  1. évaluation sur un barème différent de celui de sa matière ;
  2. note supérieure au barème de son évaluation (saisie avant la validation) ;
  3. plusieurs évaluations dans la même matière : elles sont moyennées ;
  4. élève sans note à une évaluation que d'autres ont passée : il compte 0 ;
  5. évaluation sans aucune note : ignorée par le calcul.

Lecture seule : rien n'est modifié.
"""
from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError

from apps.academique.models import Classe, Evaluation, Matiere, Note
from apps.academique.resultats import situation_periode
from apps.tenants.models import Tenant


def _n(valeur):
    """Décimal → texte court : 10, 7,5."""
    return f'{float(valeur):g}'.replace('.', ',')


class Command(BaseCommand):
    help = "Anomalies de notes et relevé complet d'une classe pour une période."

    def add_arguments(self, parser):
        parser.add_argument('--ecole', required=True)
        parser.add_argument('--classe', required=True, help='Nom ou partie du nom de la classe')
        parser.add_argument('--periode', required=True, help='Code de la période : T1, S2…')

    def handle(self, *args, **opts):
        from apps.eleves.models import Eleve
        from apps.paiements.models import Exercice

        ecoles = list(Tenant.objects.filter(nom__icontains=opts['ecole']))
        if len(ecoles) != 1:
            raise CommandError(f"Il faut exactement une école ; trouvé : "
                               f"{', '.join(t.nom for t in ecoles) or 'aucune'}")
        tenant = ecoles[0]
        classes = list(Classe.objects.filter(tenant=tenant, nom__icontains=opts['classe']))
        if len(classes) != 1:
            raise CommandError(f"Il faut exactement une classe ; trouvé : "
                               f"{', '.join(c.nom for c in classes) or 'aucune'}")
        classe = classes[0]
        periode = opts['periode'].upper()

        exercice = (Exercice.objects.filter(tenant=tenant, cloture=False)
                    .order_by('-date_debut').first())
        eleves = Eleve.objects.filter(tenant=tenant, classe=classe)
        if exercice:
            eleves = eleves.filter(exercice=exercice)
        eleves = sorted(eleves, key=lambda e: e.nom_complet)
        matieres = list(Matiere.objects.filter(tenant=tenant, classe=classe, est_active=True)
                        .order_by('ordre', 'nom'))
        evaluations = list(Evaluation.objects.filter(tenant=tenant, matiere__in=matieres,
                                                     trimestre=periode)
                           .select_related('type_eval', 'matiere').order_by('date_eval'))
        notes = {(n.eleve_id, n.evaluation_id): n
                 for n in Note.objects.filter(tenant=tenant, evaluation__in=evaluations,
                                              eleve__in=eleves)}
        par_matiere = defaultdict(list)
        for ev in evaluations:
            par_matiere[ev.matiere_id].append(ev)

        def nom_ev(ev):
            return f"{ev.matiere.nom} · {ev.type_eval.nom} {ev.titre or ''}".strip()

        self.stdout.write(f"École : {tenant.nom} — classe {classe.nom} — période {periode}")
        self.stdout.write(f"{len(eleves)} élève(s), {len(matieres)} matière(s), "
                          f"{len(evaluations)} évaluation(s)\n")

        anomalies = 0

        def signaler(texte):
            nonlocal anomalies
            anomalies += 1
            self.stdout.write(f"  ⚠ {texte}")

        for m in matieres:
            evs = par_matiere.get(m.id, [])
            if not evs:
                signaler(f"{m.nom} (/{_n(m.note_max)}) : aucune évaluation sur {periode} "
                         "— la matière manquera au bulletin")
                continue
            notees = [ev for ev in evs if any((e.id, ev.id) in notes for e in eleves)]
            if len(notees) > 1:
                signaler(f"{m.nom} : {len(notees)} évaluations notées sur {periode} — elles "
                         f"sont MOYENNÉES ({', '.join(nom_ev(ev) for ev in notees)})")
            for ev in evs:
                if ev.note_max != m.note_max:
                    signaler(f"{nom_ev(ev)} : évaluation /{_n(ev.note_max)}, matière "
                             f"/{_n(m.note_max)} — un 10 saisi vaut "
                             f"{_n(10 * float(m.note_max) / float(ev.note_max))} sur la matière")
                if ev not in notees:
                    signaler(f"{nom_ev(ev)} : aucune note (ignorée par le calcul)")
                    continue
                for e in eleves:
                    n = notes.get((e.id, ev.id))
                    if n is None:
                        signaler(f"{nom_ev(ev)} : {e.nom_complet} n'a PAS de note — compte 0")
                    elif not n.absent and n.valeur > ev.note_max:
                        signaler(f"{nom_ev(ev)} : {e.nom_complet} a {_n(n.valeur)} "
                                 f"sur /{_n(ev.note_max)}")
                    elif n.absent:
                        signaler(f"{nom_ev(ev)} : {e.nom_complet} marqué ABSENT — compte 0")

        if not anomalies:
            self.stdout.write("  Aucune anomalie de saisie.")

        # ── Relevé : ce que le système lit, élève par élève ─────────────────
        self.stdout.write(f"\nRELEVÉ {classe.nom} — {periode} (note/barème de l'évaluation)")
        for e in eleves:
            cellules = []
            for m in matieres:
                vals = []
                for ev in par_matiere.get(m.id, []):
                    n = notes.get((e.id, ev.id))
                    if n is None:
                        continue
                    vals.append('abs' if n.absent else
                                (_n(n.valeur) + ('' if ev.note_max == m.note_max
                                                 else f'/{_n(ev.note_max)}')))
                cellules.append('+'.join(vals) or '—')
            situation = situation_periode(tenant, e, periode, exercice.annee_scolaire
                                          if exercice else '')
            if situation:
                fin = (f"TOTAL {_n(situation['total_points'])} — MOYENNE "
                       f"{_n(situation['moy_generale'])} — rang {situation['rang']}")
            else:
                fin = "moyenne non calculée (relancer « Calculer Moyennes »)"
            self.stdout.write(f"\n{e.nom_complet} : {fin}")
            self.stdout.write('  ' + ' | '.join(f"{m.nom}: {c}" for m, c in zip(matieres, cellules)))
