"""Balise {% logo_ecole %} : le logo de l'école, à la bonne taille, dans un PDF.

xhtml2pdf IGNORE `max-width` / `max-height` : un logo importé en haute
résolution s'imprimait à sa taille réelle, occupait la moitié du bulletin et
poussait la fin sur une deuxième page (42 pages pour 21 élèves). WeasyPrint,
essayé en premier par certaines vues quand il est installé, ignore à son tour
les attributs `width`/`height`. Une taille explicite en points, dans le style,
est respectée par les deux — et n'en donner qu'une déforme l'image. Les dimensions sont donc calculées ici, proportions conservées, par
`dimensions_logo` : un seul endroit pour tous les documents.

    {% load logo_ecole %}
    {% logo_ecole tenant.logo 130 45 %}
"""
from functools import lru_cache

from django import template
from django.utils.html import format_html

from apps.tenants.logo import dimensions_logo

register = template.Library()


@lru_cache(maxsize=16)
def _dimensions(data_uri, largeur_max, hauteur_max):
    # Les bulletins d'une classe impriment le même logo trente fois : on ne
    # décode l'image qu'une fois.
    return dimensions_logo(data_uri, largeur_max, hauteur_max)


@register.simple_tag
def logo_ecole(data_uri, largeur_max=130, hauteur_max=45, style=''):
    """<img> du logo tenant dans la boîte largeur_max × hauteur_max (points)."""
    if not data_uri:
        return ''
    dim = _dimensions(str(data_uri), float(largeur_max), float(hauteur_max))
    # Image illisible : on garde une hauteur imposée plutôt qu'une taille réelle
    # qui envahirait la page.
    largeur, hauteur = dim if dim else (None, float(hauteur_max))
    # La taille est écrite DEUX fois : en attributs et en style. Les bulletins
    # passent d'abord par WeasyPrint quand il est installé, qui ignore les
    # attributs ; xhtml2pdf, lui, ignore max-width. Le style en points est
    # le seul langage que les deux moteurs respectent.
    if largeur:
        return format_html('<img src="{}" width="{}" height="{}" style="width:{}pt;height:{}pt;{}">',
                           data_uri, largeur, hauteur, largeur, hauteur, style)
    return format_html('<img src="{}" height="{}" style="height:{}pt;{}">',
                       data_uri, hauteur, hauteur, style)
