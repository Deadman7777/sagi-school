"""Remplissage d'un modèle Word (.docx) fourni par l'établissement.

L'école rédige son certificat dans Word, avec sa mise en page, son en-tête et
son cachet, et y place des codes entre accolades : {NOM_COMPLET}, {CLASSE}…
À chaque demande, l'app renvoie une copie du document où les codes sont
remplacés par les informations de l'élève.

Pourquoi pas une bibliothèque : python-docx n'est pas embarqué dans les
installations Windows, et un .docx n'est qu'une archive zip de XML. Le seul
piège est que Word DÉCOUPE le texte en morceaux (<w:t>) à sa guise — une
correction d'orthographe, un changement de police au milieu d'un mot suffisent.
« {NOM_COMPLET} » peut ainsi arriver en trois morceaux : « { », « NOM_ »,
« COMPLET} ». On recolle donc le texte de chaque paragraphe pour y chercher les
codes, puis on redistribue le résultat dans les morceaux d'origine, ce qui
conserve la mise en forme du premier caractère de chaque code.
"""
import io
import re
import zipfile
from xml.sax.saxutils import escape, unescape

# Parties du document où l'on remplace : corps, en-têtes, pieds de page, notes.
_PARTIES = re.compile(r'^word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml$')
_W_T = re.compile(r'<w:t(\s[^>]*)?>(.*?)</w:t>', re.S)
# Une frontière de paragraphe entre deux morceaux : un code ne la traverse pas.
_FIN_PARAGRAPHE = re.compile(r'</w:p>|<w:p[\s>]')
# Tolère les espaces et la casse : { nom_complet } vaut {NOM_COMPLET}.
_CODE = re.compile(r'\{\s*([A-Za-z_]+)\s*\}')
_ENTITES = {'&quot;': '"', '&apos;': "'"}

TAILLE_MAX = 5 * 1024 * 1024


class ModeleInvalide(ValueError):
    pass


def verifier_docx(contenu):
    """Refuse ce qui n'est pas un .docx lisible, avec un message utile à l'école."""
    if len(contenu) > TAILLE_MAX:
        raise ModeleInvalide('Le fichier dépasse 5 Mo. Réduisez la taille des images du modèle.')
    if contenu[:4] == b'\xd0\xcf\x11\xe0':
        raise ModeleInvalide(
            "Ce fichier est au format Word 97-2003 (.doc). Ouvrez-le dans Word et "
            "enregistrez-le au format « Document Word (.docx) ».")
    try:
        with zipfile.ZipFile(io.BytesIO(contenu)) as z:
            if 'word/document.xml' not in z.namelist():
                raise ModeleInvalide("Ce fichier n'est pas un document Word (.docx).")
    except zipfile.BadZipFile:
        raise ModeleInvalide("Ce fichier n'est pas un document Word (.docx).")


def codes_du_modele(contenu):
    """Codes présents dans le modèle, dans l'ordre d'apparition, sans doublon."""
    trouves = []
    with zipfile.ZipFile(io.BytesIO(contenu)) as z:
        for nom in z.namelist():
            if _PARTIES.match(nom):
                xml = z.read(nom).decode('utf-8')
                for groupe in _groupes(xml):
                    texte = ''.join(unescape(m.group(2), _ENTITES) for m in groupe)
                    for code in _CODE.findall(texte):
                        if code.upper() not in trouves:
                            trouves.append(code.upper())
    return trouves


def remplir_docx(contenu, valeurs):
    """Renvoie une copie du .docx où chaque code connu est remplacé.

    `valeurs` : {'NOM_COMPLET': 'Awa NDIAYE', …}. Un code inconnu reste tel
    quel dans le document, pour que l'école voie ce qu'elle doit corriger.
    """
    entree = zipfile.ZipFile(io.BytesIO(contenu))
    sortie_buf = io.BytesIO()
    with zipfile.ZipFile(sortie_buf, 'w', zipfile.ZIP_DEFLATED) as sortie:
        for info in entree.infolist():
            data = entree.read(info.filename)
            if _PARTIES.match(info.filename):
                data = _remplir_xml(data.decode('utf-8'), valeurs).encode('utf-8')
            sortie.writestr(info, data)
    return sortie_buf.getvalue()


def _groupes(xml):
    """Morceaux de texte <w:t> regroupés par paragraphe."""
    groupes, courant, fin_prec = [], [], None
    for m in _W_T.finditer(xml):
        if courant and _FIN_PARAGRAPHE.search(xml, fin_prec, m.start()):
            groupes.append(courant)
            courant = []
        courant.append(m)
        fin_prec = m.end()
    if courant:
        groupes.append(courant)
    return groupes


def _remplir_xml(xml, valeurs):
    nouveaux = {}   # position du morceau dans le XML -> nouveau texte
    for groupe in _groupes(xml):
        textes = [unescape(m.group(2), _ENTITES) for m in groupe]
        complet = ''.join(textes)
        codes = [c for c in _CODE.finditer(complet) if c.group(1).upper() in valeurs]
        if not codes:
            continue
        # Position de début de chaque morceau dans le texte recollé
        debuts, pos = [], 0
        for t in textes:
            debuts.append(pos)
            pos += len(t)

        def morceau(position, fin=False):
            """(indice du morceau, décalage) d'une position du texte recollé."""
            for i in range(len(textes) - 1, -1, -1):
                if debuts[i] < position or (debuts[i] == position and not fin):
                    return i, position - debuts[i]
            return 0, 0

        # De droite à gauche : une modification ne décale jamais les codes
        # restant à traiter, situés avant elle.
        for c in reversed(codes):
            valeur = str(valeurs[c.group(1).upper()] or '')
            i, off_i = morceau(c.start())
            j, off_j = morceau(c.end(), fin=True)
            if i == j:
                textes[i] = textes[i][:off_i] + valeur + textes[i][off_j:]
            else:
                textes[i] = textes[i][:off_i] + valeur
                for k in range(i + 1, j):
                    textes[k] = ''
                textes[j] = textes[j][off_j:]
        for m, t in zip(groupe, textes):
            nouveaux[m.start()] = t

    if not nouveaux:
        return xml

    def remplacer(m):
        if m.start() not in nouveaux:
            return m.group(0)
        # xml:space="preserve" : sinon Word supprime les espaces en bord de morceau
        return f'<w:t xml:space="preserve">{escape(nouveaux[m.start()])}</w:t>'

    return _W_T.sub(remplacer, xml)
