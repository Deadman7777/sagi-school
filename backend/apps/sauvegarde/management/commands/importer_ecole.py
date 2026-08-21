"""Importe une école entière depuis une base restaurée, vers la base courante.

Sert à faire basculer en cloud une école jusque-là installée en local. Le
chemin est en trois temps, et cette commande couvre le deuxième :

  1. pg_restore du dump local dans une base TEMPORAIRE du serveur
  2. importer_ecole : copie les lignes de CETTE école dans la base cloud
  3. suppression de la base temporaire

Pourquoi ne pas restaurer directement la base cloud : elle héberge toutes les
écoles dans les mêmes tables (isolation par clé étrangère `tenant`, pas par
schéma). Un pg_restore y écraserait tout le monde.

Ce qui rend l'opération sûre : les clés primaires sont des UUID. Recopier les
lignes d'une école dans une base qui en contient déjà d'autres ne peut pas
provoquer de collision d'identifiants — aucun remappage n'est nécessaire.

  python manage.py importer_ecole --source-db sagi_temp --tenant Shoumoul
      [--source-host --source-port --source-user --source-password]
      [--appliquer]

Sans --appliquer : inventaire seul, rien n'est écrit.
"""
from contextlib import contextmanager

from django.apps import apps as django_apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction

SOURCE = 'import_source'

# Données de référence partagées par toutes les écoles : barèmes fiscaux du
# Sénégal, découpage du Coran. La base cible a déjà les siennes, les recopier
# créerait des doublons.
MODELES_GLOBAUX = {'rh.ParametresFiscaux', 'daara.Sourate', 'daara.Subdivision'}
APPS_IGNOREES = {'contenttypes', 'auth', 'sessions', 'admin', 'authtoken'}

# Les données globales existent des deux côtés, mais avec des UUID DIFFÉRENTS :
# elles sont semées par base. Une école qui pointe vers elles (un bulletin de
# paie vers son barème fiscal, un suivi de mémorisation vers sa sourate) porte
# donc des identifiants qui n'existent pas dans la cible. On les réaligne sur
# une clé naturelle — l'année du barème, le numéro de la sourate.
CLES_NATURELLES = {
    'rh.ParametresFiscaux': 'annee',
    'daara.Sourate':        'numero',
}


@contextmanager
def horloge_neutralisee():
    """Suspend `auto_now_add` / `auto_now` le temps de l'import.

    Django applique ces champs jusque dans `bulk_create` : il appelle
    `pre_save()` sur chaque colonne avant l'INSERT. Sans cette neutralisation,
    l'import réécrit donc `created_at`/`updated_at` de TOUTES les lignes
    copiées — et, tant que `Paiement.date_paiement` était en `auto_now_add`,
    la date de chaque règlement — avec la date du jour de la bascule.

    C'est arrivé au Complexe Shoumoul Excellence le 19/08/2026 : les 62
    règlements de l'année se sont retrouvés au même jour, et le tableau de
    bord empilait toutes les recettes sur ce mois-là. Copier une école, c'est
    transporter son passé tel quel ; l'horloge du serveur n'a pas voix au
    chapitre. (Réparation de l'existant : `manage.py reparer_dates_paiement`.)
    """
    initial = []
    for modele in django_apps.get_models():
        for champ in modele._meta.fields:
            if getattr(champ, 'auto_now_add', False) or getattr(champ, 'auto_now', False):
                initial.append((champ, champ.auto_now_add, champ.auto_now))
                champ.auto_now_add = False
                champ.auto_now = False
    try:
        yield
    finally:
        for champ, ajout, maj in initial:
            champ.auto_now_add, champ.auto_now = ajout, maj


def arguments_source(parser):
    """Options de connexion à la base temporaire, communes aux commandes de
    bascule (`importer_ecole`, `restaurer_horodatage`)."""
    parser.add_argument('--source-db', required=True,
                        help='Nom de la base temporaire restaurée')
    parser.add_argument('--source-host', default=None)
    parser.add_argument('--source-port', default=None)
    parser.add_argument('--source-user', default=None)
    parser.add_argument('--source-password', default=None)
    parser.add_argument('--tenant', required=True,
                        help="Nom ou code de l'école dans la base source")
    parser.add_argument('--appliquer', action='store_true',
                        help='Écrire réellement (sinon inventaire seul)')


def brancher_source(opts):
    """Déclare l'alias `import_source` et vérifie qu'on peut s'y connecter."""
    defaut = settings.DATABASES['default']
    settings.DATABASES[SOURCE] = {
        **defaut,
        'NAME':     opts['source_db'],
        'HOST':     opts['source_host']     or defaut.get('HOST'),
        'PORT':     opts['source_port']     or defaut.get('PORT'),
        'USER':     opts['source_user']     or defaut.get('USER'),
        'PASSWORD': opts['source_password'] or defaut.get('PASSWORD'),
    }
    try:
        connections[SOURCE].ensure_connection()
    except Exception as exc:
        raise CommandError(f"Base source inaccessible : {exc}")


class Command(BaseCommand):
    help = "Copie une école depuis une base restaurée vers la base courante"

    def add_arguments(self, parser):
        arguments_source(parser)

    # ── Connexion à la base source ────────────────────────────────────────
    def _brancher_source(self, opts):
        brancher_source(opts)

    # ── Garde-fou de version ──────────────────────────────────────────────
    def _verifier_migrations(self):
        """Les deux bases doivent porter exactement les mêmes migrations.

        C'est LE contrôle qui évite le désastre silencieux : une source plus
        récente que la cible transporte des colonnes que la cible ignore, une
        cible plus récente attend des colonnes que la source n'a pas.
        """
        def appliquees(alias):
            with connections[alias].cursor() as cur:
                cur.execute('SELECT app, name FROM django_migrations')
                return {f'{a}.{n}' for a, n in cur.fetchall()}

        src, cible = appliquees(SOURCE), appliquees('default')
        en_trop = sorted(src - cible)
        manquantes = sorted(cible - src)
        if en_trop or manquantes:
            details = []
            if en_trop:
                details.append("La SOURCE est en avance sur %d migration(s) : %s"
                               % (len(en_trop), ', '.join(en_trop[:5])))
            if manquantes:
                details.append("La CIBLE est en avance sur %d migration(s) : %s"
                               % (len(manquantes), ', '.join(manquantes[:5])))
            raise CommandError(
                "Les deux bases ne sont pas au même niveau de schéma.\n  "
                + "\n  ".join(details)
                + "\n\nDéployez la MÊME version des deux côtés, puis relancez.")

    # ── Modèles à transporter, dans l'ordre des dépendances ───────────────
    def _modeles(self):
        retenus = []
        for modele in django_apps.get_models():
            label = modele._meta.label
            if modele._meta.app_label in APPS_IGNOREES or label in MODELES_GLOBAUX:
                continue
            if label == 'tenants.Tenant':
                continue                      # copié à part, en premier
            if any(f.name == 'tenant' for f in modele._meta.fields):
                retenus.append(modele)
        return self._trier(retenus)

    def _trier(self, modeles):
        """Tri topologique sur les clés étrangères.

        Les contraintes PostgreSQL créées par Django sont DEFERRABLE INITIALLY
        DEFERRED, donc l'ordre n'est pas vital dans une transaction — mais un
        ordre correct rend les erreurs éventuelles lisibles au lieu de toutes
        surgir au COMMIT.
        """
        restants = list(modeles)
        connus = {m._meta.label for m in restants}
        ordonnes, places = [], set()
        while restants:
            progres = False
            for modele in list(restants):
                besoins = {
                    f.related_model._meta.label
                    for f in modele._meta.fields
                    if f.is_relation and f.related_model is not None
                    and f.related_model._meta.label in connus
                    and f.related_model is not modele          # auto-référence
                }
                if besoins <= places:
                    ordonnes.append(modele)
                    places.add(modele._meta.label)
                    restants.remove(modele)
                    progres = True
            if not progres:
                # Cycle entre modèles : les contraintes différées s'en chargent.
                ordonnes.extend(restants)
                break
        return ordonnes

    # ── Exécution ─────────────────────────────────────────────────────────
    def handle(self, *args, **opts):
        from apps.tenants.models import Tenant

        self._brancher_source(opts)
        self._verifier_migrations()

        arg = opts['tenant']
        source_qs = Tenant.objects.using(SOURCE)
        tenant = (source_qs.filter(code_etablissement__iexact=arg).first()
                  or source_qs.filter(nom__icontains=arg).first())
        if not tenant:
            raise CommandError(f"École introuvable dans la base source : {arg}")

        if Tenant.objects.filter(pk=tenant.pk).exists():
            raise CommandError(
                f"L'école « {tenant.nom} » est DÉJÀ dans la base cible "
                f"(id {tenant.pk}). Import refusé : réimporter par-dessus "
                f"créerait des doublons silencieux. Supprimez-la d'abord si "
                f"c'est un nouvel essai.")
        if Tenant.objects.filter(nom__iexact=tenant.nom).exists():
            raise CommandError(
                f"Une école porte déjà le nom « {tenant.nom} » dans la base "
                f"cible, avec un autre identifiant. Import refusé — tranchez "
                f"à la main quelle est la bonne.")

        self.stdout.write(f"École  : {tenant.nom} ({tenant.code_etablissement})")
        self.stdout.write(f"Source : {opts['source_db']}\n")

        modeles = self._modeles()
        plan, total = [], 0
        for modele in modeles:
            nb = modele.objects.using(SOURCE).filter(tenant=tenant).count()
            if nb:
                plan.append((modele, nb))
                total += nb

        self.stdout.write("Lignes à importer :")
        for modele, nb in plan:
            self.stdout.write(f"   {modele._meta.label:<38} {nb:>7}")
        self.stdout.write(self.style.MIGRATE_LABEL(
            f"   {'TOTAL':<38} {total:>7}\n"))

        equilibre = self._equilibre_source(tenant)
        self.stdout.write(
            f"Contrôle comptable source : débit {equilibre[0]:,.0f} / "
            f"crédit {equilibre[1]:,.0f}"
            f"{'  ✓' if abs(equilibre[0] - equilibre[1]) < 0.01 else '  ⚠ DÉSÉQUILIBRÉ'}")

        if not opts['appliquer']:
            self.stdout.write(self.style.WARNING(
                "\nInventaire seul — relancez avec --appliquer pour importer."))
            return

        with horloge_neutralisee():
            correspondances = self._aligner_globaux()

            with transaction.atomic():
                Tenant.objects.bulk_create([tenant])
                for modele, _ in plan:
                    lignes = list(modele.objects.using(SOURCE).filter(tenant=tenant))
                    for ligne in lignes:
                        ligne._state.db = None
                        self._realigner(ligne, correspondances)
                    modele.objects.bulk_create(lignes, batch_size=500)
                self._copier_m2m(tenant)

        self.stdout.write(self.style.SUCCESS(
            f"\n✅ {total} ligne(s) importée(s) pour « {tenant.nom} »."))
        self._verifier_apres(tenant, plan)

    def _aligner_globaux(self):
        """Table de correspondance {label: {id_source: id_cible}}.

        Une donnée globale absente de la cible y est recopiée plutôt
        qu'ignorée : perdre le barème fiscal d'une année rendrait illisibles
        les bulletins de paie déjà édités.
        """
        correspondances = {}
        for label, cle in CLES_NATURELLES.items():
            try:
                modele = django_apps.get_model(label)
            except LookupError:
                continue
            cibles = dict(modele.objects.values_list(cle, 'pk'))
            table, manquants = {}, []
            for source in modele.objects.using(SOURCE).all():
                valeur = getattr(source, cle)
                if valeur in cibles:
                    table[source.pk] = cibles[valeur]
                else:
                    source._state.db = None
                    manquants.append(source)
                    table[source.pk] = source.pk
            if manquants:
                modele.objects.bulk_create(manquants, batch_size=200)
                self.stdout.write(
                    f"   + {len(manquants)} {label} absent(s) de la cible, recopié(s)")
            correspondances[label] = table
        return correspondances

    def _realigner(self, ligne, correspondances):
        """Réécrit les FK d'une ligne vers les identifiants de la cible."""
        for champ in ligne._meta.fields:
            if not (champ.is_relation and champ.related_model is not None):
                continue
            table = correspondances.get(champ.related_model._meta.label)
            if not table:
                continue
            actuel = getattr(ligne, champ.attname)
            if actuel is not None and actuel in table:
                setattr(ligne, champ.attname, table[actuel])

    def _copier_m2m(self, tenant):
        """Seul M2M métier de l'application : BulletinPaie.avances.

        Les M2M de django.contrib.auth (groupes, permissions) ne sont pas
        repris : les droits de SAGI SCHOOL vivent dans User.role, pas dans les
        groupes Django.
        """
        try:
            from apps.rh.models import BulletinPaie
        except ImportError:
            return
        for bulletin in BulletinPaie.objects.using(SOURCE).filter(tenant=tenant):
            ids = list(bulletin.avances.using(SOURCE).values_list('id', flat=True))
            if ids:
                BulletinPaie.objects.get(pk=bulletin.pk).avances.set(ids)

    def _equilibre_source(self, tenant):
        from django.db.models import Sum

        from apps.comptabilite.models import JournalEntry
        agg = (JournalEntry.objects.using(SOURCE).filter(tenant=tenant)
               .aggregate(d=Sum('debit'), c=Sum('credit')))
        return float(agg['d'] or 0), float(agg['c'] or 0)

    def _verifier_apres(self, tenant, plan):
        """Recompte tout côté cible : un import partiel doit se voir tout de
        suite, pas six mois plus tard en éditant un bilan."""
        from django.db.models import Sum

        from apps.comptabilite.models import JournalEntry

        ecarts = []
        for modele, attendu in plan:
            obtenu = modele.objects.filter(tenant=tenant).count()
            if obtenu != attendu:
                ecarts.append(f"{modele._meta.label} : {obtenu} au lieu de {attendu}")

        agg = JournalEntry.objects.filter(tenant=tenant).aggregate(
            d=Sum('debit'), c=Sum('credit'))
        debit, credit = float(agg['d'] or 0), float(agg['c'] or 0)
        self.stdout.write(
            f"   Journal importé : débit {debit:,.0f} / crédit {credit:,.0f}"
            f"{'  ✓ équilibré' if abs(debit - credit) < 0.01 else '  ⚠ DÉSÉQUILIBRÉ'}")

        if ecarts:
            self.stdout.write(self.style.ERROR(
                "   ⚠ Écarts de comptage :\n      " + "\n      ".join(ecarts)))
        else:
            self.stdout.write(self.style.SUCCESS(
                "   ✓ Tous les comptages correspondent."))
