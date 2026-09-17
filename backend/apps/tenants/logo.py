"""Dimensions d'affichage du logo de l'école dans un PDF.

xhtml2pdf déforme une image à laquelle on ne donne qu'une dimension, ou la
pousse hors de sa cellule : un logo en bannière (large et bas) finissait écrasé
et à cheval sur le nom de l'école. On lit donc les vraies proportions de
l'image et on la fait tenir dans une boîte, sans jamais l'étirer.
"""
import base64
import io
import re


def dimensions_logo(data_uri, largeur_max, hauteur_max):
    """(largeur, hauteur) en points, proportions conservées ; None si illisible."""
    trouve = re.match(r'data:[^;,]+;base64,(.+)$', str(data_uri or ''), re.S)
    if not trouve:
        return None
    try:
        from PIL import Image
        with Image.open(io.BytesIO(base64.b64decode(trouve.group(1)))) as image:
            largeur, hauteur = image.size
    except Exception:
        return None
    if not largeur or not hauteur:
        return None
    echelle = min(largeur_max / largeur, hauteur_max / hauteur)
    return round(largeur * echelle, 1), round(hauteur * echelle, 1)
