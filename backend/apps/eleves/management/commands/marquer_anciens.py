"""Renseigne la date d'entrée des fiches qui n'en ont pas.

Le renouvellement décide « nouveau ou ancien » à partir de `date_entree`, la
date de première entrée dans l'établissement — figée à vie et recopiée à chaque
réinscription. Les fiches créées avant l'existence de ce champ ne la portent
pas, et la règle est prudente : sans information, l'élève est un NOUVEL ENTRANT
et doit son inscription. Une école migrée pouvait donc activer le renouvellement
et n'en voir aucun effet.

`date_inscription` — que le formulaire de création intitule « Date d'entrée » —
porte la vraie date d'arrivée chez les écoles qui l'ont saisie. Cette commande
la recopie vers `date_entree`, et en déduit la promo.

Elle ne touche QUE les fiches dont `date_entree` est vide : une date déjà
renseignée est une donnée établie, elle n'a pas à être réécrite par un outil de
rattrapage.

    python manage.py marquer_anciens --simuler
    python manage.py marquer_anciens
    python manage.py marquer_anciens --ecole SHO
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.eleves.matricules import libelle_promo
from apps.eleves.models import Eleve
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = ("Recopie la date d'inscription vers la date d'entrée sur les fiches "
            "qui n'en ont pas — condition pour que le renouvellement s'applique.")

    def add_arguments(self, parser):
        parser.add_argument(
            '--ecole', dest='code',
            help="Code de l'établissement à traiter. À défaut, toutes les écoles.")
        parser.add_argument(
            '--simuler', action='store_true',
            help='Affiche ce qui changerait sans rien écrire.')

    def handle(self, *args, **options):
        simuler = options['simuler']
        tenants = Tenant.objects.all()
        if code := options.get('code'):
            tenants = tenants.filter(code_etablissement__iexact=code)
            if not tenants.exists():
                self.stderr.write(self.style.ERROR(
                    f"Aucune école avec le code « {code} »."))
                return

        for tenant in tenants:
            self._traiter(tenant, simuler)

    def _traiter(self, tenant, simuler):
        fiches = list(Eleve.objects
                      .filter(tenant=tenant, date_entree__isnull=True)
                      .select_related('exercice', 'tenant')
                      .order_by('nom_complet'))
        total = Eleve.objects.filter(tenant=tenant).count()
        seuil = int(getattr(tenant, 'anciennete_renouvellement_mois', 12) or 12)

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"{tenant.nom} ({tenant.code_etablissement}) — "
            f"{len(fiches)} fiche(s) sans date d'entrée sur {total}"))

        if not fiches:
            # « Rien à faire » ne répond pas à la question qu'on se pose en
            # lançant cette commande : le renouvellement va-t-il s'appliquer, et
            # à combien d'élèves ? On l'annonce donc quand même.
            self.stdout.write("  Rien à rattraper — toutes les fiches ont leur "
                              "date d'entrée.")
            self._etat_actuel(tenant, seuil)
            return
        a_ecrire, anciens = [], 0

        for e in fiches:
            if not e.date_inscription or not e.exercice_id:
                continue
            e.date_entree = e.date_inscription
            e.annee_entree = libelle_promo(e.exercice, e.date_entree)
            a_ecrire.append(e)
            # `est_renouvelant` relit date_entree, qu'on vient de poser en
            # mémoire : le décompte annonce donc l'effet réel de l'écriture.
            if e.est_renouvelant:
                anciens += 1

        for e in a_ecrire[:10]:
            statut = 'ancien' if e.est_renouvelant else 'nouveau'
            self.stdout.write(
                f"  {e.nom_complet:<32} {e.date_entree}  {statut}")
        if len(a_ecrire) > 10:
            self.stdout.write(f"  … et {len(a_ecrire) - 10} autre(s)")

        self.stdout.write(
            f"  → {anciens} ancien(s) au seuil de {seuil} mois, "
            f"{len(a_ecrire) - anciens} nouvel(le)s entrant(s)")

        if simuler:
            self.stdout.write(self.style.WARNING(
                "  SIMULATION — rien n'a été écrit."))
            return

        with transaction.atomic():
            Eleve.objects.bulk_update(a_ecrire, ['date_entree', 'annee_entree'],
                                      batch_size=500)
        self.stdout.write(self.style.SUCCESS(
            f"  {len(a_ecrire)} fiche(s) mises à jour."))
        self._etat_actuel(tenant, seuil)

    def _etat_actuel(self, tenant, seuil):
        """Ce que le renouvellement donnera en l'état, réglages compris.

        Sans ce compte-rendu, l'école active le renouvellement, saisit ses
        montants, et n'a aucun moyen de savoir avant la première saisie de
        paiement si la bascule a pris — ni sur combien d'élèves."""
        eleves = list(Eleve.objects.filter(tenant=tenant, statut='INSCRIT')
                      .select_related('exercice', 'tenant', 'section'))
        if not eleves:
            return

        anciens = [e for e in eleves if e.est_renouvelant]
        actif = getattr(tenant, 'renouvellement_actif', False)

        self.stdout.write(
            f"  Au seuil de {seuil} mois : {len(anciens)} ancien(s), "
            f"{len(eleves) - len(anciens)} nouvel(le)s entrant(s) "
            f"sur {len(eleves)} inscrit(s).")

        if not actif:
            self.stdout.write(self.style.WARNING(
                "  Le renouvellement n'est PAS activé : ces anciens élèves "
                "doivent encore l'inscription. Paramètres → Tarifs."))
            return

        # Un niveau à 0 est un renouvellement gratuit — décision légitime, mais
        # rarement voulue quand on vient d'activer le réglage.
        muets = sorted({e.section.nom for e in anciens
                        if e.section and not e.section.frais_renouvellement})
        if muets:
            self.stdout.write(self.style.WARNING(
                "  Niveau(x) sans montant de renouvellement — leurs anciens "
                f"élèves ne devront rien : {', '.join(muets)}"))
