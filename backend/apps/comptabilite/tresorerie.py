"""Ventilation d'un règlement sur plusieurs modes de paiement (multi-mode).

Un même règlement (recette élève, charge, immobilisation, paie…) peut être réglé
par plusieurs moyens à la fois — ex. 60 000 = 30 000 espèces + 20 000 Wave +
10 000 Orange Money. Ce module centralise :

* la correspondance mode → compte de trésorerie SYSCOHADA (unique source de
  vérité, auparavant dupliquée dans plusieurs vues) ;
* la validation et la normalisation de la ventilation saisie ;
* la construction des lignes d'écriture de la jambe de trésorerie, quel que soit
  le sens (débit pour un encaissement, crédit pour un décaissement).
"""

from decimal import Decimal, ROUND_HALF_UP

# Mode de règlement → (compte de trésorerie, libellé). Source unique de vérité.
COMPTE_MODE = {
    'ESPECE':       ('571',  'Caisse'),
    'WAVE':         ('5521', 'Wave'),
    'ORANGE_MONEY': ('5522', 'Orange Money'),
    'FREE_MONEY':   ('5523', 'Free Money'),
    'VIREMENT':     ('521',  'Banque'),
    'CHEQUE':       ('521',  'Banque'),
}
MODE_DEFAUT = 'ESPECE'

# Modes de règlement d'un reçu d'élève qui ne sont PAS de la trésorerie : la
# compensation règle la scolarité par ce que l'école doit au parent, membre du
# personnel (salaires impayés) — sa contrepartie est la dette 422, rien n'entre
# en caisse. Hors de COMPTE_MODE à dessein : les autres modules (charges, GMRF)
# valident leurs modes sur COMPTE_MODE et ne doivent pas l'accepter.
COMPTE_HORS_TRESORERIE = {
    'COMPENSATION': ('422', 'Compensation dû au personnel'),
}

# Tolérance d'arrondi (les montants FCFA sont entiers, mais on reste prudent).
_EPS = Decimal('0.01')


def compte_du_mode(mode, caisse=None):
    """(compte, libellé) du mode, avec repli sur la caisse si mode inconnu.

    `caisse` : caisse de l'école qui reçoit les ESPÈCES (garderie, cantine…).
    Elle ne change rien aux autres modes — un versement Wave n'entre pas dans
    une caisse en espèces.
    """
    if mode in COMPTE_HORS_TRESORERIE:
        return COMPTE_HORS_TRESORERIE[mode]
    compte, libelle = COMPTE_MODE.get(mode, COMPTE_MODE[MODE_DEFAUT])
    if caisse is not None and compte == COMPTE_MODE['ESPECE'][0]:
        return (caisse.no_compte, caisse.nom)
    return (compte, libelle)


def normaliser_ventilation(modes_reglement, total, mode_simple=None):
    """Retourne une liste normalisée [{'mode', 'montant'}] dont la somme == total.

    - `modes_reglement` : liste [{'mode': 'WAVE', 'montant': 20000}, …] issue de
      la saisie. Peut être vide/None → on retombe sur un règlement simple.
    - `total` : montant total attendu (Decimal/float/str).
    - `mode_simple` : mode à utiliser quand aucune ventilation n'est fournie
      (compat ascendante avec l'ancien champ `mode_paiement`).

    Lève ValueError si la ventilation est incohérente (somme ≠ total, montant
    négatif, mode manquant).
    """
    total = Decimal(str(total)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # Règlement simple : aucune ventilation explicite.
    if not modes_reglement:
        mode = mode_simple or MODE_DEFAUT
        return [{'mode': mode, 'montant': total}]

    lignes = []
    somme = Decimal('0')
    for i, ligne in enumerate(modes_reglement):
        mode = (ligne or {}).get('mode')
        if not mode:
            raise ValueError(f"Ligne de règlement {i + 1} : mode manquant.")
        try:
            montant = Decimal(str((ligne or {}).get('montant', 0)))
        except (TypeError, ValueError):
            raise ValueError(f"Ligne de règlement {i + 1} : montant invalide.")
        montant = montant.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if montant <= 0:
            raise ValueError(f"Ligne de règlement {i + 1} : le montant doit être positif.")
        lignes.append({'mode': mode, 'montant': montant})
        somme += montant

    if abs(somme - total) > _EPS:
        raise ValueError(
            f"La ventilation des modes de paiement ({somme:,.0f}) ne correspond "
            f"pas au total à régler ({total:,.0f} FCFA)."
        )
    return lignes


def lignes_tresorerie(ventilation, sens, libelle, ordre_debut=1, caisse=None):
    """Construit les dict d'écriture de la jambe de trésorerie.

    - `ventilation` : sortie de `normaliser_ventilation`.
    - `sens` : 'debit' (encaissement) ou 'credit' (décaissement).
    - `libelle` : libellé de base ; le mode est ajouté entre parenthèses.
    - `ordre_debut` : numéro d'ordre de la première ligne.

    Retourne une liste de dict compatibles avec JournalEntry.objects.create :
    {ordre, no_compte, debit, credit, libelle}.
    """
    if sens not in ('debit', 'credit'):
        raise ValueError("sens doit être 'debit' ou 'credit'.")

    lignes = []
    for i, v in enumerate(ventilation):
        compte, lib_compte = compte_du_mode(v['mode'], caisse)
        montant = float(v['montant'])
        lignes.append(dict(
            ordre=ordre_debut + i,
            no_compte=compte,
            debit=montant if sens == 'debit' else 0,
            credit=montant if sens == 'credit' else 0,
            libelle=f"Règlement {lib_compte} — {libelle}",
        ))
    return lignes


# ── Soldes de trésorerie à la clôture ────────────────────────────────────────
# Solde d'ouverture de chaque compte de trésorerie : le champ de l'exercice qui
# le porte. Seule correspondance compte ↔ champ ; le reste du code s'y réfère.
# `solde_initial_mobile` est le solde Wave (nom historique du champ).
SOLDES_INITIAUX = {
    '571':  'solde_initial_caisse',
    '521':  'solde_initial_banque',
    '5521': 'solde_initial_mobile',
    '5522': 'solde_initial_orange_money',
    '5523': 'solde_initial_free_money',
}


def solde_initial_compte(exercice, no_compte):
    """Solde d'ouverture du compte, 0 s'il n'en porte pas (5715, 522…)."""
    champ = SOLDES_INITIAUX.get(no_compte)
    return float(getattr(exercice, champ) or 0) if champ else 0.0


# Regroupement des comptes de trésorerie par poste. Le mobile money se détaille
# par opérateur ; le poste « mobile » en est la somme.
POSTES_TRESORERIE = {
    'caisse':       ('571',),
    'banque':       ('521',),
    'wave':         ('5521',),
    'orange_money': ('5522',),
    'free_money':   ('5523',),
}
POSTES_MOBILE = ('wave', 'orange_money', 'free_money')
# Champ de l'exercice qui porte le solde d'ouverture de chaque poste.
CHAMP_POSTE = {poste: SOLDES_INITIAUX[comptes[0]] for poste, comptes in POSTES_TRESORERIE.items()}


def soldes_cloture(exercice):
    """Solde réel de chaque poste de trésorerie à la fin d'un exercice.

    Solde d'ouverture + mouvements nets du journal sur les comptes concernés —
    le même calcul que le tableau de bord « Trésorerie par canal ». Les
    annulations sont prises en compte d'office : leurs contre-écritures se
    compensent au débit et au crédit.

    Retourne {'caisse', 'banque', 'wave', 'orange_money', 'free_money',
    'mobile' (somme des trois opérateurs), 'total'}.
    """
    from django.db.models import Sum
    from .models import JournalEntry

    # Préfixes, et non liste exacte : les caisses de service (5716, 5717…) et
    # les sous-comptes bancaires appartiennent à leur poste. Les compter à
    # l'identique laissait leur solde hors de la trésorerie de l'école.
    from django.db.models import Q
    filtre = Q()
    for postes in POSTES_TRESORERIE.values():
        for prefixe in postes:
            filtre |= Q(no_compte__startswith=prefixe)
    mouvements = {
        b['no_compte']: float(b['d'] or 0) - float(b['c'] or 0)
        for b in JournalEntry.objects
        .filter(filtre, tenant=exercice.tenant, exercice=exercice)
        .values('no_compte').annotate(d=Sum('debit'), c=Sum('credit'))
    }

    soldes = {
        poste: float(getattr(exercice, CHAMP_POSTE[poste]) or 0)
        + sum(montant for compte, montant in mouvements.items()
              if compte.startswith(tuple(comptes_poste)))
        for poste, comptes_poste in POSTES_TRESORERIE.items()
    }
    soldes['total'] = sum(soldes.values())
    soldes['mobile'] = sum(soldes[p] for p in POSTES_MOBILE)
    return soldes


# ── Encaissements par mode ───────────────────────────────────────────────────
LIBELLES_MODE = {
    'ESPECE':       'Espèce',
    'WAVE':         'Wave',
    'ORANGE_MONEY': 'Orange Money',
    'FREE_MONEY':   'Free Money',
    'VIREMENT':     'Virement',
    'CHEQUE':       'Chèque',
    'REPRISE':      'Reprise (migration)',
    'COMPENSATION': 'Compensation (dû au personnel)',
}


def encaissements_par_mode(paiements):
    """Ventile des règlements élèves sur leurs modes réels.

    Un règlement multi-mode (mode_paiement = 'MIXTE') n'est pas un mode : ses
    30 000 en espèces entrent dans la caisse, ses 20 000 Wave sur le compte
    Wave. Regrouper par `mode_paiement` faisait apparaître une rubrique
    « MIXTE » au lieu de répartir le montant — et le tableau de bord, qui ne
    connaît que les vrais canaux, perdait purement ces encaissements.

    Le montant est celui réellement encaissé (`Paiement.total`, reliquat
    antérieur compris), le même que la jambe de trésorerie du journal.

    Retourne {mode: {'nb': int, 'montant': float}} ; un règlement mixte compte
    une opération dans chacun des modes qu'il utilise.
    """
    resultat = {}
    champs = ('mode_paiement', 'modes_reglement', 'montant_inscription',
              'montant_mensualite', 'montant_uniforme', 'montant_fournitures',
              'montant_cantine', 'montant_divers', 'montant_reliquat')
    for p in paiements.only(*champs):
        total = float(p.total)
        try:
            lignes = normaliser_ventilation(p.modes_reglement, total, p.mode_paiement)
        except ValueError:
            # Ventilation historique incohérente : on ne perd pas le montant,
            # il reste sur le mode principal déclaré.
            lignes = [{'mode': p.mode_paiement, 'montant': Decimal(str(total))}]
        for ligne in lignes:
            case = resultat.setdefault(ligne['mode'], {'nb': 0, 'montant': 0.0})
            case['nb'] += 1
            case['montant'] += float(ligne['montant'])
    return resultat


def liste_par_mode(paiements):
    """encaissements_par_mode() en liste triée, prête pour l'API :
    [{'mode', 'libelle', 'nb', 'total'}], plus gros montant en premier."""
    return sorted(
        ({'mode': m, 'libelle': LIBELLES_MODE.get(m, m), 'nb': v['nb'],
          'total': round(v['montant'], 2)}
         for m, v in encaissements_par_mode(paiements).items()),
        key=lambda x: x['total'], reverse=True)
