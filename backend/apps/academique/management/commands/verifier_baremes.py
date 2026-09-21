"""Évaluations qui faussent les moyennes : diagnostic, puis correction.

Deux défauts donnent tous deux « 10 saisi, 5 affiché » :

  1. une évaluation SUR UN BARÈME PLUS GRAND que sa matière (matière /10,
     évaluation restée /20 après un changement de barème) : 10 y vaut 10/20 ;
  2. une évaluation SANS AUCUNE NOTE (créée deux fois, ou pas encore passée).
     Le calcul l'ignore désormais ; la liste permet de la supprimer.

    python manage.py verifier_baremes --ecole "Shoumoul"
    python manage.py verifier_baremes --ecole "Shoumoul" --aligner

`--aligner` ramène au barème de la matière les évaluations du cas 1 dont
aucune note ne dépasse ce barème. Les notes ne sont jamais converties. Les
moyennes des matières touchées sont effacées : relancer « Calculer Moyennes ».
"""
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Max

from apps.academique.models import BulletinCache, Evaluation
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Évaluations au barème incohérent ou sans note (moyennes divisées par deux)."

    def add_arguments(self, parser):
        parser.add_argument('--ecole', required=True, help="Nom (ou partie du nom) de l'école")
        parser.add_argument('--aligner', action='store_true',
                            help="Ramener ces évaluations au barème de leur matière")

    def handle(self, *args, **opts):
        ecoles = list(Tenant.objects.filter(nom__icontains=opts['ecole']))
        if len(ecoles) != 1:
            noms = ', '.join(t.nom for t in ecoles) or 'aucune'
            raise CommandError(f"Il faut exactement une école ; trouvé : {noms}")
        tenant = ecoles[0]
        evaluations = (Evaluation.objects.filter(tenant=tenant)
                       .select_related('matiere__classe', 'type_eval')
                       .annotate(nb_notes=Count('notes'), plus_haute=Max('notes__valeur'))
                       .order_by('matiere__classe__nom', 'matiere__nom', 'trimestre'))

        def libelle(ev):
            return (f"{ev.matiere.classe.nom} · {ev.matiere.nom} · {ev.trimestre} · "
                    f"{ev.type_eval.nom} {ev.titre or ''}".strip())

        self.stdout.write(f"École : {tenant.nom}\n")
        a_aligner, bloquees, vides = [], [], []
        for ev in evaluations:
            if ev.nb_notes == 0:
                vides.append(ev)
            elif ev.note_max > ev.matiere.note_max:
                if ev.plus_haute is None or ev.plus_haute <= ev.matiere.note_max:
                    a_aligner.append(ev)
                else:
                    bloquees.append(ev)

        self.stdout.write(f"\n1. Barème plus grand que la matière (10 saisi → 5 compté) : {len(a_aligner)}")
        for ev in a_aligner:
            self.stdout.write(f"   - {libelle(ev)} : évaluation /{float(ev.note_max):g}, matière "
                              f"/{float(ev.matiere.note_max):g}, {ev.nb_notes} note(s), max {float(ev.plus_haute):g}")
        if bloquees:
            self.stdout.write(f"\n   Non alignables (une note dépasse le barème de la matière) : {len(bloquees)}")
            for ev in bloquees:
                self.stdout.write(f"   - {libelle(ev)} : /{float(ev.note_max):g}, note max {float(ev.plus_haute):g} "
                                  f"> /{float(ev.matiere.note_max):g} — à vérifier à la main")

        self.stdout.write(f"\n2. Évaluations sans aucune note (ignorées par le calcul) : {len(vides)}")
        for ev in vides:
            self.stdout.write(f"   - {libelle(ev)} (/{float(ev.note_max):g})")

        if not opts['aligner']:
            if a_aligner:
                self.stdout.write("\nRelancez avec --aligner pour corriger le point 1.")
            return

        matieres = set()
        for ev in a_aligner:
            ev.note_max = ev.matiere.note_max
            ev.save(update_fields=['note_max'])
            matieres.add(ev.matiere_id)
        effacees, _ = BulletinCache.objects.filter(tenant=tenant, matiere_id__in=matieres).delete()
        self.stdout.write(self.style.SUCCESS(
            f"\n{len(a_aligner)} évaluation(s) alignée(s), {effacees} moyenne(s) effacée(s). "
            "Relancez « Calculer Moyennes » pour chaque classe et chaque période."))
