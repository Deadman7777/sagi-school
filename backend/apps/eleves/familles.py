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
