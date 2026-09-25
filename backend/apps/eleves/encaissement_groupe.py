"""Encaisser pour plusieurs élèves à la fois : une famille, un organisme.

Le guichet règle UN élève : on choisit ses mois, le logiciel sait ce qui reste
dû sur chacun et ventile le montant entre scolarité et services. Ce module
rend la même chose pour une fratrie — et pour un organisme qui verse la bourse
de plusieurs boursiers — sans recréer une seconde façon d'encaisser :

  1. `echeances_eleve` met à plat ce qu'un élève doit encore, poste par poste
     (impayé antérieur, frais d'entrée, uniforme, services, chaque mois, ÉCHU
     OU À VENIR), à partir de son échéancier — la source qui fait déjà foi sur
     la fiche, les alertes et les relances ;
  2. `repartir_montant` propose d'imputer une somme sur ces postes, du plus
     ancien au plus récent, et — si l'école le demande — au-delà de l'échu :
     une famille a le droit de payer d'avance ;
  3. `preparer_reglements` traduit les postes choisis en règlements ordinaires,
     que l'écran envoie un par un à l'API des paiements. C'est elle qui écrit
     les écritures : rien ici ne touche à la comptabilité.

Un mois se paie en plusieurs natures : la scolarité (706), les services
mensuels et les suppléments de garde (758). Le reste d'un mois entamé est
réparti entre elles au prorata de son dû : l'école sait toujours ce qui, dans
un règlement, relève du service éducatif.
"""
import datetime
from collections import defaultdict

from .echeancier import PREFETCH_PAIEMENTS, construire_echeancier

PRECISION = 2


def _r(x):
    return round(float(x or 0), PRECISION)


def _paiements_actifs(eleve):
    regles = getattr(eleve, PREFETCH_PAIEMENTS, None)
    if regles is not None:
        return list(regles)
    from apps.paiements.models import Paiement
    return list(Paiement.objects.filter(tenant=eleve.tenant, exercice=eleve.exercice,
                                        eleve=eleve, statut='ACTIF'))


def _deja_regle(eleve):
    """Ce qui a été réglé, par nature de frais hors mensualité."""
    regle = defaultdict(float)
    for p in _paiements_actifs(eleve):
        regle['inscription'] += float(p.montant_inscription or 0)
        regle['uniforme'] += float(p.montant_uniforme or 0)
        regle['fournitures'] += float(p.montant_fournitures or 0)
        for ligne in p.services_regles or []:
            nature = ligne.get('nature')
            if nature == 'UNIQUE':
                regle[f"unique:{ligne.get('nom')}"] += float(ligne.get('montant') or 0)
            elif nature == 'ADHESION' and ligne.get('cle'):
                regle[f"adhesion:{ligne['cle']}"] += float(ligne.get('montant') or 0)
        if p.organisme_id:
            regle['organisme:inscription'] += float(p.montant_inscription or 0)
            regle['organisme:mensualite'] += float(p.montant_mensualite or 0)
    return regle


def _postes_hors_mensualite(eleve, hors, regle):
    """Frais d'entrée, uniforme, fournitures, services uniques, adhésions.

    Le total de l'échéancier fait foi : si d'anciens règlements « divers » ont
    déjà couvert une partie de ces frais sans les nommer, le détail est réduit
    d'autant, en partant du dernier poste — jamais on ne réclame deux fois.
    """
    postes = []
    section = eleve.section

    def ajouter(cle, libelle, champ, du, deja, **extra):
        reste = _r(max(du - deja, 0.0))
        if du > 0:
            postes.append({'cle': cle, 'type': 'HORS', 'libelle': libelle, 'champ': champ,
                           'du': _r(du), 'paye': _r(min(deja, du)), 'reste': reste, **extra})

    if section:
        ajouter('ENTREE', eleve.libelle_frais_entree, 'montant_inscription',
                max(eleve.frais_entree - eleve.montant_pec_inscription, 0.0),
                regle['inscription'])
        ajouter('UNIFORME', 'Uniforme', 'montant_uniforme',
                float(section.frais_uniforme or 0), regle['uniforme'])
        ajouter('FOURNITURES', 'Fournitures', 'montant_fournitures',
                float(section.frais_fournitures or 0), regle['fournitures'])
    for ab in eleve.abonnements.all():
        s = ab.service
        if s.periodicite != 'MENSUEL':
            ajouter(f'UNIQUE:{s.id}', s.nom, 'service', float(s.montant or 0),
                    regle[f'unique:{s.nom}'], service={'nom': s.nom, 'nature': 'UNIQUE'})
    for a in eleve.adhesions_services():
        nom = f"{a['service']} — {a['libelle']}" if a['libelle'] else a['service']
        ajouter(f"ADH:{a['cle']}", nom, 'service', a['montant'],
                regle[f"adhesion:{a['cle']}"],
                service={'nom': nom, 'nature': 'ADHESION', 'cle': a['cle']})

    # Alignement sur le reste de l'échéancier.
    exces = _r(sum(p['reste'] for p in postes) - (hors['reste'] if hors else 0.0))
    for poste in reversed(postes):
        if exces <= 0:
            break
        retire = min(poste['reste'], exces)
        poste['reste'] = _r(poste['reste'] - retire)
        exces = _r(exces - retire)

    echu = bool(hors['echu']) if hors else True
    exigible = hors.get('exigible_le') if hors else None
    for poste in postes:
        poste['echu'] = echu
        poste['exigible_le'] = exigible
    return [p for p in postes if p['reste'] > 0]


def _composition_du_mois(eleve, mois):
    """Le dû d'un mois découpé : services mensuels, suppléments, scolarité."""
    from .garde_soir import du_garde_soir_du_mois

    du = float(eleve.du_du_mois(mois))
    services = []
    if eleve._mois_du_calendrier(mois):
        services = [{'nom': ab.service.nom, 'montant': float(ab.service.montant or 0)}
                    for ab in eleve.abonnements.all()
                    if ab.service.periodicite == 'MENSUEL' and float(ab.service.montant or 0) > 0]
    supplements = float(du_garde_soir_du_mois(eleve, mois))
    if eleve.a_la_journee:
        from .garderie import du_presences_du_mois
        supplements += float(du_presences_du_mois(eleve, mois))
    total_services = sum(s['montant'] for s in services)
    scolarite = max(du - total_services - supplements, 0.0)
    return du, scolarite, services, supplements


def echeances_eleve(eleve, today=None):
    """Tout ce que l'élève doit encore, poste par poste, échu ou à venir.

    Chaque poste porte `reste` (ce qui reste dû) et `reste_famille` (ce qu'on
    peut réclamer à la famille, net de la part qu'un organisme n'a pas encore
    versée). Une famille n'a pas à payer la bourse de l'État.
    """
    today = today or datetime.date.today()
    ech = construire_echeancier(eleve, today=today)
    regle = _deja_regle(eleve)

    postes = []
    reliquat = _r(getattr(eleve, 'reliquat_restant', 0))
    if reliquat > 0:
        postes.append({'cle': 'RELIQUAT', 'type': 'RELIQUAT', 'libelle': 'Impayé antérieur',
                       'champ': 'montant_reliquat', 'du': reliquat, 'paye': 0.0,
                       'reste': reliquat, 'echu': True, 'exigible_le': None})
    postes += _postes_hors_mensualite(eleve, ech['hors_mensualite'], regle)

    for ligne in ech['lignes']:
        if ligne['reste'] <= 0:
            continue
        du, scolarite, services, supplements = _composition_du_mois(eleve, ligne['mois'])
        postes.append({
            'cle': f"M{ligne['mois']}", 'type': 'MOIS', 'mois': ligne['mois'],
            'annee': ligne['annee'], 'libelle': f"{ligne['nom']} {ligne['annee']}",
            'du': _r(ligne['du']), 'paye': _r(ligne['paye']), 'reste': _r(ligne['reste']),
            'statut': ligne['statut'], 'echu': bool(ligne['echu']),
            'exigible_le': ligne['exigible_le'],
            'composition': {'du': _r(du), 'scolarite': _r(scolarite),
                            'services': services, 'supplements': _r(supplements)},
        })

    # ── Part de l'organisme : déduite de ce qu'on réclame à la famille ─────
    pec = eleve.pec_organisme
    reste_org = eleve.reste_organisme if pec else 0.0
    insc_org = mens_org = 0.0
    if pec and reste_org > 0:
        insc_org = max(float(pec.montant_inscription or 0) - regle['organisme:inscription'], 0.0)
        mens_org = min(max(float(pec.montant_mensualite or 0) * eleve.nb_mensualites_dues
                           - regle['organisme:mensualite'], 0.0),
                       max(reste_org - insc_org, 0.0))
    par_mois = float(pec.montant_mensualite or 0) if pec else 0.0
    for poste in postes:
        part = 0.0
        if poste['cle'] == 'ENTREE' and insc_org > 0:
            part = min(poste['reste'], insc_org)
            insc_org -= part
        elif poste['type'] == 'MOIS' and mens_org > 0:
            part = min(poste['reste'], par_mois, mens_org)
            mens_org -= part
        poste['part_organisme'] = _r(part)
        poste['reste_famille'] = _r(poste['reste'] - part)

    return {
        'eleve_id': str(eleve.id),
        'nom_complet': eleve.nom_complet,
        'matricule': eleve.matricule or '',
        'classe': (eleve.classe.nom if eleve.classe_id else
                   (eleve.section.nom if eleve.section else '')),
        'organisme': pec.organisme.nom if pec else '',
        'postes': postes,
        'totaux': {
            'echu': _r(sum(p['reste_famille'] for p in postes if p['echu'])),
            'a_venir': _r(sum(p['reste_famille'] for p in postes if not p['echu'])),
            'reste': _r(sum(p['reste_famille'] for p in postes)),
            'part_organisme': _r(sum(p['part_organisme'] for p in postes)),
        },
    }


def _ordre(poste):
    """Le plus ancien dû d'abord : ardoise, frais d'entrée, puis les mois."""
    rang = {'RELIQUAT': 0, 'HORS': 1, 'MOIS': 2}[poste['type']]
    date = poste.get('exigible_le') or datetime.date.min
    return (not poste['echu'], date, rang)


def repartir_montant(enfants, montant, anticiper=False, cle_reste='reste_famille'):
    """Impute `montant` sur les postes des enfants, le plus ancien d'abord.

    Sans `anticiper`, seuls les postes échus sont servis : ce qui dépasse
    reste `non_impute`, et l'école décide (avance ou monnaie rendue). Avec,
    les mois à venir sont servis ensuite, dans l'ordre du calendrier.
    Rend la sélection [{eleve_id, cle, montant}] et ce qui n'a pas été imputé.
    """
    restant = _r(montant)
    candidats = []
    for enfant in enfants:
        for poste in enfant['postes']:
            if poste[cle_reste] > 0 and (poste['echu'] or anticiper):
                candidats.append((enfant['eleve_id'], poste))
    candidats.sort(key=lambda c: _ordre(c[1]))

    selection = []
    for eleve_id, poste in candidats:
        if restant <= 0:
            break
        pris = _r(min(restant, poste[cle_reste]))
        restant = _r(restant - pris)
        selection.append({'eleve_id': eleve_id, 'cle': poste['cle'], 'montant': pris})
    return selection, restant


def preparer_reglements(enfant, choix, organisme_id=None):
    """Traduit les postes choisis d'un élève en règlements prêts à envoyer.

    `choix` : {cle: montant}. Un mois soldé se désigne ; les mois soldés de
    même montant partagent un règlement (l'échéancier répartit un règlement à
    parts égales entre ses mois désignés — deux montants différents dans le
    même règlement fausseraient les deux). Un mois entamé a son propre
    règlement, qui le désigne seul : son acompte s'impute exactement sur lui.
    """
    postes = {p['cle']: p for p in enfant['postes']}
    hors = {'montant_reliquat': 0.0, 'montant_inscription': 0.0,
            'montant_uniforme': 0.0, 'montant_fournitures': 0.0}
    services_hors = []
    detail_hors = []
    mois_pleins = defaultdict(list)   # montant → [poste]
    mois_partiels = []

    for cle, montant in choix.items():
        poste = postes.get(cle)
        montant = _r(montant)
        if poste is None or montant <= 0:
            continue
        montant = min(montant, poste['reste'])
        if poste['type'] == 'MOIS':
            if montant >= poste['reste']:
                mois_pleins[montant].append(poste)
            else:
                mois_partiels.append((poste, montant))
            continue
        if poste['champ'] == 'service':
            services_hors.append({**poste['service'], 'montant': montant})
        else:
            hors[poste['champ']] = _r(hors[poste['champ']] + montant)
        detail_hors.append({'libelle': poste['libelle'], 'montant': montant})

    def reglement_mois(postes_mois, montants):
        mensualite = accessoire = 0.0
        services = defaultdict(float)
        for poste, montant in zip(postes_mois, montants):
            comp = poste['composition']
            ratio = montant / comp['du'] if comp['du'] else 0.0
            part_services = 0.0
            for s in comp['services']:
                part = _r(s['montant'] * ratio)
                services[s['nom']] += part
                part_services += part
            supp = _r(comp['supplements'] * ratio)
            accessoire += part_services + supp
            mensualite += montant - part_services
        return {
            'montant_mensualite': _r(mensualite),
            'services_regles': [{'nom': nom, 'montant': _r(m), 'nature': 'MENSUEL'}
                                for nom, m in services.items() if m > 0],
            'part_accessoire': _r(accessoire),
            'mois_regles': [p['mois'] for p in postes_mois],
            'detail': [{'libelle': p['libelle'], 'montant': _r(m)}
                       for p, m in zip(postes_mois, montants)],
        }

    reglements = []
    groupes = [(postes_m, [m] * len(postes_m)) for m, postes_m in mois_pleins.items()]
    groupes += [([p], [m]) for p, m in mois_partiels]
    for postes_m, montants in groupes:
        reglements.append(reglement_mois(postes_m, montants))

    if any(hors.values()) or services_hors:
        # Les frais hors mensualité rejoignent le premier règlement : un reçu
        # de moins pour la famille, et rien ne change à leur imputation.
        cible = reglements[0] if reglements else {
            'montant_mensualite': 0.0, 'services_regles': [], 'part_accessoire': 0.0,
            'mois_regles': [], 'detail': []}
        cible.update({k: v for k, v in hors.items()})
        cible['services_regles'] = cible['services_regles'] + [
            {k: v for k, v in s.items()} for s in services_hors]
        cible['part_accessoire'] = _r(cible['part_accessoire']
                                      + sum(s['montant'] for s in services_hors))
        cible['detail'] = detail_hors + cible['detail']
        if not reglements:
            reglements.append(cible)

    for r in reglements:
        for champ in ('montant_reliquat', 'montant_inscription', 'montant_uniforme',
                      'montant_fournitures'):
            r.setdefault(champ, 0.0)
        r['montant_divers'] = _r(sum(s['montant'] for s in r['services_regles']))
        r['eleve'] = enfant['eleve_id']
        if organisme_id:
            r['organisme'] = organisme_id
        r['total'] = _r(r['montant_reliquat'] + r['montant_inscription'] + r['montant_uniforme']
                        + r['montant_fournitures'] + r['montant_mensualite']
                        + r['montant_divers'])
    return [r for r in reglements if r['total'] > 0]


def preparer(enfants, selection, organisme_id=None):
    """La sélection de toute la famille, en règlements, enfant par enfant."""
    par_eleve = defaultdict(dict)
    for ligne in selection:
        cle = ligne.get('cle')
        eleve_id = str(ligne.get('eleve_id') or '')
        if cle and eleve_id:
            par_eleve[eleve_id][cle] = _r(par_eleve[eleve_id].get(cle, 0) + _r(ligne.get('montant')))
    lignes = []
    for enfant in enfants:
        choix = par_eleve.get(enfant['eleve_id'])
        if not choix:
            continue
        reglements = preparer_reglements(enfant, choix, organisme_id)
        if not reglements:
            continue
        lignes.append({
            'eleve_id': enfant['eleve_id'], 'nom_complet': enfant['nom_complet'],
            'classe': enfant['classe'], 'reglements': reglements,
            'detail': [d for r in reglements for d in r['detail']],
            'total': _r(sum(r['total'] for r in reglements)),
        })
    return lignes
