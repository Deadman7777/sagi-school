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

# Tolérance d'arrondi (les montants FCFA sont entiers, mais on reste prudent).
_EPS = Decimal('0.01')


def compte_du_mode(mode):
    """(compte, libellé) du mode, avec repli sur la caisse si mode inconnu."""
    return COMPTE_MODE.get(mode, COMPTE_MODE[MODE_DEFAUT])


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


def lignes_tresorerie(ventilation, sens, libelle, ordre_debut=1):
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
        compte, lib_compte = compte_du_mode(v['mode'])
        montant = float(v['montant'])
        lignes.append(dict(
            ordre=ordre_debut + i,
            no_compte=compte,
            debit=montant if sens == 'debit' else 0,
            credit=montant if sens == 'credit' else 0,
            libelle=f"Règlement {lib_compte} — {libelle}",
        ))
    return lignes
