"""Formats d'impression du reçu de paiement.

Le ticket thermique (58/80 mm) n'a PAS de hauteur fixe : un rouleau n'a pas de
« page ». Une page de 80 × 297 mm envoyée à un pilote de rouleau réglé plus
court (80 × 160 mm, etc.) est réduite pour tenir en hauteur, donc en largeur
aussi : le reçu sortait à environ la moitié de la largeur du papier (Shoumoul,
28/09). Le ticket est rendu sur une bande très longue, puis la page est
ramenée à la hauteur de son contenu.

La page a la largeur IMPRIMABLE du rouleau, pas celle du papier : une tête
thermique de 80 mm n'imprime que 72 mm (576 points), une de 58 mm que 48 mm
(384 points). Avec une page de 80 mm, le contenu allait de 4 à 76 mm et le
pilote, qui cale la page sur le bord de la zone imprimable, coupait la droite
du reçu (montants, nom de l'élève — école test, 06/10).
"""
from io import BytesIO

MM = 72 / 25.4

# clé (paramètre ?taille=) → (gabarit, taille @page, largeur du rouleau en mm ou None)
FORMATS_RECU = {
    '58MM':   ('pdf/recu_ticket.html',   '48mm 1500mm', 58),
    '80MM':   ('pdf/recu_ticket.html',   '72mm 1500mm', 80),
    'A6':     ('pdf/recu_ticket.html',   'A6 portrait', None),
    'A5':     ('pdf/recu_paiement.html', 'A5 portrait', None),
    'A4':     ('pdf/recu_paiement.html', 'A4 portrait', None),
    'LETTER': ('pdf/recu_paiement.html', 'letter portrait', None),
    'LEGAL':  ('pdf/recu_paiement.html', 'legal portrait', None),
}


# Texte blanc, dans son propre bloc, posé en dernier par le gabarit ticket.
# On ne mesure pas « le texte le plus bas » : pypdf donne une position fausse
# à la 2e ligne d'un paragraphe coupé par <br> (le pied du ticket).
REPERE_FIN = 'FIN-DU-RECU'


def rogner_a_la_hauteur_du_contenu(pdf_bytes, marge_mm=4):
    """Ramène la page 1 à la hauteur de son contenu (repère de fin + marge).

    Le contenu est remonté plutôt que la mediabox décalée : certains pilotes
    thermiques ignorent une origine de page différente de (0, 0).
    """
    from pypdf import PdfReader, PdfWriter, Transformation

    lecteur = PdfReader(BytesIO(pdf_bytes))
    page = lecteur.pages[0]
    ys = []

    def visiteur(texte, cm, tm, _font, _size):
        if REPERE_FIN in texte:
            # Position réelle = matrice de texte × matrice courante.
            ys.append(tm[4] * cm[1] + tm[5] * cm[3] + cm[5])

    page.extract_text(visitor_text=visiteur)
    if len(lecteur.pages) != 1 or not ys:
        return pdf_bytes   # contenu inattendu : on ne coupe rien
    haut, largeur = float(page.mediabox.top), float(page.mediabox.width)
    bas = max(ys[0] - marge_mm * MM, 0)
    page.add_transformation(Transformation().translate(0, -bas))
    page.mediabox.lower_left = (0, 0)
    page.mediabox.upper_right = (largeur, haut - bas)
    page.cropbox = page.mediabox

    ecrivain = PdfWriter()
    ecrivain.add_page(page)
    sortie = BytesIO()
    ecrivain.write(sortie)
    return sortie.getvalue()
