"""États financiers : bilan, tableau des flux et dossier ETAFI — un seul calcul.

L'écran « Bilan », son export PDF et la liasse ETAFI disaient trois choses
différentes : l'export PDF ignorait les capitaux 10-14, les provisions 15 et
la classe 8, et le résultat du bilan comptait le 890 (compte d'à-nouveaux)
que le compte de résultat écarte. Tout passe désormais par ici.

Deux niveaux :

- `donnees_bilan` / `donnees_tft` : la forme attendue par les écrans et les
  exports PDF historiques (mêmes clés qu'avant) ;
- `bilan_etafi` / `compte_resultat_etafi` / `tft_etafi` / `notes_etafi` :
  la liasse SYSCOHADA Révisé (AUDCIF 2017), lignes référencées (AD…BZ,
  CA…DZ, TA…XI, ZA…ZH), colonnes N et N-1.

Conventions, valables partout :
  · soldes de clôture = journal de l'exercice + soldes initiaux de trésorerie
    (Exercice.solde_initial_*) ;
  · résultat net = produits − charges des classes 6, 7 et 8, 890 exclu (le
    890 n'est pas un résultat : c'est la contrepartie des à-nouveaux) ;
  · le 890 net et les soldes initiaux de trésorerie forment les capitaux
    d'ouverture non ventilés, présentés en report à nouveau (CH) : c'est
    exactement ce qui équilibre le bilan d'une école ouverte sans bilan
    d'entrée détaillé.

Les montants sont des Decimal au centime ; les sorties « écran » restent en
float comme avant.
"""
from collections import defaultdict
from decimal import Decimal

from django.db.models import Q, Sum

from .models import JournalEntry

ZERO = Decimal('0')
SOURCES_OUVERTURE = ('AN', 'REPORT_RELIQUAT')
COMPTE_A_NOUVEAUX = '890'


def _d(x):
    return Decimal(str(x or 0)).quantize(Decimal('0.01'))


def _f(x):
    return float(round(x, 2))


# ── Soldes ────────────────────────────────────────────────────────────────────
def soldes(exercice):
    """{compte: D − C} de clôture (soldes initiaux de trésorerie compris)."""
    from .exercices import soldes_comptes
    return soldes_comptes(exercice)


def _filtre_ouverture():
    return Q(source__in=SOURCES_OUVERTURE) | Q(source='BALANCE_IMPORT', no_piece__startswith='BAL-OUV')


def mouvements(exercice, exclure_ouverture=True, **filtres):
    """{compte: D − C} des opérations de l'exercice (sans les pièces
    d'ouverture : à-nouveaux, impayés reportés, balance d'ouverture)."""
    qs = JournalEntry.objects.filter(tenant=exercice.tenant, exercice=exercice, **filtres)
    if exclure_ouverture:
        qs = qs.exclude(_filtre_ouverture())
    out = defaultdict(lambda: ZERO)
    for r in qs.values('no_compte').annotate(d=Sum('debit'), c=Sum('credit')):
        out[r['no_compte']] += _d(r['d']) - _d(r['c'])
    return out


def ouverture(exercice):
    """{compte: D − C} d'ouverture : soldes initiaux + pièces d'ouverture."""
    out = defaultdict(lambda: ZERO)
    for r in (JournalEntry.objects.filter(_filtre_ouverture(), tenant=exercice.tenant, exercice=exercice)
              .values('no_compte').annotate(d=Sum('debit'), c=Sum('credit'))):
        out[r['no_compte']] += _d(r['d']) - _d(r['c'])
    for compte, champ in (('571', 'solde_initial_caisse'), ('521', 'solde_initial_banque'),
                          ('5521', 'solde_initial_mobile')):
        out[compte] += _d(getattr(exercice, champ))
    return out


def _somme(dico, prefixes, exclus=(), signe=1):
    total = ZERO
    for compte, v in dico.items():
        if compte.startswith(tuple(prefixes)) and not compte.startswith(tuple(exclus) or ('\0',)):
            total += v
    return total * signe


def resultat_net(exercice, s=None):
    """Produits − charges (classes 6, 7, 8 ; 890 exclu), sans plafonnement."""
    s = s if s is not None else soldes(exercice)
    return -sum((v for c, v in s.items() if c[:1] in '678' and c != COMPTE_A_NOUVEAUX), ZERO)


def capitaux_ouverture_non_ventiles(exercice, s=None):
    """Soldes initiaux de trésorerie + 890 net créditeur : la part des capitaux
    d'ouverture que l'école n'a pas détaillée dans un bilan d'entrée."""
    s = s if s is not None else soldes(exercice)
    init = (_d(exercice.solde_initial_caisse) + _d(exercice.solde_initial_banque)
            + _d(exercice.solde_initial_mobile))
    return init - s.get(COMPTE_A_NOUVEAUX, ZERO)


# ── Bilan « écran » (clés historiques de BilanView) ─────────────────────────
def donnees_bilan(tenant, exercice):
    from apps.paiements.models import Paiement
    from .views import (SEUIL_SMT_SERVICES, _compute_account_sfs, _detecter_systeme,
                        _sum_paiements, _sum_sf_side, get_plan_dict)

    plan = get_plan_dict(tenant)
    entries = JournalEntry.objects.filter(tenant=tenant, exercice=exercice)
    caht = _sum_paiements(Paiement.objects.filter(tenant=tenant, exercice=exercice))
    systeme = _detecter_systeme(caht)
    sfs = _compute_account_sfs(entries, exercice, tenant)

    incorporel_t, incorporel_d = _sum_sf_side(sfs, 'sf_d', ['20', '21'], plan)
    corporel_t, corporel_d = _sum_sf_side(sfs, 'sf_d', ['22', '23', '24', '25'], plan)
    financier_t, financier_d = _sum_sf_side(sfs, 'sf_d', ['26', '27'], plan)
    amort_t, _ = _sum_sf_side(sfs, 'sf_c', ['28'], plan)
    total_corporel_net = round(max(corporel_t - amort_t, 0), 2)
    total_immobilise = round(incorporel_t + total_corporel_net + financier_t, 2)

    stocks_t, stocks_d = _sum_sf_side(sfs, 'sf_d', ['31', '32', '33', '34', '35', '36', '37', '38'], plan)
    creances_t, creances_d = _sum_sf_side(sfs, 'sf_d', ['40', '41', '42', '43', '44', '45', '46', '47'], plan)
    prov_b_t, _ = _sum_sf_side(sfs, 'sf_c', ['49'], plan)
    total_circulant_ao = round(stocks_t + creances_t - prov_b_t, 2)
    hao_actif_t, hao_actif_d = _sum_sf_side(sfs, 'sf_d', ['48'], plan)
    treso_actif_t, treso_actif_d = _sum_sf_side(sfs, 'sf_d', ['51', '52', '53', '54', '55', '57', '58'], plan)
    total_actif = round(total_immobilise + total_circulant_ao + hao_actif_t + treso_actif_t, 2)

    # Résultat : classes 6, 7, 8 — 890 EXCLU, comme au compte de résultat.
    # Le 890 net rejoint les capitaux d'ouverture (soldes initiaux de
    # trésorerie) : jusqu'en octobre 2026 il était compté dans le résultat, et
    # le bilan affichait un autre résultat que le compte de résultat.
    s = soldes(exercice)
    resultat = round(float(resultat_net(exercice, s)), 2)
    capital = round(float(capitaux_ouverture_non_ventiles(exercice, s)), 2)
    prov_regl_t, _ = _sum_sf_side(sfs, 'sf_c', ['15'], plan)
    # 10 à 14 au solde : un 12 débiteur (report à nouveau négatif, 129)
    # diminue les capitaux au lieu de disparaître.
    autres_cp_d = []
    for no in sorted(sfs):
        if no.startswith(('10', '11', '12', '14')):
            montant = sfs[no]['sf_c'] - sfs[no]['sf_d']
            if montant:
                autres_cp_d.append({'compte': no, 'libelle': plan.get(no, no), 'montant': round(montant, 2)})
    autres_cp_t = round(sum(x['montant'] for x in autres_cp_d), 2)
    # Débiteurs 10-14 : retirés de l'actif circulant/trésorerie où
    # _sum_sf_side ne les range pas — ils n'y étaient pas, rien à corriger.
    total_capitaux = round(capital + resultat + prov_regl_t + autres_cp_t, 2)

    dettes_fin_t, dettes_fin_d = _sum_sf_side(sfs, 'sf_c', ['16', '17', '18', '19'], plan)
    dettes_ao_t, dettes_ao_d = _sum_sf_side(sfs, 'sf_c', ['40', '41', '42', '43', '44', '45', '46', '47'], plan)
    hao_passif_t, hao_passif_d = _sum_sf_side(sfs, 'sf_c', ['48'], plan)
    treso_passif_t, treso_passif_d = _sum_sf_side(sfs, 'sf_c', ['51', '52', '53', '54', '55', '57', '58'], plan)
    total_passif = round(total_capitaux + dettes_fin_t + dettes_ao_t + hao_passif_t + treso_passif_t, 2)

    def _sub(detail, prefixes):
        return round(sum(x['montant'] for x in detail if any(x['compte'].startswith(p) for p in prefixes)), 2)

    return {
        'exercice': exercice.annee_scolaire,
        'date_bilan': str(exercice.date_fin),
        'systeme': systeme,
        'caht': round(caht, 2),
        'seuil_smt': SEUIL_SMT_SERVICES,
        'actif': {
            'immobilise': {'incorporel': incorporel_d, 'corporel': corporel_d, 'financier': financier_d,
                           'amort': round(amort_t, 2), 'total': total_immobilise},
            'circulant_ao': {'stocks': stocks_d, 'creances': creances_d, 'total': total_circulant_ao},
            'circulant_hao': {'detail': hao_actif_d, 'total': hao_actif_t},
            'tresorerie_actif': {'detail': treso_actif_d, 'total': treso_actif_t},
            'total_actif': total_actif,
        },
        'passif': {
            'capitaux_propres': {
                # Capitaux d'ouverture non ventilés (soldes initiaux + 890).
                'capital': capital,
                'resultat_net': resultat,
                'subventions_investissement': _sub(autres_cp_d, ['14']),
                'autres': autres_cp_d,
                'provisions_reglementees': prov_regl_t,
                'total': total_capitaux,
            },
            'dettes_financieres': {'detail': dettes_fin_d, 'total': dettes_fin_t},
            'passif_circulant_ao': {
                'detail': dettes_ao_d,
                'fournisseurs': _sub(dettes_ao_d, ['40', '401', '404']),
                'dettes_fiscales': _sub(dettes_ao_d, ['44']),
                'dettes_personnel': _sub(dettes_ao_d, ['42']),
                'dettes_sociales': _sub(dettes_ao_d, ['43']),
                'total': dettes_ao_t,
            },
            'passif_circulant_hao': {'detail': hao_passif_d, 'total': hao_passif_t},
            'tresorerie_passif': {'detail': treso_passif_d, 'total': treso_passif_t},
            'total_passif': total_passif,
        },
        'equilibre': abs(total_actif - total_passif) < 1,
    }


# ── Bilan ETAFI ───────────────────────────────────────────────────────────────
# (référence, libellé, préfixes, exclusions). Les comptes de bilan des classes
# 4 et 5 vont à l'actif s'ils sont débiteurs, au passif s'ils sont créditeurs.
ACTIF = [
    ('AE', 'Frais de développement et de prospection', ('211',), ()),
    ('AF', 'Brevets, licences, logiciels et droits similaires', ('212', '213', '214'), ()),
    ('AG', 'Fonds commercial et droit au bail', ('215', '216'), ()),
    ('AH', 'Autres immobilisations incorporelles', ('20', '217', '218', '219'), ()),
    ('AJ', 'Terrains', ('22',), ()),
    ('AK', 'Bâtiments', ('231', '232', '233', '234'), ()),
    ('AL', 'Aménagements, agencements et installations', ('235', '237', '238', '239'), ()),
    ('AM', 'Matériel, mobilier et actifs biologiques', ('24',), ('245',)),
    ('AN', 'Matériel de transport', ('245',), ()),
    ('AP', 'Avances et acomptes versés sur immobilisations', ('25',), ()),
    ('AR', 'Titres de participation', ('26',), ()),
    ('AS', 'Autres immobilisations financières', ('27',), ()),
    ('BA', 'Actif circulant HAO', ('48',), ()),
    ('BB', 'Stocks et encours', ('3',), ()),
    ('BH', 'Fournisseurs, avances versées', ('409',), ()),
    ('BI', 'Clients', ('41',), ()),
    ('BJ', 'Autres créances', ('40', '42', '43', '44', '45', '46', '47'), ('409', '478')),
    ('BQ', 'Titres de placement', ('50',), ()),
    ('BR', 'Valeurs à encaisser', ('51',), ()),
    ('BS', 'Banques, chèques postaux, caisse et assimilés', ('52', '53', '54', '55', '56', '57', '58'), ()),
    ('BU', "Écart de conversion-Actif", ('478',), ()),
]
TOTAUX_ACTIF = [
    ('AD', 'IMMOBILISATIONS INCORPORELLES', ('AE', 'AF', 'AG', 'AH'), 'AE'),
    ('AI', 'IMMOBILISATIONS CORPORELLES', ('AJ', 'AK', 'AL', 'AM', 'AN'), 'AJ'),
    ('AQ', 'IMMOBILISATIONS FINANCIÈRES', ('AR', 'AS'), 'AR'),
    ('AZ', 'TOTAL ACTIF IMMOBILISÉ', ('AD', 'AI', 'AP', 'AQ'), None),
    ('BG', 'CRÉANCES ET EMPLOIS ASSIMILÉS', ('BH', 'BI', 'BJ'), 'BH'),
    ('BK', 'TOTAL ACTIF CIRCULANT', ('BA', 'BB', 'BG'), None),
    ('BT', 'TOTAL TRÉSORERIE-ACTIF', ('BQ', 'BR', 'BS'), None),
    ('BZ', 'TOTAL GÉNÉRAL', ('AZ', 'BK', 'BT', 'BU'), None),
]
ORDRE_ACTIF = ['AD', 'AE', 'AF', 'AG', 'AH', 'AI', 'AJ', 'AK', 'AL', 'AM', 'AN', 'AP', 'AQ', 'AR',
               'AS', 'AZ', 'BA', 'BB', 'BG', 'BH', 'BI', 'BJ', 'BK', 'BQ', 'BR', 'BS', 'BT', 'BU', 'BZ']

PASSIF = [
    ('CA', "Capital (ou compte de l'exploitant)", ('101', '102', '103', '104', '108'), ()),
    ('CB', 'Apporteurs, capital non appelé (−)', ('109',), ()),
    ('CD', 'Primes liées au capital social', ('105',), ()),
    ('CE', 'Écarts de réévaluation', ('106',), ()),
    ('CF', 'Réserves indisponibles', ('111', '112'), ()),
    ('CG', 'Réserves libres', ('113', '118'), ()),
    ('CH', 'Report à nouveau (+ ou −)', ('12',), ()),
    ('CJ', "Résultat net de l'exercice (bénéfice + ou perte −)", ('13',), ()),
    ('CL', "Subventions d'investissement", ('14',), ()),
    ('CM', 'Provisions réglementées', ('15',), ()),
    ('DA', 'Emprunts et dettes financières diverses', ('16', '18'), ()),
    ('DB', 'Dettes de location-acquisition', ('17',), ()),
    ('DC', 'Provisions pour risques et charges', ('19',), ()),
    ('DH', 'Dettes circulantes HAO', ('48',), ()),
    ('DI', 'Clients, avances reçues', ('41',), ()),
    ('DJ', "Fournisseurs d'exploitation", ('40',), ()),
    ('DK', 'Dettes fiscales et sociales', ('42', '43', '44'), ()),
    ('DM', 'Autres dettes', ('45', '46', '47'), ('479',)),
    ('DN', 'Provisions pour risques à court terme', ('499',), ()),
    ('DQ', "Banques, crédits d'escompte", ('564', '565'), ()),
    ('DR', 'Banques, établissements financiers et crédits de trésorerie',
     ('50', '51', '52', '53', '54', '55', '56', '57', '58'), ('564', '565')),
    ('DV', "Écart de conversion-Passif", ('479',), ()),
]
TOTAUX_PASSIF = [
    ('CP', 'TOTAL CAPITAUX PROPRES ET RESSOURCES ASSIMILÉES',
     ('CA', 'CB', 'CD', 'CE', 'CF', 'CG', 'CH', 'CJ', 'CL', 'CM'), None),
    ('DD', 'TOTAL DETTES FINANCIÈRES ET RESSOURCES ASSIMILÉES', ('DA', 'DB', 'DC'), None),
    ('DF', 'TOTAL RESSOURCES STABLES', ('CP', 'DD'), None),
    ('DP', 'TOTAL PASSIF CIRCULANT', ('DH', 'DI', 'DJ', 'DK', 'DM', 'DN'), None),
    ('DT', 'TOTAL TRÉSORERIE-PASSIF', ('DQ', 'DR'), None),
    ('DZ', 'TOTAL GÉNÉRAL', ('DF', 'DP', 'DT', 'DV'), None),
]
ORDRE_PASSIF = ['CA', 'CB', 'CD', 'CE', 'CF', 'CG', 'CH', 'CJ', 'CL', 'CM', 'CP', 'DA', 'DB',
                'DC', 'DD', 'DF', 'DH', 'DI', 'DJ', 'DK', 'DM', 'DN', 'DP', 'DQ', 'DR', 'DT', 'DV', 'DZ']


def _ligne_de(compte, table):
    for ref, _lib, prefixes, exclus in table:
        if compte.startswith(prefixes) and not (exclus and compte.startswith(exclus)):
            return ref
    return None


def _compte_actif_de_correction(compte):
    """Compte d'actif corrigé par un compte d'amortissement ou de dépréciation
    (2845 → 245 ; 491 → 41 ; 39 → 3), ou None."""
    if compte.startswith('499'):
        return None                          # provision pour risques CT (passif)
    for prefixe, base in (('28', '2'), ('29', '2'), ('39', '3'), ('49', '4'), ('59', '5')):
        if compte.startswith(prefixe):
            return base + compte[len(prefixe):] if len(compte) > len(prefixe) else base
    return None


def _calcul_bilan(exercice):
    """{'brut', 'amort', 'passif'} par référence, et le détail par compte."""
    s = soldes(exercice)
    brut, amort, passif = defaultdict(lambda: ZERO), defaultdict(lambda: ZERO), defaultdict(lambda: ZERO)
    detail = defaultdict(list)
    for compte, v in s.items():
        if v == 0 or not compte or compte[0] not in '12345':
            continue
        base = _compte_actif_de_correction(compte)
        if base is not None:
            ref = _ligne_de(base, ACTIF) or ('BJ' if base.startswith('4') else None)
            if ref:
                amort[ref] += -v            # amortissement créditeur → positif
                detail[ref].append((compte, -v, 'amort'))
            continue
        if compte[0] in '23':
            # Repli : un compte non référencé reste dans sa masse, jamais perdu.
            ref = _ligne_de(compte, ACTIF) or ('AS' if compte[0] == '2' else 'BB')
            brut[ref] += v
            detail[ref].append((compte, v, 'brut'))
            continue
        if compte[0] == '1':
            ref = _ligne_de(compte, PASSIF) or ('DA' if compte[1:2] in '6789' else 'CG')
            passif[ref] += -v
            detail[ref].append((compte, -v, 'passif'))
            continue
        # Classes 4 et 5 : au sens du solde.
        if v > 0:
            ref = _ligne_de(compte, ACTIF)
            if ref:
                brut[ref] += v
                detail[ref].append((compte, v, 'brut'))
        else:
            ref = _ligne_de(compte, PASSIF)
            if ref:
                passif[ref] += -v
                detail[ref].append((compte, -v, 'passif'))
    passif['CJ'] += resultat_net(exercice, s)
    passif['CH'] += capitaux_ouverture_non_ventiles(exercice, s)
    return brut, amort, passif, detail


def _cumuler(valeurs, totaux):
    for ref, _lib, composants, _ in totaux:
        valeurs[ref] = sum((valeurs[c] for c in composants), ZERO)


def bilan_etafi(exercice, precedent=None):
    from .exercices import exercice_precedent
    precedent = precedent if precedent is not None else exercice_precedent(exercice)

    def calcul(ex):
        brut, amort, passif, detail = _calcul_bilan(ex)
        net = defaultdict(lambda: ZERO)
        for ref, *_ in ACTIF:
            net[ref] = brut[ref] - amort[ref]
        for t in (brut, amort, net):
            _cumuler(t, TOTAUX_ACTIF)
        _cumuler(passif, TOTAUX_PASSIF)
        return brut, amort, net, passif, detail

    brut, amort, net, passif, detail = calcul(exercice)
    n1 = calcul(precedent) if precedent is not None else None
    libelles_a = {r: l for r, l, *_ in ACTIF} | {r: l for r, l, *_ in TOTAUX_ACTIF}
    libelles_p = {r: l for r, l, *_ in PASSIF} | {r: l for r, l, *_ in TOTAUX_PASSIF}
    totaux_a = {r for r, *_ in TOTAUX_ACTIF}
    totaux_p = {r for r, *_ in TOTAUX_PASSIF}
    actif = [{'ref': r, 'libelle': libelles_a[r], 'total': r in totaux_a,
              'brut': _f(brut[r]), 'amort': _f(amort[r]), 'net': _f(net[r]),
              'net_n1': _f(n1[2][r]) if n1 else None} for r in ORDRE_ACTIF]
    passif_l = [{'ref': r, 'libelle': libelles_p[r], 'total': r in totaux_p,
                 'net': _f(passif[r]), 'net_n1': _f(n1[3][r]) if n1 else None} for r in ORDRE_PASSIF]
    return {'actif': actif, 'passif': passif_l,
            'total_actif': _f(net['BZ']), 'total_passif': _f(passif['DZ']),
            'equilibre': abs(net['BZ'] - passif['DZ']) < 1,
            'tresorerie_nette': _f(net['BT'] - passif['DT']),
            'resultat': _f(passif['CJ']),
            'precedent': precedent.annee_scolaire if precedent else None}


# ── Compte de résultat ETAFI ──────────────────────────────────────────────────
# (référence, libellé, sens, préfixes, exclusions). Sens : 'P' produit
# (crédit − débit), 'C' charge (débit − crédit). Les comptes non listés de la
# classe 6 vont en RJ (autres charges), ceux de la classe 7 en TH (autres
# produits) : rien ne se perd, le résultat XI égale toujours le résultat net.
CR = [
    ('TA', 'Ventes de marchandises', 'P', ('701',), ()),
    ('RA', 'Achats de marchandises', 'C', ('601',), ()),
    ('RB', 'Variation de stocks de marchandises', 'C', ('6031',), ()),
    ('TB', 'Ventes de produits fabriqués', 'P', ('702', '703', '704'), ()),
    ('TC', 'Travaux, services vendus', 'P', ('705', '706'), ()),
    ('TD', 'Produits accessoires', 'P', ('707', '708'), ()),
    ('TE', 'Production stockée (ou déstockage)', 'P', ('73',), ()),
    ('TF', 'Production immobilisée', 'P', ('72',), ()),
    ('TG', "Subventions d'exploitation", 'P', ('71', '74'), ()),
    ('TH', 'Autres produits', 'P', ('75',), ()),
    ('TI', "Transferts de charges d'exploitation", 'P', ('781',), ()),
    ('RC', 'Achats de matières premières et fournitures liées', 'C', ('602',), ()),
    ('RD', 'Variation de stocks de matières premières', 'C', ('6032',), ()),
    ('RE', 'Autres achats', 'C', ('604', '605', '606', '607', '608', '609'), ()),
    ('RF', "Variation de stocks d'autres approvisionnements", 'C', ('6033',), ()),
    ('RG', 'Transports', 'C', ('61',), ()),
    ('RH', 'Services extérieurs', 'C', ('62', '63'), ()),
    ('RI', 'Impôts et taxes', 'C', ('64',), ()),
    ('RJ', 'Autres charges', 'C', ('65',), ()),
    ('RK', 'Charges de personnel', 'C', ('66',), ()),
    ('TJ', "Reprises d'amortissements, provisions et dépréciations", 'P', ('791', '798', '799'), ()),
    ('RL', 'Dotations aux amortissements, provisions et dépréciations', 'C', ('681', '691'), ()),
    ('TK', 'Revenus financiers et assimilés', 'P', ('77',), ()),
    ('TL', 'Reprises de provisions et dépréciations financières', 'P', ('797',), ()),
    ('TM', 'Transferts de charges financières', 'P', ('787',), ()),
    ('RM', 'Frais financiers et charges assimilées', 'C', ('67',), ()),
    ('RN', 'Dotations aux provisions et dépréciations financières', 'C', ('697',), ()),
    ('TN', "Produits des cessions d'immobilisations", 'P', ('82',), ()),
    ('TO', 'Autres produits HAO', 'P', ('84', '86', '88'), ()),
    ('RO', "Valeurs comptables des cessions d'immobilisations", 'C', ('81',), ()),
    ('RP', 'Autres charges HAO', 'C', ('83', '85'), ()),
    ('RQ', 'Participation des travailleurs', 'C', ('87',), ()),
    ('RS', 'Impôts sur le résultat', 'C', ('89',), ('890',)),
]
SOLDES_CR = [
    ('XA', 'MARGE COMMERCIALE', lambda v: v['TA'] - v['RA'] - v['RB']),
    ('XB', "CHIFFRE D'AFFAIRES", lambda v: v['TA'] + v['TB'] + v['TC'] + v['TD']),
    ('XC', 'VALEUR AJOUTÉE', lambda v: v['XA'] + v['TB'] + v['TC'] + v['TD'] + v['TE'] + v['TF']
     + v['TG'] + v['TH'] + v['TI'] - v['RC'] - v['RD'] - v['RE'] - v['RF'] - v['RG'] - v['RH']
     - v['RI'] - v['RJ']),
    ('XD', "EXCÉDENT BRUT D'EXPLOITATION", lambda v: v['XC'] - v['RK']),
    ('XE', "RÉSULTAT D'EXPLOITATION", lambda v: v['XD'] + v['TJ'] - v['RL']),
    ('XF', 'RÉSULTAT FINANCIER', lambda v: v['TK'] + v['TL'] + v['TM'] - v['RM'] - v['RN']),
    ('XG', 'RÉSULTAT DES ACTIVITÉS ORDINAIRES', lambda v: v['XE'] + v['XF']),
    ('XH', 'RÉSULTAT HORS ACTIVITÉS ORDINAIRES', lambda v: v['TN'] + v['TO'] - v['RO'] - v['RP']),
    ('XI', 'RÉSULTAT NET', lambda v: v['XG'] + v['XH'] - v['RQ'] - v['RS']),
]
ORDRE_CR = ['TA', 'RA', 'RB', 'XA', 'TB', 'TC', 'TD', 'XB', 'TE', 'TF', 'TG', 'TH', 'TI', 'RC',
            'RD', 'RE', 'RF', 'RG', 'RH', 'RI', 'RJ', 'XC', 'RK', 'XD', 'TJ', 'RL', 'XE', 'TK',
            'TL', 'TM', 'RM', 'RN', 'XF', 'XG', 'TN', 'TO', 'RO', 'RP', 'XH', 'RQ', 'RS', 'XI']


def _valeurs_cr(exercice):
    s = soldes(exercice)
    v = defaultdict(lambda: ZERO)
    for compte, solde in s.items():
        if not compte or compte[0] not in '678' or compte == COMPTE_A_NOUVEAUX:
            continue
        ref = sens = None
        for r, _l, sn, prefixes, exclus in CR:
            if compte.startswith(prefixes) and not (exclus and compte.startswith(exclus)):
                ref, sens = r, sn
                break
        if ref is None:
            if compte[0] == '6':
                ref, sens = 'RJ', 'C'
            elif compte[0] == '7':
                ref, sens = 'TH', 'P'
            else:                                # classe 8 non référencée
                ref, sens = ('TO', 'P') if solde < 0 else ('RP', 'C')
        v[ref] += -solde if sens == 'P' else solde
    for ref, _l, f in SOLDES_CR:
        v[ref] = f(v)
    return v


def compte_resultat_etafi(exercice, precedent=None):
    from .exercices import exercice_precedent
    precedent = precedent if precedent is not None else exercice_precedent(exercice)
    v = _valeurs_cr(exercice)
    v1 = _valeurs_cr(precedent) if precedent is not None else None
    lib = {r: l for r, l, *_ in CR} | {r: l for r, l, _ in SOLDES_CR}
    soldes_refs = {r for r, *_ in SOLDES_CR}
    signe = {r: sn for r, _l, sn, *_ in CR}
    lignes = [{'ref': r, 'libelle': lib[r], 'total': r in soldes_refs,
               'signe': '+' if signe.get(r) == 'P' else ('−' if signe.get(r) == 'C' else ''),
               'net': _f(v[r]), 'net_n1': _f(v1[r]) if v1 else None} for r in ORDRE_CR]
    return {'lignes': lignes, 'resultat': _f(v['XI']), 'chiffre_affaires': _f(v['XB']),
            'precedent': precedent.annee_scolaire if precedent else None}


# ── Tableau des flux de trésorerie ────────────────────────────────────────────
def _est_treso(compte):
    return compte.startswith('5') and not compte.startswith('59')


def _calcul_tft(exercice):
    """Flux de l'exercice (référence SYSCOHADA → montant), exacts par
    construction : la variation de trésorerie se retrouve au franc près,
    ou l'écart est montré (ligne de contrôle)."""
    m = mouvements(exercice)
    cession = mouvements(exercice, source='CESSION')
    o = ouverture(exercice)

    def mv(prefixes, exclus=(), base=None):
        return _somme(base if base is not None else m, prefixes, exclus)

    # Résultat hors cessions (81/82) et hors 890 : la CAFG.
    hors = mv(('6', '7', '8'), ('81', '82', COMPTE_A_NOUVEAUX))
    dotations = -(mv(('28', '29', '15', '19')) - mv(('28', '29'), base=cession))
    v = defaultdict(lambda: ZERO)
    v['FA'] = -hors + dotations
    v['FB'] = -mv(('48',))
    v['FC'] = -mv(('3',))
    creances = dettes = ZERO
    s = soldes(exercice)
    for compte, valeur in m.items():
        if compte.startswith('4') and not compte.startswith('48'):
            if s.get(compte, ZERO) >= 0:
                creances += valeur
            else:
                dettes += valeur
    v['FD'] = -creances
    v['FE'] = -dettes
    # À-nouveaux de reprise (migration) passés hors ouverture : ni produit ni
    # flux d'investissement — présentés à part pour ne rien cacher.
    v['FE2'] = -m.get(COMPTE_A_NOUVEAUX, ZERO) - mv(('59',))
    v['ZB'] = v['FA'] + v['FB'] + v['FC'] + v['FD'] + v['FE'] + v['FE2']

    hors_cession = {c: m[c] - cession.get(c, ZERO) for c in m}
    v['FF'] = -mv(('21', '20'), base=hors_cession)
    v['FG'] = -mv(('22', '23', '24', '25'), base=hors_cession)
    v['FH'] = -mv(('26', '27'), base=hors_cession)
    v['FI'] = -mv(('82',))
    v['FJ'] = ZERO
    v['ZC'] = v['FF'] + v['FG'] + v['FH'] + v['FI'] + v['FJ']

    v['FK'] = -mv(('10', '11'))
    v['FL'] = -mv(('14',))
    v['FM'] = ZERO
    v['FN'] = -mv(('12', '13'))
    v['ZD'] = v['FK'] + v['FL'] + v['FM'] + v['FN']
    emprunts = defaultdict(lambda: ZERO)
    for r in (JournalEntry.objects.filter(tenant=exercice.tenant, exercice=exercice)
              .exclude(_filtre_ouverture())
              .filter(Q(no_compte__startswith='16') | Q(no_compte__startswith='17')
                      | Q(no_compte__startswith='18'))
              .values('no_compte').annotate(d=Sum('debit'), c=Sum('credit'))):
        cle = 'FO' if r['no_compte'].startswith('16') else 'FP'
        emprunts[cle] += _d(r['c'])
        emprunts['FQ'] += _d(r['d'])
    v['FO'], v['FP'], v['FQ'] = emprunts['FO'], emprunts['FP'], -emprunts['FQ']
    v['ZE'] = v['FO'] + v['FP'] + v['FQ']
    v['ZF'] = v['ZD'] + v['ZE']
    v['ZG'] = v['ZB'] + v['ZC'] + v['ZF']
    v['ZA'] = sum((val for c, val in o.items() if _est_treso(c)), ZERO)
    v['ZH'] = v['ZA'] + v['ZG']
    v['TN_BILAN'] = sum((val for c, val in s.items() if _est_treso(c)), ZERO)
    v['ECART'] = v['TN_BILAN'] - v['ZH']
    return v


LIGNES_TFT = [
    ('ZA', 'Trésorerie nette au début de l’exercice', True),
    ('FA', 'Capacité d’autofinancement globale (CAFG)', False),
    ('FB', '− Variation de l’actif circulant HAO', False),
    ('FC', '− Variation des stocks', False),
    ('FD', '− Variation des créances', False),
    ('FE', '+ Variation du passif circulant', False),
    ('FE2', 'Autres éléments (à-nouveaux de reprise, dépréciations de trésorerie)', False),
    ('ZB', 'Flux de trésorerie provenant des activités opérationnelles', True),
    ('FF', '− Décaissements liés aux acquisitions d’immobilisations incorporelles', False),
    ('FG', '− Décaissements liés aux acquisitions d’immobilisations corporelles', False),
    ('FH', '− Décaissements liés aux acquisitions d’immobilisations financières', False),
    ('FI', '+ Encaissements liés aux cessions d’immobilisations corporelles et incorporelles', False),
    ('FJ', '+ Encaissements liés aux cessions d’immobilisations financières', False),
    ('ZC', 'Flux de trésorerie provenant des activités d’investissement', True),
    ('FK', '+ Augmentations de capital par apports nouveaux', False),
    ('FL', '+ Subventions d’investissement reçues', False),
    ('FM', '− Prélèvements sur le capital', False),
    ('FN', '− Dividendes versés', False),
    ('ZD', 'Flux de trésorerie provenant des capitaux propres', True),
    ('FO', '+ Emprunts', False),
    ('FP', '+ Autres dettes financières', False),
    ('FQ', '− Remboursements des emprunts et autres dettes financières', False),
    ('ZE', 'Flux de trésorerie provenant des capitaux étrangers', True),
    ('ZF', 'Flux de trésorerie provenant des activités de financement', True),
    ('ZG', 'VARIATION DE LA TRÉSORERIE NETTE DE LA PÉRIODE', True),
    ('ZH', 'Trésorerie nette à la fin de l’exercice', True),
]


def tft_etafi(exercice, precedent=None):
    from .exercices import exercice_precedent
    precedent = precedent if precedent is not None else exercice_precedent(exercice)
    v = _calcul_tft(exercice)
    v1 = _calcul_tft(precedent) if precedent is not None else None
    lignes = [{'ref': r, 'libelle': l, 'total': t, 'net': _f(v[r]),
               'net_n1': _f(v1[r]) if v1 else None} for r, l, t in LIGNES_TFT]
    return {'lignes': lignes, 'ecart': _f(v['ECART']), 'tresorerie_bilan': _f(v['TN_BILAN']),
            'precedent': precedent.annee_scolaire if precedent else None}


def donnees_tft(tenant, exercice):
    """Tableau des flux pour l'écran et son export PDF (clés historiques)."""
    from apps.paiements.models import Paiement
    from .tresorerie import liste_par_mode
    from .views import _detecter_systeme, _sum_paiements

    paiements = Paiement.objects.filter(tenant=tenant, exercice=exercice)
    v = _calcul_tft(exercice)
    return {
        'exercice': exercice.annee_scolaire,
        'methode': 'Indirecte',
        'systeme': _detecter_systeme(_sum_paiements(paiements)),
        'flux_a': {
            'resultat_net': _f(resultat_net(exercice)),
            'amort': _f(v['FA'] - resultat_net(exercice)),
            'var_actif_b': _f(v['FB'] + v['FC'] + v['FD']),
            'var_passif_h': _f(v['FE']),
            'autres': _f(v['FE2']),
            'cafg': _f(v['FA']),
            'flux_net': _f(v['ZB']),
        },
        'flux_b': {'acquisitions': _f(-(v['FF'] + v['FG'] + v['FH'])),
                   'cessions': _f(v['FI'] + v['FJ']), 'flux_net': _f(v['ZC'])},
        'flux_c': {'emprunts': _f(v['FO'] + v['FP']), 'remboursements': _f(-v['FQ']),
                   'capitaux_propres': _f(v['ZD']), 'flux_net': _f(v['ZF'])},
        'tresorerie': {'tn_debut': _f(v['ZA']), 'variation': _f(v['ZG']), 'tn_fin': _f(v['ZH']),
                       'tn_bilan': _f(v['TN_BILAN']), 'ecart': _f(v['ECART'])},
        'par_mode': liste_par_mode(paiements.filter(statut='ACTIF').exclude(mode_paiement='REPRISE')),
    }


# ── Notes annexes ─────────────────────────────────────────────────────────────
def _note_comptes(exercice, precedent, prefixes, sens, plan, exclus=()):
    """Lignes {compte, libellé, N, N-1} des comptes visés, au sens demandé
    ('D' : solde débiteur positif, 'C' : créditeur positif)."""
    s = soldes(exercice)
    s1 = soldes(precedent) if precedent is not None else {}
    comptes = sorted({c for c in list(s) + list(s1)
                      if c.startswith(tuple(prefixes)) and not (exclus and c.startswith(tuple(exclus)))})
    lignes = []
    tot = tot1 = ZERO
    k = 1 if sens == 'D' else -1
    for c in comptes:
        n, n1 = s.get(c, ZERO) * k, s1.get(c, ZERO) * k
        if n == 0 and n1 == 0:
            continue
        tot += n
        tot1 += n1
        lignes.append([c, plan.get(c, c), _f(n), _f(n1) if precedent else None])
    lignes.append(['', 'TOTAL', _f(tot), _f(tot1) if precedent else None])
    return lignes


def notes_etafi(tenant, exercice, precedent=None):
    from apps.eleves.models import Eleve
    from django.db.models import Count
    from .activites import resultats_par_activite
    from .exercices import exercice_precedent
    from .views import get_plan_dict

    precedent = precedent if precedent is not None else exercice_precedent(exercice)
    plan = get_plan_dict(tenant)
    cols_n = ['Compte', 'Libellé', 'Exercice N', 'Exercice N-1']
    notes = []

    # Note 3A / 3C — immobilisations et amortissements (mouvements)
    o, m, s = ouverture(exercice), mouvements(exercice), soldes(exercice)
    lignes_3a, lignes_3c = [], []
    for ref, lib, prefixes, exclus in ACTIF[:12]:
        def tot(dico, base_prefixes=prefixes):
            return _somme(dico, base_prefixes, exclus)
        aug = sum((v for c, v in m.items() if c.startswith(prefixes)
                   and not (exclus and c.startswith(exclus)) and v > 0), ZERO)
        dim = -sum((v for c, v in m.items() if c.startswith(prefixes)
                    and not (exclus and c.startswith(exclus)) and v < 0), ZERO)
        if tot(o) or aug or dim or tot(s):
            lignes_3a.append([ref, lib, _f(tot(o)), _f(aug), _f(dim), _f(tot(s))])
        am_pref = tuple('28' + p[1:] for p in prefixes) + tuple('29' + p[1:] for p in prefixes)
        am_excl = tuple('28' + p[1:] for p in exclus)
        ao = -_somme(o, am_pref, am_excl)
        ac = -_somme(s, am_pref, am_excl)
        dot = -sum((v for c, v in m.items() if c.startswith(am_pref)
                    and not (am_excl and c.startswith(am_excl)) and v < 0), ZERO)
        rep = sum((v for c, v in m.items() if c.startswith(am_pref)
                   and not (am_excl and c.startswith(am_excl)) and v > 0), ZERO)
        if ao or ac or dot or rep:
            lignes_3c.append([ref, lib, _f(ao), _f(dot), _f(rep), _f(ac)])
    notes.append({'numero': '3A', 'titre': 'Immobilisations brutes',
                  'colonnes': ['Réf.', 'Rubrique', 'Début', 'Augmentations', 'Diminutions', 'Fin'],
                  'lignes': lignes_3a or [['', 'Néant', None, None, None, None]]})
    notes.append({'numero': '3C', 'titre': 'Amortissements et dépréciations des immobilisations',
                  'colonnes': ['Réf.', 'Rubrique', 'Début', 'Dotations', 'Reprises', 'Fin'],
                  'lignes': lignes_3c or [['', 'Néant', None, None, None, None]]})
    notes.append({'numero': '6', 'titre': 'Stocks et encours', 'colonnes': cols_n,
                  'lignes': _note_comptes(exercice, precedent, ('3',), 'D', plan)})
    notes.append({'numero': '7', 'titre': 'Clients (familles, organismes, clients des activités)',
                  'colonnes': cols_n, 'lignes': _note_comptes(exercice, precedent, ('41',), 'D', plan)})
    notes.append({'numero': '8', 'titre': 'Autres créances', 'colonnes': cols_n,
                  'lignes': _note_comptes(exercice, precedent, ('42', '43', '44', '45', '46', '47'), 'D', plan,
                                          exclus=('478',))})
    notes.append({'numero': '11', 'titre': 'Disponibilités (trésorerie-actif)', 'colonnes': cols_n,
                  'lignes': _note_comptes(exercice, precedent, ('5',), 'D', plan, exclus=('59',))})
    notes.append({'numero': '13', 'titre': 'Capitaux propres et ressources assimilées', 'colonnes': cols_n,
                  'lignes': _note_comptes(exercice, precedent, ('10', '11', '12', '13', '14', '15'), 'C', plan)})
    notes.append({'numero': '16', 'titre': 'Dettes financières et provisions pour risques',
                  'colonnes': cols_n,
                  'lignes': _note_comptes(exercice, precedent, ('16', '17', '18', '19'), 'C', plan)})
    notes.append({'numero': '17', 'titre': "Fournisseurs d'exploitation", 'colonnes': cols_n,
                  'lignes': _note_comptes(exercice, precedent, ('40',), 'C', plan)})
    notes.append({'numero': '18', 'titre': 'Dettes fiscales et sociales', 'colonnes': cols_n,
                  'lignes': _note_comptes(exercice, precedent, ('42', '43', '44'), 'C', plan)})
    notes.append({'numero': '21', 'titre': "Chiffre d'affaires et autres produits", 'colonnes': cols_n,
                  'lignes': _note_comptes(exercice, precedent, ('70', '71', '72', '73', '74', '75'), 'C',
                                          plan)})
    act = resultats_par_activite(tenant, exercice)
    notes.append({'numero': '21B', 'titre': 'Produits, charges et résultat par activité',
                  'colonnes': ['Activité', 'Produits', 'Charges', 'Résultat'],
                  'lignes': [[a['libelle'], a['produits'], a['charges'], a['resultat']]
                             for a in act['activites']]
                  + [['TOTAL', act['total_produits'], act['total_charges'], act['total_resultat']]]})
    notes.append({'numero': '22', 'titre': 'Achats, transports et services extérieurs', 'colonnes': cols_n,
                  'lignes': _note_comptes(exercice, precedent, ('60', '61', '62', '63'), 'D', plan)})
    notes.append({'numero': '26', 'titre': 'Impôts et taxes, autres charges', 'colonnes': cols_n,
                  'lignes': _note_comptes(exercice, precedent, ('64', '65'), 'D', plan)})
    lignes_27 = _note_comptes(exercice, precedent, ('66',), 'D', plan)
    try:
        from apps.rh.models import Employe
        nb = Employe.objects.filter(tenant=tenant, statut='ACTIF').count()
        lignes_27.append(['', 'Effectif du personnel (à la date d’édition)', nb, None])
    except Exception:
        pass
    notes.append({'numero': '27', 'titre': 'Charges de personnel et effectifs', 'colonnes': cols_n,
                  'lignes': lignes_27})
    sections = (Eleve.objects.filter(tenant=tenant, exercice=exercice)
                .values('section__nom').annotate(nb=Count('id')).order_by('section__nom'))
    notes.append({'numero': '36', 'titre': "Informations propres à l'établissement d'enseignement",
                  'colonnes': ['Section', 'Élèves inscrits'],
                  'lignes': [[x['section__nom'] or '—', x['nb']] for x in sections]
                  + [['TOTAL', sum(x['nb'] for x in sections)]]})
    return notes


# ── Balance générale ──────────────────────────────────────────────────────────
def balance_generale(tenant, exercice):
    """Balance à 6 colonnes : ouverture, mouvements, clôture."""
    from .views import get_plan_dict
    plan = get_plan_dict(tenant)
    o, m = ouverture(exercice), mouvements(exercice)
    md = defaultdict(lambda: ZERO)
    mc = defaultdict(lambda: ZERO)
    for r in (JournalEntry.objects.filter(tenant=tenant, exercice=exercice).exclude(_filtre_ouverture())
              .values('no_compte').annotate(d=Sum('debit'), c=Sum('credit'))):
        md[r['no_compte']] += _d(r['d'])
        mc[r['no_compte']] += _d(r['c'])
    s = soldes(exercice)
    lignes = []
    tot = defaultdict(lambda: ZERO)
    for c in sorted(set(o) | set(m) | set(s), key=lambda x: (x.replace('.', ''), x)):
        ov, sv = o.get(c, ZERO), s.get(c, ZERO)
        if not (ov or md[c] or mc[c] or sv):
            continue
        ligne = {'compte': c, 'libelle': plan.get(c, c),
                 'ouv_d': max(ov, ZERO), 'ouv_c': max(-ov, ZERO),
                 'mvt_d': md[c], 'mvt_c': mc[c],
                 'clo_d': max(sv, ZERO), 'clo_c': max(-sv, ZERO)}
        for k in ('ouv_d', 'ouv_c', 'mvt_d', 'mvt_c', 'clo_d', 'clo_c'):
            tot[k] += ligne[k]
        lignes.append(ligne)
    return {'lignes': lignes, 'totaux': dict(tot)}
