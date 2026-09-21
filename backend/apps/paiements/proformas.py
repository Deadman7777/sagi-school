"""Facture proforma de scolarité : ce que la famille aura à payer, et quand.

Deux demandes arrivent au guichet :

  - un parent veut régler TOUTE L'ANNÉE d'un coup et demande un document qui
    dise combien (souvent pour son employeur, qui avance les frais) ;
  - un parent se RENSEIGNE avant d'inscrire son enfant — ou avant la rentrée
    suivante — et veut savoir ce que coûtera l'année et à quelles échéances.

Aucun nouveau calcul du dû n'est introduit ici. Pour un élève inscrit, les
montants sortent de son échéancier (`eleves/echeancier.py`), celui que lisent
sa fiche, les rappels et le tableau de bord : la proforma ne peut pas annoncer
un reste que la fiche contredirait. Pour un futur élève, le nombre et le
calendrier des mensualités viennent du même prorata que les fiches
(`Eleve.nb_mensualites_dues`, `echeancier.mois_de_base`), appliqué à une fiche
fictive jamais enregistrée.

Une proforma n'écrit rien en comptabilité. Elle est figée à l'émission.
"""
import datetime
import re

from django.db import IntegrityError, transaction

from .models import Exercice, Proforma

VALIDITE_JOURS = 30

# Ce que l'école ajoute aux mentions fixes du document (caractère non
# comptable, validité, référence) : où et comment payer. Modifiable à chaque
# proforma ; la dernière saisie devient la proposition suivante.
CONDITIONS_DEFAUT = "Règlement au secrétariat de l'établissement, contre reçu."

MOIS = {1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril', 5: 'Mai', 6: 'Juin',
        7: 'Juillet', 8: 'Août', 9: 'Septembre', 10: 'Octobre', 11: 'Novembre',
        12: 'Décembre'}

# Sous ce seuil, un écart est un arrondi, pas un montant.
EPSILON = 0.5


class ProformaErreur(ValueError):
    """Demande impossible à chiffrer, avec un message lisible par l'école."""


def _f(x):
    return round(float(x or 0), 2)


def francs(montant):
    """243000 → « 243 000 F » (espace insécable : un montant ne se coupe pas)."""
    signe = '− ' if round(float(montant)) < 0 else ''
    return signe + f'{abs(round(float(montant))):,}'.replace(',', ' ') + ' F'


def _ligne(designation, montant, quantite=1, prix_unitaire=None, detail='', nature=''):
    return {
        'designation':   designation,
        'detail':        detail,
        'quantite':      quantite,
        'prix_unitaire': _f(montant if prix_unitaire is None else prix_unitaire),
        'montant':       _f(montant),
        'nature':        nature,
    }


# ── Exercice chiffré ─────────────────────────────────────────────────────

def _annee_suivante(libelle):
    """« 2025-2026 » → « 2026-2027 » ; « 2026 » → « 2027 »."""
    return re.sub(r'\d{4}', lambda m: str(int(m.group(0)) + 1), libelle or '') or libelle


def _decaler_un_an(jour):
    try:
        return jour.replace(year=jour.year + 1)
    except ValueError:              # 29 février
        return jour.replace(year=jour.year + 1, day=28)


def exercice_chiffre(exercice, annee_suivante=False):
    """L'exercice dont on déroule le calendrier.

    Année suivante : la même organisation (nombre de mensualités, mois de
    rentrée), un an plus tard. Un exercice non enregistré — les écoles ne
    créent le suivant qu'à la clôture, alors que les familles se renseignent
    dès juin. Les tarifs chiffrés restent ceux des sections, que l'école met à
    jour avant de remettre la proforma.
    """
    if not annee_suivante:
        return exercice
    return Exercice(
        tenant=exercice.tenant,
        annee_scolaire=_annee_suivante(exercice.annee_scolaire),
        date_debut=_decaler_un_an(exercice.date_debut),
        date_fin=_decaler_un_an(exercice.date_fin),
        nb_mensualites=exercice.nb_mensualites,
    )


# ── Regroupement des mois ────────────────────────────────────────────────

def _periode(mois):
    """[(num, annee)] → « Octobre 2026 à Juin 2027 », ou la liste des mois."""
    if len(mois) == 1:
        m, a = mois[0]
        return f'{MOIS[m]} {a}'
    contigus = all((mois[i][0] - mois[i - 1][0]) % 12 == 1 for i in range(1, len(mois)))
    if contigus:
        (m1, a1), (m2, a2) = mois[0], mois[-1]
        return f'{MOIS[m1]} {a1} à {MOIS[m2]} {a2}'
    return ', '.join(f'{MOIS[m]} {a}' for m, a in mois)


def _grouper(par_mois, nature):
    """Une ligne par suite de mois consécutifs au même montant.

    `par_mois` : [(designation, num, annee, montant)] dans l'ordre de l'année.
    « Mensualité × 9 » se lit mieux que neuf lignes identiques ; un mois au
    montant différent (réduction d'entrée, mois saisi) garde sa propre ligne.
    """
    ordre, series = [], {}
    for designation, m, annee, montant in par_mois:
        if designation not in series:
            ordre.append(designation)
            series[designation] = []
        runs = series[designation]
        if runs and abs(runs[-1]['pu'] - montant) < 0.01:
            runs[-1]['mois'].append((m, annee))
        else:
            runs.append({'pu': montant, 'mois': [(m, annee)]})
    lignes = []
    for designation in ordre:
        for run in series[designation]:
            n = len(run['mois'])
            if abs(run['pu']) < 0.01:
                continue
            lignes.append(_ligne(designation, run['pu'] * n, quantite=n,
                                 prix_unitaire=run['pu'],
                                 detail=f"{_periode(run['mois'])}"
                                        + (f' ({n} mois)' if n > 1 else ''),
                                 nature='REDUCTION' if run['pu'] < 0 else nature))
    return lignes


def _libelle_reduction(eleve):
    motif = eleve.get_prise_en_charge_display() if eleve.prise_en_charge else ''
    if not motif:
        return 'Réduction accordée'
    return motif if motif.lower().startswith('réduction') else f'Réduction — {motif}'


def _detail_composition(section, montant):
    """« Frais de dossier 5 000 F · Assurance 2 000 F », si la composition
    tombe juste — sinon rien plutôt qu'un détail qui contredirait le total."""
    compo = [c for c in (section.composition_inscription or [])
             if float(c.get('montant') or 0) > 0]
    if not compo or abs(sum(float(c['montant']) for c in compo) - float(montant)) > EPSILON:
        return ''
    return ' · '.join(f"{c.get('libelle') or '—'} {francs(c['montant'])}" for c in compo)


# ── Élève inscrit ────────────────────────────────────────────────────────

def _lignes_entree(eleve, du_hors):
    """Le « hors mensualité » de l'échéancier, détaillé. Leur somme vaut
    exactement `du_hors` ; sinon une seule ligne, qui ne ment pas."""
    lignes = []
    section = eleve.section
    if section:
        libelle = eleve.libelle_frais_entree
        entree = eleve.frais_entree
        if entree > 0:
            detail = '' if eleve.renouvellement_du else _detail_composition(section, entree)
            lignes.append(_ligne(libelle, entree, detail=detail, nature='ENTREE'))
        pec = eleve.montant_pec_inscription
        if pec > 0:
            lignes.append(_ligne(_libelle_reduction(eleve), -pec,
                                 detail=f'Sur {libelle.lower()}', nature='REDUCTION'))
        for nom, champ in (('Uniforme', 'frais_uniforme'), ('Fournitures', 'frais_fournitures')):
            if float(getattr(section, champ) or 0) > 0:
                lignes.append(_ligne(nom, getattr(section, champ), nature='ENTREE'))
    for ab in eleve.abonnements.all():
        s = ab.service
        if s.periodicite != 'MENSUEL' and float(s.montant or 0) > 0:
            lignes.append(_ligne(s.nom, s.montant, detail='Paiement unique', nature='SERVICE'))
    for a in eleve.adhesions_services():
        lignes.append(_ligne(f"{a['service']} — {a['libelle'] or 'adhésion'}", a['montant'],
                             detail="Frais d'adhésion au service", nature='SERVICE'))
    if abs(sum(l['montant'] for l in lignes) - du_hors) > EPSILON:
        return [_ligne("Frais d'entrée et frais uniques", du_hors, nature='ENTREE')]
    return lignes


def _lignes_mois(eleve, retenus):
    """Les mois retenus, décomposés en mensualité, réduction, services et
    suppléments. La somme vaut exactement la somme des dus de l'échéancier."""
    services = [(ab.service.nom, float(ab.service.montant or 0))
                for ab in eleve.abonnements.all() if ab.service.periodicite == 'MENSUEL']
    total_services = sum(m for _, m in services)
    par_mois = []
    for l in retenus:
        m, annee, du = l['mois'], l['annee'], l['du']
        if l.get('montant_saisi') or eleve.a_la_journee:
            libelle = 'Garderie (jours de présence)' if eleve.a_la_journee else 'Mensualité scolaire'
            par_mois.append((libelle, m, annee, du))
            continue
        brut = eleve.mensualite_brute_du_mois(m)
        pec = eleve.pec_du_mois(m)
        supplement = round(du - (brut - pec + total_services), 2)
        if supplement < -EPSILON:
            # Mois hors calendrier, ou tarif que la décomposition ne sait pas
            # expliquer : le dû du mois, tel quel.
            par_mois.append(('Mensualité scolaire', m, annee, du))
            continue
        formule = eleve.formule_du_mois(m)
        par_mois.append(('Mensualité scolaire' + (f' — {formule.nom}' if formule else ''),
                         m, annee, brut))
        if pec > 0:
            par_mois.append((_libelle_reduction(eleve), m, annee, -pec))
        for nom, montant in services:
            par_mois.append((nom, m, annee, montant))
        if supplement > EPSILON:
            par_mois.append(('Garde du soir et suppléments', m, annee, supplement))
    lignes = _grouper(par_mois, 'MENSUALITE')
    for l in lignes:
        if l['nature'] == 'MENSUALITE' and not l['designation'].startswith('Mensualité') \
                and not l['designation'].startswith('Garderie'):
            l['nature'] = 'SERVICE'
    return lignes


def chiffrer_eleve(eleve, mois=None, inclure_entree=True, inclure_anterieur=True, today=None):
    """Proforma d'un élève inscrit : ce qui reste à régler sur son année.

    `mois` : les seuls mois à chiffrer (numéros) — sinon tous ceux qui ne sont
    pas soldés. Un mois soldé n'apparaît pas : la famille ne le doit plus.
    """
    from apps.eleves.echeancier import construire_echeancier, precharger
    from apps.eleves.models import Eleve

    today = today or datetime.date.today()
    eleve = precharger(Eleve.objects.filter(pk=eleve.pk)).get()
    ech = construire_echeancier(eleve, today=today)
    synth = ech['synthese']

    lignes, echeances, deja = [], [], 0.0
    hors = ech['hors_mensualite']
    if hors and inclure_entree and hors['reste'] > EPSILON:
        lignes += _lignes_entree(eleve, hors['du'])
        deja += hors['paye']
        echeances.append({'libelle': hors['libelle'] or eleve.libelle_frais_entree,
                          'date': hors['exigible_le'] or eleve.date_inscription or today,
                          'montant': hors['reste']})

    retenus = [l for l in ech['lignes'] if l['reste'] > EPSILON
               and (not mois or l['mois'] in mois)]
    lignes += _lignes_mois(eleve, retenus)
    deja += sum(l['paye'] for l in retenus)
    echeances += [{'libelle': f"{l['nom']} {l['annee']}", 'date': l['exigible_le'],
                   'montant': l['reste']} for l in retenus]

    anterieur = synth['impaye_anterieur']
    if inclure_anterieur and anterieur > EPSILON:
        lignes.append(_ligne('Reste dû sur les années antérieures', anterieur,
                             detail=eleve.reliquat_origine_libelle or '', nature='ANTERIEUR'))
        echeances.append({'libelle': 'Années antérieures', 'date': today, 'montant': anterieur})

    if not lignes:
        raise ProformaErreur(f"{eleve.nom_complet} n'a plus rien à régler sur cette période.")

    organisme = synth['reste_organisme'] if synth['organisme_nom'] else 0.0
    return {
        'lignes': lignes,
        'deja_regle': round(deja, 2),
        'part_organisme': organisme,
        'organisme_nom': synth['organisme_nom'],
        'echeances': echeances,
        'annee_scolaire': eleve.exercice.annee_scolaire,
        'exercice': eleve.exercice,
        'observations_auto': '',
    }


# ── Futur élève (ou réinscription de l'année suivante) ────────────────────

def chiffrer_nouvel_eleve(tenant, exercice, section, formule=None, date_entree=None,
                          services=(), renouvellement=False, annee_suivante=False):
    """Proforma d'un enfant qui n'a pas encore de fiche.

    `date_entree` : mois d'arrivée, pour le prorata des mensualités ; par
    défaut la rentrée. `renouvellement` : ancien élève qui se réinscrit, dans
    une école qui pratique le renouvellement.
    """
    from apps.eleves.echeancier import _annee_du_mois, date_exigibilite, mois_de_base
    from apps.eleves.models import Eleve

    ex = exercice_chiffre(exercice, annee_suivante)
    entree = date_entree or ex.date_debut
    if entree < ex.date_debut:
        entree = ex.date_debut
    if entree > ex.date_fin:
        raise ProformaErreur(
            f"La date d'entrée tombe après la fin de l'année scolaire {ex.annee_scolaire}.")

    # Fiche fictive, jamais enregistrée : elle porte le prorata des fiches
    # réelles (nombre de mensualités dues selon l'entrée, calendrier).
    fictive = Eleve(tenant=tenant, exercice=ex, section=section,
                    date_inscription=entree, nom_complet='')
    mois = mois_de_base(fictive)

    renouv = bool(renouvellement and getattr(tenant, 'renouvellement_actif', False))
    libelle_entree = ((getattr(tenant, 'libelle_renouvellement', '') or 'Renouvellement')
                      if renouv else 'Inscription')
    frais_entree = float(section.frais_renouvellement if renouv else section.frais_inscription)

    lignes, a_l_entree, par_mois_unique = [], [], {}
    if frais_entree > 0:
        lignes.append(_ligne(libelle_entree, frais_entree,
                             detail='' if renouv else _detail_composition(section, frais_entree),
                             nature='ENTREE'))
        a_l_entree.append(frais_entree)
    for nom, champ in (('Uniforme', 'frais_uniforme'), ('Fournitures', 'frais_fournitures')):
        if float(getattr(section, champ) or 0) > 0:
            lignes.append(_ligne(nom, getattr(section, champ), nature='ENTREE'))
            a_l_entree.append(float(getattr(section, champ)))

    uniques = [s for s in services if s.periodicite != 'MENSUEL' and float(s.montant or 0) > 0]
    mensuels = [s for s in services if s.periodicite == 'MENSUEL']
    for s in uniques:
        dans_l_annee = s.mois_unique and int(s.mois_unique) in mois
        lignes.append(_ligne(s.nom, s.montant, nature='SERVICE',
                             detail=(f'Paiement unique, en {MOIS[int(s.mois_unique)].lower()}'
                                     if dans_l_annee else 'Paiement unique, à l\'inscription')))
        if dans_l_annee:
            par_mois_unique[int(s.mois_unique)] = (par_mois_unique.get(int(s.mois_unique), 0)
                                                   + float(s.montant))
        else:
            a_l_entree.append(float(s.montant))
    for s in services:
        for el in s.composition_adhesion or []:
            montant = float(el.get('montant') or 0)
            if montant <= 0:
                continue
            lignes.append(_ligne(f"{s.nom} — {el.get('libelle') or 'adhésion'}", montant,
                                 nature='SERVICE',
                                 detail=('Première adhésion seulement' if el.get('premiere_fois')
                                         else "Frais d'adhésion au service")))
            a_l_entree.append(montant)

    observations = ''
    par_mois, dus_du_mois = [], {}
    if section.a_la_journee:
        # Rien n'est dû d'avance : la garderie se paie à la présence.
        observations = (f"Garderie facturée à la présence : demi-journée "
                        f"{francs(section.tarif_demi_journee)}, journée "
                        f"{francs(section.tarif_journee)}.")
        mensualite = 0.0
    else:
        mensualite = float(formule.frais_mensualite if formule else section.frais_mensualite)
    libelle_mois = 'Mensualité scolaire' + (f' — {formule.nom}' if formule else '')
    for m in mois:
        annee = _annee_du_mois(ex, m)
        if mensualite > 0:
            par_mois.append((libelle_mois, m, annee, mensualite))
        for s in mensuels:
            par_mois.append((s.nom, m, annee, float(s.montant or 0)))
        dus_du_mois[m] = (mensualite + sum(float(s.montant or 0) for s in mensuels)
                          + par_mois_unique.get(m, 0.0))
    lignes += _grouper(par_mois, 'MENSUALITE')
    for l in lignes:
        if l['nature'] == 'MENSUALITE' and not l['designation'].startswith('Mensualité'):
            l['nature'] = 'SERVICE'

    # Échéancier : ce qui se règle à l'inscription, puis mois par mois selon
    # le réglage d'exigibilité de l'école.
    a_inscription = set()
    if mois:
        if getattr(tenant, 'premier_mois_a_inscription', False) \
                or any(s.premier_mois_a_inscription for s in services):
            a_inscription.add(mois[0])
        if getattr(tenant, 'dernier_mois_a_inscription', False):
            a_inscription.add(mois[-1])
    echeances = []
    montant_entree = sum(a_l_entree) + sum(dus_du_mois[m] for m in a_inscription)
    if montant_entree > EPSILON:
        noms = ', '.join(MOIS[m].lower() for m in mois if m in a_inscription)
        echeances.append({'libelle': "À l'inscription" + (f' (dont {noms})' if noms else ''),
                          'date': entree, 'montant': montant_entree})
    for m in mois:
        if m in a_inscription or dus_du_mois[m] <= 0:
            continue
        annee = _annee_du_mois(ex, m)
        # Un mois déjà entamé à l'arrivée ne peut pas être exigible avant elle.
        echeances.append({'libelle': f'{MOIS[m]} {annee}',
                          'date': max(date_exigibilite(tenant, annee, m), entree),
                          'montant': dus_du_mois[m]})

    if not lignes:
        raise ProformaErreur("Aucun frais n'est paramétré pour cette section.")
    return {
        'lignes': lignes,
        'deja_regle': 0.0,
        'part_organisme': 0.0,
        'organisme_nom': '',
        'echeances': echeances,
        'annee_scolaire': ex.annee_scolaire,
        'exercice': exercice,
        'entree': entree,
        'observations_auto': observations,
    }


# ── Totaux, remise, échéancier ───────────────────────────────────────────

def finaliser(calcul, lignes_libres=(), remise_type='', remise_valeur=0,
              remise_libelle='', today=None):
    """Ajoute les lignes libres et la remise, puis arrête les totaux.

    Remise : consentie pour un règlement en UNE fois (c'est l'usage des écoles
    qui en font) ; elle ne s'applique donc pas à l'échéancier, qui reste la
    formule sans remise.
    """
    today = today or datetime.date.today()
    lignes = list(calcul['lignes'])
    echeances = [dict(e) for e in calcul['echeances']]

    libres = 0.0
    for l in lignes_libres or []:
        designation = str(l.get('designation') or '').strip()
        quantite = float(l.get('quantite') or 1)
        pu = float(l.get('prix_unitaire') or 0)
        if not designation or quantite <= 0 or pu <= 0:
            continue
        q = int(quantite) if quantite == int(quantite) else quantite
        lignes.append(_ligne(designation, pu * quantite, quantite=q, prix_unitaire=pu,
                             detail=str(l.get('detail') or '').strip(), nature='AUTRE'))
        libres += pu * quantite
    if libres:
        if echeances:
            echeances[0]['montant'] += libres
        else:
            echeances.append({'libelle': 'À la commande', 'date': today, 'montant': libres})

    total_du = round(sum(l['montant'] for l in lignes), 2)
    deja = round(calcul['deja_regle'], 2)
    organisme = round(min(calcul['part_organisme'], max(total_du - deja, 0.0)), 2)
    reste = round(max(total_du - deja - organisme, 0.0), 2)

    remise = 0.0
    valeur = float(remise_valeur or 0)
    if remise_type == 'TAUX':
        if not 0 <= valeur <= 100:
            raise ProformaErreur('Le taux de remise doit être compris entre 0 et 100 %.')
        remise = round(reste * valeur / 100)
    elif remise_type == 'MONTANT':
        if valeur < 0:
            raise ProformaErreur('La remise ne peut pas être négative.')
        remise = min(round(valeur, 2), reste)
    if remise and not (remise_libelle or '').strip():
        remise_libelle = 'Remise pour règlement de l\'année en une fois'

    # Échéances passées : une seule ligne « dès maintenant ». Une famille n'a
    # que faire de dates déjà échues — elle veut savoir ce qu'on lui demande.
    passees = [e for e in echeances if e['date'] and e['date'] <= today]
    futures = [e for e in echeances if not (e['date'] and e['date'] <= today)]
    plan = []
    if passees:
        plan.append({'libelle': 'À régler dès maintenant' + (
                         f" ({', '.join(e['libelle'] for e in passees)})"
                         if len(passees) <= 4 else ' (échéances passées)'),
                     'date': today, 'montant': sum(e['montant'] for e in passees)})
    plan += futures
    # Une bourse change le payeur de certaines échéances, et rien ne dit
    # lesquelles : plutôt pas d'échéancier qu'un échéancier faux.
    if organisme > EPSILON:
        plan = []
    plan = [{'libelle': e['libelle'], 'date': e['date'].isoformat() if e['date'] else None,
             'montant': _f(e['montant'])} for e in plan if e['montant'] > EPSILON]

    return {
        'lignes': lignes,
        'echeancier': plan,
        'total_du': total_du,
        'deja_regle': deja,
        'part_organisme': organisme,
        'organisme_nom': calcul['organisme_nom'],
        'reste': reste,
        'remise_libelle': (remise_libelle or '').strip() if remise else '',
        'remise_montant': _f(remise),
        'net_a_payer': _f(reste - remise),
        'annee_scolaire': calcul['annee_scolaire'],
        'observations_auto': calcul.get('observations_auto', ''),
    }


# ── Émission ─────────────────────────────────────────────────────────────

def prochain_numero(tenant, annee):
    """PF-2026-0001 : séquence numérique de l'école pour l'année d'émission."""
    prefixe = f'PF-{annee}-'
    numeros = [int(n[len(prefixe):]) for n in Proforma.objects.filter(
                   tenant=tenant, numero__startswith=prefixe).values_list('numero', flat=True)
               if n[len(prefixe):].isdigit()]
    return f'{prefixe}{max(numeros, default=0) + 1:04d}'


def emettre(tenant, exercice, resultat, eleve=None, beneficiaire='', section_nom='',
            formule_nom='', parent_nom='', parent_telephone='', validite_jours=VALIDITE_JOURS,
            observations='', conditions='', parametres=None, auteur='', today=None):
    """Enregistre la proforma, numérotée et figée."""
    today = today or datetime.date.today()
    try:
        validite_jours = int(validite_jours or VALIDITE_JOURS)
    except (TypeError, ValueError):
        validite_jours = VALIDITE_JOURS
    if not 1 <= validite_jours <= 365:
        raise ProformaErreur('La validité doit être comprise entre 1 et 365 jours.')
    if not (beneficiaire or '').strip():
        raise ProformaErreur("Indiquez le nom de l'enfant.")
    auto = resultat.get('observations_auto') or ''
    observations = '\n'.join(x for x in (auto, (observations or '').strip()) if x)

    for _essai in range(5):
        try:
            with transaction.atomic():
                return Proforma.objects.create(
                    tenant=tenant, exercice=exercice, eleve=eleve,
                    numero=prochain_numero(tenant, today.year),
                    annee_scolaire=resultat['annee_scolaire'],
                    beneficiaire=beneficiaire.strip(),
                    matricule=(eleve.matricule or '') if eleve else '',
                    section_nom=section_nom, formule_nom=formule_nom,
                    parent_nom=(parent_nom or '').strip(),
                    parent_telephone=(parent_telephone or '').strip(),
                    date_emission=today,
                    date_validite=today + datetime.timedelta(days=validite_jours),
                    lignes=resultat['lignes'], echeancier=resultat['echeancier'],
                    total_du=resultat['total_du'], deja_regle=resultat['deja_regle'],
                    part_organisme=resultat['part_organisme'],
                    organisme_nom=resultat['organisme_nom'],
                    remise_libelle=resultat['remise_libelle'],
                    remise_montant=resultat['remise_montant'],
                    net_a_payer=resultat['net_a_payer'],
                    parametres=parametres or {}, observations=observations,
                    conditions=(conditions or '').strip(), emise_par=auteur or '',
                )
        except IntegrityError:
            # Deux guichets ont pris le même numéro au même instant : on reprend.
            continue
    raise ProformaErreur('Numérotation indisponible, réessayez.')


def derniere_conditions(tenant):
    """Les conditions de la dernière proforma de l'école, sinon le texte type :
    l'école les écrit une fois, pas à chaque parent."""
    derniere = (Proforma.objects.filter(tenant=tenant).exclude(conditions='')
                .order_by('-created_at').values_list('conditions', flat=True).first())
    return derniere or CONDITIONS_DEFAUT


# ── PDF ──────────────────────────────────────────────────────────────────

def contexte_pdf(proforma):
    from apps.prospects.facturation import montant_en_lettres

    def fmt_q(q):
        q = float(q)
        return str(int(q)) if q == int(q) else f'{q:.2f}'.rstrip('0').replace('.', ',')

    tenant = proforma.tenant
    echeancier = []
    for e in proforma.echeancier or []:
        jour = datetime.date.fromisoformat(e['date']) if e.get('date') else None
        echeancier.append({'libelle': e['libelle'], 'date': jour, 'montant': francs(e['montant'])})
    # Au-delà de quatre échéances, deux colonnes : une année de dix mois
    # tient alors sur la page, signatures comprises.
    moitie = (len(echeancier) + 1) // 2 if len(echeancier) > 4 else len(echeancier)
    gauche, droite = echeancier[:moitie], echeancier[moitie:]
    rangees = [(g, droite[i] if i < len(droite) else None) for i, g in enumerate(gauche)]
    return {
        'p': proforma,
        'rangees_echeancier': rangees,
        'deux_colonnes': bool(droite),
        'tenant': tenant,
        'lignes': [{**l, 'quantite': fmt_q(l['quantite']),
                    'prix_unitaire': francs(l['prix_unitaire']),
                    'montant': francs(l['montant']),
                    'negatif': float(l['montant']) < 0} for l in proforma.lignes],
        'montants': {
            'total_du': francs(proforma.total_du),
            'deja_regle': francs(proforma.deja_regle),
            'part_organisme': francs(proforma.part_organisme),
            'remise': francs(proforma.remise_montant),
            'reste': francs(proforma.total_du - proforma.deja_regle - proforma.part_organisme),
            'net': francs(proforma.net_a_payer),
        },
        'nouvel_eleve': (proforma.parametres or {}).get('mode') != 'ELEVE',
        'a_deduire': proforma.deja_regle > 0 or proforma.part_organisme > 0,
        'echeancier': echeancier,
        'en_lettres': montant_en_lettres(proforma.net_a_payer),
    }
