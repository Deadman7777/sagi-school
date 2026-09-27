"""Relie l'existant : ressources de Gouvernance ↔ financements et prêts GMRF.

Avant la liaison automatique (v1.53), une subvention reçue dans GMRF était
ressaisie à la main dans Gouvernance. Cette commande reprend l'existant :

1. chaque financement reçu et chaque prêt sans ressource est RELIÉ à la
   ressource saisie à la main qui lui correspond (même montant, même
   organisme ou même libellé) — jamais dupliqué ;
2. à défaut de correspondance, sa ressource est créée ;
3. les ressources saisies à la main qui ne correspondent à aucune opération
   GMRF et n'ont pas de compte de trésorerie sont LISTÉES : leur argent n'est
   dans aucun compte. L'école décide (les annuler, ou les encaisser dans GMRF).

Simulation par défaut ; --appliquer pour écrire.

    python manage.py lier_ressources_gmrf [--ecole CODE] [--appliquer]
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.gmrf.models import Financement, Pret
from apps.gouvernance.liaison_gmrf import SANS_ENCAISSEMENT, suivre_financement, suivre_pret
from apps.gouvernance.models import Ressource
from apps.tenants.models import Tenant


def _proche(a, b):
    a, b = (a or '').strip().lower(), (b or '').strip().lower()
    return bool(a and b and (a in b or b in a))


class Command(BaseCommand):
    help = "Relie les ressources de Gouvernance aux financements et prêts GMRF (simulation par défaut)."

    def add_arguments(self, parser):
        parser.add_argument('--ecole', help="Code établissement (toutes les écoles sinon)")
        parser.add_argument('--appliquer', action='store_true', help="Écrire (sinon simulation)")

    def handle(self, *args, **opts):
        ecoles = Tenant.objects.all()
        if opts.get('ecole'):
            ecoles = ecoles.filter(code_etablissement=opts['ecole'])
        appliquer = opts['appliquer']
        with transaction.atomic():
            for tenant in ecoles:
                self._ecole(tenant, appliquer)
            if not appliquer:
                transaction.set_rollback(True)
        self.stdout.write(self.style.WARNING('Simulation : rien n\'a été écrit (--appliquer pour écrire).')
                          if not appliquer else self.style.SUCCESS('Liaison appliquée.'))

    def _ecole(self, tenant, appliquer):
        libres = list(Ressource.objects.filter(tenant=tenant, financement__isnull=True, pret__isnull=True)
                      .exclude(statut='ANNULEE'))
        lignes = []

        def correspondance(montant, organisme, libelle):
            for r in libres:
                if r.montant == montant and (_proche(r.organisme, organisme) or _proche(r.libelle, libelle)):
                    libres.remove(r)
                    return r
            return None

        for f in (Financement.objects.filter(tenant=tenant, statut='RECU', ressources_gouv__isnull=True)
                  .select_related('type_financement')):
            r = correspondance(f.montant, f.source, f.libelle)
            if r:
                r.financement = f
                r.save(update_fields=['financement', 'updated_at'])
                lignes.append(f'  relié   {f.reference} → {r.reference} (saisie manuelle existante)')
            else:
                lignes.append(f'  créé    {f.reference} → nouvelle ressource')
            suivre_financement(f)

        for p in Pret.objects.filter(tenant=tenant, ressources_gouv__isnull=True):
            r = correspondance(p.montant, p.organisme_preteur, p.objet)
            if r:
                r.pret = p
                r.save(update_fields=['pret', 'updated_at'])
                lignes.append(f'  relié   {p.reference} → {r.reference} (saisie manuelle existante)')
            else:
                lignes.append(f'  créé    {p.reference} → nouvelle ressource')
            suivre_pret(p)

        hors_tresorerie = [r for r in libres
                           if r.type_ressource not in SANS_ENCAISSEMENT and not r.compte_tresorerie]
        if lignes or hors_tresorerie:
            self.stdout.write(self.style.MIGRATE_HEADING(f'{tenant.nom}'))
            for l in lignes:
                self.stdout.write(l)
            for r in hors_tresorerie:
                self.stdout.write(self.style.WARNING(
                    f'  À RÉGULARISER {r.reference} « {r.libelle} » {r.montant:,.0f} F : '
                    f'aucune opération GMRF, aucun compte de trésorerie.'))
