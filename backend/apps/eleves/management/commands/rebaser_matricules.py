"""Renumérote les matricules au format promo AAAA-CODE-NNNN.

  python manage.py rebaser_matricules --settings=config.settings.production
      [--tenant <code ou nom>] [--tout] [--appliquer]

Sans --appliquer : diagnostic seul, affiche la correspondance ancien → nouveau
sans rien écrire. C'est le mode par défaut : on regarde avant de renuméroter
toute une école.

L'ancien matricule est conservé dans `matricule_ancien` — les carnets papier
et les anciens reçus restent exploitables. La commande est rejouable : un
second passage recalcule les mêmes matricules et ne touche plus rien.
"""
from django.core.management.base import BaseCommand, CommandError

from apps.eleves.rebasage import appliquer_rebasage, calculer_rebasage
from apps.tenants.models import Tenant

APERCU = 40


class Command(BaseCommand):
    help = "Renumérote les matricules par promo et ordre d'entrée"

    def add_arguments(self, parser):
        parser.add_argument('--tenant', help="Code ou nom de l'école (défaut : la seule école)")
        parser.add_argument('--tout', action='store_true',
                            help='Afficher toutes les lignes (défaut : les %d premières)' % APERCU)
        parser.add_argument('--appliquer', action='store_true',
                            help='Écrire réellement (sinon diagnostic seul)')

    def _tenant(self, arg):
        qs = Tenant.objects.all()
        if arg:
            t = (qs.filter(code_etablissement__iexact=arg).first()
                 or qs.filter(nom__icontains=arg).first())
            if not t:
                raise CommandError(f"École introuvable : {arg}")
            return t
        if qs.count() != 1:
            raise CommandError("Plusieurs écoles en base — précisez --tenant.")
        return qs.first()

    def handle(self, *args, **opts):
        tenant = self._tenant(opts.get('tenant'))
        appliquer = opts['appliquer']

        self.stdout.write(
            f"École : {tenant}\n"
            f"Rebasage des matricules{'' if appliquer else '  (DIAGNOSTIC)'}\n")

        rapport = (appliquer_rebasage(tenant) if appliquer
                   else calculer_rebasage(tenant))

        lignes = [l for l in rapport['lignes'] if l['change']]
        for ligne in (lignes if opts['tout'] else lignes[:APERCU]):
            self.stdout.write(
                f"  {ligne['nom_complet'][:30]:<30} "
                f"{(ligne['ancien'] or '—'):<20} → {ligne['nouveau']:<18} "
                f"{ligne['promo']:<10} entré le {ligne['date_entree']:%d/%m/%Y}"
                + (f"  ({ligne['nb_fiches']} fiches)" if ligne['nb_fiches'] > 1 else ''))

        if not opts['tout'] and len(lignes) > APERCU:
            self.stdout.write(f"  … et {len(lignes) - APERCU} autre(s) — --tout pour tout voir")

        self.stdout.write(
            f"\n{rapport['nb_eleves']} élève(s) distinct(s) sur "
            f"{rapport['nb_fiches']} fiche(s) — "
            f"{rapport['nb_changements']} matricule(s) à changer")

        if appliquer:
            self.stdout.write(self.style.SUCCESS(
                f"✓ {rapport['nb_fiches_ecrites']} fiche(s) mise(s) à jour."))
        elif rapport['nb_changements']:
            self.stdout.write(self.style.WARNING(
                "Diagnostic seul — relancez avec --appliquer pour écrire."))
        else:
            self.stdout.write(self.style.SUCCESS("✓ Rien à changer."))
