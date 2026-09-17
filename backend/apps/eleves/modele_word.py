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

**Sans codes, les blancs du modèle.** Une école dépose le plus souvent son
certificat tel qu'elle l'imprime : « Nom et prénom : ................ »,
« Né(e) le ........ à ........ », « Fait à ........, le ........ ». Lui demander
d'y placer des codes, c'est lui demander de retoucher son document à chaque
version. Chaque suite de points, de soulignés ou de points de suspension est
donc un blanc, et le libellé qui le précède dans le paragraphe dit ce qu'il
attend. Un blanc dont le libellé n'est pas reconnu, ou dont la valeur manque
sur la fiche, reste tel quel : il se remplit à la main, comme avant.
"""
import unicodedata
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


# Un blanc : au moins QUATRE points, soulignés ou points de suspension, espaces
# isolés tolérés (« . . . . »). Trois points sont une ponctuation ordinaire.
_BLANC = re.compile(r'(?:[._\u2026][ \u00a0]?){4,}')

# Libellé → code, du plus précis au plus général. À égalité de position, la
# première règle gagne.
_REGLES = [
    (r"date de naissance", 'DATE_NAISSANCE'),
    (r"\bnee?s? ?(\(e\))? ?le\b", 'DATE_NAISSANCE'),
    (r"lieu de naissance", 'LIEU_NAISSANCE'),
    (r"date d'inscription|inscrite? le\b", 'DATE_INSCRIPTION'),
    (r"date d'entree|depuis le\b", 'DATE_ENTREE'),
    (r"nom et prenoms?|prenoms? et noms?|nom complet|prenoms? nom", 'NOM_COMPLET'),
    (r"\b(l'eleve|eleve|l'enfant|enfant|certifie que|atteste que)\b", 'NOM_COMPLET'),
    (r"matricule", 'MATRICULE'),
    (r"annee scolaire", 'ANNEE_SCOLAIRE'),
    (r"\bclasse\b|\bniveau\b", 'CLASSE'),
    (r"\b(fils|fille|enfant) de\b|\bpere\b", 'NOM_PERE'),
    (r"\bmere\b", 'NOM_MERE'),
    (r"tuteur", 'NOM_TUTEUR'),
    (r"\bsexe\b|\bgenre\b", 'SEXE'),
    (r"fait a\b", 'VILLE'),
    (r"\bnom\b", 'NOM_COMPLET'),
]
_REGLES = [(re.compile(motif), code) for motif, code in _REGLES]

# Ce que la brève liaison entre deux blancs veut dire, selon le blanc précédent :
# « né le ..... à ..... », « fils de ..... et de ..... », « Fait à ....., le ..... ».
_SUITES = {
    ('DATE_NAISSANCE', 'a'): 'LIEU_NAISSANCE',
    ('NOM_PERE', 'et de'): 'NOM_MERE',
    ('VILLE', 'le'): 'DATE_DU_JOUR',
}

LIBELLES_CHAMPS = {
    'NOM_COMPLET': "Prénom et nom", 'MATRICULE': 'Matricule', 'DATE_NAISSANCE': 'Date de naissance',
    'LIEU_NAISSANCE': 'Lieu de naissance', 'CLASSE': 'Classe', 'ANNEE_SCOLAIRE': 'Année scolaire',
    'NOM_PERE': 'Père', 'NOM_MERE': 'Mère', 'NOM_TUTEUR': 'Tuteur', 'SEXE': 'Sexe',
    'DATE_INSCRIPTION': "Date d'inscription", 'DATE_ENTREE': "Date d'entrée",
    'VILLE': 'Lieu de délivrance', 'DATE_DU_JOUR': 'Date de délivrance',
}


def _normaliser(texte):
    sans_accents = unicodedata.normalize('NFKD', texte)
    sans_accents = ''.join(c for c in sans_accents if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', sans_accents.replace('\u2019', "'").lower())


def _champ_du_blanc(avant, precedent):
    """Le code attendu par un blanc, d'après le texte qui le précède."""
    liaison = re.sub(r'[\s:,;()\-]+', ' ', _normaliser(avant)).strip()
    if precedent and (precedent, liaison) in _SUITES:
        return _SUITES[(precedent, liaison)]
    if liaison in ('le', 'en date du') and precedent is None:
        return 'DATE_DU_JOUR'
    proche = _normaliser(avant)[-60:]
    meilleur, fin_max = None, -1
    for motif, code in _REGLES:
        for m in motif.finditer(proche):
            if m.end() > fin_max:
                meilleur, fin_max = code, m.end()
    return meilleur


def _blancs(complet, occupes=()):
    """[(début, fin, code|None)] des blancs d'un paragraphe, hors zones de codes."""
    trouves, precedent, fin_prec = [], None, 0
    for m in _BLANC.finditer(complet):
        debut, fin = m.start(), m.end()
        while fin > debut and complet[fin - 1] in ' \u00a0':
            fin -= 1
        if any(a < fin and debut < b for a, b in occupes):
            continue
        code = _champ_du_blanc(complet[fin_prec:debut], precedent)
        trouves.append((debut, fin, code))
        precedent, fin_prec = code, fin
    return trouves


def champs_reconnus(contenu):
    """Ce que l'app remplira dans ce modèle : codes {…} et blancs reconnus.

    [{'code', 'libelle', 'source': 'code'|'blanc'}], sans doublon, dans l'ordre.
    """
    vus, champs = set(), []
    with zipfile.ZipFile(io.BytesIO(contenu)) as z:
        for nom in z.namelist():
            if not _PARTIES.match(nom):
                continue
            for groupe in _groupes(z.read(nom).decode('utf-8')):
                texte = ''.join(unescape(m.group(2), _ENTITES) for m in groupe)
                codes = [(c.start(), c.end(), c.group(1).upper(), 'code') for c in _CODE.finditer(texte)]
                blancs = [(a, b, code, 'blanc') for a, b, code in
                          _blancs(texte, [(a, b) for a, b, _, _ in codes]) if code]
                for _, _, code, source in sorted(codes + blancs):
                    if code not in vus:
                        vus.add(code)
                        champs.append({'code': code, 'source': source,
                                       'libelle': LIBELLES_CHAMPS.get(code, code)})
    return champs


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
        tous_codes = list(_CODE.finditer(complet))
        # (début, fin, valeur) : les codes connus, puis les blancs reconnus
        # dont la fiche a la valeur. Un blanc sans valeur reste à remplir à la main.
        remplacements = [(c.start(), c.end(), str(valeurs[c.group(1).upper()] or ''))
                         for c in tous_codes if c.group(1).upper() in valeurs]
        for debut, fin, code in _blancs(complet, [(c.start(), c.end()) for c in tous_codes]):
            if code and str(valeurs.get(code) or '').strip():
                remplacements.append((debut, fin, str(valeurs[code])))
        if not remplacements:
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

        # De droite à gauche : une modification ne décale jamais les zones
        # restant à traiter, situées avant elle.
        for debut, fin, valeur in sorted(remplacements, reverse=True):
            i, off_i = morceau(debut)
            j, off_j = morceau(fin, fin=True)
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
