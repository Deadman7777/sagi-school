from django.db.models import Sum, Q
from django.db.models.functions import ExtractMonth
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status as drf_status
from apps.paiements.models import Exercice, Paiement
from apps.eleves.models import Eleve
from core.tenant import get_tenant
from .models import JournalEntry, CompteComptable, BudgetLigne, Immobilisation
from django.utils import timezone


# ── Plan comptable SYSCOHADA Révisé — Enseignement privé Sénégal ─────────────
# Référence : AUDCIF 2017 + Règlement n°01/2017/CM/UEMOA
PLAN_COMPTABLE = {
    # ── Classe 1 — Ressources durables ──
    '10':    'Capitaux propres',
    '101':   'Capital personnel',
    '111':   'Réserve légale',
    '118':   'Autres réserves',
    '12':    'Report à nouveau',
    '131':   'Résultat net — Bénéfice',
    '139':   'Résultat net — Perte',
    '15':    'Provisions pour risques et charges',
    '16':    'Emprunts et dettes financières',
    # ── Classe 2 — Actif immobilisé ──
    '21':    'Immobilisations incorporelles',
    '211':   'Frais de développement capitalisés',
    '212':   'Brevets, licences, logiciels',
    '22':    'Terrains',
    '221':   'Terrains naturels',
    '222':   'Terrains bâtis',
    '23':    'Bâtiments, installations et agencements',
    '231':   'Bâtiments sur sol propre',
    '232':   'Bâtiments sur sol d\'autrui',
    '233':   'Installations techniques et agencements',
    '234':   'Aménagements et agencements divers',
    '24':    'Matériel, mobilier et actifs biologiques',
    '241':   'Matériel et outillage',
    '244':   'Matériel et mobilier',
    '245':   'Matériel de transport',
    '248':   'Autres matériels et équipements',
    '25':    'Avances et acomptes sur immobilisations',
    '26':    'Titres de participation',
    '27':    'Autres immobilisations financières',
    '271':   'Prêts et créances non courantes',
    '272':   'Dépôts et cautionnements versés',
    '28':    'Amortissements',
    '281':   'Amort. immobilisations incorporelles',
    '2811':  'Amort. frais de développement capitalisés',
    '2812':  'Amort. brevets, licences, logiciels',
    '282':   'Amort. terrains',
    '2821':  'Amort. terrains naturels',
    '2822':  'Amort. terrains bâtis',
    '283':   'Amort. bâtiments et installations',
    '2831':  'Amort. bâtiments sur sol propre',
    '2832':  'Amort. bâtiments sur sol d\'autrui',
    '2833':  'Amort. installations techniques et agencements',
    '2834':  'Amort. aménagements et agencements divers',
    '284':   'Amort. matériel et mobilier',
    '2841':  'Amort. matériel et outillage',
    '2844':  'Amort. matériel et mobilier',
    '2845':  'Amort. matériel de transport',
    '2848':  'Amort. autres matériels et équipements',
    '285':   'Amort. matériel de transport',
    # ── Classe 3 — Stocks ──
    '32':    'Fournitures consommables',
    # ── Classe 4 — Créances et dettes ──
    '40':    'Fournisseurs et comptes rattachés',
    '401':   'Fournisseurs (dettes en compte)',
    '402':   'Fournisseurs — effets à payer',
    '404':   'Fournisseurs, acquisitions d\'immobilisations',
    '405':   'Fournisseurs de prestations de services',
    '408':   'Fournisseurs — factures non parvenues',
    '409':   'Fournisseurs débiteurs (avances et acomptes versés)',
    '41':    'Clients et comptes rattachés',
    '411':   'Clients (Parents / Élèves)',
    '412':   'Clients — effets à recevoir',
    '413':   'Clients — avances et acomptes reçus sur commandes',
    '416':   'Clients douteux ou litigieux',
    '417':   'Clients — retenues de garantie',
    '419':   'Clients créditeurs (avances reçues)',
    '42':    'Personnel',
    '421':   'Personnel — avances et acomptes sur salaires',
    '422':   'Personnel — rémunérations dues',
    '423':   'Personnel — oppositions et saisies-arrêts',
    '424':   'Personnel — participation aux bénéfices',
    '425':   'Personnel — charges sociales à payer',
    '43':    'Organismes sociaux',
    '431':   'Organismes de sécurité sociale (CSS / ATMP)',
    '4311':  'CSS — Prestations familiales',
    '4312':  'ATMP — Accidents du travail',
    '4313':  'IPRES — Cotisations retraite',
    '432':   'Organismes de prévoyance sociale',
    '433':   'Autres organismes sociaux',
    '434':   'Caisse nationale de sécurité sociale',
    '44':    'État et organismes internationaux',
    '441':   'État — impôts sur bénéfices',
    '4421':  'CFCE — Contribution forfaitaire à la charge de l\'employeur',
    '443':   'État — TVA et taxes assimilées',
    '4431':  'TVA collectée (facturée)',
    '4432':  'TVA déductible sur achats',
    '4434':  'TVA — crédit de taxe à reporter',
    '444':   'État — autres impôts et taxes',
    '4472':  'État — IR retenu à la source',
    '445':   'État — subventions à recevoir',
    '447':   'État — autres impôts et taxes divers',
    '449':   'État — autres opérations',
    '46':    'Débiteurs divers',
    '461':   'Créances sur cessions d\'actifs immobilisés',
    '462':   'Créances sur cessions de titres de placement',
    '467':   'Autres débiteurs divers',
    '47':    'Créditeurs divers',
    '471':   'Comptes transitoires ou d\'attente (débit)',
    '472':   'Comptes transitoires ou d\'attente (crédit)',
    '473':   'Autres créditeurs divers',
    '48':    'Créances et dettes hors exploitation',
    '481':   'Fournisseurs d\'immobilisations',
    '482':   'Clients — achats d\'immobilisations',
    '484':   'Charges à payer (comptes de régularisation)',
    '485':   'Produits à recevoir',
    '486':   'Charges constatées d\'avance',
    '487':   'Produits constatés d\'avance',
    '488':   'Intérêts courus (à payer ou à recevoir)',
    '49':    'Dépréciations des comptes de tiers',
    '491':   'Dépréciation des comptes clients',
    '499':   'Dépréciation des autres créances',
    # ── Classe 5 — Trésorerie ──
    '52':    'Banques',
    '521':   'Banque — compte courant',
    '522':   'Banque — compte d\'épargne',
    '55':    'Mobile Money',
    '5521':  'Wave',
    '5522':  'Orange Money',
    '5523':  'Free Money',
    '5524':  'Wizall',
    '57':    'Caisse',
    '571':   'Caisse principale',
    # ── Classe 6 — Charges ──
    '60':    'Achats et variations de stocks',
    '601':   'Achats de marchandises',
    '604':   'Achats stockés — matières et fournitures consommables',
    '605':   'Autres achats',
    '6051':  'Fournitures non stockables — Eau',
    '6052':  'Fournitures non stockables — Électricité',
    '6054':  'Matériel et fournitures non stockables',
    '61':    'Transports',
    '614':   'Transports du personnel',
    '618':   'Autres frais de transport',
    '62':    'Services extérieurs A',
    '621':   'Sous-traitance générale',
    '622':   'Locations et charges locatives',
    '624':   'Entretien, réparations et maintenance',
    '625':   'Primes d\'assurance',
    '626':   'Études, recherches et documentation',
    '627':   'Publicité, publications et relations publiques',
    '628':   'Frais de télécommunications',
    '63':    'Services extérieurs B',
    '631':   'Frais bancaires',
    '633':   'Frais de formation du personnel',
    '635':   'Frais de déplacements et de réception',
    '64':    'Impôts et taxes',
    '641':   'Impôts directs',
    '6413':  'Taxes sur la masse salariale (CFCE)',
    '645':   'Droits d\'enregistrement et de timbre',
    '65':    'Autres charges',
    '651':   'Pertes sur créances irrecouvrables',
    '658':   'Charges diverses',
    '66':    'Charges de personnel',
    '661':   'Appointements et salaires',
    '662':   'Charges sociales salariales (IPRES)',
    '663':   'Indemnités et avantages divers',
    '664':   'Cotisations sociales de l\'employeur',
    '6641':  'Cotisations patronales (IPRES/CSS/ATMP)',
    '67':    'Frais financiers et charges assimilées',
    '671':   'Intérêts d\'emprunts',
    '675':   'Escomptes accordés',
    '68':    'Dotations aux amortissements et provisions',
    '681':   'Dotations aux amortissements d\'exploitation',
    '691':   'Dotations aux provisions d\'exploitation',
    # ── Classe 7 — Produits ──
    '70':    'Ventes et produits',
    '706':   'Prestations de services — Scolarité',
    '706.1': 'Prestations de services — Cantine',
    '706.2': 'Prestations de services — Transport',
    '706.3': 'Activités extrascolaires',
    '707':   'Ventes de marchandises',
    '74':    'Subventions d\'exploitation',
    '75':    'Autres produits',
    '751':   'Redevances et recettes diverses',
    '758':   'Produits divers d\'exploitation',
    '77':    'Revenus financiers',
    '771':   'Intérêts de dépôts et prêts',
    '78':    'Transferts de charges',
    '781':   'Reprises d\'amortissements et provisions',
}


def get_plan_dict(tenant):
    """Retourne {no_compte: libelle} fusionné — DB tenant prioritaire sur le dict statique."""
    try:
        db = {c.no_compte: c.libelle
              for c in CompteComptable.objects.filter(tenant=tenant, est_actif=True)}
        return {**PLAN_COMPTABLE, **db}
    except Exception:
        return PLAN_COMPTABLE

MOBILE_ACCOUNTS = ('552', '5521', '5522', '5523')

# Article 11 AUDCIF — seuil SMT pour le secteur des services (dont éducation)
SEUIL_SMT_SERVICES = 30_000_000


def get_exercice(tenant, request=None):
    """Exercice ciblé par les rapports.

    Si la requête fournit `?exercice=<id>` (vue de lecture : consultation d'une
    année clôturée), on renvoie cet exercice — qu'il soit clôturé ou non — tant
    qu'il appartient au tenant. À défaut, l'exercice actif (non clôturé) le plus
    récent. Les vues d'écriture appellent get_exercice(tenant) sans request,
    donc elles restent toujours sur l'exercice actif (clôturé = lecture seule).
    """
    if request is not None:
        ex_id = request.query_params.get('exercice')
        if ex_id:
            ex = Exercice.objects.filter(tenant=tenant, id=ex_id).first()
            if ex:
                return ex
    return Exercice.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()


def _compte_sort_key(no):
    """Tri SYSCOHADA Révisé : regroupement hiérarchique par classe.
    Ex : 10 < 101 < 102 < 11 < 111 < 12 < ... < 706 < 706.1 < 707
    Méthode : padding trailing-zeros sur 8 chars (sans le point).
    """
    clean = no.replace('.', '').replace('_', '')
    if clean.isdigit():
        return clean.ljust(8, '0')
    return '99999999'  # comptes non numériques en fin


def _mobile_aggregate(tenant, exercice):
    agg = JournalEntry.objects.filter(
        tenant=tenant, exercice=exercice, no_compte__in=MOBILE_ACCOUNTS
    ).aggregate(d=Sum('debit'), c=Sum('credit'))
    return float(agg['d'] or 0), float(agg['c'] or 0)


def _sum_paiements(qs):
    a = qs.aggregate(
        t=Sum('montant_inscription') + Sum('montant_mensualite') +
          Sum('montant_uniforme')    + Sum('montant_fournitures') +
          Sum('montant_cantine')     + Sum('montant_divers')
    )
    return float(a['t'] or 0)


def _detecter_systeme(caht):
    return 'SN' if caht >= SEUIL_SMT_SERVICES else 'SMT'


# ── Journal ───────────────────────────────────────────────────────────────────
class JournalView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant   = get_tenant(request)
        exercice = get_exercice(tenant, request)
        if not exercice:
            return Response([])

        plan = get_plan_dict(tenant)
        qs = JournalEntry.objects.filter(tenant=tenant, exercice=exercice)

        if source_filter := request.query_params.get('source'):
            qs = qs.filter(source=source_filter)

        entries = qs.order_by('date_ecriture', 'no_piece', 'ordre')

        return Response([{
            'date':           str(e.date_ecriture),
            'no_piece':       e.no_piece,
            'no_compte':      e.no_compte,
            'libelle_compte': plan.get(e.no_compte, e.no_compte),
            'libelle':        e.libelle,
            'debit':          float(e.debit),
            'credit':         float(e.credit),
            'source':         e.source,
        } for e in entries])


# ── Grand Livre ───────────────────────────────────────────────────────────────
class GrandLivreView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant   = get_tenant(request)
        exercice = get_exercice(tenant, request)
        if not exercice:
            return Response([])

        comptes = JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice
        ).exclude(
            no_compte__in=('5521', '5522', '5523')
        ).values('no_compte').annotate(
            total_debit=Sum('debit'),
            total_credit=Sum('credit')
        ).order_by('no_compte')

        mob_d, mob_c = _mobile_aggregate(tenant, exercice)

        plan = get_plan_dict(tenant)
        data = {}
        for c in comptes:
            no = c['no_compte']
            d  = float(c['total_debit']  or 0)
            cr = float(c['total_credit'] or 0)
            if no == '552':
                d, cr = mob_d, mob_c
            data[no] = {
                'no_compte':       no,
                'libelle':         plan.get(no, no),
                'total_debit':     round(d, 2),
                'total_credit':    round(cr, 2),
                'solde_debiteur':  round(max(d - cr, 0), 2),
                'solde_crediteur': round(max(cr - d, 0), 2),
                'is_synthetic':    False,
            }

        if mob_d > 0 or mob_c > 0:
            if '552' not in data:
                data['552'] = {
                    'no_compte':       '552',
                    'libelle':         plan.get('552', '552'),
                    'total_debit':     round(mob_d, 2),
                    'total_credit':    round(mob_c, 2),
                    'solde_debiteur':  round(max(mob_d - mob_c, 0), 2),
                    'solde_crediteur': round(max(mob_c - mob_d, 0), 2),
                    'is_synthetic':    True,
                }

        for sub in ('5521', '5522', '5523'):
            agg = JournalEntry.objects.filter(
                tenant=tenant, exercice=exercice, no_compte=sub
            ).aggregate(d=Sum('debit'), c=Sum('credit'))
            sub_d = float(agg['d'] or 0)
            sub_c = float(agg['c'] or 0)
            if sub_d > 0 or sub_c > 0:
                data[sub] = {
                    'no_compte':       sub,
                    'libelle':         f"  └ {plan.get(sub, sub)}",
                    'total_debit':     round(sub_d, 2),
                    'total_credit':    round(sub_c, 2),
                    'solde_debiteur':  round(max(sub_d - sub_c, 0), 2),
                    'solde_crediteur': round(max(sub_c - sub_d, 0), 2),
                    'is_synthetic':    False,
                }

        result = sorted(data.values(), key=lambda x: _compte_sort_key(x['no_compte']))
        return Response(result)


# ── Balance ───────────────────────────────────────────────────────────────────
class BalanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant   = get_tenant(request)
        exercice = get_exercice(tenant, request)
        if not exercice:
            return Response({'lignes': [], 'totaux': {}})

        plan = get_plan_dict(tenant)
        soldes_initiaux = {
            '521': float(exercice.solde_initial_banque),
            '571': float(exercice.solde_initial_caisse),
            '552': float(exercice.solde_initial_mobile),
        }

        comptes = JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice
        ).exclude(
            no_compte__in=('5521', '5522', '5523')
        ).values('no_compte').annotate(
            mvt_debit=Sum('debit'),
            mvt_credit=Sum('credit')
        ).order_by('no_compte')

        mob_d, mob_c = _mobile_aggregate(tenant, exercice)

        lignes = {}
        tot_so_d = tot_so_c = tot_mvt_d = tot_mvt_c = tot_sf_d = tot_sf_c = 0

        for c in comptes:
            no    = c['no_compte']
            mvt_d = float(c['mvt_debit']  or 0)
            mvt_c = float(c['mvt_credit'] or 0)
            if no == '552':
                mvt_d, mvt_c = mob_d, mob_c

            so_d = soldes_initiaux.get(no, 0)
            total_d = so_d + mvt_d
            total_c = mvt_c
            sf_d = round(max(total_d - total_c, 0), 2)
            sf_c = round(max(total_c - total_d, 0), 2)

            if no not in lignes:
                lignes[no] = {
                    'no_compte':    no,
                    'libelle':      plan.get(no, no),
                    'so_debiteur':  round(so_d, 2),
                    'so_crediteur': 0,
                    'mvt_debit':    round(mvt_d, 2),
                    'mvt_credit':   round(mvt_c, 2),
                    'sf_debiteur':  sf_d,
                    'sf_crediteur': sf_c,
                    'is_synthetic': False,
                }
                tot_so_d  += so_d
                tot_mvt_d += mvt_d; tot_mvt_c += mvt_c
                tot_sf_d  += sf_d;  tot_sf_c  += sf_c

        if '552' not in lignes and (mob_d > 0 or mob_c > 0):
            so_d = float(exercice.solde_initial_mobile)
            total_d = so_d + mob_d
            sf_d = round(max(total_d - mob_c, 0), 2)
            sf_c = round(max(mob_c - total_d, 0), 2)
            lignes['552'] = {
                'no_compte':    '552',
                'libelle':      plan.get('552', '552'),
                'so_debiteur':  round(so_d, 2),
                'so_crediteur': 0,
                'mvt_debit':    round(mob_d, 2),
                'mvt_credit':   round(mob_c, 2),
                'sf_debiteur':  sf_d,
                'sf_crediteur': sf_c,
                'is_synthetic': True,
            }
            tot_so_d  += so_d
            tot_mvt_d += mob_d; tot_mvt_c += mob_c
            tot_sf_d  += sf_d;  tot_sf_c  += sf_c

        result = sorted(lignes.values(), key=lambda x: _compte_sort_key(x['no_compte']))
        return Response({
            'lignes': result,
            'totaux': {
                'so_debiteur':  round(tot_so_d, 2),
                'so_crediteur': round(tot_so_c, 2),
                'mvt_debit':    round(tot_mvt_d, 2),
                'mvt_credit':   round(tot_mvt_c, 2),
                'sf_debiteur':  round(tot_sf_d, 2),
                'sf_crediteur': round(tot_sf_c, 2),
            }
        })


# ── Compte de Résultat SYSCOHADA Révisé — SIG en cascade ─────────────────────
class CompteResultatView(APIView):
    permission_classes = [IsAuthenticated]

    def _sum(self, entries, prefixes, field='debit'):
        q = Q()
        for p in prefixes:
            q |= Q(no_compte__startswith=p)
        agg = entries.filter(q).aggregate(t=Sum(field))
        return float(agg['t'] or 0)

    def _detail(self, entries, prefixes, field='debit', plan_dict=None):
        _plan = plan_dict or PLAN_COMPTABLE
        q = Q()
        for p in prefixes:
            q |= Q(no_compte__startswith=p)
        rows = entries.filter(q).values('no_compte').annotate(t=Sum(field)).order_by('no_compte')
        return [{'compte': r['no_compte'],
                 'libelle': _plan.get(r['no_compte'], r['no_compte']),
                 'montant': round(float(r['t'] or 0), 2)}
                for r in rows if float(r['t'] or 0) > 0]

    def get(self, request):
        tenant   = get_tenant(request)
        exercice = get_exercice(tenant, request)
        if not exercice:
            return Response({})

        plan    = get_plan_dict(tenant)
        entries = JournalEntry.objects.filter(tenant=tenant, exercice=exercice)
        caht    = _sum_paiements(Paiement.objects.filter(tenant=tenant, exercice=exercice))
        systeme = _detecter_systeme(caht)

        # ── PRODUITS DES ACTIVITÉS ORDINAIRES ───────────────────────────
        # Production de l'exercice = prestations de services + autres produits
        ventes_marchandises       = self._sum(entries, ['701'],              'credit')
        prestations_services      = self._sum(entries, ['706', '707', '708'], 'credit')
        subventions_exploitation  = self._sum(entries, ['74'],               'credit')
        autres_produits           = self._sum(entries, ['75'],               'credit')
        reprises_amort            = self._sum(entries, ['781', '791'],       'credit')
        production_exercice = prestations_services + subventions_exploitation + autres_produits + reprises_amort

        # ── CHARGES DES ACTIVITÉS ORDINAIRES ────────────────────────────
        # Achats de marchandises
        achats_marchandises   = self._sum(entries, ['601'], 'debit')
        # Autres achats & consommations
        autres_achats         = self._sum(entries, ['602', '604', '605', '607', '608'], 'debit')
        transports            = self._sum(entries, ['61'], 'debit')
        services_ext_a        = self._sum(entries, ['621', '622', '623', '624', '625'], 'debit')
        services_ext_b        = self._sum(entries, ['626', '627', '628'], 'debit')
        impots_taxes          = self._sum(entries, ['641', '642', '645'], 'debit')
        autres_charges        = self._sum(entries, ['651', '652', '653', '655', '658'], 'debit')
        charges_personnel     = self._sum(entries, ['661', '662', '663', '664', '665', '666', '6641'], 'debit')
        dotations_amort       = self._sum(entries, ['681', '691'], 'debit')

        # ── SIG EN CASCADE (SYSCOHADA Révisé) ────────────────────────────
        # 1. Marge Commerciale (MC)
        mc = ventes_marchandises - achats_marchandises

        # 2. Valeur Ajoutée Brute (VAB)
        consommations_interm = autres_achats + transports + services_ext_a + services_ext_b
        vab = mc + production_exercice - consommations_interm

        # 3. Excédent Brut d'Exploitation (EBE)
        ebe = vab - charges_personnel - impots_taxes

        # 4. Résultat d'Exploitation (RE)
        re = ebe - dotations_amort - autres_charges

        # 5. Résultat Financier (RF)
        produits_financiers = self._sum(entries, ['77'], 'credit')
        charges_financieres = self._sum(entries, ['67', '631'], 'debit')
        rf = produits_financiers - charges_financieres

        # 6. Résultat des Activités Ordinaires (RAO)
        rao = re + rf

        # 7. Résultat HAO
        produits_hao = self._sum(entries, ['82', '84', '85', '86', '88'], 'credit')
        charges_hao  = self._sum(entries, ['81', '83', '85', '87'], 'debit')
        resultat_hao = produits_hao - charges_hao

        # 8. Résultat avant impôt
        resultat_avant_impot = rao + resultat_hao

        # 9. Impôt sur le résultat
        impot = self._sum(entries, ['89'], 'debit')

        # 10. Résultat net de l'exercice
        resultat_net = resultat_avant_impot - impot

        # Totaux COMPLETS : 7x + HAO produits (82,84,86,88) vs 6x + HAO charges (81,83,87,89)
        _7agg = entries.filter(no_compte__startswith='7').aggregate(d=Sum('debit'), c=Sum('credit'))
        _6agg = entries.filter(no_compte__startswith='6').aggregate(d=Sum('debit'), c=Sum('credit'))
        _haop_agg = entries.filter(
            Q(no_compte__startswith='82') | Q(no_compte__startswith='84') |
            Q(no_compte__startswith='86') | Q(no_compte__startswith='88')
        ).aggregate(d=Sum('debit'), c=Sum('credit'))
        _haoc_agg = entries.filter(
            Q(no_compte__startswith='81') | Q(no_compte__startswith='83') |
            Q(no_compte__startswith='87') | Q(no_compte__startswith='89')
        ).aggregate(d=Sum('debit'), c=Sum('credit'))
        total_produits = round(
            float(_7agg['c'] or 0) - float(_7agg['d'] or 0) +
            max(float(_haop_agg['c'] or 0) - float(_haop_agg['d'] or 0), 0), 2)
        total_charges = round(
            float(_6agg['d'] or 0) - float(_6agg['c'] or 0) +
            max(float(_haoc_agg['d'] or 0) - float(_haoc_agg['c'] or 0), 0), 2)
        resultat_net  = round(total_produits - total_charges, 2)

        return Response({
            'exercice':       exercice.annee_scolaire,
            'systeme':        systeme,
            'caht':           round(caht, 2),
            'sig': {
                'ventes_marchandises':      round(ventes_marchandises, 2),
                'achats_marchandises':      round(achats_marchandises, 2),
                'mc':                       round(mc, 2),
                'production_exercice':      round(production_exercice, 2),
                'consommations_interm':     round(consommations_interm, 2),
                'vab':                      round(vab, 2),
                'charges_personnel':        round(charges_personnel, 2),
                'impots_taxes':             round(impots_taxes, 2),
                'ebe':                      round(ebe, 2),
                'dotations_amort':          round(dotations_amort, 2),
                'autres_charges':           round(autres_charges, 2),
                're':                       round(re, 2),
                'produits_financiers':      round(produits_financiers, 2),
                'charges_financieres':      round(charges_financieres, 2),
                'rf':                       round(rf, 2),
                'rao':                      round(rao, 2),
                'resultat_hao':             round(resultat_hao, 2),
                'resultat_avant_impot':     round(resultat_avant_impot, 2),
                'impot':                    round(impot, 2),
                'resultat_net':             round(resultat_net, 2),
            },
            'detail_produits': self._detail(entries, ['7', '82', '84', '86', '88'], 'credit', plan),
            'detail_charges':  self._detail(entries, ['6', '81', '83', '85', '87', '89'], 'debit', plan),
            'total_produits':  total_produits,
            'total_charges':   total_charges,
            'resultat_net':    resultat_net,
        })


# ── Helpers Bilan / TFT SYSCOHADA ────────────────────────────────────────────
def _compute_account_sfs(entries, exercice, tenant):
    """SF_D / SF_C par compte, soldes initiaux tréso inclus."""
    MOBILE_SUBS = ('5521', '5522', '5523')
    raw = {}
    for r in entries.exclude(no_compte__in=MOBILE_SUBS).values('no_compte').annotate(
        d=Sum('debit'), c=Sum('credit')
    ):
        raw[r['no_compte']] = [float(r['d'] or 0), float(r['c'] or 0)]
    for no, init in [('521', float(exercice.solde_initial_banque)),
                     ('571', float(exercice.solde_initial_caisse))]:
        if no in raw:
            raw[no][0] += init
        elif init:
            raw[no] = [init, 0.0]
    mob_d, mob_c = _mobile_aggregate(tenant, exercice)
    raw['552'] = [float(exercice.solde_initial_mobile) + mob_d, mob_c]
    return {no: {'sf_d': round(max(d - c, 0), 2), 'sf_c': round(max(c - d, 0), 2)}
            for no, (d, c) in raw.items()}


def _sum_sf_side(sfs, side, prefixes, plan):
    """Somme sf_d ou sf_c pour les comptes dont le numéro commence par l'un des préfixes."""
    total = 0.0
    detail = []
    for no in sorted(sfs):
        amt = sfs[no][side]
        if amt > 0 and any(no.startswith(p) for p in prefixes):
            total += amt
            detail.append({'compte': no, 'libelle': plan.get(no, no), 'montant': round(amt, 2)})
    return round(total, 2), detail


# ── Bilan SYSCOHADA Révisé (Articles 7-11 et 23 AUDCIF) ─────────────────────
class BilanView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant    = get_tenant(request)
        exercice  = get_exercice(tenant, request)
        if not exercice:
            return Response({})

        plan      = get_plan_dict(tenant)
        entries   = JournalEntry.objects.filter(tenant=tenant, exercice=exercice)
        paiements = Paiement.objects.filter(tenant=tenant, exercice=exercice)
        caht      = _sum_paiements(paiements)
        systeme   = _detecter_systeme(caht)

        sfs = _compute_account_sfs(entries, exercice, tenant)

        # ── A — Actif Immobilisé ─────────────────────────────────────────
        incorporel_t, incorporel_d = _sum_sf_side(sfs, 'sf_d', ['20', '21'], plan)
        corporel_t,   corporel_d   = _sum_sf_side(sfs, 'sf_d', ['22', '23', '24', '25'], plan)
        financier_t,  financier_d  = _sum_sf_side(sfs, 'sf_d', ['26', '27'], plan)
        amort_t, _                 = _sum_sf_side(sfs, 'sf_c', ['28'], plan)
        total_corporel_net = round(max(corporel_t - amort_t, 0), 2)
        total_immobilise   = round(incorporel_t + total_corporel_net + financier_t, 2)

        # ── B — Actif Circulant AO (stocks + créances tiers 40-47 SF_D) ─
        stocks_t,   stocks_d   = _sum_sf_side(sfs, 'sf_d', ['31','32','33','34','35','36','37','38'], plan)
        creances_t, creances_d = _sum_sf_side(sfs, 'sf_d', ['40','41','42','43','44','45','46','47'], plan)
        prov_b_t,   _          = _sum_sf_side(sfs, 'sf_c', ['49'], plan)
        total_circulant_ao = round(stocks_t + creances_t - prov_b_t, 2)

        # ── C — Actif Circulant HAO (48x SF_D) ───────────────────────────
        hao_actif_t, hao_actif_d = _sum_sf_side(sfs, 'sf_d', ['48'], plan)

        # ── D — Trésorerie-Actif ─────────────────────────────────────────
        treso_actif_t, treso_actif_d = _sum_sf_side(sfs, 'sf_d', ['51','52','53','54','55','57','58'], plan)

        total_actif = round(total_immobilise + total_circulant_ao + hao_actif_t + treso_actif_t, 2)

        # ── F — Capitaux Propres ─────────────────────────────────────────
        capital = float(exercice.solde_initial_banque + exercice.solde_initial_caisse +
                        exercice.solde_initial_mobile)
        _7agg = entries.filter(no_compte__startswith='7').aggregate(d=Sum('debit'), c=Sum('credit'))
        _6agg = entries.filter(no_compte__startswith='6').aggregate(d=Sum('debit'), c=Sum('credit'))
        resultat_net = round(
            float(_7agg['c'] or 0) - float(_7agg['d'] or 0) -
            (float(_6agg['d'] or 0) - float(_6agg['c'] or 0)), 2)
        total_capitaux = round(capital + resultat_net, 2)

        # ── G — Dettes Financières (16x-19x SF_C) ───────────────────────
        dettes_fin_t, dettes_fin_d = _sum_sf_side(sfs, 'sf_c', ['16', '17', '18', '19'], plan)

        # ── H — Passif Circulant AO (40x-47x SF_C) ──────────────────────
        dettes_ao_t, dettes_ao_d = _sum_sf_side(sfs, 'sf_c', ['40','41','42','43','44','45','46','47'], plan)

        # ── I — Passif Circulant HAO (48x SF_C) ─────────────────────────
        hao_passif_t, hao_passif_d = _sum_sf_side(sfs, 'sf_c', ['48'], plan)

        # ── J — Trésorerie-Passif (découverts 5x SF_C) ──────────────────
        treso_passif_t, treso_passif_d = _sum_sf_side(sfs, 'sf_c', ['51','52','53','54','55','57','58'], plan)

        total_passif = round(total_capitaux + dettes_fin_t + dettes_ao_t + hao_passif_t + treso_passif_t, 2)

        def _sub(detail, prefixes):
            return round(sum(x['montant'] for x in detail if any(x['compte'].startswith(p) for p in prefixes)), 2)

        return Response({
            'exercice':   exercice.annee_scolaire,
            'date_bilan': str(exercice.date_fin),
            'systeme':    systeme,
            'caht':       round(caht, 2),
            'seuil_smt':  SEUIL_SMT_SERVICES,
            'actif': {
                'immobilise': {
                    'incorporel': incorporel_d,
                    'corporel':   corporel_d,
                    'financier':  financier_d,
                    'amort':      round(amort_t, 2),
                    'total':      total_immobilise,
                },
                'circulant_ao': {
                    'stocks':   stocks_d,
                    'creances': creances_d,
                    'total':    total_circulant_ao,
                },
                'circulant_hao': {
                    'detail': hao_actif_d,
                    'total':  hao_actif_t,
                },
                'tresorerie_actif': {
                    'detail': treso_actif_d,
                    'total':  treso_actif_t,
                },
                'total_actif': total_actif,
            },
            'passif': {
                'capitaux_propres': {
                    'capital':      round(capital, 2),
                    'resultat_net': resultat_net,
                    'total':        total_capitaux,
                },
                'dettes_financieres': {
                    'detail': dettes_fin_d,
                    'total':  dettes_fin_t,
                },
                'passif_circulant_ao': {
                    'detail':           dettes_ao_d,
                    'fournisseurs':     _sub(dettes_ao_d, ['40', '401', '404']),
                    'dettes_fiscales':  _sub(dettes_ao_d, ['44']),
                    'dettes_personnel': _sub(dettes_ao_d, ['42']),
                    'dettes_sociales':  _sub(dettes_ao_d, ['43']),
                    'total':            dettes_ao_t,
                },
                'passif_circulant_hao': {
                    'detail': hao_passif_d,
                    'total':  hao_passif_t,
                },
                'tresorerie_passif': {
                    'detail': treso_passif_d,
                    'total':  treso_passif_t,
                },
                'total_passif': total_passif,
            },
            'equilibre': abs(total_actif - total_passif) < 1,
        })


# ── Tableau des Flux de Trésorerie — Méthode Indirecte (AUDCIF Art. 32) ──────
class TableauFluxView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.db.models import Count

        tenant   = get_tenant(request)
        exercice = get_exercice(tenant, request)
        if not exercice:
            return Response({})

        paiements = Paiement.objects.filter(tenant=tenant, exercice=exercice)
        entries   = JournalEntry.objects.filter(tenant=tenant, exercice=exercice)
        plan      = get_plan_dict(tenant)
        systeme   = _detecter_systeme(_sum_paiements(paiements))

        sfs = _compute_account_sfs(entries, exercice, tenant)

        # ── A — Flux opérationnels (méthode indirecte) ───────────────────
        _7agg = entries.filter(no_compte__startswith='7').aggregate(d=Sum('debit'), c=Sum('credit'))
        _6agg = entries.filter(no_compte__startswith='6').aggregate(d=Sum('debit'), c=Sum('credit'))
        resultat_net = round(
            float(_7agg['c'] or 0) - float(_7agg['d'] or 0) -
            (float(_6agg['d'] or 0) - float(_6agg['c'] or 0)), 2)

        amort = round(float(entries.filter(
            Q(no_compte__startswith='681') | Q(no_compte__startswith='691')
        ).aggregate(t=Sum('debit'))['t'] or 0), 2)

        actif_b_t, _ = _sum_sf_side(sfs, 'sf_d',
            ['31','32','33','34','35','36','37','38','40','41','42','43','44','45','46','47'], plan)
        passif_h_t, _ = _sum_sf_side(sfs, 'sf_c',
            ['40','41','42','43','44','45','46','47'], plan)
        var_actif_b  = round(-actif_b_t, 2)
        var_passif_h = round(passif_h_t, 2)
        flux_a = round(resultat_net + amort + var_actif_b + var_passif_h, 2)

        # ── B — Flux d'investissement ────────────────────────────────────
        TRESO_COMPTES = list(MOBILE_ACCOUNTS) + ['521', '522', '571']
        agg_inv_out = entries.filter(
            source='INVEST', no_compte__in=TRESO_COMPTES, credit__gt=0,
        ).aggregate(t=Sum('credit'))
        acquisitions = round(float(agg_inv_out['t'] or 0), 2)

        agg_inv_in = entries.filter(
            source__in=('INVEST', 'CESSION'), no_compte__in=TRESO_COMPTES, debit__gt=0,
        ).aggregate(t=Sum('debit'))
        cessions = round(float(agg_inv_in['t'] or 0), 2)

        flux_b = round(cessions - acquisitions, 2)

        # ── C — Flux de financement ──────────────────────────────────────
        agg_empr = entries.filter(
            Q(no_compte__startswith='16') | Q(no_compte__startswith='17') |
            Q(no_compte__startswith='18') | Q(no_compte__startswith='19')
        ).aggregate(d=Sum('debit'), c=Sum('credit'))
        nouveaux_emprunts = round(float(agg_empr['c'] or 0), 2)
        remboursements    = round(float(agg_empr['d'] or 0), 2)
        flux_c = round(nouveaux_emprunts - remboursements, 2)

        # ── TRÉSORERIE ────────────────────────────────────────────────────
        treso_actif_t,  _ = _sum_sf_side(sfs, 'sf_d', ['51','52','53','54','55','57','58'], plan)
        treso_passif_t, _ = _sum_sf_side(sfs, 'sf_c', ['51','52','53','54','55','57','58'], plan)
        tn_fin   = round(treso_actif_t - treso_passif_t, 2)
        tn_debut = round(float(exercice.solde_initial_banque + exercice.solde_initial_caisse +
                               exercice.solde_initial_mobile), 2)
        variation = round(flux_a + flux_b + flux_c, 2)

        par_mode = paiements.values('mode_paiement').annotate(
            nb=Count('id'),
            total=Sum('montant_inscription') + Sum('montant_mensualite') +
                  Sum('montant_uniforme')    + Sum('montant_fournitures') +
                  Sum('montant_cantine')     + Sum('montant_divers')
        ).order_by('-total')

        return Response({
            'exercice': exercice.annee_scolaire,
            'methode':  'Indirecte',
            'systeme':  systeme,
            'flux_a': {
                'resultat_net':  resultat_net,
                'amort':         amort,
                'var_actif_b':   var_actif_b,
                'var_passif_h':  var_passif_h,
                'flux_net':      flux_a,
            },
            'flux_b': {
                'acquisitions': acquisitions,
                'cessions':     cessions,
                'flux_net':     flux_b,
            },
            'flux_c': {
                'emprunts':       nouveaux_emprunts,
                'remboursements': remboursements,
                'flux_net':       flux_c,
            },
            'tresorerie': {
                'tn_debut':  tn_debut,
                'variation': variation,
                'tn_fin':    tn_fin,
            },
            'par_mode': [{'mode': m['mode_paiement'], 'nb': m['nb'],
                          'total': float(m['total'] or 0)} for m in par_mode],
        })


# ── Notes Annexes ──────────────────────────────────────────────────────────────
class NotesAnnexesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant   = get_tenant(request)
        exercice = get_exercice(tenant, request)
        if not exercice:
            return Response({})

        paiements = Paiement.objects.filter(tenant=tenant, exercice=exercice)
        entries   = JournalEntry.objects.filter(tenant=tenant, exercice=exercice)
        caht      = _sum_paiements(paiements)
        systeme   = _detecter_systeme(caht)

        nb_eleves      = Eleve.objects.filter(tenant=tenant, exercice=exercice).count()
        nb_paiements   = paiements.count()
        total_charges  = float(entries.filter(no_compte__startswith='6').aggregate(t=Sum('debit'))['t'] or 0)
        charges_perso  = float(entries.filter(no_compte__in=['661', '662']).aggregate(t=Sum('debit'))['t'] or 0)

        # Répartition par section
        from apps.eleves.models import Section
        from django.db.models import Count
        sections = Eleve.objects.filter(tenant=tenant, exercice=exercice).values(
            'section__nom'
        ).annotate(nb=Count('id')).order_by('-nb')

        # Trésorerie de clôture par compte
        treso_cloture = []
        for no, lib in [('521', 'Banque'), ('571', 'Caisse'), ('552', 'Mobile Money')]:
            if no == '552':
                mob_d, mob_c = _mobile_aggregate(tenant, exercice)
                solde = float(getattr(exercice, 'solde_initial_mobile', 0)) + mob_d - mob_c
            else:
                so = float(getattr(exercice, f'solde_initial_{"banque" if no=="521" else "caisse"}', 0))
                agg = entries.filter(no_compte=no).aggregate(d=Sum('debit'), c=Sum('credit'))
                solde = so + float(agg['d'] or 0) - float(agg['c'] or 0)
            if abs(solde) > 0:
                treso_cloture.append({'compte': no, 'libelle': lib, 'solde': round(solde, 2)})

        return Response({
            'exercice':   exercice.annee_scolaire,
            'date_debut': str(exercice.date_debut),
            'date_fin':   str(exercice.date_fin),
            'systeme':    systeme,
            'caht':       round(caht, 2),
            'seuil_smt':  SEUIL_SMT_SERVICES,
            # Note 1 — Présentation de l'entité
            'note1': {
                'secteur':       'Éducation (Services)',
                'referentiel':   f'SYSCOHADA Révisé (AUDCIF 2017) — {systeme}',
                'nb_eleves':     nb_eleves,
                'nb_paiements':  nb_paiements,
                'sections':      [{'nom': s['section__nom'] or '—', 'nb': s['nb']} for s in sections],
            },
            # Note 2 — Méthodes et principes
            'note2': {
                'base_evaluation': 'Coût historique',
                'amortissement':   'Linéaire sur la durée d\'utilisation estimée',
                'creances':        'Évaluées à leur valeur nominale — dépréciation en cas de risque d\'irrecouvrabilité',
                'tresorerie':      'Inscrite à sa valeur nominale. Mobile Money : WAVE (5521), Orange Money (5522), Free Money (5523)',
                'comptabilite':    'Comptabilité d\'engagement — créances et dettes constatées à la date de l\'opération',
            },
            # Note 3 — Charges de personnel
            'note3': {
                'masse_salariale': round(charges_perso, 2),
                'total_charges':   round(total_charges, 2),
            },
            # Note 4 — Trésorerie de clôture
            'note4': { 'comptes': treso_cloture },
        })


# ── Historique des exercices ───────────────────────────────────────────────────
class HistoriqueExercicesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = get_tenant(request)

        exercices_clotures = Exercice.objects.filter(
            tenant=tenant, cloture=True
        ).order_by('-date_debut')

        exercice_actif = Exercice.objects.filter(
            tenant=tenant, cloture=False
        ).order_by('-date_debut').first()

        historique = []
        for ex in exercices_clotures:
            pmt = Paiement.objects.filter(tenant=tenant, exercice=ex)
            total_rec = _sum_paiements(pmt)
            total_cha = float(JournalEntry.objects.filter(
                tenant=tenant, exercice=ex, no_compte__startswith='6'
            ).aggregate(t=Sum('debit'))['t'] or 0)
            nb_eleves = Eleve.objects.filter(tenant=tenant, exercice=ex).count()

            historique.append({
                'id':             str(ex.id),
                'annee_scolaire': ex.annee_scolaire,
                'date_debut':     str(ex.date_debut),
                'date_fin':       str(ex.date_fin),
                'date_cloture':   str(ex.date_cloture) if ex.date_cloture else None,
                'total_recettes': round(total_rec, 2),
                'total_charges':  round(total_cha, 2),
                'resultat_net':   round(total_rec - total_cha, 2),
                'nb_eleves':      nb_eleves,
                'nb_paiements':   pmt.count(),
            })

        return Response({
            'exercice_actif': {
                'annee_scolaire': exercice_actif.annee_scolaire,
                'date_debut':     str(exercice_actif.date_debut),
                'date_fin':       str(exercice_actif.date_fin),
            } if exercice_actif else None,
            'historique':            historique,
            'nb_exercices_clotures': len(historique),
        })


# ── Charges ───────────────────────────────────────────────────────────────────
class ChargeView(APIView):
    permission_classes = [IsAuthenticated]

    # Comptes de charge acceptés — uniquement classe 6 (SYSCOHADA Révisé).
    # Les immobilisations (classe 2) relèvent du module Investissement, pas des charges.
    PLAN_CHARGES = {
        # Classe 6 — Achats
        '601': 'Achats de marchandises',
        '604': 'Achats stockés — matières et fournitures',
        '605': 'Autres achats',
        '6051': 'Fournitures non stockables — Eau',
        '6052': 'Fournitures non stockables — Électricité',
        '6054': 'Matériel et fournitures non stockables',
        # Transports
        '614': 'Transports du personnel',
        '618': 'Autres frais de transport',
        # Services extérieurs A
        '621': 'Sous-traitance générale',
        '622': 'Locations et charges locatives',
        '624': 'Entretien, réparations et maintenance',
        '625': "Primes d'assurance",
        '626': 'Études, recherches et documentation',
        '627': 'Publicité, publications et relations publiques',
        '628': 'Frais de télécommunications',
        # Services extérieurs B
        '631': 'Frais bancaires',
        '633': 'Frais de formation du personnel',
        '635': 'Frais de déplacements et de réception',
        # Impôts et taxes
        '641': 'Impôts directs',
        '6413': 'Taxes sur la masse salariale (CFCE)',
        '645': "Droits d'enregistrement et de timbre",
        # Autres charges
        '651': 'Pertes sur créances irrecouvrables',
        '658': 'Charges diverses',
        # Charges de personnel
        '661': 'Appointements et salaires',
        '662': 'Charges sociales salariales (IPRES)',
        '663': 'Indemnités et avantages divers',
        '664': 'Cotisations sociales de l\'employeur',
        '6641': 'Cotisations patronales (IPRES/CSS/ATMP)',
        # Frais financiers
        '671': "Intérêts d'emprunts",
        '675': 'Escomptes accordés',
        # Dotations
        '681': 'Dotations aux amortissements d\'exploitation',
        '691': 'Dotations aux provisions d\'exploitation',
    }

    # Compte fournisseur par défaut selon la nature de la charge
    COMPTE_FOURN_MAP = {
        '2': '404',   # Immobilisations → 404 Fournisseurs d'immobilisations
        '6': '401',   # Charges d'exploitation → 401 Fournisseurs ordinaires
    }
    PLAN_FOURNISSEURS = {
        '401': '401 — Fournisseurs (dettes en compte)',
        '404': '404 — Fournisseurs, acquisitions d\'immobilisations',
        '481': '481 — Fournisseurs d\'immobilisations',
    }

    def get(self, request):
        tenant   = get_tenant(request)
        exercice = get_exercice(tenant)
        if not exercice:
            return Response([])

        # Toutes les charges : manuelles (CHARGE) + paie (PAIE) + comptabilisations
        # budget (BUDGET) sur comptes 6xx — le suivi doit être identique quelle
        # que soit l'origine. Les immobilisations (2xx, INVEST) relèvent du
        # module Investissement.
        charges = JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice,
            source__in=('CHARGE', 'PAIE', 'BUDGET'),
            debit__gt=0,
            no_compte__startswith='6',
        ).order_by('-date_ecriture')

        # Masquer les écritures annulées/modifiées : leur contre-écriture les
        # référence par source_id (le journal, lui, garde tout — SYSCOHADA).
        annulees = set(JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice,
            source__in=('CHARGE', 'BUDGET'),
            source_id__isnull=False,
        ).values_list('source_id', flat=True))
        charges = [c for c in charges if c.id not in annulees]

        return Response([{
            'id':             str(c.id),
            'date':           str(c.date_ecriture),
            'no_piece':       c.no_piece,
            'no_compte':      c.no_compte,
            'libelle':        c.libelle,
            'montant':        float(c.debit),
            'source':         c.source,
            'libelle_compte': self.PLAN_CHARGES.get(c.no_compte, c.no_compte),
        } for c in charges])

    def post(self, request):
        tenant   = get_tenant(request)
        exercice = get_exercice(tenant)
        if not exercice:
            return Response({'error': 'Aucun exercice actif'}, status=400)

        data      = request.data
        no_compte = data.get('no_compte', '658')  # 658 Charges diverses — 606 n'existe pas en SYSCOHADA
        montant   = float(data.get('montant', 0))
        libelle   = data.get('libelle', '')
        date      = data.get('date', str(timezone.now().date()))

        if montant <= 0:
            return Response({'error': 'Montant invalide'}, status=400)

        if not str(no_compte).startswith('6'):
            return Response({'error': "Compte de charge invalide : seuls les comptes de classe 6 sont autorisés. "
                                      "Les immobilisations relèvent du module Investissement."}, status=400)

        from django.db.models import Max
        import re
        # Séquence commune CHARGE + BUDGET : les deux produisent des pièces
        # CHG-xxxx, ignorer l'une des sources créait des collisions de numéro.
        last = JournalEntry.objects.filter(
            tenant=tenant, source__in=('CHARGE', 'BUDGET')
        ).aggregate(Max('no_piece'))['no_piece__max']
        nums     = re.findall(r'\d+', last or 'CHG-0000')
        no_piece = f"CHG-{int(nums[-1]) + 1:04d}" if nums else 'CHG-0001'

        libelle_compte = self.PLAN_CHARGES.get(no_compte, no_compte)

        # Compte trésorerie au crédit (règlement)
        compte_tresorerie = data.get('compte_credit', '571')

        # Compte fournisseur intermédiaire : fourni par le client ou déduit du compte charge
        # 401 pour charges 6xx, 404 pour immobilisations 2xx, 481 explicitement possible
        compte_fournisseur = data.get('compte_fournisseur') or \
                             self.COMPTE_FOURN_MAP.get(no_compte[0] if no_compte else '6', '401')

        libelle_fourn = self.PLAN_FOURNISSEURS.get(compte_fournisseur,
                                                    f"Fournisseur ({compte_fournisseur})")

        # Écriture 1 — Constatation dette fournisseur : Débit 6xx/2xx / Crédit 401|404|481
        # Écriture 2 — Règlement                     : Débit 401|404|481 / Crédit 5xx
        ecritures = [
            dict(ordre=1, no_compte=no_compte,         debit=montant, credit=0,
                 libelle=f"{libelle_compte} — {libelle}"),
            dict(ordre=2, no_compte=compte_fournisseur, debit=0,       credit=montant,
                 libelle=f"{libelle_fourn} — {libelle}"),
            dict(ordre=3, no_compte=compte_fournisseur, debit=montant, credit=0,
                 libelle=f"Règlement {libelle_fourn} — {libelle}"),
            dict(ordre=4, no_compte=compte_tresorerie,  debit=0,       credit=montant,
                 libelle=f"Règlement {libelle_fourn} — {libelle}"),
        ]

        for e in ecritures:
            JournalEntry.objects.create(
                tenant=tenant, exercice=exercice,
                no_piece=no_piece, date_ecriture=date,
                source='CHARGE', source_id=None, **e
            )

        return Response({'success': True, 'no_piece': no_piece,
                         'montant': montant, 'libelle': libelle}, status=201)

    def put(self, request, pk):
        """Modification SYSCOHADA : contre-écritures sur l'original + nouvelle charge."""
        import datetime
        import re as _re
        tenant   = get_tenant(request)
        exercice = get_exercice(tenant)
        if not exercice:
            return Response({'error': 'Aucun exercice actif'}, status=400)
        try:
            entry = JournalEntry.objects.get(id=pk)
        except JournalEntry.DoesNotExist:
            return Response({'error': 'Écriture introuvable'}, status=404)

        # Fonctionne pour les charges directes (CHARGE) comme pour les
        # comptabilisations de budget (BUDGET) : la pièce garde sa source
        # d'origine pour que le réalisé budget continue de la suivre.
        source_piece = entry.source if entry.source in ('CHARGE', 'BUDGET') else 'CHARGE'
        entries_orig = JournalEntry.objects.filter(
            tenant=tenant, source=source_piece, no_piece=entry.no_piece
        )

        # 1 — Contre-écritures (annulation de l'original)
        from django.db.models import Max as _Max
        last = JournalEntry.objects.filter(tenant=tenant, source__in=('CHARGE', 'BUDGET')).aggregate(
            _Max('no_piece')
        )['no_piece__max']
        nums = _re.findall(r'\d+', last or 'CHG-0000')
        no_piece_annul = f"CHG-{int(nums[-1]) + 1:04d}" if nums else 'CHG-0001'

        for e in entries_orig:
            JournalEntry.objects.create(
                tenant=tenant, exercice=exercice,
                no_piece=no_piece_annul, date_ecriture=datetime.date.today(),
                # source_id = écriture annulée → la liste des charges masque l'original
                source=source_piece, source_id=e.id,
                no_compte=e.no_compte, debit=e.credit, credit=e.debit,
                libelle=f"MODIF — {e.libelle}", ordre=e.ordre,
            )

        # 2 — Nouvelle charge avec les données modifiées
        data_new      = request.data
        no_compte_new = data_new.get('no_compte', entry.no_compte)
        montant_new   = float(data_new.get('montant', 0))
        libelle_new   = data_new.get('libelle', entry.libelle)
        date_new      = data_new.get('date', str(entry.date_ecriture))
        compte_tresorerie_new = data_new.get('compte_credit', '571')

        if montant_new <= 0:
            return Response({'error': 'Montant invalide'}, status=400)

        if not str(no_compte_new).startswith('6'):
            return Response({'error': "Compte de charge invalide : seuls les comptes de classe 6 sont autorisés. "
                                      "Les immobilisations relèvent du module Investissement."}, status=400)

        last2 = JournalEntry.objects.filter(tenant=tenant, source__in=('CHARGE', 'BUDGET')).aggregate(
            _Max('no_piece')
        )['no_piece__max']
        nums2 = _re.findall(r'\d+', last2 or 'CHG-0000')
        no_piece_new = f"CHG-{int(nums2[-1]) + 1:04d}" if nums2 else 'CHG-0001'

        compte_fournisseur = self.COMPTE_FOURN_MAP.get(
            no_compte_new[0] if no_compte_new else '6', '401'
        )
        libelle_compte = self.PLAN_CHARGES.get(no_compte_new, no_compte_new)
        libelle_fourn  = self.PLAN_FOURNISSEURS.get(compte_fournisseur,
                                                      f"Fournisseur ({compte_fournisseur})")

        ecritures_new = [
            dict(ordre=1, no_compte=no_compte_new,      debit=montant_new, credit=0,
                 libelle=f"{libelle_compte} — {libelle_new}"),
            dict(ordre=2, no_compte=compte_fournisseur,  debit=0, credit=montant_new,
                 libelle=f"{libelle_fourn} — {libelle_new}"),
            dict(ordre=3, no_compte=compte_fournisseur,  debit=montant_new, credit=0,
                 libelle=f"Règlement {libelle_fourn} — {libelle_new}"),
            dict(ordre=4, no_compte=compte_tresorerie_new, debit=0, credit=montant_new,
                 libelle=f"Règlement {libelle_fourn} — {libelle_new}"),
        ]
        for e in ecritures_new:
            JournalEntry.objects.create(
                tenant=tenant, exercice=exercice,
                no_piece=no_piece_new, date_ecriture=date_new,
                source=source_piece, source_id=None, **e
            )

        from core.models import log_audit
        log_audit(request, 'MODIFIER', 'Charge', entry.no_piece,
                  f"Modification {entry.no_piece} → {no_piece_new} — {montant_new:,.0f} FCFA")

        return Response({
            'success':       True,
            'ancien_no_piece': entry.no_piece,
            'no_piece_annul':  no_piece_annul,
            'no_piece_new':    no_piece_new,
            'montant':         montant_new,
        })

    def delete(self, request, pk):
        """Annulation par contre-écritures SYSCOHADA (pas de suppression physique)."""
        tenant   = get_tenant(request)
        exercice = get_exercice(tenant)
        try:
            entry   = JournalEntry.objects.get(id=pk)
            source_piece = entry.source if entry.source in ('CHARGE', 'BUDGET') else 'CHARGE'
            entries = JournalEntry.objects.filter(tenant=tenant, source=source_piece, no_piece=entry.no_piece)
        except JournalEntry.DoesNotExist:
            return Response({'success': True})

        if not exercice:
            return Response({'error': 'Aucun exercice actif'}, status=400)

        import re as _re2
        from django.db.models import Max as _Max2
        last = JournalEntry.objects.filter(tenant=tenant, source__in=('CHARGE', 'BUDGET')).aggregate(_Max2('no_piece'))['no_piece__max']
        nums = _re2.findall(r'\d+', last or 'CHG-0000')
        no_piece_annul = f"CHG-{int(nums[-1]) + 1:04d}" if nums else 'CHG-0001'

        import datetime
        for e in entries:
            JournalEntry.objects.create(
                tenant=tenant, exercice=exercice,
                no_piece=no_piece_annul, date_ecriture=datetime.date.today(),
                # source_id = écriture annulée → la liste des charges masque l'original
                source=source_piece, source_id=e.id,
                no_compte=e.no_compte,
                debit=e.credit,
                credit=e.debit,
                libelle=f"Annulation {e.no_piece} — {e.libelle}",
                ordre=e.ordre,
            )

        from core.models import log_audit
        log_audit(request, 'ANNULER', 'Charge', entry.no_piece,
                  f"Contre-écriture {no_piece_annul} générée pour annuler {entry.no_piece}")
        return Response({'success': True, 'no_piece_annulation': no_piece_annul})


# ── Plan Comptable Paramétrable ───────────────────────────────────────────────
class PlanComptableView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = get_tenant(request)
        plan   = get_plan_dict(tenant)

        # Filtre optionnel ?type=CHARGE&classe=6
        type_filter   = request.query_params.get('type')
        classe_filter = request.query_params.get('classe')

        # Comptes DB (avec flag est_systeme, est_actif)
        db_comptes = {c.no_compte: c for c in CompteComptable.objects.filter(tenant=tenant)}

        NOMS_CLASSES = {
            1: 'Classe 1 — Ressources Durables',
            2: 'Classe 2 — Actif Immobilisé',
            3: 'Classe 3 — Stocks',
            4: 'Classe 4 — Créances et Dettes',
            5: 'Classe 5 — Trésorerie',
            6: 'Classe 6 — Charges des Activités Ordinaires',
            7: 'Classe 7 — Produits des Activités Ordinaires',
            8: 'Classe 8 — Comptes des Engagements Hors Bilan',
            9: 'Classe 9 — Comptes Analytiques',
        }

        rows = []
        classe_courante = None

        for no, libelle in sorted(plan.items(), key=lambda x: _compte_sort_key(x[0])):
            db = db_comptes.get(no)
            classe = int(no[0]) if no and no[0].isdigit() else 0
            type_compte = (
                'CHARGE'  if classe == 6 else
                'PRODUIT' if classe == 7 else
                'BILAN'
            )
            if db:
                type_compte = db.type
                classe      = db.classe

            if type_filter and type_compte != type_filter:
                continue
            if classe_filter and str(classe) != classe_filter:
                continue

            # Insérer un séparateur de classe (row_type='CLASSE') si la classe change
            if classe != classe_courante and not type_filter and not classe_filter:
                classe_courante = classe
                rows.append({
                    'no_compte':    '',
                    'libelle':      NOMS_CLASSES.get(classe, f'Classe {classe}'),
                    'type':         'CLASSE',
                    'classe':       classe,
                    'est_actif':    True,
                    'est_systeme':  True,
                    'est_personnalise': False,
                    'row_type':     'CLASSE',
                    'profondeur':   0,
                })

            # Profondeur basée sur la longueur du numéro de compte (sans les points)
            clean_len = len(no.replace('.', ''))
            profondeur = max(0, clean_len - 2)  # 2 chiffres = niveau 0, 3 = niveau 1, etc.

            rows.append({
                'no_compte':    no,
                'libelle':      db.libelle if db else libelle,
                'type':         type_compte,
                'classe':       classe,
                'est_actif':    db.est_actif if db else True,
                'est_systeme':  db.est_systeme if db else False,
                'est_personnalise': db is not None,
                'row_type':     'COMPTE',
                'profondeur':   profondeur,
            })
        return Response(rows)

    def post(self, request):
        tenant = get_tenant(request)
        no     = (request.data.get('no_compte') or '').strip()
        if not no:
            return Response({'error': 'no_compte requis'}, status=400)

        libelle = request.data.get('libelle', '').strip() or PLAN_COMPTABLE.get(no, no)
        try:
            classe = int(no[0]) if no[0].isdigit() else 1
        except (IndexError, ValueError):
            classe = 6

        type_compte = request.data.get('type') or (
            'CHARGE' if classe == 6 else 'PRODUIT' if classe == 7 else 'BILAN'
        )

        obj, created = CompteComptable.objects.update_or_create(
            tenant=tenant, no_compte=no,
            defaults={
                'libelle': libelle,
                'type':    type_compte,
                'classe':  classe,
                'est_actif': True,
            }
        )
        return Response({
            'no_compte': obj.no_compte,
            'libelle':   obj.libelle,
            'type':      obj.type,
            'classe':    obj.classe,
        }, status=201 if created else 200)

    def put(self, request, no_compte):
        tenant = get_tenant(request)
        try:
            obj = CompteComptable.objects.get(tenant=tenant, no_compte=no_compte)
        except CompteComptable.DoesNotExist:
            # Créer à partir du dict statique
            return self.post(request)

        if 'libelle' in request.data:
            obj.libelle = request.data['libelle']
        if 'type' in request.data:
            obj.type = request.data['type']
        if 'est_actif' in request.data:
            obj.est_actif = request.data['est_actif']
        obj.save()
        return Response({'no_compte': obj.no_compte, 'libelle': obj.libelle})

    def delete(self, request, no_compte):
        tenant = get_tenant(request)
        try:
            obj = CompteComptable.objects.get(tenant=tenant, no_compte=no_compte)
            if obj.est_systeme:
                return Response({'error': 'Compte système — non supprimable'}, status=403)
            obj.delete()
        except CompteComptable.DoesNotExist:
            pass
        return Response({'success': True})


# ── Budget Prévisionnel ───────────────────────────────────────────────────────
MOIS_CHAMPS = ['m01','m02','m03','m04','m05','m06','m07','m08','m09','m10','m11','m12']
MOIS_NOMS   = ['Jan','Fév','Mar','Avr','Mai','Jun','Jul','Aoû','Sep','Oct','Nov','Déc']


class BudgetView(APIView):
    permission_classes = [IsAuthenticated]

    def _realise_par_mois(self, tenant, exercice, no_compte):
        """Réalisé NET par mois pour un compte (et ses sous-comptes) :
        débits − crédits, pour que les annulations/modifications par
        contre-écriture (crédit sur le 6xx) soient bien déduites."""
        qs = JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice,
            source__in=('CHARGE', 'PAIE', 'BUDGET'),
        ).filter(
            Q(no_compte=no_compte) | Q(no_compte__startswith=no_compte)
        ).annotate(
            mois=ExtractMonth('date_ecriture')
        ).values('mois').annotate(d=Sum('debit'), c=Sum('credit'))
        return {r['mois']: float(r['d'] or 0) - float(r['c'] or 0) for r in qs}

    def get(self, request):
        tenant   = get_tenant(request)
        exercice = get_exercice(tenant)
        if not exercice:
            return Response({'lignes': [], 'totaux': {}, 'exercice': None})

        plan    = get_plan_dict(tenant)
        lignes  = BudgetLigne.objects.filter(tenant=tenant, exercice=exercice)

        result = []
        total_prevu = total_realise = 0.0
        total_fixe_prevu = total_fixe_realise = 0.0
        total_var_prevu  = total_var_realise  = 0.0
        # Totaux par mois (toutes lignes confondues) → comparaison mensuelle
        mois_prevu   = [0.0] * 12
        mois_realise = [0.0] * 12

        for l in lignes:
            realise_mois = self._realise_par_mois(tenant, exercice, l.no_compte)
            mois_data = []
            t_prevu = t_realise = 0.0

            for i, champ in enumerate(MOIS_CHAMPS, start=1):
                p = float(getattr(l, champ))
                r = realise_mois.get(i, 0.0)
                t_prevu   += p
                t_realise += r
                mois_prevu[i-1]   += p
                mois_realise[i-1] += r
                mois_data.append({'mois': i, 'nom': MOIS_NOMS[i-1], 'prevu': p, 'realise': r})

            pct = round(t_realise / t_prevu * 100, 1) if t_prevu else 0

            total_prevu   += t_prevu
            total_realise += t_realise
            if l.type_charge == 'FIXE':
                total_fixe_prevu   += t_prevu
                total_fixe_realise += t_realise
            else:
                total_var_prevu   += t_prevu
                total_var_realise += t_realise

            result.append({
                'id':          str(l.id),
                'no_compte':   l.no_compte,
                'libelle':     l.libelle or plan.get(l.no_compte, l.no_compte),
                'type_charge': l.type_charge,
                'mois':        mois_data,
                'total_prevu': round(t_prevu, 2),
                'total_realise': round(t_realise, 2),
                'taux_realisation': pct,
            })

        return Response({
            'exercice': exercice.annee_scolaire,
            'lignes':   result,
            'totaux': {
                'fixe':    {'prevu': round(total_fixe_prevu, 2), 'realise': round(total_fixe_realise, 2)},
                'variable':{'prevu': round(total_var_prevu, 2),  'realise': round(total_var_realise, 2)},
                'total':   {'prevu': round(total_prevu, 2),       'realise': round(total_realise, 2)},
            },
            # Comparaison budgétisé / réalisé mois par mois (toutes lignes)
            'mois_totaux': [
                {'mois': i + 1, 'nom': MOIS_NOMS[i],
                 'prevu': round(mois_prevu[i], 2), 'realise': round(mois_realise[i], 2),
                 'ecart': round(mois_prevu[i] - mois_realise[i], 2)}
                for i in range(12)
            ],
            'mois_noms': MOIS_NOMS,
        })

    def post(self, request):
        tenant   = get_tenant(request)
        exercice = get_exercice(tenant)
        if not exercice:
            return Response({'error': 'Aucun exercice actif'}, status=400)

        no_compte = (request.data.get('no_compte') or '').strip()
        if not no_compte:
            return Response({'error': 'no_compte requis'}, status=400)

        plan    = get_plan_dict(tenant)
        libelle = request.data.get('libelle') or plan.get(no_compte, no_compte)

        defaults = {
            'libelle':     libelle,
            'type_charge': request.data.get('type_charge', 'FIXE'),
        }
        # Montants mensuels
        for champ in MOIS_CHAMPS:
            val = request.data.get(champ, 0)
            defaults[champ] = float(val) if val else 0

        obj, created = BudgetLigne.objects.update_or_create(
            tenant=tenant, exercice=exercice, no_compte=no_compte,
            defaults=defaults,
        )
        return Response({'id': str(obj.id), 'no_compte': obj.no_compte}, status=201 if created else 200)

    def delete(self, request, pk):
        tenant = get_tenant(request)
        BudgetLigne.objects.filter(tenant=tenant, id=pk).delete()
        return Response({'success': True})


class BudgetComptabiliserView(APIView):
    """Génère une écriture de charge réelle depuis une ligne budget."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        tenant   = get_tenant(request)
        exercice = get_exercice(tenant)
        if not exercice:
            return Response({'error': 'Aucun exercice actif'}, status=400)

        try:
            ligne = BudgetLigne.objects.get(tenant=tenant, id=pk)
        except BudgetLigne.DoesNotExist:
            return Response({'error': 'Ligne budget introuvable'}, status=404)

        montant = float(request.data.get('montant', 0))
        if montant <= 0:
            return Response({'error': 'Montant invalide (doit être > 0)'}, status=400)

        libelle    = request.data.get('libelle') or ligne.libelle
        date_str   = request.data.get('date', str(timezone.now().date()))
        compte_tresorerie  = request.data.get('compte_credit', '571')
        compte_fournisseur = request.data.get('compte_fournisseur', '401')

        import re as _re
        from django.db.models import Max as _Max
        # Même séquence que les charges directes (pièces CHG-xxxx communes)
        last_piece = JournalEntry.objects.filter(tenant=tenant, source__in=('CHARGE', 'BUDGET')).aggregate(
            m=_Max('no_piece')
        )['m']
        nums = _re.findall(r'\d+', last_piece or 'CHG-0000')
        no_piece = f"CHG-{int(nums[-1]) + 1:04d}" if nums else 'CHG-0001'

        no_compte    = ligne.no_compte
        lib_compte   = ligne.libelle or no_compte
        lib_fourn    = f"Fournisseur ({compte_fournisseur})"

        for ordre, (nc, db, cr, lib) in enumerate([
            (no_compte,          montant, 0,       f"{lib_compte} — {libelle}"),
            (compte_fournisseur, 0,       montant, f"{lib_fourn} — {libelle}"),
            (compte_fournisseur, montant, 0,       f"Règlement {lib_fourn} — {libelle}"),
            (compte_tresorerie,  0,       montant, f"Règlement {lib_fourn} — {libelle}"),
        ], 1):
            JournalEntry.objects.create(
                tenant=tenant, exercice=exercice,
                no_piece=no_piece, date_ecriture=date_str,
                source='BUDGET', source_id=None,
                no_compte=nc, debit=db, credit=cr,
                libelle=lib, ordre=ordre,
            )

        return Response({'no_piece': no_piece, 'montant': montant, 'no_compte': no_compte})


# ── Investissements / Immobilisations ─────────────────────────────────────────
PLAN_IMMO = {
    '211': 'Frais de développement capitalisés',
    '212': 'Brevets, licences, logiciels',
    '221': 'Terrains naturels',
    '222': 'Terrains bâtis',
    '231': 'Bâtiments sur sol propre',
    '232': 'Bâtiments sur sol d\'autrui',
    '233': 'Installations techniques et agencements',
    '234': 'Aménagements et agencements divers',
    '241': 'Matériel et outillage',
    '244': 'Matériel et mobilier',
    '245': 'Matériel de transport',
    '248': 'Autres matériels et équipements',
}
PLAN_AMORT = {
    '2811': 'Amort. frais de développement',
    '2812': 'Amort. brevets, licences, logiciels',
    '2821': 'Amort. terrains naturels',
    '2822': 'Amort. terrains bâtis',
    '2831': 'Amort. bâtiments sur sol propre',
    '2832': 'Amort. bâtiments sur sol d\'autrui',
    '2833': 'Amort. installations techniques',
    '2834': 'Amort. aménagements et agencements',
    '2841': 'Amort. matériel et outillage',
    '2844': 'Amort. matériel et mobilier',
    '2845': 'Amort. matériel de transport',
    '2848': 'Amort. autres matériels et équipements',
}


def _immo_reste_a_regler(immo):
    """Reste dû au fournisseur pour ce bien = crédits (engagement) − débits (règlements)
    sur le compte fournisseur, à partir du journal INVEST. Couvre les acquisitions à
    crédit réglées plus tard, et les règlements partiels."""
    agg = JournalEntry.objects.filter(
        tenant_id=immo.tenant_id, source='INVEST', source_id=immo.id,
        no_compte=immo.compte_fournisseur,
    ).aggregate(d=Sum('debit'), c=Sum('credit'))
    credit = float(agg['c'] or 0)
    debit  = float(agg['d'] or 0)
    return round(max(credit - debit, 0.0), 2)


def _immo_to_dict(immo):
    reste = _immo_reste_a_regler(immo)
    return {
        'id':                    str(immo.id),
        'no_bien':               immo.no_bien,
        'libelle':               immo.libelle,
        'date_entree':           str(immo.date_entree),
        'valeur_entree':         float(immo.valeur_entree),
        'duree_utilisation':     immo.duree_utilisation,
        'mode_amortissement':    immo.mode_amortissement,
        'taux_amortissement':    immo.taux_amortissement,
        'annuite_amortissement': immo.annuite_amortissement,
        'cumul_amortissements':  float(immo.cumul_amortissements),
        'valeur_nette_comptable': immo.valeur_nette_comptable,
        'no_compte_immobilisation': immo.no_compte_immobilisation,
        'no_compte_amortissement':  immo.no_compte_amortissement,
        'libelle_compte_immo':   PLAN_IMMO.get(immo.no_compte_immobilisation)
                                 or PLAN_COMPTABLE.get(immo.no_compte_immobilisation, immo.no_compte_immobilisation),
        'compte_fournisseur':    immo.compte_fournisseur,
        'mode_reglement':        immo.mode_reglement,
        'compte_tresorerie':     immo.compte_tresorerie,
        'reste_a_regler':        reste,
        'montant_regle':         round(float(immo.valeur_entree) - reste, 2),
        'est_regle':             reste <= 0.01,
        'est_cede':              immo.est_cede,
        'est_amorti':            immo.est_amorti,
    }


class ImmobilisationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk=None):
        tenant = get_tenant(request)
        if pk:
            try:
                immo = Immobilisation.objects.get(tenant=tenant, id=pk)
                return Response(_immo_to_dict(immo))
            except Immobilisation.DoesNotExist:
                return Response({'error': 'Non trouvé'}, status=404)

        qs = Immobilisation.objects.filter(tenant=tenant)
        if not request.query_params.get('include_cede'):
            qs = qs.filter(est_cede=False)

        lignes = [_immo_to_dict(i) for i in qs]
        total_brut = sum(i['valeur_entree']         for i in lignes)
        total_amort = sum(i['cumul_amortissements'] for i in lignes)
        total_vnc   = sum(i['valeur_nette_comptable'] for i in lignes)

        return Response({
            'immobilisations': lignes,
            'synthese': {
                'total_brut':  round(total_brut, 2),
                'total_amort': round(total_amort, 2),
                'total_vnc':   round(total_vnc, 2),
                'nb_biens':    len(lignes),
            },
        })

    def post(self, request):
        tenant   = get_tenant(request)
        exercice = get_exercice(tenant)
        if not exercice:
            return Response({'error': 'Aucun exercice actif'}, status=400)

        data    = request.data
        libelle = data.get('libelle', '').strip()
        if not libelle:
            return Response({'error': 'Libellé requis'}, status=400)

        try:
            valeur = float(data.get('valeur_entree', 0))
            duree  = int(data.get('duree_utilisation', 0))
        except (ValueError, TypeError):
            return Response({'error': 'Valeur ou durée invalide'}, status=400)

        if valeur <= 0 or duree <= 0:
            return Response({'error': 'Valeur et durée doivent être > 0'}, status=400)

        import re as _re
        last = Immobilisation.objects.filter(tenant=tenant).order_by('-no_bien').first()
        nums = _re.findall(r'\d+', last.no_bien if last else 'IMM-0000')
        no_bien = f"IMM-{int(nums[-1]) + 1:04d}" if nums else 'IMM-0001'

        date_str           = data.get('date_entree', str(timezone.now().date()))
        no_immo            = data.get('no_compte_immobilisation', '231')
        no_amort           = data.get('no_compte_amortissement',  '2831')
        compte_fournisseur = data.get('compte_fournisseur', '404')
        mode_reglement     = data.get('mode_reglement', '')
        compte_tresorerie  = data.get('compte_tresorerie', '571') if mode_reglement else ''

        # Comptes fournisseurs valides pour acquisition d'immobilisation (SYSCOHADA)
        COMPTES_FOURN_IMMO_VALIDES = {'401', '402', '404', '405', '408', '481', '484'}
        if compte_fournisseur not in COMPTES_FOURN_IMMO_VALIDES:
            compte_fournisseur = '404'

        immo = Immobilisation.objects.create(
            tenant=tenant,
            no_bien=no_bien,
            libelle=libelle,
            date_entree=date_str,
            valeur_entree=valeur,
            duree_utilisation=duree,
            mode_amortissement=data.get('mode_amortissement', 'LINEAIRE'),
            no_compte_immobilisation=no_immo,
            no_compte_amortissement=no_amort,
            compte_fournisseur=compte_fournisseur,
            mode_reglement=mode_reglement,
            compte_tresorerie=compte_tresorerie,
        )

        from django.db.models import Max as _Max
        last_piece = JournalEntry.objects.filter(tenant=tenant, source='INVEST').aggregate(_Max('no_piece'))['no_piece__max']
        nums2 = _re.findall(r'\d+', last_piece or 'INV-0000')
        no_piece = f"INV-{int(nums2[-1]) + 1:04d}" if nums2 else 'INV-0001'

        libelle_immo  = PLAN_IMMO.get(no_immo, no_immo)
        lib_fourn     = f"{compte_fournisseur} Fournisseurs immo"

        # Écriture de constatation (engagement) : Débit 2xx / Crédit 404|481
        ecritures = [
            (no_immo,           valeur, 0,      f"Acquisition {libelle_immo} — {libelle}", 1),
            (compte_fournisseur, 0,     valeur, f"{lib_fourn} — {libelle}",                2),
        ]

        # Écriture de règlement : Débit 404|481 / Crédit 5xx (uniquement si règlement immédiat)
        if mode_reglement:
            ecritures += [
                (compte_fournisseur, valeur, 0,      f"Règlement {lib_fourn} — {libelle}",        3),
                (compte_tresorerie,  0,      valeur, f"Règlement par {mode_reglement} — {libelle}", 4),
            ]

        for nc, db, cr, lib, ordre in ecritures:
            JournalEntry.objects.create(
                tenant=tenant, exercice=exercice,
                no_piece=no_piece, date_ecriture=date_str,
                source='INVEST', source_id=immo.id,
                no_compte=nc, debit=db, credit=cr,
                libelle=lib, ordre=ordre,
            )

        return Response(_immo_to_dict(immo), status=201)

    def put(self, request, pk):
        tenant = get_tenant(request)
        try:
            immo = Immobilisation.objects.get(tenant=tenant, id=pk)
        except Immobilisation.DoesNotExist:
            return Response({'error': 'Non trouvé'}, status=404)

        for f in ('libelle', 'duree_utilisation', 'mode_amortissement',
                  'no_compte_immobilisation', 'no_compte_amortissement'):
            if f in request.data:
                setattr(immo, f, request.data[f])
        immo.save()
        return Response(_immo_to_dict(immo))

    def delete(self, request, pk):
        """Annulation investissement : contre-écritures SYSCOHADA + suppression immobilisation."""
        tenant   = get_tenant(request)
        exercice = get_exercice(tenant)
        try:
            immo = Immobilisation.objects.get(tenant=tenant, id=pk)
        except Immobilisation.DoesNotExist:
            return Response({'error': 'Non trouvé'}, status=404)

        if not exercice:
            return Response({'error': 'Aucun exercice actif'}, status=400)

        import re as _re3, datetime as _dt3
        from django.db.models import Max as _Max3
        entries = JournalEntry.objects.filter(tenant=tenant, source='INVEST', source_id=immo.id)
        last = JournalEntry.objects.filter(tenant=tenant, source='INVEST').aggregate(_Max3('no_piece'))['no_piece__max']
        nums3 = _re3.findall(r'\d+', last or 'INV-0000')
        no_piece_annul = f"INV-{int(nums3[-1]) + 1:04d}" if nums3 else 'INV-0001'

        for e in entries:
            JournalEntry.objects.create(
                tenant=tenant, exercice=exercice,
                no_piece=no_piece_annul, date_ecriture=_dt3.date.today(),
                source='INVEST', source_id=None,
                no_compte=e.no_compte,
                debit=e.credit,
                credit=e.debit,
                libelle=f"Annulation {e.no_piece} — {e.libelle}",
                ordre=e.ordre,
            )

        from core.models import log_audit
        log_audit(request, 'ANNULER', 'Investissement', str(immo.id),
                  f"Annulation {immo.libelle} ({float(immo.valeur_entree):,.0f} FCFA) — contre-écriture {no_piece_annul}")
        immo.delete()
        return Response({'success': True, 'no_piece_annulation': no_piece_annul})


class AmortirView(APIView):
    """Enregistre la dotation aux amortissements d'une immobilisation."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        tenant   = get_tenant(request)
        exercice = get_exercice(tenant)
        if not exercice:
            return Response({'error': 'Aucun exercice actif'}, status=400)

        try:
            immo = Immobilisation.objects.get(tenant=tenant, id=pk)
        except Immobilisation.DoesNotExist:
            return Response({'error': 'Non trouvé'}, status=404)

        if immo.est_amorti:
            return Response({'error': 'Immobilisation totalement amortie'}, status=400)
        if immo.est_cede:
            return Response({'error': 'Immobilisation cédée'}, status=400)

        # Annuité (peut être ajustée par le frontend)
        montant = float(request.data.get('montant', immo.annuite_amortissement))
        # Ne pas dépasser la VNC
        montant = min(montant, immo.valeur_nette_comptable)
        if montant <= 0:
            return Response({'error': 'Montant invalide'}, status=400)

        import re as _re
        from django.db.models import Max as _Max
        last_piece = JournalEntry.objects.filter(tenant=tenant, source='AMORT').aggregate(_Max('no_piece'))['no_piece__max']
        nums = _re.findall(r'\d+', last_piece or 'AMT-0000')
        no_piece = f"AMT-{int(nums[-1]) + 1:04d}" if nums else 'AMT-0001'

        date_str = request.data.get('date', str(timezone.now().date()))
        lib = f"Dotation amort. — {immo.libelle}"

        JournalEntry.objects.create(
            tenant=tenant, exercice=exercice,
            no_piece=no_piece, date_ecriture=date_str,
            source='AMORT', source_id=immo.id,
            no_compte='681', debit=montant, credit=0,
            libelle=lib, ordre=1,
        )
        JournalEntry.objects.create(
            tenant=tenant, exercice=exercice,
            no_piece=no_piece, date_ecriture=date_str,
            source='AMORT', source_id=immo.id,
            no_compte=immo.no_compte_amortissement, debit=0, credit=montant,
            libelle=lib, ordre=2,
        )

        from decimal import Decimal
        immo.cumul_amortissements += Decimal(str(montant))
        immo.save()

        return Response(_immo_to_dict(immo))


class ReglerImmobilisationView(APIView):
    """Règlement d'un bien acquis à crédit (remboursement du fournisseur).

    Génère l'écriture SYSCOHADA : Débit compte fournisseur (404/481…) / Crédit
    trésorerie (5xx). Gère les règlements partiels (plusieurs remboursements
    jusqu'à extinction de la dette)."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        tenant   = get_tenant(request)
        exercice = get_exercice(tenant)
        if not exercice:
            return Response({'error': 'Aucun exercice actif'}, status=400)

        try:
            immo = Immobilisation.objects.get(tenant=tenant, id=pk)
        except Immobilisation.DoesNotExist:
            return Response({'error': 'Non trouvé'}, status=404)

        reste = _immo_reste_a_regler(immo)
        if reste <= 0.01:
            return Response({'error': 'Ce bien est déjà entièrement réglé'}, status=400)

        try:
            montant = float(request.data.get('montant', reste))
        except (ValueError, TypeError):
            return Response({'error': 'Montant invalide'}, status=400)

        # Ne jamais régler plus que le reste dû
        montant = round(min(montant, reste), 2)
        if montant <= 0:
            return Response({'error': 'Montant invalide'}, status=400)

        mode_reglement    = request.data.get('mode_reglement', '') or 'Espèces'
        compte_tresorerie = request.data.get('compte_tresorerie', '571') or '571'
        date_str          = request.data.get('date', str(timezone.now().date()))

        import re as _re
        from django.db.models import Max as _Max
        last_piece = JournalEntry.objects.filter(tenant=tenant, source='INVEST').aggregate(_Max('no_piece'))['no_piece__max']
        nums = _re.findall(r'\d+', last_piece or 'INV-0000')
        no_piece = f"INV-{int(nums[-1]) + 1:04d}" if nums else 'INV-0001'

        lib_fourn = f"{immo.compte_fournisseur} Fournisseurs immo"
        lib = f"Règlement {lib_fourn} — {immo.libelle}"

        JournalEntry.objects.create(
            tenant=tenant, exercice=exercice,
            no_piece=no_piece, date_ecriture=date_str,
            source='INVEST', source_id=immo.id,
            no_compte=immo.compte_fournisseur, debit=montant, credit=0,
            libelle=lib, ordre=1,
        )
        JournalEntry.objects.create(
            tenant=tenant, exercice=exercice,
            no_piece=no_piece, date_ecriture=date_str,
            source='INVEST', source_id=immo.id,
            no_compte=compte_tresorerie, debit=0, credit=montant,
            libelle=f"Règlement par {mode_reglement} — {immo.libelle}", ordre=2,
        )

        # Mémorise le dernier mode/compte ; marque réglé si la dette est éteinte
        immo.mode_reglement    = mode_reglement
        immo.compte_tresorerie = compte_tresorerie
        immo.save(update_fields=['mode_reglement', 'compte_tresorerie'])

        from core.models import log_audit
        log_audit(request, 'UPDATE', 'Investissement', str(immo.id),
                  f"Règlement {immo.libelle} ({montant:,.0f} FCFA) par {mode_reglement} — pièce {no_piece}")

        return Response(_immo_to_dict(immo))
