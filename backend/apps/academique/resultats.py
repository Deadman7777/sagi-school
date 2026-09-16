"""Moyennes générales, rangs et suivi pédagogique — un seul calcul.

Le moteur de calcul range dans BulletinCache une ligne par élève × matière ×
période (moyenne, points, rang dans la matière). Tout le reste en découle :
moyenne générale = Σ points / Σ coefficients des matières notées, rang =
1 + nombre d'élèves de la classe ayant une moyenne strictement supérieure.

Le bulletin PDF, le bulletin à l'écran, la fiche pédagogique et l'historique
passent tous par ici : deux calculs séparés finissent toujours par diverger.

Établissement hybride : on ne mélange JAMAIS les deux programmes. Une moyenne
qui additionnerait le français et l'arabe ne correspond à aucun bulletin.
"""
from collections import defaultdict

from .models import BulletinCache

PROGRAMMES = ('FR', 'AR')

# Seuils de la fiche pédagogique, sur 20
SEUIL_FORT = 14.0
SEUIL_FAIBLE = 10.0
BAISSE_NOTABLE = 1.5     # points perdus d'une période à l'autre
ECART_CLASSE = 1.0       # points sous la moyenne de la classe


def programme_valide(valeur):
    """'FR' / 'AR' si fourni et reconnu, sinon None (= toutes les matières)."""
    valeur = (valeur or '').upper()
    return valeur if valeur in PROGRAMMES else None


def lignes_cache(tenant, annee, programme=None, **filtres):
    qs = BulletinCache.objects.filter(tenant=tenant, annee_scolaire=annee, **filtres)
    if programme:
        qs = qs.filter(matiere__programme=programme)
    return qs.select_related('matiere')


def moyenne_generale(lignes):
    """Σ points / Σ coefficients ; None si aucune matière notée."""
    coef = sum(float(l.matiere.coefficient) for l in lignes)
    if coef <= 0:
        return None
    return round(sum(float(l.points or 0) for l in lignes) / coef, 2)


def rang(moyenne, moyennes):
    return 1 + sum(1 for m in moyennes if m > moyenne)


def numero_periode(code):
    chiffres = ''.join(ch for ch in (code or '') if ch.isdigit())
    return int(chiffres) if chiffres else 0


def sur_20(valeur, note_max):
    if valeur is None:
        return None
    note_max = float(note_max or 20)
    return round(float(valeur) * 20 / note_max, 2) if note_max else None


def resultats_classe(tenant, classe, periode, annee, programme=None):
    """{eleve_id: moyenne générale} pour une classe et une période."""
    par_eleve = defaultdict(list)
    for l in lignes_cache(tenant, annee, programme, trimestre=periode, matiere__classe=classe):
        par_eleve[str(l.eleve_id)].append(l)
    resultats = {}
    for eleve_id, lignes in par_eleve.items():
        moy = moyenne_generale(lignes)
        if moy is not None:
            resultats[eleve_id] = moy
    return resultats


def situation_periode(tenant, eleve, periode, annee, programme=None):
    """Ce qu'imprime un bulletin : lignes de l'élève, moyenne, rang, stats de classe.

    None si l'élève n'a aucune note calculée pour cette période (et ce programme).
    """
    lignes = list(lignes_cache(tenant, annee, programme, eleve=eleve, trimestre=periode)
                  .select_related('matiere__classe__niveau').order_by('matiere__ordre', 'matiere__nom'))
    if not lignes:
        return None
    moy = moyenne_generale(lignes) or 0
    classe = lignes[0].matiere.classe
    moyennes = list(resultats_classe(tenant, classe, periode, annee, programme).values())
    return {
        'lignes':       lignes,
        'classe':       classe,
        'moy_generale': moy,
        'total_points': round(sum(float(l.points or 0) for l in lignes), 2),
        'total_coef':   round(sum(float(l.matiere.coefficient) for l in lignes), 1),
        'rang':         rang(moy, moyennes),
        'moy_classe':   round(sum(moyennes) / len(moyennes), 2) if moyennes else 0,
        'moy_max':      max(moyennes) if moyennes else 0,
        'moy_min':      min(moyennes) if moyennes else 0,
        'effectif':     len(moyennes),
    }


def fiche_pedagogique(tenant, eleve, annee, programme=None):
    """Situation pédagogique de l'élève sur l'année : évolution par période,
    matière par matière, et lecture des points forts, faibles et à améliorer.

    Les appréciations portent sur la DERNIÈRE période notée de chaque matière,
    ramenée sur 20 pour comparer une matière sur 10 à une matière sur 20.
    """
    lignes = list(lignes_cache(tenant, annee, programme, eleve=eleve)
                  .select_related('matiere__classe'))
    codes = sorted({l.trimestre for l in lignes}, key=numero_periode)

    periodes = []
    for code in codes:
        s = situation_periode(tenant, eleve, code, annee, programme)
        if s:
            periodes.append({'code': code, 'moyenne': s['moy_generale'], 'rang': s['rang'],
                             'effectif': s['effectif'], 'moy_classe': s['moy_classe']})

    # Moyenne de la classe par matière et par période : une requête
    matiere_ids = {l.matiere_id for l in lignes}
    moy_classe_matiere = defaultdict(list)
    for l in BulletinCache.objects.filter(tenant=tenant, annee_scolaire=annee,
                                          matiere_id__in=matiere_ids, moyenne__isnull=False):
        moy_classe_matiere[(l.matiere_id, l.trimestre)].append(float(l.moyenne))

    par_matiere = defaultdict(dict)
    matieres_obj = {}
    for l in lignes:
        if l.moyenne is None:
            continue
        par_matiere[l.matiere_id][l.trimestre] = float(l.moyenne)
        matieres_obj[l.matiere_id] = l.matiere

    matieres = []
    for mid, notes in par_matiere.items():
        m = matieres_obj[mid]
        ordre = sorted(notes, key=numero_periode)
        derniere_periode = ordre[-1]
        derniere = sur_20(notes[derniere_periode], m.note_max)
        precedente = sur_20(notes[ordre[-2]], m.note_max) if len(ordre) > 1 else None
        evolution = round(derniere - precedente, 2) if precedente is not None else None
        classe_vals = moy_classe_matiere.get((mid, derniere_periode), [])
        moy_classe = sur_20(sum(classe_vals) / len(classe_vals), m.note_max) if classe_vals else None

        if derniere >= SEUIL_FORT:
            statut = 'FORT'
        elif derniere < SEUIL_FAIBLE:
            statut = 'FAIBLE'
        else:
            statut = 'MOYEN'

        # « À améliorer » : pas (encore) faible, mais un signal à surveiller
        raisons = []
        if statut != 'FAIBLE':
            if evolution is not None and evolution <= -BAISSE_NOTABLE:
                raisons.append('BAISSE')
            if statut == 'MOYEN' and moy_classe is not None and derniere < moy_classe - ECART_CLASSE:
                raisons.append('SOUS_CLASSE')

        matieres.append({
            'matiere_id':  str(mid),
            'nom':         m.nom,
            'coefficient': float(m.coefficient),
            'note_max':    float(m.note_max),
            'par_periode': {c: notes.get(c) for c in codes},
            'derniere':    derniere,
            'moy_classe':  moy_classe,
            'evolution':   evolution,
            'statut':      statut,
            'a_ameliorer': raisons,
            'en_progres':  evolution is not None and evolution >= BAISSE_NOTABLE,
            '_ordre':      (m.ordre, m.nom),
        })
    matieres.sort(key=lambda x: x.pop('_ordre'))

    evolution_generale = None
    if len(periodes) > 1:
        evolution_generale = round(periodes[-1]['moyenne'] - periodes[-2]['moyenne'], 2)

    fiche = {
        'programme':          programme or 'FR',
        'annee':              annee,
        'periodes':           periodes,
        'matieres':           matieres,
        'points_forts':       [m['nom'] for m in matieres if m['statut'] == 'FORT'],
        'points_faibles':     [m['nom'] for m in matieres if m['statut'] == 'FAIBLE'],
        'a_ameliorer':        [{'nom': m['nom'], 'raisons': m['a_ameliorer']}
                               for m in matieres if m['a_ameliorer']],
        'en_progres':         [m['nom'] for m in matieres if m['en_progres']],
        'evolution_generale': evolution_generale,
    }
    fiche['recommandations'] = recommandations(fiche)
    return fiche


def recommandations(fiche):
    """Recommandations sous forme de codes : le PDF et l'écran les rédigent
    chacun dans leur langue, mais les décident au même endroit."""
    recs = []
    if fiche['points_faibles']:
        recs.append({'code': 'faibles', 'noms': fiche['points_faibles']})
    baisse = [a['nom'] for a in fiche['a_ameliorer'] if 'BAISSE' in a['raisons']]
    if baisse:
        recs.append({'code': 'baisse', 'noms': baisse})
    sous = [a['nom'] for a in fiche['a_ameliorer'] if 'SOUS_CLASSE' in a['raisons']]
    if sous:
        recs.append({'code': 'sous_classe', 'noms': sous})
    if fiche['points_forts']:
        recs.append({'code': 'forts', 'noms': fiche['points_forts']})
    evo = fiche['evolution_generale']
    if evo is not None and evo >= 1:
        recs.append({'code': 'hausse_gen', 'n': evo})
    elif evo is not None and evo <= -1:
        recs.append({'code': 'baisse_gen', 'n': abs(evo)})
    if not recs:
        recs.append({'code': 'regulier'})
    return recs
