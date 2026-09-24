"""Ramène les moyennes calculées sous l'année de l'exercice de l'école.

    python manage.py realigner_annee_bulletins --ecole "Shoumoul"              # simulation
    python manage.py realigner_annee_bulletins --ecole "Shoumoul" --appliquer

Jusqu'à la v1.51.1, l'écran Gestion académique envoyait au calcul des moyennes
l'année du CALENDRIER (« 2025-2026 », puis « 2026-2027 » dès le 1er
septembre). L'analyse, le suivi pédagogique et les bulletins lisent l'année de
l'EXERCICE (« 2026 » chez Shoumoul) : ils ne trouvaient rien et restaient vides.

Une moyenne ne dépend pas de l'année sous laquelle elle est rangée — le calcul
part des notes de la période. La commande recalcule donc, sous l'année de
l'exercice ouvert, chaque classe et chaque période déjà calculées sous une
année qu'aucun exercice ne porte, puis supprime ces lignes orphelines. Les
notes ne sont pas touchées.

Sans --appliquer : rien n'est modifié, la commande dit ce qu'elle ferait.
"""
from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.academique.models import BulletinCache, Classe
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Recalcule sous l'année de l'exercice les moyennes rangées sous une année inconnue."

    def add_arguments(self, parser):
        parser.add_argument('--ecole', required=True)
        parser.add_argument('--appliquer', action='store_true',
                            help='Recalculer et supprimer (sinon : simulation)')

    def handle(self, *args, **opts):
        from apps.paiements.models import Exercice

        ecoles = list(Tenant.objects.filter(nom__icontains=opts['ecole']))
        if len(ecoles) != 1:
            raise CommandError(f"Il faut exactement une école ; trouvé : "
                               f"{', '.join(t.nom for t in ecoles) or 'aucune'}")
        tenant = ecoles[0]

        exercice = (Exercice.objects.filter(tenant=tenant, cloture=False)
                    .order_by('-date_debut').first())
        if exercice is None:
            raise CommandError("Aucun exercice ouvert : pas d'année sous laquelle recalculer.")
        annees_connues = set(Exercice.objects.filter(tenant=tenant)
                             .values_list('annee_scolaire', flat=True))
        orphelines = BulletinCache.objects.filter(tenant=tenant).exclude(
            annee_scolaire__in=annees_connues)

        self.stdout.write(f"École : {tenant.nom} — exercice ouvert : « {exercice.annee_scolaire} »")
        par_annee = defaultdict(int)
        for annee in orphelines.values_list('annee_scolaire', flat=True):
            par_annee[annee] += 1
        if not par_annee:
            self.stdout.write(self.style.SUCCESS("Aucune moyenne sous une année inconnue : rien à faire."))
            return
        for annee, n in sorted(par_annee.items()):
            self.stdout.write(f"  « {annee} » : {n} ligne(s) de moyenne, lue(s) par aucun écran")

        # (classe, période) → programmes : ce qui a été calculé, à recalculer.
        a_recalculer = defaultdict(set)
        for classe_id, periode, programme in orphelines.values_list(
                'eleve__classe_id', 'trimestre', 'matiere__programme').distinct():
            if classe_id:
                a_recalculer[(classe_id, periode)].add(programme)
        classes = {c.id: c.nom for c in Classe.objects.filter(id__in={c for c, _ in a_recalculer})}

        self.stdout.write(f"\nÀ recalculer sous « {exercice.annee_scolaire} » :")
        for (classe_id, periode) in sorted(a_recalculer, key=lambda k: (classes.get(k[0], ''), k[1])):
            self.stdout.write(f"  {classes.get(classe_id, '?')} — {periode}")

        if not opts['appliquer']:
            self.stdout.write(self.style.WARNING(
                "\nSimulation : rien n'a été modifié. Relancer avec --appliquer."))
            return

        with transaction.atomic():
            for (classe_id, periode), programmes in a_recalculer.items():
                # Établissement hybride : une moyenne par programme ; sinon un
                # seul calcul couvre toutes les matières.
                for programme in (programmes if tenant.programmes_hybrides else {None}):
                    reponse = _calculer(tenant, classe_id, periode, programme)
                    if reponse.status_code != 200:
                        raise CommandError(
                            f"Échec du calcul {classes.get(classe_id, '?')} {periode} : "
                            f"{getattr(reponse, 'data', reponse.status_code)} — rien n'a été modifié.")
            supprimees, _ = orphelines.delete()

        self.stdout.write(self.style.SUCCESS(
            f"\n{len(a_recalculer)} classe(s)/période(s) recalculée(s) sous "
            f"« {exercice.annee_scolaire} », {supprimees} ligne(s) orpheline(s) supprimée(s)."))


def _calculer(tenant, classe_id, periode, programme):
    """Le calcul de l'écran, tel quel : un seul moteur pour les moyennes."""
    from rest_framework.test import APIRequestFactory, force_authenticate

    from apps.academique.views import MoteurCalculView
    from apps.users.models import User

    utilisateur = User.objects.filter(tenant=tenant, actif=True).order_by('created_at').first()
    if utilisateur is None:
        raise CommandError(f"{tenant.nom} n'a aucun utilisateur actif : calcul impossible.")
    donnees = {'classe_id': str(classe_id), 'trimestre': periode}
    if programme:
        donnees['programme'] = programme
    requete = APIRequestFactory().post('/api/academique/calculer/', donnees, format='json')
    requete.tenant = tenant          # ce que pose le middleware en temps normal
    force_authenticate(requete, user=utilisateur)
    return MoteurCalculView.as_view()(requete)
