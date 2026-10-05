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
from types import SimpleNamespace

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
    return qs.select_related('matiere', 'matiere__domaine')


# ── Classement et paliers d'appréciation ────────────────────────────────────
# L'échelle historique, écrite en dur jusqu'en octobre 2026 à trois endroits
# (moteur, bulletin, analyse). Elle reste la règle d'une école qui n'a saisi
# aucun palier. Seuils sur 20, inclus.
PALIERS_DEFAUT = (
    {'libelle': 'Excellent',        'seuil': 18, 'couleur': '#1b5e20', 'badge': '', 'distinction': True},
    {'libelle': 'Très Bien',        'seuil': 16, 'couleur': '#2e7d32', 'badge': '', 'distinction': True},
    {'libelle': 'Bien',             'seuil': 14, 'couleur': '#1565c0', 'badge': '', 'distinction': False},
    {'libelle': 'Assez Bien',       'seuil': 12, 'couleur': '#00838f', 'badge': '', 'distinction': False},
    {'libelle': 'Passable',         'seuil': 10, 'couleur': '#ef6c00', 'badge': '', 'distinction': False},
    {'libelle': 'Insuffisant',      'seuil': 8,  'couleur': '#c62828', 'badge': '', 'distinction': False},
    {'libelle': 'Très Insuffisant', 'seuil': 0,  'couleur': '#b71c1c', 'badge': '', 'distinction': False},
)


def paliers_ecole(tenant):
    """Les paliers de l'école, du plus haut au plus bas ; l'échelle historique
    si elle n'en a saisi aucun. Une requête : à appeler une fois par écran ou
    par bulletin, puis passer la liste à `apprecier`."""
    from .models import PalierMention
    paliers = [{'libelle': p.libelle, 'seuil': float(p.seuil), 'couleur': p.couleur,
                'badge': p.badge, 'distinction': p.distinction}
               for p in PalierMention.objects.filter(tenant=tenant).order_by('-seuil')]
    return paliers or [dict(p) for p in PALIERS_DEFAUT]


def apprecier(moyenne, note_max, paliers):
    """Le palier atteint par une moyenne (dict libellé/couleur/badge/…), ou
    None sans moyenne. La moyenne est d'abord ramenée sur 20 : 8/10 = 16/20.
    Sous le plus bas des seuils, le plus bas des paliers."""
    if moyenne is None or not paliers:
        return None
    sur20 = ramener(moyenne, note_max or 20, 20)
    for p in paliers:
        if sur20 + 1e-9 >= float(p['seuil']):
            return p
    return paliers[-1]


def libelle_appreciation(moyenne, note_max, paliers):
    p = apprecier(moyenne, note_max, paliers)
    return p['libelle'] if p else ''


def mode_classement(tenant):
    return getattr(tenant, 'mode_classement', 'CLASSIQUE') or 'CLASSIQUE'


def avec_rangs(tenant):
    """Les rangs (général et par matière) ne sortent que si l'école classe.
    Ils restent calculés : changer de mode ne demande aucun recalcul."""
    return mode_classement(tenant) == 'CLASSIQUE'


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


def arrondir(valeur, mode='ARRONDI'):
    """Une moyenne à deux décimales, selon la règle de l'école
    (`Tenant.arrondi_moyenne`) : arrondie (9,666… → 9,67) ou tronquée
    (9,666… → 9,66, comme à la main). Toute moyenne imprimée ou comparée passe
    par ici : un rang calculé sur 9,67 et un bulletin qui affiche 9,66
    finiraient par se contredire.

    Tronquer un flottant est piégeux : 7 peut valoir 6,9999999999 en mémoire
    et deviendrait 6,99. D'où la tolérance d'un milliardième.
    """
    if valeur is None:
        return None
    if mode == 'TRONQUE':
        from decimal import ROUND_DOWN, Decimal
        signe = -1 if valeur < 0 else 1
        brut = Decimal(repr(abs(float(valeur)) + 1e-9))
        return signe * float(brut.quantize(Decimal('0.01'), rounding=ROUND_DOWN))
    return round(float(valeur), 2)


def mode_arrondi(tenant):
    return getattr(tenant, 'arrondi_moyenne', 'ARRONDI') or 'ARRONDI'


def poids_ligne(ligne):
    """Poids d'une ligne de BulletinCache dans la moyenne générale : son poids
    propre (mode POINTS), sinon le coefficient de la matière."""
    if ligne.poids is not None:
        return float(ligne.poids)
    return float(ligne.matiere.coefficient)


def compte(ligne):
    """La ligne entre-t-elle dans la moyenne générale ? Une matière marquée
    « hors moyenne » s'imprime avec sa note, mais ne pèse pas."""
    return getattr(ligne.matiere, 'compte_dans_moyenne', True) is not False


def lignes_comptees(lignes):
    return [l for l in lignes if compte(l)]


def ligne_calcul(points, poids, matiere):
    """Une ligne au format de BulletinCache, pour le moteur de calcul qui
    n'a pas encore écrit ses lignes en base : la moyenne générale passe par la
    MÊME fonction, qu'elle vienne du moteur ou du cache."""
    return SimpleNamespace(points=points, poids=poids, matiere=matiere)


def moyennes_domaines(lignes):
    """[(domaine ou None, Σ points, Σ poids)] des lignes comptées, dans l'ordre
    des domaines. Une matière sans domaine forme son propre groupe."""
    groupes = {}
    for l in lignes_comptees(lignes):
        dom = getattr(l.matiere, 'domaine', None) if getattr(l.matiere, 'domaine_id', None) else None
        cle = ('D', dom.id) if dom is not None else ('M', l.matiere.id)
        g = groupes.setdefault(cle, [dom, 0.0, 0.0])
        g[1] += float(l.points or 0)
        g[2] += poids_ligne(l)
    return list(groupes.values())


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


def moyenne_generale(lignes, arrondi='ARRONDI', domaines=False):
    """Σ points / Σ poids ; None si aucune matière notée.

    Les points sont déjà au barème du niveau (voir `resultat_matiere`), donc
    cette moyenne l'est aussi : c'est elle qu'on imprime « /20 ». Le poids est
    le coefficient, ou le barème de la matière en calcul « total des points ».

    Les matières « hors moyenne » ne pèsent pas. `domaines=True` (réglage
    `Tenant.agregation_domaines`) : moyenne des domaines pondérée par leur
    coefficient ; un domaine sans coefficient pèse la somme de ceux de ses
    matières — auquel cas le résultat est identique au calcul simple.
    """
    lignes = lignes_comptees(lignes)
    if domaines:
        num = den = 0.0
        for dom, pts, poids in moyennes_domaines(lignes):
            if poids <= 0:
                continue
            coef_dom = (float(dom.coefficient) if dom is not None and dom.coefficient is not None
                        else poids)
            num += pts / poids * coef_dom
            den += coef_dom
        return arrondir(num / den, arrondi) if den > 0 else None
    coef = sum(poids_ligne(l) for l in lignes)
    if coef <= 0:
        return None
    return arrondir(sum(float(l.points or 0) for l in lignes) / coef, arrondi)


def moyenne_eleve(lignes, tenant):
    """La moyenne générale selon les réglages de l'école — à utiliser partout."""
    return moyenne_generale(lignes, mode_arrondi(tenant),
                            bool(getattr(tenant, 'agregation_domaines', False)))


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
        moy = moyenne_eleve(lignes, tenant)
        if moy is not None:
            resultats[eleve_id] = moy
    return resultats


def situation_periode(tenant, eleve, periode, annee, programme=None):
    """Ce qu'imprime un bulletin : lignes de l'élève, moyenne, rang, stats de classe.

    None si l'élève n'a aucune note calculée pour cette période (et ce programme).
    """
    lignes = list(lignes_cache(tenant, annee, programme, eleve=eleve, trimestre=periode)
                  .select_related('matiere__classe__niveau')
                  .order_by('matiere__domaine__ordre', 'matiere__domaine__nom',
                            'matiere__ordre', 'matiere__nom'))
    if not lignes:
        return None
    moy = moyenne_eleve(lignes, tenant) or 0
    classe = lignes[0].matiere.classe
    moyennes = list(resultats_classe(tenant, classe, periode, annee, programme).values())
    comptees = lignes_comptees(lignes)
    return {
        'lignes':       lignes,
        'classe':       classe,
        'moy_generale': moy,
        'total_points': round(sum(float(l.points or 0) for l in comptees), 2),
        'total_coef':   round(sum(poids_ligne(l) for l in comptees), 2),
        # Calculé toujours, montré seulement si l'école classe (avec_rangs).
        'rang':         rang(moy, moyennes) if avec_rangs(tenant) else None,
        'moy_classe':   arrondir(sum(moyennes) / len(moyennes), mode_arrondi(tenant)) if moyennes else 0,
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
                  .select_related('matiere__classe__niveau', 'matiere__classe__tenant'))
    codes = sorted({l.trimestre for l in lignes}, key=numero_periode)
    # Les seuils (FORT, FAIBLE) raisonnent sur 20 ; l'école, elle, lit ses
    # moyennes sur SON barème — 8/10 s'affiche 8, pas 16.
    bareme = note_max_reference(lignes[0].matiere.classe if lignes else None,
                                [l.matiere for l in lignes])

    def afficher(valeur_sur_20):
        return None if valeur_sur_20 is None else round(ramener(valeur_sur_20, 20, bareme), 2)

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
            'derniere':    afficher(derniere),
            'moy_classe':  afficher(moy_classe),
            'evolution':   afficher(evolution),
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
        # Barème sur lequel l'écran et le PDF affichent ces valeurs.
        'bareme':             bareme,
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
