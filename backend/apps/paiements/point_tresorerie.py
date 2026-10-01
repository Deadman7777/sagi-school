"""Point de trésorerie — jour par jour, par mode et par responsable.

Une école qui confie la caisse à plusieurs chargés de scolarité fait chaque
soir le point de chacun : combien d'opérations, combien est entré et sorti,
en espèces, Wave, Orange Money…, et ce que la trésorerie doit contenir.

Tout se lit dans le JOURNAL, sur les comptes de trésorerie (571x, 5521-5523,
521x) : les mêmes lignes que les soldes par canal du tableau de bord, donc les
mêmes soldes. Les encaissements élèves, les charges, la paie, les avances, les
prêts… y passent tous ; rien n'est recompté à côté.

Classement d'une ligne de trésorerie :
  · entrée     — débit d'un compte de trésorerie ;
  · sortie     — crédit d'un compte de trésorerie ;
  · annulation — contre-écriture d'une opération (`ANNUL_*`, ou charge dont
    `source_id` désigne la ligne annulée). Elle a sa propre colonne, signée :
    les entrées et les sorties restent ce qui a réellement été saisi, jamais
    un nombre négatif ;
  · transfert  — mouvement interne entre deux comptes de trésorerie : il
    change la répartition par mode, jamais le total, et n'est compté ni en
    entrée ni en sortie.

Annulée LE JOUR MÊME, une opération est une erreur de saisie : l'argent n'a
jamais bougé. L'opération et son annulation sortent alors toutes deux des
totaux (elles restent visibles dans le détail de la journée). Annulée un
autre jour, c'est une correction : elle apparaît ce jour-là en annulation.
La règle est fixée par jour, si bien que les journées s'additionnent toujours
exactement en mois et en exercice.

Le responsable d'une opération est l'auteur de l'écriture
(JournalEntry.saisi_par, posé à l'enregistrement — voir core/auteur.py).
"""
import datetime
from collections import defaultdict

from django.utils import timezone

from apps.comptabilite.models import JournalEntry

MODES = [
    ('ESPECE',       'Espèces'),
    ('WAVE',         'Wave'),
    ('ORANGE_MONEY', 'Orange Money'),
    ('FREE_MONEY',   'Free Money'),
    ('BANQUE',       'Banque'),
]
LIBELLE_MODE = dict(MODES)
SOURCES_TRANSFERT = ('TRANSFERT', 'ANNUL_TRANSFERT')
SOURCES_CHARGE = ('CHARGE', 'BUDGET')
NON_RENSEIGNE = 'Non renseigné'

NOMS_MOIS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet',
             'août', 'septembre', 'octobre', 'novembre', 'décembre']


def mode_du_compte(no_compte):
    if no_compte.startswith('571'):
        return 'ESPECE'
    if no_compte.startswith('521'):
        return 'BANQUE'
    return {'5521': 'WAVE', '5522': 'ORANGE_MONEY', '5523': 'FREE_MONEY'}.get(no_compte)


def soldes_initiaux(exercice):
    """Comme le tableau de bord : le solde initial « mobile » est porté par Wave."""
    return {
        'ESPECE': float(exercice.solde_initial_caisse),
        'WAVE':   float(exercice.solde_initial_mobile),
        'BANQUE': float(exercice.solde_initial_banque),
    }


def _nom(prenom, nom):
    return f"{prenom or ''} {nom or ''}".strip() or NON_RENSEIGNE


def _classer(r):
    """(nature, clé de l'opération) d'une ligne du journal.

    La clé relie une opération à son annulation : une extourne `ANNUL_X`
    porte le source_id de l'opération X ; la contre-écriture d'une charge
    porte en source_id l'id de la LIGNE qu'elle annule.
    """
    source, sid = r['source'] or '', r['source_id']
    if source in SOURCES_TRANSFERT:
        return 'TRANSFERT', None
    if source.startswith('ANNUL_'):
        return 'ANNULATION', (source[len('ANNUL_'):], sid) if sid else None
    if source in SOURCES_CHARGE:
        if sid:
            return 'ANNULATION', ('LIGNE', sid)
        return 'OPERATION', ('LIGNE', r['id'])
    return 'OPERATION', (source, sid) if sid else None


def _lignes(tenant, exercice):
    """Les lignes de trésorerie de l'exercice, classées."""
    from apps.dashboard.views import _filtre_tresorerie
    qs = (JournalEntry.objects
          .filter(_filtre_tresorerie(), tenant=tenant, exercice=exercice)
          .values('id', 'date_ecriture', 'no_piece', 'no_compte', 'libelle', 'debit',
                  'credit', 'source', 'source_id', 'created_at', 'saisi_par_id',
                  'saisi_par__prenom', 'saisi_par__nom')
          .order_by('date_ecriture', 'created_at', 'no_piece'))
    sortie = []
    for r in qs:
        mode = mode_du_compte(r['no_compte'])
        if mode is None:
            continue
        nature, cle = _classer(r)
        sortie.append({
            'date':   r['date_ecriture'],
            'piece':  r['no_piece'],
            'libelle': r['libelle'],
            'mode':   mode,
            'debit':  float(r['debit'] or 0),
            'credit': float(r['credit'] or 0),
            'nature': nature,
            'cle':    cle,
            'annulee_jour': False,
            'heure':  r['created_at'],
            'resp_id': str(r['saisi_par_id']) if r['saisi_par_id'] else '',
            'resp':   (_nom(r['saisi_par__prenom'], r['saisi_par__nom'])
                       if r['saisi_par_id'] else NON_RENSEIGNE),
        })
    _marquer_annulations_du_jour(sortie)
    return sortie


def _marquer_annulations_du_jour(lignes):
    """Une opération et son annulation passées le MÊME jour, qui se compensent
    exactement mode par mode, sont une erreur de saisie : on les marque pour
    les tenir hors des totaux."""
    groupes = defaultdict(list)
    for l in lignes:
        if l['cle'] is not None and l['nature'] in ('OPERATION', 'ANNULATION'):
            groupes[(l['date'], l['cle'])].append(l)
    for groupe in groupes.values():
        natures = {l['nature'] for l in groupe}
        if natures != {'OPERATION', 'ANNULATION'}:
            continue
        net = defaultdict(float)
        for l in groupe:
            net[l['mode']] += l['debit'] - l['credit']
        if all(abs(v) < 0.005 for v in net.values()):
            for l in groupe:
                l['annulee_jour'] = True


class _Cumul:
    """Entrées, sorties, annulations et nombre d'opérations d'un ensemble de lignes."""

    def __init__(self):
        self.entrees = defaultdict(float)
        self.sorties = defaultdict(float)
        self.annulations = defaultdict(float)
        self.pieces = set()
        self.pieces_annulation = set()

    def ajouter(self, l):
        m = l['mode']
        if l['nature'] == 'TRANSFERT':
            return
        if l['nature'] == 'ANNULATION':
            self.pieces_annulation.add(l['piece'])
            if not l['annulee_jour']:
                # Effet réel sur la trésorerie : négatif quand on annule un
                # encaissement, positif quand on annule une dépense.
                self.annulations[m] += l['debit'] - l['credit']
            return
        if l['annulee_jour']:
            return
        self.entrees[m] += l['debit']
        self.sorties[m] += l['credit']
        self.pieces.add(l['piece'])

    def rendu(self):
        def montants(d):
            par_mode = {m: round(d.get(m, 0.0), 2) for m, _ in MODES}
            return {'total': round(sum(par_mode.values()), 2), 'par_mode': par_mode}
        e, s, a = montants(self.entrees), montants(self.sorties), montants(self.annulations)
        return {
            'nb_operations':  len(self.pieces),
            'nb_annulations': len(self.pieces_annulation),
            'entrees': e,
            'sorties': s,
            'annulations': a,
            'solde':   round(e['total'] - s['total'] + a['total'], 2),
        }


def _soldes(courant):
    par_mode = {m: round(courant.get(m, 0.0), 2) for m, _ in MODES}
    return {'total': round(sum(par_mode.values()), 2), 'par_mode': par_mode}


def _par_responsable(lignes):
    cumuls, noms = defaultdict(_Cumul), {}
    for l in lignes:
        cle = l['resp_id'] or '-'
        cumuls[cle].ajouter(l)
        noms[cle] = l['resp']
    sortie = [{'id': cle if cle != '-' else '', 'nom': noms[cle], **c.rendu()}
              for cle, c in cumuls.items()]
    sortie = [r for r in sortie if r['nb_operations'] or r['nb_annulations']]
    return sorted(sortie, key=lambda r: (r['nom'] == NON_RENSEIGNE, r['nom'].lower()))


def _mois_suivant(d):
    return datetime.date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def point_tresorerie(tenant, exercice, debut, fin, today=None):
    """Le point de la période [debut, fin] (bornes incluses)."""
    today = today or timezone.localdate()
    lignes = _lignes(tenant, exercice)
    initial = soldes_initiaux(exercice)

    # Solde d'ouverture : solde initial + tout ce qui précède la période.
    courant = defaultdict(float, initial)
    for l in lignes:
        if l['date'] < debut:
            courant[l['mode']] += l['debit'] - l['credit']
    ouverture = _soldes(courant)

    periode = [l for l in lignes if debut <= l['date'] <= fin]
    par_jour = defaultdict(list)
    for l in periode:
        par_jour[l['date']].append(l)

    jours = []
    for jour in sorted(par_jour):
        du_jour = par_jour[jour]
        cumul = _Cumul()
        for l in du_jour:
            cumul.ajouter(l)
            courant[l['mode']] += l['debit'] - l['credit']
        jours.append({
            'date': jour.isoformat(),
            **cumul.rendu(),
            'nb_transferts': len({l['piece'] for l in du_jour if l['nature'] == 'TRANSFERT'}),
            'solde_fin': _soldes(courant),
            'responsables': _par_responsable(du_jour),
        })

    total = _Cumul()
    for l in periode:
        total.ajouter(l)

    resultat = {
        'exercice':    exercice.annee_scolaire,
        'exercice_id': str(exercice.id),
        'debut': debut.isoformat(),
        'fin':   fin.isoformat(),
        'genere_le': timezone.localtime().isoformat(),
        'modes': [{'code': m, 'libelle': lib} for m, lib in MODES],
        'solde_ouverture': ouverture,
        'solde_cloture':   _soldes(courant),
        'totaux': total.rendu(),
        'responsables': _par_responsable(periode),
        'jours': jours,
        'mois': _mensuel(lignes, initial, exercice, today),
    }
    if debut == fin:
        resultat['operations'] = [_operation(l) for l in periode]
    return resultat


def _operation(l):
    heure = timezone.localtime(l['heure']) if l['heure'] else None
    return {
        'heure':   heure.strftime('%H:%M') if heure else '',
        'piece':   l['piece'],
        'libelle': l['libelle'],
        'mode':    l['mode'],
        'mode_libelle': LIBELLE_MODE[l['mode']],
        'nature':  l['nature'],
        'annulee_jour': l['annulee_jour'],
        'entree':  round(l['debit'], 2),
        'sortie':  round(l['credit'], 2),
        'responsable': l['resp'],
    }


def _mensuel(lignes, initial, exercice, today):
    """Le récapitulatif mois par mois de l'exercice, jusqu'au mois en cours."""
    derniere = max([today] + [l['date'] for l in lignes])
    courant = defaultdict(float, initial)
    debut_ex = exercice.date_debut.replace(day=1)
    # Les lignes datées avant l'exercice (reprises, avances de rentrée)
    # entrent dans le premier mois.
    avant = [l for l in lignes if l['date'] < debut_ex]

    sortie, mois = [], debut_ex
    while mois <= min(exercice.date_fin, derniere):
        suivant = _mois_suivant(mois)
        du_mois = [l for l in lignes if mois <= l['date'] < suivant]
        if mois == debut_ex:
            du_mois = avant + du_mois
        cumul = _Cumul()
        for l in du_mois:
            cumul.ajouter(l)
            courant[l['mode']] += l['debit'] - l['credit']
        sortie.append({
            'annee': mois.year, 'mois': mois.month,
            'libelle': f"{NOMS_MOIS[mois.month - 1].capitalize()} {mois.year}",
            **cumul.rendu(),
            'solde_fin': _soldes(courant),
        })
        mois = suivant
    return sortie


def pour_pdf(point):
    """Le point remis en lignes ordonnées pour le gabarit PDF (les gabarits
    Django ne lisent pas un dictionnaire par clé variable)."""
    codes = [m for m, _ in MODES]
    t = point['totaux']
    modes = [{
        'libelle':     lib,
        'ouverture':   point['solde_ouverture']['par_mode'][m],
        'entrees':     t['entrees']['par_mode'][m],
        'sorties':     t['sorties']['par_mode'][m],
        'annulations': t['annulations']['par_mode'][m],
        'cloture':     point['solde_cloture']['par_mode'][m],
    } for m, lib in MODES]
    # On ne garde que les modes qui ont servi, et toujours les espèces.
    modes_actifs = [m for m, ligne in zip(codes, modes)
                    if m == 'ESPECE' or any(ligne[k] for k in ligne if k != 'libelle')]

    def ligne_resp(r):
        return {**r, 'entrees_modes': [r['entrees']['par_mode'][m] for m in modes_actifs]}

    return {
        'modes': [ligne for m, ligne in zip(codes, modes) if m in modes_actifs],
        'libelles_modes': [LIBELLE_MODE[m] for m in modes_actifs],
        'responsables': [ligne_resp(r) for r in point['responsables']],
        'jours_responsables': [
            {'date': datetime.date.fromisoformat(j['date']), 'premier': i == 0, **ligne_resp(r)}
            for j in point['jours'] for i, r in enumerate(j['responsables'])],
        'jours': [{**j, 'date': datetime.date.fromisoformat(j['date'])} for j in point['jours']],
        'a_annulations': any(m['annulations'] for m in modes),
    }
