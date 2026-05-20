from django.db.models import Sum, Q
from django.db.models.functions import ExtractMonth
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status as drf_status
from apps.paiements.models import Exercice, Paiement
from apps.eleves.models import Eleve
from .models import JournalEntry, CompteComptable, BudgetLigne
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
    '282':   'Amort. terrains',
    '283':   'Amort. bâtiments et installations',
    '284':   'Amort. matériel et mobilier',
    '285':   'Amort. matériel de transport',
    # ── Classe 3 — Stocks ──
    '32':    'Fournitures consommables',
    # ── Classe 4 — Créances et dettes ──
    '40':    'Fournisseurs et comptes rattachés',
    '401':   'Fournisseurs',
    '408':   'Fournisseurs — factures non parvenues',
    '41':    'Clients et comptes rattachés',
    '411':   'Clients (Parents / Élèves)',
    '42':    'Personnel',
    '421':   'Avances et acomptes sur salaires',
    '422':   'Personnel — rémunérations dues',
    '423':   'Oppositions et saisies-arrêts',
    '43':    'Organismes sociaux',
    '431':   'CSS / ATMP',
    '4311':  'CSS — Prestations familiales',
    '4312':  'ATMP — Accidents du travail',
    '4313':  'IPRES — Cotisations retraite',
    '44':    'État et organismes internationaux',
    '441':   'État — impôts sur bénéfices',
    '4421':  'CFCE — Contribution patronale',
    '447':   'État — autres impôts et taxes',
    '4472':  'État — IR retenu à la source',
    '46':    'Débiteurs divers',
    '47':    'Créditeurs divers',
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


def get_tenant(request):
    if request.tenant:
        return request.tenant
    if request.user.role == 'SUPER_ADMIN':
        from apps.tenants.models import Tenant
        return Tenant.objects.first()
    return None


def get_exercice(tenant):
    return Exercice.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()


def _compte_sort_key(no):
    parts = no.replace('.', '__').split('__')
    return tuple(p.zfill(6) for p in parts)


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
        exercice = get_exercice(tenant)
        if not exercice:
            return Response([])

        plan = get_plan_dict(tenant)
        qs = JournalEntry.objects.filter(tenant=tenant, exercice=exercice)

        if source_filter := request.query_params.get('source'):
            qs = qs.filter(source=source_filter)

        entries = qs.order_by('-date_ecriture', 'no_piece', 'ordre')

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
        exercice = get_exercice(tenant)
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
        exercice = get_exercice(tenant)
        if not exercice:
            return Response({'lignes': [], 'totaux': {}})

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

    def _detail(self, entries, prefixes, field='debit'):
        q = Q()
        for p in prefixes:
            q |= Q(no_compte__startswith=p)
        rows = entries.filter(q).values('no_compte').annotate(t=Sum(field)).order_by('no_compte')
        return [{'compte': r['no_compte'],
                 'libelle': plan.get(r['no_compte'], r['no_compte']),
                 'montant': round(float(r['t'] or 0), 2)}
                for r in rows if float(r['t'] or 0) > 0]

    def get(self, request):
        tenant   = get_tenant(request)
        exercice = get_exercice(tenant)
        if not exercice:
            return Response({})

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
        autres_achats         = self._sum(entries, ['602', '604', '605', '606', '607', '608'], 'debit')
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

        # Totaux globaux pour affichage simplifié
        total_produits = production_exercice + ventes_marchandises
        total_charges  = achats_marchandises + consommations_interm + impots_taxes + autres_charges + charges_personnel + dotations_amort

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
            'detail_produits': self._detail(entries, ['706', '707', '708', '701', '74', '75', '781'], 'credit'),
            'detail_charges':  self._detail(entries, ['601', '602', '604', '606', '61', '621', '622', '623', '624', '625', '641', '6413', '651', '661', '662', '6641', '681'], 'debit'),
            'total_produits':  round(total_produits, 2),
            'total_charges':   round(total_charges, 2),
            'resultat_net':    round(resultat_net, 2),
        })


# ── Bilan SYSCOHADA Révisé (Articles 7-11 et 23 AUDCIF) ─────────────────────
class BilanView(APIView):
    permission_classes = [IsAuthenticated]

    IMMO_INCORPOREL  = ['211', '212', '213', '214', '215', '216', '217', '218']
    IMMO_CORPOREL    = ['221', '222', '231', '232', '241', '244', '245']
    IMMO_FINANCIER   = ['261', '262', '271', '272', '274', '275', '276', '277']
    DETTES_FIN       = ['16', '17', '18', '19']
    DETTES_FISCALES  = ['441', '442', '443', '444', '445', '447']
    DETTES_SOCIALES  = ['421', '422', '423', '424', '431', '432', '433']

    def _solde_comptes(self, entries, prefixes):
        q = Q()
        for p in prefixes:
            q |= Q(no_compte__startswith=p) if len(p) <= 3 else Q(no_compte=p)
        agg = entries.filter(q).aggregate(d=Sum('debit'), c=Sum('credit'))
        return float(agg['d'] or 0), float(agg['c'] or 0)

    def _detail_comptes(self, entries, prefixes):
        q = Q()
        for p in prefixes:
            q |= Q(no_compte__startswith=p) if len(p) <= 3 else Q(no_compte=p)
        rows = entries.filter(q).values('no_compte').annotate(
            d=Sum('debit'), c=Sum('credit')
        )
        result = []
        for r in rows:
            net = float(r['d'] or 0) - float(r['c'] or 0)
            if net > 0:
                result.append({
                    'compte':  r['no_compte'],
                    'libelle': plan.get(r['no_compte'], r['no_compte']),
                    'montant': round(net, 2),
                })
        return result

    def get(self, request):
        tenant   = get_tenant(request)
        exercice = get_exercice(tenant)
        if not exercice:
            return Response({})

        entries    = JournalEntry.objects.filter(tenant=tenant, exercice=exercice)
        paiements  = Paiement.objects.filter(tenant=tenant, exercice=exercice)
        caht       = _sum_paiements(paiements)
        systeme    = _detecter_systeme(caht)

        # ── ACTIF IMMOBILISÉ ─────────────────────────────────────────────
        immo_incorporel = self._detail_comptes(entries, self.IMMO_INCORPOREL)
        immo_corporel   = self._detail_comptes(entries, self.IMMO_CORPOREL)
        immo_financier  = self._detail_comptes(entries, self.IMMO_FINANCIER)
        # Déduire dotations aux amortissements (681) des immobilisations corporelles
        amort_d, amort_c = self._solde_comptes(entries, ['681'])
        amort_net = float(amort_d)

        total_incorporel = sum(x['montant'] for x in immo_incorporel)
        total_corporel   = max(sum(x['montant'] for x in immo_corporel) - amort_net, 0)
        total_financier  = sum(x['montant'] for x in immo_financier)
        total_immobilise = round(total_incorporel + total_corporel + total_financier, 2)

        # ── ACTIF CIRCULANT AO ────────────────────────────────────────────
        # Créances clients : reste à payer par élève (solde réel)
        from django.db.models import Value, DecimalField
        from django.db.models.functions import Coalesce
        from django.db.models import Sum as DSum

        eleves = Eleve.objects.filter(tenant=tenant, exercice=exercice).annotate(
            paye=Coalesce(
                DSum('paiements__montant_inscription') +
                DSum('paiements__montant_mensualite')  +
                DSum('paiements__montant_uniforme')    +
                DSum('paiements__montant_fournitures') +
                DSum('paiements__montant_cantine')     +
                DSum('paiements__montant_divers'),
                Value(0), output_field=DecimalField()
            )
        ).select_related('section')

        creances_clients = round(sum(
            max(float(e.total_attendu) - float(e.paye or 0), 0) for e in eleves
        ), 2)
        total_circulant_ao = creances_clients

        # ── TRÉSORERIE-ACTIF & TRÉSORERIE-PASSIF ─────────────────────────
        so = {
            '521': float(exercice.solde_initial_banque),
            '571': float(exercice.solde_initial_caisse),
            '552': float(exercice.solde_initial_mobile),
        }
        TRESO_PLAN = {'521': 'Banque — compte courant', '552': 'Mobile Money (WAVE / Orange / Free)', '571': 'Caisse'}
        tresorerie_actif  = []
        tresorerie_passif = []
        total_treso_actif = total_treso_passif = 0

        for no, libelle in TRESO_PLAN.items():
            if no == '552':
                mob_d, mob_c = _mobile_aggregate(tenant, exercice)
                solde = so['552'] + mob_d - mob_c
            else:
                agg = entries.filter(no_compte=no).aggregate(d=Sum('debit'), c=Sum('credit'))
                solde = so.get(no, 0) + float(agg['d'] or 0) - float(agg['c'] or 0)

            if solde > 0:
                tresorerie_actif.append({'compte': no, 'libelle': libelle, 'montant': round(solde, 2)})
                total_treso_actif += solde
            elif solde < 0:
                tresorerie_passif.append({'compte': no, 'libelle': f"Découvert — {libelle}", 'montant': round(abs(solde), 2)})
                total_treso_passif += abs(solde)

        total_actif = round(total_immobilise + total_circulant_ao + total_treso_actif, 2)

        # ── CAPITAUX PROPRES & RESSOURCES ASSIMILÉES ──────────────────────
        capital = float(exercice.solde_initial_caisse +
                        exercice.solde_initial_banque +
                        exercice.solde_initial_mobile)
        prod_7xx = entries.filter(no_compte__startswith='7').aggregate(t=Sum('credit'))
        char_6xx = entries.filter(no_compte__startswith='6').aggregate(t=Sum('debit'))
        resultat_net = float(prod_7xx['t'] or 0) - float(char_6xx['t'] or 0)
        total_capitaux = round(capital + resultat_net, 2)

        # ── DETTES FINANCIÈRES & RESSOURCES ASSIMILÉES (classe 16, 17, 18, 19) ──
        dettes_fin_d, dettes_fin_c = self._solde_comptes(entries, self.DETTES_FIN)
        total_dettes_fin = round(max(dettes_fin_c - dettes_fin_d, 0), 2)

        # ── PASSIF CIRCULANT AO ───────────────────────────────────────────
        agg_401 = entries.filter(no_compte='401').aggregate(d=Sum('debit'), c=Sum('credit'))
        dettes_fournisseurs = round(max(float(agg_401['c'] or 0) - float(agg_401['d'] or 0), 0), 2)

        agg_fisc = entries.filter(no_compte__in=self.DETTES_FISCALES).aggregate(d=Sum('debit'), c=Sum('credit'))
        dettes_fiscales = round(max(float(agg_fisc['c'] or 0) - float(agg_fisc['d'] or 0), 0), 2)

        agg_soc = entries.filter(no_compte__in=self.DETTES_SOCIALES).aggregate(d=Sum('debit'), c=Sum('credit'))
        dettes_sociales = round(max(float(agg_soc['c'] or 0) - float(agg_soc['d'] or 0), 0), 2)

        total_passif_circ_ao = round(dettes_fournisseurs + dettes_fiscales + dettes_sociales, 2)

        total_passif = round(total_capitaux + total_dettes_fin + total_passif_circ_ao + total_treso_passif, 2)

        return Response({
            'exercice':   exercice.annee_scolaire,
            'date_bilan': str(exercice.date_fin),
            'systeme':    systeme,
            'caht':       round(caht, 2),
            'seuil_smt':  SEUIL_SMT_SERVICES,
            'actif': {
                'immobilise': {
                    'incorporel':    immo_incorporel,
                    'corporel':      immo_corporel,
                    'financier':     immo_financier,
                    'total':         total_immobilise,
                },
                'circulant_ao': {
                    'stocks':          0,
                    'creances_clients': creances_clients,
                    'total':           total_circulant_ao,
                },
                'circulant_hao': 0,
                'tresorerie_actif': {
                    'detail': tresorerie_actif,
                    'total':  round(total_treso_actif, 2),
                },
                'ecart_conversion': 0,
                'total_actif': total_actif,
            },
            'passif': {
                'capitaux_propres': {
                    'capital':      round(capital, 2),
                    'resultat_net': round(resultat_net, 2),
                    'total':        total_capitaux,
                },
                'dettes_financieres': {
                    'emprunts': total_dettes_fin,
                    'total':    total_dettes_fin,
                },
                'passif_circulant_ao': {
                    'fournisseurs':     dettes_fournisseurs,
                    'dettes_fiscales':  dettes_fiscales,
                    'dettes_sociales':  dettes_sociales,
                    'total':            total_passif_circ_ao,
                },
                'passif_circulant_hao': 0,
                'tresorerie_passif': {
                    'detail': tresorerie_passif,
                    'total':  round(total_treso_passif, 2),
                },
                'ecart_conversion': 0,
                'total_passif': total_passif,
            },
            'equilibre': abs(total_actif - total_passif) < 1,
        })


# ── Tableau des Flux de Trésorerie ────────────────────────────────────────────
class TableauFluxView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.db.models.functions import TruncMonth
        from django.db.models import Count

        tenant   = get_tenant(request)
        exercice = get_exercice(tenant)
        if not exercice:
            return Response({})

        paiements = Paiement.objects.filter(tenant=tenant, exercice=exercice)
        entries   = JournalEntry.objects.filter(tenant=tenant, exercice=exercice)
        caht      = _sum_paiements(paiements)
        systeme   = _detecter_systeme(caht)

        encaissements_clients = caht

        agg_dec = entries.filter(
            source='CHARGE',
            no_compte__in=list(MOBILE_ACCOUNTS) + ['521', '571']
        ).aggregate(t=Sum('credit'))
        decaissements_charges = float(agg_dec['t'] or 0)

        flux_exploitation = encaissements_clients - decaissements_charges

        solde_initial = float(exercice.solde_initial_caisse +
                              exercice.solde_initial_banque +
                              exercice.solde_initial_mobile)
        solde_final   = solde_initial + flux_exploitation

        par_mode = paiements.values('mode_paiement').annotate(
            nb=Count('id'),
            total=Sum('montant_inscription') + Sum('montant_mensualite') +
                  Sum('montant_uniforme')    + Sum('montant_fournitures') +
                  Sum('montant_cantine')     + Sum('montant_divers')
        ).order_by('-total')

        mensuel = paiements.annotate(mois=TruncMonth('date_paiement')).values('mois').annotate(
            encaisse=Sum('montant_inscription') + Sum('montant_mensualite') +
                     Sum('montant_uniforme')    + Sum('montant_fournitures') +
                     Sum('montant_cantine')     + Sum('montant_divers')
        ).order_by('mois')

        charges_detail = entries.filter(
            source='CHARGE', no_compte__startswith='6'
        ).values('no_compte').annotate(total=Sum('debit')).order_by('-total')

        return Response({
            'exercice':  exercice.annee_scolaire,
            'methode':   'Directe',
            'systeme':   systeme,
            'flux_exploitation': {
                'encaissements_clients': round(encaissements_clients, 2),
                'decaissements_charges': round(decaissements_charges, 2),
                'flux_net':              round(flux_exploitation, 2),
            },
            'flux_investissement': {'acquisitions': 0, 'cessions': 0, 'flux_net': 0},
            'flux_financement': {
                'apports_capital': round(solde_initial, 2),
                'flux_net':        round(solde_initial, 2),
            },
            'tresorerie': {
                'solde_initial': round(solde_initial, 2),
                'variation':     round(flux_exploitation, 2),
                'solde_final':   round(solde_final, 2),
            },
            'par_mode': [{'mode': m['mode_paiement'], 'nb': m['nb'],
                          'total': float(m['total'] or 0)} for m in par_mode],
            'flux_mensuels': [{'mois': m['mois'].strftime('%b %Y') if m['mois'] else '',
                               'encaisse': float(m['encaisse'] or 0)}
                              for m in mensuel if m['mois']],
            'charges_detail': [{'compte': c['no_compte'],
                                 'libelle': plan.get(c['no_compte'], c['no_compte']),
                                 'montant': float(c['total'] or 0)}
                                for c in charges_detail],
        })


# ── Notes Annexes ──────────────────────────────────────────────────────────────
class NotesAnnexesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant   = get_tenant(request)
        exercice = get_exercice(tenant)
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

    # Comptes de charge acceptés (6xx + immobilisations 2xx)
    PLAN_CHARGES = {
        '221': 'Bâtiments (acquisition)',
        '231': 'Matériel et outillage (acquisition)',
        '241': 'Mobilier (acquisition)',
        '244': 'Matériel informatique (acquisition)',
        '245': 'Matériel de transport (acquisition)',
        '601': 'Achats de marchandises',
        '602': 'Achats de matières premières',
        '604': 'Achats de fournitures',
        '606': 'Eau, électricité, fournitures',
        '611': 'Transports',
        '612': 'Loyer',
        '613': 'Locations diverses',
        '621': 'Personnel extérieur',
        '622': 'Rémunérations intermédiaires',
        '623': 'Publicité',
        '624': 'Transport du personnel',
        '625': 'Déplacements et missions',
        '631': 'Frais bancaires',
        '641': 'Impôts et taxes',
        '651': 'Pertes sur créances',
        '661': 'Salaires',
        '662': 'Charges sociales (IPRES / CSS)',
        '681': 'Dotations aux amortissements',
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

        # Toutes les charges : manuelles (CHARGE) + paie (PAIE) sur comptes 6xx/2xx
        charges = JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice,
            source__in=('CHARGE', 'PAIE'),
            debit__gt=0,
        ).filter(
            Q(no_compte__startswith='6') | Q(no_compte__startswith='2')
        ).order_by('-date_ecriture')

        return Response([{
            'id':             str(c.id),
            'date':           str(c.date_ecriture),
            'no_piece':       c.no_piece,
            'no_compte':      c.no_compte,
            'libelle':        c.libelle,
            'montant':        float(c.debit),
            'libelle_compte': self.PLAN_CHARGES.get(c.no_compte, c.no_compte),
        } for c in charges])

    def post(self, request):
        tenant   = get_tenant(request)
        exercice = get_exercice(tenant)
        if not exercice:
            return Response({'error': 'Aucun exercice actif'}, status=400)

        data      = request.data
        no_compte = data.get('no_compte', '606')
        montant   = float(data.get('montant', 0))
        libelle   = data.get('libelle', '')
        date      = data.get('date', str(timezone.now().date()))

        if montant <= 0:
            return Response({'error': 'Montant invalide'}, status=400)

        from django.db.models import Max
        import re
        last = JournalEntry.objects.filter(
            tenant=tenant, source='CHARGE'
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

    def delete(self, request, pk):
        tenant = get_tenant(request)
        try:
            entry = JournalEntry.objects.get(id=pk)
            JournalEntry.objects.filter(
                tenant=tenant, source='CHARGE', no_piece=entry.no_piece
            ).delete()
        except JournalEntry.DoesNotExist:
            pass
        return Response({'success': True})


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

        rows = []
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

            rows.append({
                'no_compte':    no,
                'libelle':      db.libelle if db else libelle,
                'type':         type_compte,
                'classe':       classe,
                'est_actif':    db.est_actif if db else True,
                'est_systeme':  db.est_systeme if db else False,
                'est_personnalise': db is not None,
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
        """Somme des débits par mois pour un compte (et ses sous-comptes)."""
        qs = JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice,
            source__in=('CHARGE', 'PAIE'),
            debit__gt=0,
        ).filter(
            Q(no_compte=no_compte) | Q(no_compte__startswith=no_compte)
        ).annotate(
            mois=ExtractMonth('date_ecriture')
        ).values('mois').annotate(realise=Sum('debit'))
        return {r['mois']: float(r['realise']) for r in qs}

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

        for l in lignes:
            realise_mois = self._realise_par_mois(tenant, exercice, l.no_compte)
            mois_data = []
            t_prevu = t_realise = 0.0

            for i, champ in enumerate(MOIS_CHAMPS, start=1):
                p = float(getattr(l, champ))
                r = realise_mois.get(i, 0.0)
                t_prevu   += p
                t_realise += r
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
