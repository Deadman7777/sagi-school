"""Ramène les reliquats reportés pour des élèves sortis à ce qui était dû au départ.

    python manage.py recaler_reliquats_sortants --ecole "Shoumoul" --settings=config.settings.cloud
    python manage.py recaler_reliquats_sortants --ecole "Shoumoul" --appliquer --settings=...

Sans --appliquer : simple rapport, rien n'est écrit.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.paiements.recalage_sortants import recaler_reliquats_sortants
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Recale les reliquats des élèves sortis sur le dû au jour du départ."

    def add_arguments(self, parser):
        parser.add_argument('--ecole', required=True, help="Nom (partiel) ou id de l'école")
        parser.add_argument('--appliquer', action='store_true', help='Écrire les corrections')

    def handle(self, *args, ecole, appliquer, **options):
        qs = Tenant.objects.filter(id=ecole) if len(ecole) == 36 else Tenant.objects.filter(nom__icontains=ecole)
        if qs.count() != 1:
            from apps.eleves.models import Eleve
            detail = "\n".join(
                f"  {t.id}  {t.nom}  ({Eleve.objects.filter(tenant=t).count()} fiches"
                f"{', inactive' if not getattr(t, 'actif', True) else ''})" for t in qs)
            raise CommandError(f"{qs.count()} école(s) correspondent à « {ecole} ». "
                               f"Relancez avec --ecole <id> :\n{detail}")
        tenant = qs.get()
        with transaction.atomic():
            r = recaler_reliquats_sortants(tenant, appliquer=appliquer)
        self.stdout.write(f"École : {tenant.nom} — {'CORRECTIONS APPLIQUÉES' if appliquer else 'SIMULATION (rien écrit)'}")
        for l in r['lignes']:
            note = '  (plafonné à l\'encaissé)' if l['plafonne_a_l_encaisse'] else ''
            self.stdout.write(
                f"  {l['matricule']:<18} {l['nom_complet'][:32]:<32} sorti le {l['sortie']:%d/%m/%Y}  "
                f"{l['avant']:>12,.0f} → {l['apres']:>12,.0f}{note}")
        self.stdout.write(f"{r['nb']} fiche(s) · avant {r['total_avant']:,.0f} · après {r['total_apres']:,.0f} "
                          f"· réduction {r['reduction']:,.0f} FCFA")
        if not appliquer and r['nb']:
            self.stdout.write(self.style.WARNING("Relancez avec --appliquer pour écrire ces corrections."))
