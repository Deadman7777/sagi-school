"""Produits, charges et résultat net — un seul calcul pour toute l'application.

Le compte de résultat et le tableau de bord répondaient chacun avec leur
propre agrégation. Le tableau de bord ne retenait que les écritures
`source in (CHARGE, BUDGET, MIGRATION)` : la paie, les dotations aux
amortissements et les intérêts d'emprunt tombaient hors du total, et
l'école lisait un bénéfice presque double du vrai (61 194 350 au tableau de
bord contre 31 391 766 au compte de résultat, sur les mêmes écritures).

Toute grandeur « produits / charges / résultat » de l'application passe
désormais par ici.
"""
from django.db.models import Q, Sum

# Comptes techniques exclus du résultat : le 890 porte le bilan d'ouverture
# d'une migration, il ne constate ni produit ni charge de l'exercice.
HORS_RESULTAT = ('890',)

# Produits : classe 7 + produits HAO. Charges : classe 6 + charges HAO.
PREFIXES_PRODUITS = ('7',)
PREFIXES_PRODUITS_HAO = ('82', '84', '86', '88')
PREFIXES_CHARGES = ('6',)
PREFIXES_CHARGES_HAO = ('81', '83', '87', '89')


def _net(entries, prefixes, sens):
    """Contribution NETTE des comptes visés.

    Un produit compte pour crédit − débit, une charge pour débit − crédit :
    sommer le seul sens naturel ignorerait les annulations et les
    neutralisations de migration.
    """
    q = Q()
    for p in prefixes:
        q |= Q(no_compte__startswith=p)
    agg = (entries.filter(q).exclude(no_compte__in=HORS_RESULTAT)
           .aggregate(d=Sum('debit'), c=Sum('credit')))
    debit, credit = float(agg['d'] or 0), float(agg['c'] or 0)
    return credit - debit if sens == 'credit' else debit - credit


def totaux_resultat(entries):
    """(total_produits, total_charges, resultat_net) pour un jeu d'écritures.

    `entries` est un queryset de JournalEntry déjà restreint au tenant et à
    l'exercice voulus. Le HAO n'est retenu que s'il est positif : un HAO net
    négatif relève de l'autre colonne, il ne vient pas minorer celle-ci.
    """
    produits = (_net(entries, PREFIXES_PRODUITS, 'credit')
                + max(_net(entries, PREFIXES_PRODUITS_HAO, 'credit'), 0))
    charges = (_net(entries, PREFIXES_CHARGES, 'debit')
               + max(_net(entries, PREFIXES_CHARGES_HAO, 'debit'), 0))
    return {
        'total_produits': round(produits, 2),
        'total_charges': round(charges, 2),
        'resultat_net': round(produits - charges, 2),
    }
