"""
Commande : python manage.py init_plan_comptable [--tenant_id UUID] [--tous] [--force]
Initialise le plan comptable SYSCOHADA Révisé pour un ou tous les établissements.
"""
from django.core.management.base import BaseCommand, CommandError
from apps.comptabilite.models import CompteComptable
from apps.tenants.models import Tenant

# (no_compte, libelle, type, classe, est_systeme)
COMPTES_SYSCOHADA = [
    # ── Classe 1 — Ressources durables ──────────────────────────────────────
    ('10',   'Capitaux propres',                              'BILAN', 1, True),
    ('101',  'Capital personnel',                             'BILAN', 1, True),
    ('111',  'Réserve légale',                                'BILAN', 1, False),
    ('118',  'Autres réserves',                               'BILAN', 1, False),
    ('12',   'Report à nouveau',                              'BILAN', 1, True),
    ('131',  'Résultat net — Bénéfice',                       'BILAN', 1, True),
    ('139',  'Résultat net — Perte',                          'BILAN', 1, True),
    ('15',   'Provisions pour risques et charges',            'BILAN', 1, False),
    ('16',   'Emprunts et dettes financières',                'BILAN', 1, False),
    # ── Classe 2 — Actif immobilisé ─────────────────────────────────────────
    ('21',   'Immobilisations incorporelles',                 'BILAN', 2, True),
    ('211',  'Frais de développement capitalisés',            'BILAN', 2, False),
    ('212',  'Brevets, licences, logiciels',                  'BILAN', 2, False),
    ('22',   'Terrains',                                      'BILAN', 2, True),
    ('221',  'Terrains naturels',                             'BILAN', 2, False),
    ('222',  'Terrains bâtis',                                'BILAN', 2, False),
    ('23',   'Bâtiments, installations et agencements',       'BILAN', 2, True),
    ('231',  'Bâtiments sur sol propre',                      'BILAN', 2, False),
    ('232',  'Bâtiments sur sol d\'autrui',                   'BILAN', 2, False),
    ('233',  'Installations techniques et agencements',       'BILAN', 2, False),
    ('234',  'Aménagements et agencements divers',            'BILAN', 2, False),
    ('24',   'Matériel, mobilier et actifs biologiques',      'BILAN', 2, True),
    ('241',  'Matériel et outillage',                         'BILAN', 2, False),
    ('244',  'Matériel et mobilier',                          'BILAN', 2, False),
    ('245',  'Matériel de transport',                         'BILAN', 2, False),
    ('248',  'Autres matériels et équipements',               'BILAN', 2, False),
    ('25',   'Avances et acomptes sur immobilisations',       'BILAN', 2, False),
    ('26',   'Titres de participation',                       'BILAN', 2, False),
    ('27',   'Autres immobilisations financières',            'BILAN', 2, False),
    ('271',  'Prêts et créances non courantes',               'BILAN', 2, False),
    ('272',  'Dépôts et cautionnements versés',               'BILAN', 2, False),
    ('28',   'Amortissements',                                'BILAN', 2, True),
    ('281',  'Amort. immobilisations incorporelles',          'BILAN', 2, True),
    ('282',  'Amort. terrains',                               'BILAN', 2, True),
    ('283',  'Amort. bâtiments et installations',             'BILAN', 2, True),
    ('284',  'Amort. matériel et mobilier',                   'BILAN', 2, True),
    ('285',  'Amort. matériel de transport',                  'BILAN', 2, True),
    # ── Classe 3 — Stocks ───────────────────────────────────────────────────
    ('32',   'Fournitures consommables',                      'BILAN', 3, False),
    # ── Classe 4 — Créances et dettes ───────────────────────────────────────
    ('40',   'Fournisseurs et comptes rattachés',             'BILAN', 4, True),
    ('401',  'Fournisseurs',                                  'BILAN', 4, True),
    ('408',  'Fournisseurs — factures non parvenues',         'BILAN', 4, False),
    ('41',   'Clients et comptes rattachés',                  'BILAN', 4, True),
    ('411',  'Clients (Parents / Élèves)',                    'BILAN', 4, True),
    ('42',   'Personnel',                                     'BILAN', 4, True),
    ('421',  'Avances et acomptes sur salaires',              'BILAN', 4, True),
    ('422',  'Personnel — rémunérations dues',                'BILAN', 4, True),
    ('423',  'Oppositions et saisies-arrêts',                 'BILAN', 4, True),
    ('43',   'Organismes sociaux',                            'BILAN', 4, True),
    ('431',  'CSS / ATMP',                                    'BILAN', 4, True),
    ('4311', 'CSS — Prestations familiales',                  'BILAN', 4, True),
    ('4312', 'ATMP — Accidents du travail',                   'BILAN', 4, True),
    ('4313', 'IPRES — Cotisations retraite',                  'BILAN', 4, True),
    ('44',   'État et organismes internationaux',             'BILAN', 4, True),
    ('441',  'État — impôts sur bénéfices',                   'BILAN', 4, False),
    ('4421', 'CFCE — Contribution patronale',                 'BILAN', 4, True),
    ('447',  'État — autres impôts et taxes',                 'BILAN', 4, False),
    ('4472', 'État — IR retenu à la source',                  'BILAN', 4, True),
    ('46',   'Débiteurs divers',                              'BILAN', 4, False),
    ('47',   'Créditeurs divers',                             'BILAN', 4, False),
    # ── Classe 5 — Trésorerie ───────────────────────────────────────────────
    ('52',   'Banques',                                       'BILAN', 5, True),
    ('521',  'Banque — compte courant',                       'BILAN', 5, True),
    ('522',  'Banque — compte d\'épargne',                    'BILAN', 5, False),
    ('55',   'Mobile Money',                                  'BILAN', 5, True),
    ('5521', 'Wave',                                          'BILAN', 5, True),
    ('5522', 'Orange Money',                                  'BILAN', 5, True),
    ('5523', 'Free Money',                                    'BILAN', 5, True),
    ('5524', 'Wizall',                                        'BILAN', 5, True),
    ('57',   'Caisse',                                        'BILAN', 5, True),
    ('571',  'Caisse principale',                             'BILAN', 5, True),
    # ── Classe 6 — Charges ──────────────────────────────────────────────────
    ('60',   'Achats et variations de stocks',                'CHARGE', 6, True),
    ('601',  'Achats de marchandises',                        'CHARGE', 6, False),
    ('604',  'Achats stockés — matières et fournitures',      'CHARGE', 6, False),
    ('605',  'Autres achats',                                 'CHARGE', 6, False),
    ('6051', 'Fournitures non stockables — Eau',              'CHARGE', 6, False),
    ('6052', 'Fournitures non stockables — Électricité',      'CHARGE', 6, False),
    ('6054', 'Matériel et fournitures non stockables',        'CHARGE', 6, False),
    ('61',   'Transports',                                    'CHARGE', 6, True),
    ('614',  'Transports du personnel',                       'CHARGE', 6, False),
    ('618',  'Autres frais de transport',                     'CHARGE', 6, False),
    ('62',   'Services extérieurs A',                         'CHARGE', 6, True),
    ('621',  'Sous-traitance générale',                       'CHARGE', 6, False),
    ('622',  'Locations et charges locatives',                'CHARGE', 6, False),
    ('624',  'Entretien, réparations et maintenance',         'CHARGE', 6, False),
    ('625',  'Primes d\'assurance',                           'CHARGE', 6, False),
    ('626',  'Études, recherches et documentation',           'CHARGE', 6, False),
    ('627',  'Publicité, publications, relations publiques',  'CHARGE', 6, False),
    ('628',  'Frais de télécommunications',                   'CHARGE', 6, False),
    ('63',   'Services extérieurs B',                         'CHARGE', 6, True),
    ('631',  'Frais bancaires',                               'CHARGE', 6, False),
    ('633',  'Frais de formation du personnel',               'CHARGE', 6, False),
    ('635',  'Frais de déplacements et de réception',         'CHARGE', 6, False),
    ('64',   'Impôts et taxes',                               'CHARGE', 6, True),
    ('641',  'Impôts directs',                                'CHARGE', 6, False),
    ('6413', 'Taxes sur la masse salariale (CFCE)',           'CHARGE', 6, True),
    ('645',  'Droits d\'enregistrement et de timbre',         'CHARGE', 6, False),
    ('65',   'Autres charges',                                'CHARGE', 6, False),
    ('651',  'Pertes sur créances irrecouvrables',            'CHARGE', 6, False),
    ('658',  'Charges diverses',                              'CHARGE', 6, False),
    # Dépenses reprises d'un journal de caisse à la migration, dont l'école
    # n'a pas fourni le détail. Ce sont de VRAIES charges — les sortir de la
    # classe 6 gonflerait le résultat — mais les laisser en « Charges
    # diverses » présente comme un fourre-tout ce qui est en fait un héritage
    # assumé. Un compte dédié le dit, et un banquier comprend au premier coup
    # d'œil pourquoi la ligne est grosse.
    ('6588', 'Charges reprises à la migration (détail non communiqué)',
                                                              'CHARGE', 6, False),
    ('66',   'Charges de personnel',                          'CHARGE', 6, True),
    ('661',  'Appointements et salaires',                     'CHARGE', 6, True),
    ('662',  'Charges sociales salariales (IPRES)',           'CHARGE', 6, True),
    ('663',  'Indemnités et avantages divers',                'CHARGE', 6, False),
    ('664',  'Cotisations sociales de l\'employeur',          'CHARGE', 6, True),
    ('6641', 'Cotisations patronales (IPRES/CSS/ATMP)',       'CHARGE', 6, True),
    ('67',   'Frais financiers et charges assimilées',        'CHARGE', 6, False),
    ('671',  'Intérêts d\'emprunts',                          'CHARGE', 6, False),
    ('675',  'Escomptes accordés',                            'CHARGE', 6, False),
    ('68',   'Dotations aux amortissements et provisions',    'CHARGE', 6, True),
    ('681',  'Dotations aux amortissements d\'exploitation',  'CHARGE', 6, True),
    ('691',  'Dotations aux provisions d\'exploitation',      'CHARGE', 6, False),
    # ── Classe 7 — Produits ─────────────────────────────────────────────────
    ('70',   'Ventes et produits des activités',             'PRODUIT', 7, True),
    ('706',  'Prestations de services — Scolarité',          'PRODUIT', 7, True),
    ('706.1','Prestations de services — Cantine',            'PRODUIT', 7, False),
    ('706.2','Prestations de services — Transport',          'PRODUIT', 7, False),
    ('706.3','Activités extrascolaires',                     'PRODUIT', 7, False),
    ('707',  'Ventes de marchandises',                       'PRODUIT', 7, False),
    ('74',   'Subventions d\'exploitation',                  'PRODUIT', 7, False),
    ('75',   'Autres produits',                              'PRODUIT', 7, False),
    ('751',  'Redevances et recettes diverses',              'PRODUIT', 7, False),
    ('758',  'Produits divers d\'exploitation',              'PRODUIT', 7, False),
    ('77',   'Revenus financiers',                           'PRODUIT', 7, False),
    ('771',  'Intérêts de dépôts et prêts',                  'PRODUIT', 7, False),
    ('78',   'Transferts de charges',                        'PRODUIT', 7, False),
    ('781',  'Reprises d\'amortissements et provisions',     'PRODUIT', 7, True),
]


class Command(BaseCommand):
    help = 'Initialise le plan comptable SYSCOHADA Révisé pour un établissement'

    def add_arguments(self, parser):
        parser.add_argument('--tenant_id', type=str, help='UUID du tenant')
        parser.add_argument('--tous',      action='store_true', help='Initialiser tous les tenants')
        parser.add_argument('--force',     action='store_true', help='Écraser les libellés existants')

    def handle(self, *args, **options):
        if options['tous']:
            tenants = Tenant.objects.all()
        elif options['tenant_id']:
            try:
                tenants = [Tenant.objects.get(id=options['tenant_id'])]
            except Tenant.DoesNotExist:
                raise CommandError(f"Tenant {options['tenant_id']} introuvable")
        else:
            tenants = Tenant.objects.all()

        for tenant in tenants:
            self._init_tenant(tenant, force=options['force'])

    def _init_tenant(self, tenant, force=False):
        created = updated = 0
        for no, libelle, type_c, classe, est_sys in COMPTES_SYSCOHADA:
            defaults = {'libelle': libelle, 'type': type_c, 'classe': classe, 'est_systeme': est_sys}
            if not force:
                obj, was_created = CompteComptable.objects.get_or_create(
                    tenant=tenant, no_compte=no, defaults=defaults
                )
                if was_created:
                    created += 1
            else:
                _, was_created = CompteComptable.objects.update_or_create(
                    tenant=tenant, no_compte=no, defaults=defaults
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'{tenant.nom} : {created} créés, {updated} mis à jour — {len(COMPTES_SYSCOHADA)} comptes SYSCOHADA'
            )
        )
