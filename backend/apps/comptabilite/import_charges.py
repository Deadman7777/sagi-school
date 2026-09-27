"""Import Excel des charges (dépenses) — migration/saisie en masse.

Même esprit que l'import des élèves : on télécharge un modèle, on téléverse le
fichier rempli, on obtient un aperçu ligne par ligne (statut OK / ERREUR, compte
suggéré par nature), puis on confirme pour générer les écritures SYSCOHADA.

Chaque ligne OK → 2 écritures équilibrées : `6xx D (charge) / trésorerie C`
(571 caisse par défaut). Source 'CHARGE' pour apparaître dans la liste des
charges. openpyxl est importé paresseusement (poste Windows sans la lib).
"""
import re
import datetime
from decimal import Decimal, InvalidOperation

# Le compte suggéré d'après le libellé vient de suggestion_compte : la même
# table que le formulaire « Nouvelle charge ».
from .suggestion_compte import COMPTE_DEFAUT as DEFAUT_CHARGE  # noqa: E402
COMPTES_TRESORERIE = {'571', '5715', '521', '5521', '5522', '5523'}

COLONNES = ['Date', 'Libellé', 'Compte (optionnel)', 'Montant', 'Réglé via (571 défaut)']


def _openpyxl():
    try:
        import openpyxl
        return openpyxl
    except ImportError:
        raise ImportError(
            "La bibliothèque openpyxl n'est pas installée sur ce poste. "
            "Exécutez « python -m pip install openpyxl » puis relancez l'application.")


def _norm(s):
    import unicodedata
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode()
    return s.upper().strip()


def suggerer_compte(libelle):
    from .suggestion_compte import suggerer
    return suggerer(libelle)['compte']


def _date(val):
    if isinstance(val, (datetime.datetime, datetime.date)):
        return val.date() if isinstance(val, datetime.datetime) else val
    s = str(val or '').strip()
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%d/%m/%y'):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _montant(val):
    if val in (None, ''):
        return None
    try:
        return Decimal(str(val).replace(' ', '').replace(' ', '').replace(',', '.'))
    except (InvalidOperation, ValueError):
        return None


def generer_template(tenant):
    openpyxl = _openpyxl()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Charges'
    ws.append(COLONNES)
    # Exemples indicatifs
    ws.append(['15/01/2026', 'Loyer janvier',        '',    150000, '571'])
    ws.append(['20/01/2026', 'Facture SENELEC',       '6052', 45000, '571'])
    ws.append(['25/01/2026', 'Salaire oustaz Modou',  '',    120000, '571'])
    from io import BytesIO
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def analyser(fichier, tenant, exercice):
    """Rend {'resume': {...}, 'lignes': [...]}. Chaque ligne :
    {ligne, date, libelle, no_compte, compte_suggere(bool), montant,
     compte_tresorerie, statut OK|ERREUR, erreurs[]}."""
    openpyxl = _openpyxl()
    try:
        wb = openpyxl.load_workbook(fichier, read_only=True, data_only=True)
    except Exception:
        raise ValueError("Fichier illisible — envoyez un .xlsx (Excel 2007+), pas un .xls ni un CSV.")
    ws = wb['Charges'] if 'Charges' in wb.sheetnames else wb.active

    lignes, total = [], Decimal(0)
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) > 5000:
        raise ValueError("Fichier trop volumineux (plus de 5000 lignes).")

    def _txt(row, i):
        v = row[i] if len(row) > i else None
        return '' if v is None else str(v).strip()

    for i, row in enumerate(rows[1:], start=2):  # saute l'en-tête
        if row is None or all(c in (None, '') for c in row):
            continue
        date_v = _date(row[0] if len(row) > 0 else None)
        libelle = _txt(row, 1)
        compte_saisi = _txt(row, 2)
        montant = _montant(row[3] if len(row) > 3 else None)
        tresor = _txt(row, 4) or '571'

        erreurs = []
        if not libelle:
            erreurs.append('Libellé manquant')
        if montant is None or montant <= 0:
            erreurs.append('Montant invalide')
        if date_v is None:
            erreurs.append('Date invalide (jj/mm/aaaa)')
        if tresor not in COMPTES_TRESORERIE:
            tresor = '571'
        compte = compte_saisi or suggerer_compte(libelle)
        if not compte.startswith('6'):
            erreurs.append(f'Compte {compte} : une charge doit être en classe 6')

        lignes.append({
            'ligne': i,
            'date': date_v.isoformat() if date_v else '',
            'libelle': libelle,
            'no_compte': compte,
            'compte_suggere': not compte_saisi and not erreurs,
            'montant': float(montant) if montant else 0,
            'compte_tresorerie': tresor,
            'statut': 'OK' if not erreurs else 'ERREUR',
            'erreurs': erreurs,
        })
        if not erreurs:
            total += montant

    ok = sum(1 for l in lignes if l['statut'] == 'OK')
    return {
        'resume': {
            'total_lignes': len(lignes),
            'ok': ok,
            'erreurs': len(lignes) - ok,
            'montant_total': float(total),
            'exercice': exercice.annee_scolaire,
        },
        'lignes': lignes,
    }
