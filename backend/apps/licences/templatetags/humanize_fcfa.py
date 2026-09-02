"""Le formatage des montants en francs CFA pour les documents.

Django propose `intcomma`, qui met des virgules — illisible ici. Le franc CFA
s'écrit avec une espace comme séparateur de milliers et n'a pas de décimale :
un catalogue qui afficherait « 25,000.00 » ne serait pas français.
"""
from django import template

register = template.Library()


@register.filter
def fcfa(valeur):
    try:
        n = int(valeur)
    except (TypeError, ValueError):
        return valeur
    # Espace insécable : un montant ne doit jamais se couper en fin de ligne.
    return f'{n:,}'.replace(',', ' ')
