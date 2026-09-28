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


def _seuil_otsu(histogramme):
    """Seuil qui sépare le mieux les deux tons dominants (méthode d'Otsu)."""
    total = sum(histogramme)
    somme = sum(i * n for i, n in enumerate(histogramme))
    poids_fonce = somme_fonce = 0
    meilleur, seuil = -1.0, 128
    for i, n in enumerate(histogramme):
        poids_fonce += n
        if not poids_fonce or poids_fonce == total:
            continue
        somme_fonce += i * n
        moy_fonce = somme_fonce / poids_fonce
        moy_clair = (somme - somme_fonce) / (total - poids_fonce)
        ecart = poids_fonce * (total - poids_fonce) * (moy_fonce - moy_clair) ** 2
        if ecart > meilleur:
            meilleur, seuil = ecart, i + 1
    return seuil


def logo_noir_et_blanc(data_uri):
    """Le logo en noir pur sur fond blanc, pour l'imprimante thermique.

    Une tête thermique ne fait que du noir ou rien : un logo en couleur ou en
    gris y sort en trame pâle, presque invisible (Shoumoul, 28/09). La
    transparence est posée sur du blanc, les deux tons dominants sont séparés
    (seuil d'Otsu : un seuil fixe effaçait les couleurs claires), puis, si le
    fond est devenu noir (logo sur fond coloré), l'image est inversée : un
    pavé noir se lit mal et vide la tête. Renvoie le data URI d'origine si
    l'image est illisible.
    """
    trouve = re.match(r'data:[^;,]+;base64,(.+)$', str(data_uri or ''), re.S)
    if not trouve:
        return data_uri
    try:
        from PIL import Image, ImageOps
        with Image.open(io.BytesIO(base64.b64decode(trouve.group(1)))) as image:
            image = image.convert('RGBA')
            fond = Image.new('RGBA', image.size, (255, 255, 255, 255))
            gris = Image.alpha_composite(fond, image).convert('L')
            seuil = _seuil_otsu(gris.histogram())
            net = gris.point(lambda v: 0 if v < seuil else 255)
            largeur, hauteur = net.size
            bord = ([net.getpixel((x, y)) for x in range(largeur) for y in (0, hauteur - 1)]
                    + [net.getpixel((x, y)) for y in range(hauteur) for x in (0, largeur - 1)])
            if bord.count(0) > len(bord) / 2:
                net = ImageOps.invert(net)
            sortie = io.BytesIO()
            net.save(sortie, format='PNG')
    except Exception:
        return data_uri
    return 'data:image/png;base64,' + base64.b64encode(sortie.getvalue()).decode()
