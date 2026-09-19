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
