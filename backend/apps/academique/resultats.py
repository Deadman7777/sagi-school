"""Moyennes générales, rangs et suivi pédagogique — un seul calcul.

Le moteur de calcul range dans BulletinCache une ligne par élève × matière ×
période (moyenne, points, rang dans la matière). Tout le reste en découle :
moyenne générale = Σ points / Σ coefficients des matières notées, rang =
1 + nombre d'élèves de la classe ayant une moyenne strictement supérieure.

Le bulletin PDF, le bulletin à l'écran, la fiche pédagogique et l'historique
passent tous par ici : deux calculs séparés finissent toujours par diverger.

Établissement hybride : on ne mélange JAMAIS les deux programmes. Une moyenne
qui additionnerait le français et l'arabe ne correspond à aucun bulletin.

Barèmes : depuis que la note maximale est libre (5, 10, 15, 30, 60…), trois
échelles coexistent — celle de l'évaluation, celle de la matière, celle du
niveau. La règle tient en une phrase : **chaque matière s'affiche sur SON
barème, et seule l'agrégation ramène au barème du niveau.** Concrètement,
`BulletinCache.moyenne` est sur le barème de la matière (une récitation notée
sur 10 s'imprime « 8/10 »), tandis que `BulletinCache.points` est déjà ramené
au barème du niveau — sans quoi Σ points / Σ coef ne vaudrait pas la moyenne
générale imprimée juste en dessous, et le parent ne retrouverait pas son
addition. Toute conversion passe par `ramener()` : c'est le seul endroit.

Deux façons de faire la moyenne générale, au choix de l'école
(`Tenant.calcul_moyenne`) :

  MATIERES — Σ (moyenne de la matière ramenée au niveau × coefficient) / Σ coef.
  POINTS   — Σ points obtenus / Σ points possibles, ramené au barème du
             niveau : le calcul fait à la main (145 sur 150 → 9,67/10). Il
             revient au premier en donnant à chaque matière un poids égal à
             son barème divisé par celui du niveau : c'est ce poids que porte
             `BulletinCache.poids`, pour que Σ points / Σ poids reste LA
             formule de la moyenne générale, quel que soit le mode.
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


def ramener(valeur, depuis, vers):
    """Change une note d'échelle : 8 sur /10 vaut 16 sur /20.

    Renvoie la valeur inchangée si l'une des deux échelles est absente ou
    absurde (≤ 0) : mieux vaut un chiffre non converti qu'une division par
    zéro au milieu d'un bulletin.
    """
    if valeur is None:
        return None
    depuis = float(depuis or 0)
    vers   = float(vers or 0)
    if depuis <= 0 or vers <= 0 or depuis == vers:
        return float(valeur)
    return float(valeur) * vers / depuis


def points_matiere(moyenne, note_max_matiere, note_max_niveau, coefficient):
    """Les points d'une matière, ramenés au barème du niveau.

    La moyenne affichée reste sur le barème de la matière ; les points, eux,
    servent à additionner des matières entre elles. Une récitation sur /10 et
    des maths sur /20 ne s'additionnent qu'une fois mises à la même échelle.
    """
    if moyenne is None:
        return None
    return ramener(moyenne, note_max_matiere, note_max_niveau) * float(coefficient)


def resultat_matiere(evaluations_notes, matiere, note_max_niveau, mode='MATIERES'):
    """(moyenne, points, poids) d'un élève dans une matière ; None s'il n'y a
    aucune note saisie.

    `evaluations_notes` : [(évaluation, note ou None)] pour TOUTES les
    évaluations de la matière sur la période — une évaluation sans note compte
    zéro, comme un absent (règle inchangée).

    - `moyenne` : sur le barème de la MATIÈRE (ce que le bulletin affiche) ;
    - `points`  : au barème du NIVEAU, multipliés par le poids ;
    - `poids`   : None en mode MATIERES (le coefficient fait foi) ; en mode
      POINTS, coefficient × points possibles / barème du niveau.

    Le poids d'un type d'évaluation (composition ×2…) pèse des deux côtés.
    """
    somme_ramenee = somme_poids = 0.0      # mode MATIERES
    obtenus = possibles = 0.0              # mode POINTS
    une_note = False
    for ev, note in evaluations_notes:
        poids_type = float(ev.type_eval.poids)
        bareme_ev = float(ev.note_max or matiere.note_max or 20)
        somme_poids += poids_type
        possibles += bareme_ev * poids_type
        if note is None:
            continue
        une_note = True
        if note.absent or note.valeur is None:
            continue
        # Une interro sur /10 dans une matière sur /20 : 8 vaut 16.
        somme_ramenee += ramener(note.valeur, bareme_ev, matiere.note_max) * poids_type
        obtenus += float(note.valeur) * poids_type
    if not une_note:
        return None

    coef = float(matiere.coefficient)
    if mode == 'POINTS' and possibles > 0 and note_max_niveau:
        moyenne = obtenus / possibles * float(matiere.note_max)
        # ramener(moyenne, matière → niveau) × poids se simplifie en
        # obtenus × coef : les points SONT les points obtenus.
        return moyenne, obtenus * coef, coef * possibles / float(note_max_niveau)

    moyenne = somme_ramenee / somme_poids if somme_poids > 0 else 0.0
    return moyenne, points_matiere(moyenne, matiere.note_max, note_max_niveau, coef), None


def poids_ligne(ligne):
    """Poids d'une ligne de BulletinCache dans la moyenne générale : son poids
    propre (mode POINTS), sinon le coefficient de la matière."""
    if ligne.poids is not None:
        return float(ligne.poids)
    return float(ligne.matiere.coefficient)


def oublier_moyennes(tenant):
    """Efface les moyennes calculées de l'année en cours ; rend leur nombre.

    Appelé quand l'école change sa règle de calcul (mode ou barème) : l'école
    relance « Calculer les moyennes » classe par classe. Les années clôturées
    gardent leurs bulletins, calculés selon la règle de leur temps.
    """
    from apps.paiements.models import Exercice

    exercice = (Exercice.objects.filter(tenant=tenant, cloture=False)
                .order_by('-date_debut').first())
    if exercice is None:
        return 0
    nb, _ = BulletinCache.objects.filter(
        tenant=tenant, annee_scolaire=exercice.annee_scolaire).delete()
    return nb


def note_max_reference(classe, matieres):
    """Le barème sur lequel s'imprime la moyenne GÉNÉRALE d'un bulletin.

    Dans cet ordre :

    1. celui que l'école a fixé pour toutes ses moyennes (`Tenant.bareme_moyenne`,
       « moyenne sur 10 / sur 20 » dans Académique → Paramétrage) ;
    2. celui du niveau de la classe. Mais `Classe.niveau` est nullable — une
       classe peut exister avant que l'école se soit rangée en niveaux ;
    3. toutes les matières partagent le même barème → c'est celui-là, et
       aucune conversion n'a lieu (le cas d'une école entièrement sur /10) ;
    4. sinon 20, faute de mieux.

    Le moteur de calcul et le bulletin appellent cette fonction avec les
    MÊMES arguments (la classe, ses matières du programme demandé). Deux
    déductions séparées divergeaient : une classe sans niveau dont les
    matières sont sur /10 faisait calculer la moyenne sur 20 et l'imprimer
    « /10 ».
    """
    tenant = getattr(classe, 'tenant', None) if classe is not None else None
    if tenant is not None and getattr(tenant, 'bareme_moyenne', None):
        return float(tenant.bareme_moyenne)
    niveau = getattr(classe, 'niveau', None) if classe is not None else None
    if niveau is not None and niveau.note_max:
        return float(niveau.note_max)
    baremes = {float(m.note_max) for m in matieres if m.note_max}
    return baremes.pop() if len(baremes) == 1 else 20.0


def moyenne_generale(lignes):
    """Σ points / Σ poids ; None si aucune matière notée.

    Les points sont déjà au barème du niveau (voir `resultat_matiere`), donc
    cette moyenne l'est aussi : c'est elle qu'on imprime « /20 ». Le poids est
    le coefficient, ou le barème de la matière en calcul « total des points ».
    """
    coef = sum(poids_ligne(l) for l in lignes)
    if coef <= 0:
        return None
    return round(sum(float(l.points or 0) for l in lignes) / coef, 2)


def rang(moyenne, moyennes):
    return 1 + sum(1 for m in moyennes if m > moyenne)


def numero_periode(code):
    chiffres = ''.join(ch for ch in (code or '') if ch.isdigit())
    return int(chiffres) if chiffres else 0


def sur_20(valeur, note_max):
    """Échelle de travail de la fiche pédagogique, dont les seuils sont sur 20."""
    valeur = ramener(valeur, note_max, 20)
    return None if valeur is None else round(valeur, 2)


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
        'total_coef':   round(sum(poids_ligne(l) for l in lignes), 2),
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
