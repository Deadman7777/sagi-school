"""Import d'élèves depuis un fichier Excel (.xlsx).

Le fichier suit le template généré par generer_template() : une ligne
d'en-têtes (l'ordre des colonnes est libre, seuls Nom complet et Section
sont obligatoires), puis une ligne par élève. analyser() ne touche pas à
la base : elle rend un rapport ligne par ligne que le front affiche avant
confirmation — la création effective se fait dans la vue, en transaction.

openpyxl est importé paresseusement : sur une installation Windows
existante où la lib manque, l'API répond un message clair au lieu de
faire tomber tout le module eleves.
"""
import datetime
import io
import unicodedata


MAX_LIGNES = 2000

# clé interne -> en-tête affiché dans le template
COLONNES = {
    'nom_complet':      'Nom complet *',
    'genre':            'Genre (G/F)',
    'date_naissance':   'Date de naissance (JJ/MM/AAAA)',
    'lieu_naissance':   'Lieu de naissance',
    'section':          'Section *',
    'classe':           'Classe',
    'nom_pere':         'Nom du père',
    'telephone_pere':   'Téléphone père',
    'nom_mere':         'Nom de la mère',
    'telephone_mere':   'Téléphone mère',
    'date_inscription': "Date d'inscription (JJ/MM/AAAA)",
    'matricule':        'Matricule (vide = automatique)',
}

# en-têtes acceptés (normalisés) -> clé interne ; tolère les variantes
# courantes des fichiers que les écoles ont déjà
_SYNONYMES = {
    'nom complet':        'nom_complet',
    'nom et prenom':      'nom_complet',
    'prenom et nom':      'nom_complet',
    'nom':                'nom_complet',
    'genre':              'genre',
    'sexe':               'genre',
    'date de naissance':  'date_naissance',
    'date naissance':     'date_naissance',
    'ne le':              'date_naissance',
    'lieu de naissance':  'lieu_naissance',
    'lieu naissance':     'lieu_naissance',
    'section':            'section',
    'niveau':             'section',
    'classe':             'classe',
    'nom du pere':        'nom_pere',
    'pere':               'nom_pere',
    'telephone pere':     'telephone_pere',
    'tel pere':           'telephone_pere',
    'nom de la mere':     'nom_mere',
    'mere':               'nom_mere',
    'telephone mere':     'telephone_mere',
    'tel mere':           'telephone_mere',
    "date d'inscription": 'date_inscription',
    'date inscription':   'date_inscription',
    'matricule':          'matricule',
}

_FORMATS_DATE = ('%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%d/%m/%y')


def _openpyxl():
    try:
        import openpyxl
        return openpyxl
    except ImportError:
        raise ImportError(
            "La bibliothèque openpyxl n'est pas installée sur ce poste. "
            "Exécutez « python -m pip install openpyxl » puis relancez l'application."
        )


def _norm(s):
    """minuscules, sans accents, espaces réduits — pour comparer noms et en-têtes."""
    if s is None:
        return ''
    s = unicodedata.normalize('NFKD', str(s))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return ' '.join(s.lower().split())


def _norm_entete(s):
    """Normalise un en-tête : on coupe la partie entre parenthèses et les astérisques."""
    s = str(s or '').split('(')[0].replace('*', '')
    return _norm(s)


def _texte(val):
    """Cellule -> str propre. Les téléphones/matricules saisis en numérique
    dans Excel arrivent en float (771234567.0) : on retombe sur l'entier."""
    if val is None:
        return ''
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    return str(val).strip()


def _date(val):
    """Cellule -> (date | None, erreur | None). Accepte les vraies dates Excel
    et les chaînes aux formats usuels."""
    if val is None or val == '':
        return None, None
    if isinstance(val, datetime.datetime):
        return val.date(), None
    if isinstance(val, datetime.date):
        return val, None
    txt = str(val).strip()
    for fmt in _FORMATS_DATE:
        try:
            return datetime.datetime.strptime(txt, fmt).date(), None
        except ValueError:
            continue
    return None, f"date illisible « {txt} » (attendu JJ/MM/AAAA)"


def _genre(val):
    """-> ('G'|'F'|'', avertissement | None)"""
    n = _norm(val)
    if not n:
        return '', None
    if n in ('g', 'm', 'h', 'garcon', 'masculin', 'homme'):
        return 'G', None
    if n in ('f', 'fille', 'feminin', 'femme'):
        return 'F', None
    return '', f"genre « {val} » non reconnu (attendu G ou F) — laissé vide"


def generer_template(tenant):
    """Construit le classeur template et le rend en bytes (BytesIO)."""
    openpyxl = _openpyxl()
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    from .models import Section

    wb = openpyxl.Workbook()

    # ── Feuille de saisie ────────────────────────────────────────────────
    ws = wb.active
    ws.title = 'Élèves'
    entetes = list(COLONNES.values())
    ws.append(entetes)
    fill = PatternFill('solid', fgColor='00B894')
    for col, _ in enumerate(entetes, start=1):
        c = ws.cell(row=1, column=col)
        c.font = Font(bold=True, color='FFFFFF')
        c.fill = fill
        c.alignment = Alignment(vertical='center')
        ws.column_dimensions[get_column_letter(col)].width = max(len(entetes[col - 1]) + 2, 16)
    ws.freeze_panes = 'A2'

    # ── Feuille consignes ────────────────────────────────────────────────
    sections = list(Section.objects.filter(tenant=tenant).values_list('nom', flat=True))
    aide = wb.create_sheet('Consignes')
    aide.column_dimensions['A'].width = 46
    aide.column_dimensions['B'].width = 64
    lignes = [
        ('Consignes de remplissage', ''),
        ('', ''),
        ('Nom complet *', 'Obligatoire. Ex. : Moussa Ndiaye'),
        ('Genre (G/F)', 'G ou F (Garçon / Fille). Optionnel.'),
        ('Date de naissance', 'JJ/MM/AAAA ou format date Excel. Optionnel.'),
        ('Section *', 'Obligatoire. Doit exister dans SAGI SCHOOL (liste ci-dessous).'),
        ('Classe', "Optionnel. Nom exact de la classe (ex. CI A) si l'école en utilise."),
        ('Téléphones', 'Chiffres uniquement, ex. 771234567. Optionnel.'),
        ("Date d'inscription", "Optionnel. Vide = début de l'année scolaire (aucun prorata)."),
        ('Matricule', 'Laissez VIDE pour une génération automatique (recommandé).'),
        ('', ''),
        ('Sections existantes dans votre école :', ', '.join(sections) or
         "(aucune — créez d'abord vos sections dans SAGI SCHOOL)"),
        ('', ''),
        ('Limite', f'{MAX_LIGNES} élèves par fichier maximum.'),
    ]
    for a, b in lignes:
        aide.append([a, b])
    aide['A1'].font = Font(bold=True, size=13)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def analyser(fichier, tenant, exercice):
    """Lit le .xlsx et rend le rapport {'resume': {...}, 'lignes': [...]}.

    Chaque ligne : {ligne, nom_complet, section, statut OK|DOUBLON|ERREUR,
    erreurs[], avertissements[], data{...}} — data contient les valeurs
    nettoyées prêtes pour Eleve.objects.create().
    Lève ValueError (fichier illisible / en-têtes absents / trop de lignes).
    """
    openpyxl = _openpyxl()
    from .models import Eleve, Section
    from apps.academique.models import Classe

    try:
        wb = openpyxl.load_workbook(fichier, read_only=True, data_only=True)
    except Exception:
        raise ValueError("Fichier illisible — envoyez un .xlsx (Excel 2007+), pas un .xls ni un CSV.")

    ws = wb['Élèves'] if 'Élèves' in wb.sheetnames else wb.active
    rows = ws.iter_rows(values_only=True)

    # 1re ligne non vide = en-têtes
    entetes = None
    for row in rows:
        if any(v not in (None, '') for v in row):
            entetes = row
            break
    if entetes is None:
        raise ValueError('Fichier vide.')

    colmap = {}   # index -> clé interne
    for i, h in enumerate(entetes):
        cle = _SYNONYMES.get(_norm_entete(h))
        if cle and cle not in colmap.values():
            colmap[i] = cle
    if 'nom_complet' not in colmap.values() or 'section' not in colmap.values():
        raise ValueError(
            'En-têtes non reconnus — il faut au minimum les colonnes '
            '« Nom complet » et « Section ». Téléchargez le template fourni.'
        )

    sections = {_norm(s.nom): s for s in Section.objects.filter(tenant=tenant)}
    classes  = {_norm(c.nom): c for c in Classe.objects.filter(tenant=tenant)}
    deja_la  = set(
        (_norm(n), d) for n, d in
        Eleve.objects.filter(tenant=tenant, exercice=exercice)
                     .values_list('nom_complet', 'date_naissance')
    )
    matricules_pris = set(
        m for m in Eleve.objects.filter(tenant=tenant).values_list('matricule', flat=True) if m
    )

    lignes, vus_fichier = [], set()
    no_ligne = 1  # la ligne d'en-têtes ; les données commencent après
    for row in rows:
        no_ligne += 1
        if not any(v not in (None, '') for v in row):
            continue
        if len(lignes) >= MAX_LIGNES:
            raise ValueError(f'Fichier trop volumineux : maximum {MAX_LIGNES} élèves par import.')

        brut = {cle: row[i] if i < len(row) else None for i, cle in colmap.items()}
        erreurs, avert = [], []

        nom = _texte(brut.get('nom_complet'))
        if not nom:
            erreurs.append('Nom complet manquant')

        genre, warn = _genre(brut.get('genre'))
        if warn:
            avert.append(warn)

        date_naiss, err = _date(brut.get('date_naissance'))
        if err:
            erreurs.append(f'Date de naissance : {err}')

        date_insc, err = _date(brut.get('date_inscription'))
        if err:
            erreurs.append(f"Date d'inscription : {err}")
        if date_insc is None:
            # vide = présent depuis le début de l'année -> pas de prorata
            date_insc = exercice.date_debut

        nom_section = _texte(brut.get('section'))
        section = sections.get(_norm(nom_section))
        if not nom_section:
            erreurs.append('Section manquante')
        elif not section:
            erreurs.append(
                f'Section « {nom_section} » introuvable — créez-la dans '
                'Paramètres > Sections puis relancez l\'import'
            )

        nom_classe = _texte(brut.get('classe'))
        classe = classes.get(_norm(nom_classe)) if nom_classe else None
        if nom_classe and not classe:
            avert.append(f'Classe « {nom_classe} » inconnue — élève importé sans classe')

        matricule = _texte(brut.get('matricule'))
        if matricule:
            if matricule in matricules_pris:
                erreurs.append(f'Matricule « {matricule} » déjà utilisé')
            else:
                matricules_pris.add(matricule)

        statut = 'ERREUR' if erreurs else 'OK'
        cle_doublon = (_norm(nom), date_naiss)
        if statut == 'OK':
            if cle_doublon in deja_la:
                statut = 'DOUBLON'
                avert.append('Déjà inscrit cette année (même nom et date de naissance) — ignoré')
            elif cle_doublon in vus_fichier:
                statut = 'DOUBLON'
                avert.append('Présent en double dans le fichier — ignoré')
            else:
                vus_fichier.add(cle_doublon)

        lignes.append({
            'ligne':          no_ligne,
            'nom_complet':    nom,
            'section':        section.nom if section else nom_section,
            'statut':         statut,
            'erreurs':        erreurs,
            'avertissements': avert,
            'data': {
                'nom_complet':      nom,
                'genre':            genre,
                'date_naissance':   date_naiss,   # DRF sérialise les dates en ISO dans le rapport
                'lieu_naissance':   _texte(brut.get('lieu_naissance')),
                'section_id':       section.id if section else None,
                'classe_id':        classe.id if classe else None,
                'nom_pere':         _texte(brut.get('nom_pere')),
                'telephone_pere':   _texte(brut.get('telephone_pere')),
                'nom_mere':         _texte(brut.get('nom_mere')),
                'telephone_mere':   _texte(brut.get('telephone_mere')),
                'date_inscription': date_insc,
                'matricule':        matricule or None,
            },
        })

    resume = {
        'total':    len(lignes),
        'ok':       sum(1 for l in lignes if l['statut'] == 'OK'),
        'doublons': sum(1 for l in lignes if l['statut'] == 'DOUBLON'),
        'erreurs':  sum(1 for l in lignes if l['statut'] == 'ERREUR'),
    }
    return {'resume': resume, 'lignes': lignes}
