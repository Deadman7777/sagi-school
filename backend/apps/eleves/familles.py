"""Le foyer payeur d'une fratrie : identifiant, contact, situation d'ensemble.

Une école ne raisonne pas seulement par enfant. Mr NDIAYE a cinq enfants
inscrits : il paie une fois, on l'appelle une fois, et la réduction qu'on lui
accorde porte sur la fratrie. Ce module rassemble ce que le regroupement
apporte, sans toucher au calcul du dû — regrouper des élèves ne change aucun
montant, et c'est la condition pour que ce chantier n'ait aucun effet sur les
écoles qui ne s'en serviront pas.
"""
import re

# Dernier groupe de chiffres du code : « FAM-0007 » → 7.
_DERNIER_NOMBRE = re.compile(r'(\d+)(?!.*\d)')


def prochain_code_famille(tenant):
    """Prochain code libre de cette école, calculé sur des NOMBRES.

    Le maximum alphabétique ferait repartir la séquence au premier code d'un
    autre format (données migrées, saisie manuelle), et l'insertion suivante
    violerait l'unicité par tenant. Le numéro retenu est donc vérifié libre.
    """
    from .models import Famille

    codes = list(Famille.objects.filter(tenant=tenant).values_list('code', flat=True))
    numeros = [int(m.group(1)) for c in codes
               if (m := _DERNIER_NOMBRE.search(c or ''))]
    suivant = max(numeros, default=0) + 1

    pris = set(codes)
    while (code := f'FAM-{suivant:04d}') in pris:
        suivant += 1
    return code


def contact_effectif(eleve):
    """Qui l'école appelle pour cet élève : {nom, telephone, origine}.

    UNE seule réponse, et un seul endroit qui la donne. Le contact d'un élève
    se lisait jusqu'ici en enchaînant `telephone_tuteur or telephone_pere or
    telephone_mere` à chaque endroit qui en avait besoin ; ajouter la famille
    comme source aurait multiplié les variantes, et deux écrans auraient fini
    par afficher deux numéros pour le même enfant.

    Ordre : le responsable principal de la famille, puis le tuteur de la
    fiche, puis le père, puis la mère. La famille passe devant parce que
    c'est elle que l'école tient à jour une fois regroupée ; les champs de la
    fiche restent le repli pour les milliers d'élèves jamais rattachés.
    """
    famille = eleve.famille if eleve.famille_id else None
    if famille is not None:
        responsable = famille.responsable_principal
        if responsable is not None and responsable.telephone:
            return {'nom': responsable.nom, 'telephone': responsable.telephone,
                    'origine': 'FAMILLE'}

    for origine, nom, telephone in (
            ('TUTEUR', eleve.nom_tuteur, eleve.telephone_tuteur),
            ('PERE',   eleve.nom_pere,   eleve.telephone_pere),
            ('MERE',   eleve.nom_mere,   eleve.telephone_mere)):
        if telephone:
            return {'nom': nom or '', 'telephone': telephone, 'origine': origine}

    # Aucun numéro : on rend quand même le nom connu, l'école saura de qui il
    # s'agit même si elle doit chercher le numéro ailleurs.
    if famille is not None and famille.responsable_principal is not None:
        return {'nom': famille.responsable_principal.nom, 'telephone': '',
                'origine': 'FAMILLE'}
    nom = eleve.nom_tuteur or eleve.nom_pere or eleve.nom_mere or ''
    return {'nom': nom, 'telephone': '', 'origine': 'FICHE' if nom else 'AUCUN'}


def situation_famille(famille, exercice):
    """Ce que la famille doit et a payé, tous enfants confondus.

    Les montants ne sont pas recalculés ici : ils sont repris tels quels des
    fiches élèves, qui sont la seule autorité sur le dû. Ce module additionne,
    il n'arbitre pas — deux calculs séparés de la même grandeur finissent
    toujours par diverger.

    Les fiches de créance (ouvertes pour porter l'ardoise d'un élève parti)
    sont comptées : la famille doit toujours cet argent.
    """
    from .echeancier import precharger

    enfants = list(precharger(
        famille.eleves.filter(exercice=exercice).select_related('section', 'classe')))

    lignes = []
    for eleve in enfants:
        lignes.append({
            'eleve_id':       str(eleve.id),
            'matricule':      eleve.matricule or '',
            'nom_complet':    eleve.nom_complet,
            'classe':         eleve.classe.nom if eleve.classe_id else (
                              eleve.section.nom if eleve.section else ''),
            'statut':         eleve.statut,
            'total_attendu':  float(eleve.total_attendu),
            'total_paye':     float(eleve.total_paye),
            'reste_a_payer':  float(eleve.reste_a_payer_global),
        })
    lignes.sort(key=lambda l: l['nom_complet'])

    return {
        'famille_id':    str(famille.id),
        'code':          famille.code,
        'nom':           famille.nom,
        'nb_enfants':    len(lignes),
        'enfants':       lignes,
        'total_attendu': round(sum(l['total_attendu'] for l in lignes), 2),
        'total_paye':    round(sum(l['total_paye'] for l in lignes), 2),
        'reste_a_payer': round(sum(l['reste_a_payer'] for l in lignes), 2),
    }


# ── Regrouper l'existant ──────────────────────────────────────────────────
def cle_telephone(numero):
    """Forme comparable d'un numéro, ou None s'il n'est pas exploitable.

    Sur le terrain un même numéro s'écrit « 77 687 66 10 », « 77-687-66-10 »,
    « +221 77 687 66 10 », et la fiche en porte parfois deux séparés par « / ».
    Comparer les chaînes telles quelles ne rapprocherait presque personne.

    On garde le premier numéro, ses chiffres seuls, sans l'indicatif 221, et
    on ne retient que les neuf derniers — un fixe à huit chiffres et un
    portable à neuf restent distincts, mais « +221 77… » et « 77… » se
    rejoignent enfin.
    """
    texte = (numero or '').strip()
    if not texte:
        return None
    for sep in ('/', ';', ','):
        if sep in texte:
            texte = texte.split(sep)[0]
            break
    chiffres = ''.join(c for c in texte if c.isdigit())
    if chiffres.startswith('221') and len(chiffres) > 9:
        chiffres = chiffres[3:]
    if chiffres.startswith('00221'):
        chiffres = chiffres[5:]
    # Moins de sept chiffres : un reliquat de saisie (« 77 », « 0000 »), pas un
    # numéro. Rapprocher là-dessus fusionnerait des familles sans lien.
    if len(chiffres) < 7:
        return None
    return chiffres[-9:]


def _contacts(eleve):
    """Les (clé téléphone, nom, lien) exploitables d'une fiche."""
    sources = (('TUTEUR', eleve.nom_tuteur, eleve.telephone_tuteur),
               ('PERE',   eleve.nom_pere,   eleve.telephone_pere),
               ('MERE',   eleve.nom_mere,   eleve.telephone_mere))
    return [(cle, nom or '', lien) for lien, nom, numero in sources
            if (cle := cle_telephone(numero))]


def fratries_probables(tenant, exercice):
    """Groupes d'élèves qui partagent un numéro de parent, à valider.

    Le rapprochement se fait sur le TÉLÉPHONE et jamais sur le seul nom : dans
    une école sénégalaise, rapprocher tous les NDIAYE constituerait une famille
    de quarante enfants sans lien entre eux.

    Deux élèves reliés par un numéro entrent dans le même groupe, même si ce
    n'est pas le même parent qui les relie : le père pour deux, la mère pour
    trois, le père de nouveau — c'est un seul foyer, et l'école le verrait
    coupé en morceaux si on groupait numéro par numéro.

    Rien n'est créé ici : l'école valide. Fusionner deux familles homonymes
    sans lien est très difficile à défaire, et une proposition silencieuse
    n'aurait laissé personne vérifier.
    """
    from .models import Eleve
    from .tri import cle_nom

    eleves = list(Eleve.objects.filter(tenant=tenant, exercice=exercice,
                                       famille__isnull=True, fiche_creance=False))

    # Union-find : deux élèves qui partagent un numéro finissent dans le même
    # groupe, de proche en proche.
    parent = {}

    def racine(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def unir(a, b):
        ra, rb = racine(a), racine(b)
        if ra != rb:
            parent[rb] = ra

    par_numero = {}
    for eleve in eleves:
        parent.setdefault(eleve.id, eleve.id)
        for cle, _nom, _lien in _contacts(eleve):
            if cle in par_numero:
                unir(par_numero[cle], eleve.id)
            else:
                par_numero[cle] = eleve.id

    groupes = {}
    for eleve in eleves:
        if _contacts(eleve):
            groupes.setdefault(racine(eleve.id), []).append(eleve)

    propositions = []
    for membres in groupes.values():
        if len(membres) < 2:
            continue
        membres.sort(key=lambda e: cle_nom(e.nom_complet))
        noms_famille = {cle_nom(e.nom_complet)[0] for e in membres}
        # Le contact le plus représenté du groupe : c'est lui que l'école
        # appellera, et c'est le plus souvent le père ou le tuteur payeur.
        compte = {}
        for eleve in membres:
            for cle, nom, lien in _contacts(eleve):
                entree = compte.setdefault(cle, {'cle': cle, 'nom': nom, 'lien': lien,
                                                 'numero': '', 'n': 0})
                entree['n'] += 1
                if not entree['nom'] and nom:
                    entree['nom'] = nom
        for eleve in membres:
            for lien, nom, numero in (('TUTEUR', eleve.nom_tuteur, eleve.telephone_tuteur),
                                      ('PERE', eleve.nom_pere, eleve.telephone_pere),
                                      ('MERE', eleve.nom_mere, eleve.telephone_mere)):
                cle = cle_telephone(numero)
                if cle in compte and not compte[cle]['numero']:
                    compte[cle]['numero'] = numero
        principal = max(compte.values(), key=lambda c: c['n'])
        nom_famille = sorted(noms_famille)[0] if len(noms_famille) == 1 else ''

        propositions.append({
            # Identifiant stable d'une proposition à l'autre : l'écran peut
            # cocher, recharger, et retrouver ses groupes.
            'cle':         principal['cle'],
            'nom_propose': f'Famille {nom_famille}'.strip() if nom_famille else
                           f"Famille {principal['nom']}".strip(),
            # Un seul nom de famille pour tout le groupe : le rapprochement
            # est franc. Plusieurs : l'école doit regarder (famille
            # recomposée, ou deux foyers qui se partagent un numéro).
            'confiance':   'SURE' if len(noms_famille) == 1 else 'A_VERIFIER',
            'noms_famille': sorted(noms_famille),
            'contact':     {'nom': principal['nom'], 'telephone': principal['numero'],
                            'lien': principal['lien']},
            'eleves':      [{'id': str(e.id), 'nom_complet': e.nom_complet,
                             'matricule': e.matricule or '',
                             'classe': e.classe.nom if e.classe_id else (
                                       e.section.nom if e.section else '')}
                            for e in membres],
            'nb':          len(membres),
        })

    # Les groupes les plus nombreux d'abord : c'est là que l'école gagne le
    # plus de saisie, et c'est par là qu'elle a envie de commencer.
    propositions.sort(key=lambda p: (-p['nb'], p['nom_propose']))
    return propositions


# ── Réduction fratrie ─────────────────────────────────────────────────────
#
# Le barème de l'école (BaremeFratrie) ne calcule aucun dû : il produit la
# prise en charge des fiches, motif FRATRIE. Le dû continue de se calculer en
# un seul endroit, « frais − prise en charge ».
MOTIF_FRATRIE = 'FRATRIE'


def enfants_classes(famille, exercice):
    """Les enfants de la famille, du plus ancien au plus récent.

    Le rang se prend par ANCIENNETÉ : l'aîné est le rang 1. Le prendre sur le
    tarif (« le plus cher d'abord ») ferait changer la remise d'enfant à
    chaque changement de classe, et la famille ne comprendrait plus rien à sa
    facture.

    Les sortants et les fiches de créance sont exclus : un enfant qui a quitté
    l'établissement ne doit pas bloquer le rang 1 et priver ses cadets de la
    remise.
    """
    from .parcours import STATUTS_SORTIE

    enfants = [e for e in famille.eleves.filter(exercice=exercice)
               .select_related('section')
               .exclude(statut__in=STATUTS_SORTIE)
               if not e.fiche_creance]
    # date_entree d'abord (l'entrée dans l'établissement, figée à vie), puis le
    # numéro : deux enfants inscrits le même jour gardent un ordre stable
    # d'un calcul à l'autre.
    enfants.sort(key=lambda e: (e.date_entree or e.date_inscription,
                                e.numero or 0, str(e.id)))
    return enfants


def _ligne_bareme(lignes, rang):
    """La ligne qui s'applique à ce rang, ou None.

    La ligne du rang le plus élevé vaut pour tous les rangs au-dessus : une
    école qui écrit « 4e et suivants » saisit une ligne 4, pas une ligne par
    enfant supplémentaire.
    """
    if not lignes:
        return None
    exacte = next((l for l in lignes if l.rang == rang), None)
    if exacte is not None:
        return exacte
    plus_haute = max(lignes, key=lambda l: l.rang)
    return plus_haute if rang > plus_haute.rang else None


def apercu_bareme(famille, exercice):
    """Ce que le barème changerait pour cette famille, sans rien écrire.

    L'aperçu existe parce que les rangs BOUGENT : un sixième enfant arrive en
    cours d'année, et toute la fratrie se décale. Réappliquer en silence
    modifierait des remises déjà consommées sur des mois payés — l'école doit
    voir ce qui change avant de valider.

    Une fiche dont la prise en charge vient d'un AUTRE motif (orphelin,
    handicap…) n'est jamais touchée : elle est signalée, et l'école tranche.
    Écraser une décision sociale par un calcul automatique serait le genre
    d'erreur qu'on ne rattrape pas auprès d'une famille.
    """
    from .models import BaremeFratrie

    lignes = list(BaremeFratrie.objects.filter(tenant=famille.tenant, actif=True))
    enfants = enfants_classes(famille, exercice)

    apercu = []
    for rang, eleve in enumerate(enfants, start=1):
        ligne = _ligne_bareme(lignes, rang)
        motif = (eleve.prise_en_charge or '').strip()
        protege = bool(motif) and motif != MOTIF_FRATRIE

        pec_inscription = ligne.sur_inscription(eleve.frais_entree) if ligne else 0.0
        pec_mensualite = (ligne.sur_mensualite(eleve.mensualite_brute_du_mois())
                          if ligne else 0.0)

        apercu.append({
            'eleve_id':    str(eleve.id),
            'nom_complet': eleve.nom_complet,
            'classe':      eleve.classe.nom if eleve.classe_id else (
                           eleve.section.nom if eleve.section else ''),
            'rang':        rang,
            'actuel': {'inscription': float(eleve.pec_inscription or 0),
                       'mensualite':  float(eleve.pec_mensualite or 0),
                       'motif':       motif},
            'propose': {'inscription': pec_inscription, 'mensualite': pec_mensualite},
            # Ce que l'école regarde en premier : qu'est-ce qui bouge ?
            'change':  (not protege
                        and (round(float(eleve.pec_inscription or 0), 2) != pec_inscription
                             or round(float(eleve.pec_mensualite or 0), 2) != pec_mensualite)),
            'protege': protege,
        })

    return {
        'famille_id': str(famille.id),
        'nom':        famille.nom,
        'bareme_defini': bool(lignes),
        'lignes':     apercu,
        'nb_change':  sum(1 for l in apercu if l['change']),
        'nb_protege': sum(1 for l in apercu if l['protege']),
    }


def appliquer_bareme(famille, exercice):
    """Écrit la prise en charge FRATRIE sur les fiches de la famille.

    N'écrit que ce qui change, et ne touche jamais une fiche dont la prise en
    charge relève d'un autre motif. Rejouable : réappliquer un barème inchangé
    ne modifie rien.
    """
    apercu = apercu_bareme(famille, exercice)
    if not apercu['bareme_defini']:
        return {**apercu, 'nb_applique': 0}

    from .models import Eleve

    modifies = 0
    for ligne in apercu['lignes']:
        if not ligne['change']:
            continue
        propose = ligne['propose']
        eleve = Eleve.objects.get(id=ligne['eleve_id'])
        eleve.pec_inscription = propose['inscription']
        eleve.pec_mensualite = propose['mensualite']
        # Le motif n'est posé que s'il y a effectivement une remise : sinon
        # une fiche sans réduction porterait « Réduction fratrie » pour rien,
        # et l'école croirait avoir accordé quelque chose.
        if propose['inscription'] or propose['mensualite']:
            eleve.prise_en_charge = MOTIF_FRATRIE
        elif (eleve.prise_en_charge or '') == MOTIF_FRATRIE:
            eleve.prise_en_charge = None
        eleve.save(update_fields=['pec_inscription', 'pec_mensualite',
                                  'prise_en_charge', 'updated_at'])
        modifies += 1

    return {**apercu_bareme(famille, exercice), 'nb_applique': modifies}


# ── Encaissement groupé ───────────────────────────────────────────────────
def repartir_versement(famille, exercice, montant, today=None):
    """Répartit un versement entre les enfants, le plus ancien dû d'abord.

    Un père arrive avec 150 000 F pour cinq enfants. Sans cette répartition,
    l'école fait cinq saisies et décide à la main de qui est servi en
    premier — au risque de solder le mois courant d'un enfant pendant qu'un
    autre traîne un arriéré de trois mois.

    L'ordre est celui de la dette, pas celui des enfants : impayé antérieur,
    puis inscription, puis mois échus du plus ancien au plus récent, toutes
    fiches confondues. Ce qui reste après les échéances échues n'est pas
    imputé d'office sur les mois à venir : l'école le fait explicitement si
    la famille paie d'avance.

    Ne crée RIEN. Rend une proposition que l'école modifie avant d'encaisser :
    chaque ligne reste un règlement normal, écrit par le chemin habituel, avec
    ses écritures.
    """
    import datetime

    from .echeancier import construire_echeancier, precharger

    today = today or datetime.date.today()
    restant = round(float(montant or 0), 2)

    enfants = list(precharger(
        famille.eleves.filter(exercice=exercice).select_related('section', 'classe')))

    # Toutes les échéances des enfants, mises à plat et classées par priorité.
    echeances = []
    for eleve in enfants:
        ech = construire_echeancier(eleve, today=today)
        reliquat = float(getattr(eleve, 'reliquat_restant', 0) or 0)
        if reliquat > 0:
            echeances.append({'eleve': eleve, 'poste': 'RELIQUAT', 'rang': 0,
                              'libelle': 'Impayé antérieur', 'mois': None,
                              'reste': round(reliquat, 2)})
        hors = ech.get('hors_mensualite')
        if hors and hors['reste'] > 0:
            echeances.append({'eleve': eleve, 'poste': 'INSCRIPTION', 'rang': 1,
                              'libelle': hors.get('libelle') or 'Inscription',
                              'mois': None, 'reste': round(hors['reste'], 2)})
        for ordre, ligne in enumerate(ech['lignes']):
            if ligne['reste'] > 0 and ligne['echu']:
                echeances.append({'eleve': eleve, 'poste': 'MENSUALITE',
                                  'rang': 2 + ordre, 'libelle': ligne['nom'],
                                  'mois': ligne['mois'], 'reste': round(ligne['reste'], 2)})

    echeances.sort(key=lambda e: e['rang'])

    # Une ligne de règlement par enfant servi.
    parts = {}
    for echeance in echeances:
        if restant <= 0:
            break
        pris = round(min(restant, echeance['reste']), 2)
        restant = round(restant - pris, 2)
        eleve = echeance['eleve']
        part = parts.setdefault(str(eleve.id), {
            'eleve_id': str(eleve.id), 'nom_complet': eleve.nom_complet,
            'classe': eleve.classe.nom if eleve.classe_id else (
                      eleve.section.nom if eleve.section else ''),
            'montant_reliquat': 0.0, 'montant_inscription': 0.0,
            'montant_mensualite': 0.0, 'mois_regles': [], 'detail': [], 'total': 0.0})
        if echeance['poste'] == 'RELIQUAT':
            part['montant_reliquat'] = round(part['montant_reliquat'] + pris, 2)
        elif echeance['poste'] == 'INSCRIPTION':
            part['montant_inscription'] = round(part['montant_inscription'] + pris, 2)
        else:
            part['montant_mensualite'] = round(part['montant_mensualite'] + pris, 2)
            # Le mois n'est désigné que s'il est SOLDÉ par ce versement : une
            # imputation partielle laisserait croire le mois réglé.
            if pris >= echeance['reste'] and echeance['mois'] not in part['mois_regles']:
                part['mois_regles'].append(echeance['mois'])
        part['detail'].append({'libelle': echeance['libelle'], 'montant': pris})
        part['total'] = round(part['total'] + pris, 2)

    lignes = sorted(parts.values(), key=lambda p: p['nom_complet'])
    return {
        'famille_id':  str(famille.id),
        'nom':         famille.nom,
        'montant':     round(float(montant or 0), 2),
        'lignes':      lignes,
        'reparti':     round(sum(l['total'] for l in lignes), 2),
        # Ce que le versement dépasse des échéances échues. L'école décide :
        # avance sur les mois à venir, ou monnaie rendue.
        'non_impute':  restant,
        'nb_enfants':  len(lignes),
    }
