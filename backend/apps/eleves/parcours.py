"""Parcours d'un élève — toute sa scolarité, année après année.

Un enfant possède une fiche PAR exercice (voir report_reliquats) : son
histoire est éparpillée sur autant de lignes qu'il a passé d'années dans
l'établissement. Ce module les rassemble et en fait une lecture continue,
de son entrée à sa sortie.

C'est ce qui permet de suivre un élève qui reste plusieurs années, et de
retrouver le dossier complet d'un diplômé longtemps après son départ.

Les fiches d'un même enfant se reconnaissent au matricule — il est attribué
une fois et recopié à chaque réinscription (voir matricules.py). La chaîne
`eleve_precedent` sert de filet quand le matricule manque (base ancienne,
fiche saisie à la main avant le rebasage).
"""
from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce

from .models import Eleve

STATUTS_SORTIE = ('DIPLOME', 'TRANSFERE', 'ABANDONNE')


def annoter(qs):
    """Ajoute le payé et le reliquat réglé, pour éviter une requête par fiche."""
    actif = Q(paiements__statut='ACTIF')

    def zero(expr):
        return Coalesce(expr, Value(0), output_field=DecimalField())

    return qs.annotate(
        total_paye_sql=zero(
            Sum('paiements__montant_inscription', filter=actif) +
            Sum('paiements__montant_mensualite',  filter=actif) +
            Sum('paiements__montant_uniforme',    filter=actif) +
            Sum('paiements__montant_fournitures', filter=actif) +
            Sum('paiements__montant_cantine',     filter=actif) +
            Sum('paiements__montant_divers',      filter=actif)
        ),
        reliquat_paye_sql=zero(Sum('paiements__montant_reliquat', filter=actif)),
    )


def _racine(parents, x):
    while parents[x] != x:
        parents[x] = parents[parents[x]]
        x = parents[x]
    return x


def _unir(parents, a, b):
    ra, rb = _racine(parents, a), _racine(parents, b)
    if ra != rb:
        parents[rb] = ra


def grouper_par_eleve(fiches):
    """Regroupe des fiches par enfant réel. Rend [[fiche, ...], ...].

    Deux fiches appartiennent au même enfant si elles sont chaînées par
    `eleve_precedent`, ou si elles portent le même matricule non vide — le
    lien de chaîne manque sur les fiches créées à la main ou importées avant
    le report, et le matricule manque sur les bases d'avant le rebasage. Il
    faut les deux critères pour ne perdre personne.
    """
    parents = {f.id: f.id for f in fiches}
    presentes = set(parents)
    par_matricule = {}

    for f in fiches:
        if f.eleve_precedent_id in presentes:
            _unir(parents, f.eleve_precedent_id, f.id)
        if f.matricule:
            cle = f.matricule.strip().upper()
            if cle in par_matricule:
                _unir(parents, par_matricule[cle], f.id)
            else:
                par_matricule[cle] = f.id

    groupes = {}
    for f in fiches:
        groupes.setdefault(_racine(parents, f.id), []).append(f)
    return list(groupes.values())


def _chaine(eleve):
    """Fiches liées par `eleve_precedent`, dans les deux sens."""
    fiches, vus = [], set()

    fiche = eleve
    while fiche and fiche.id not in vus:
        vus.add(fiche.id)
        fiches.append(fiche)
        fiche = fiche.eleve_precedent

    a_explorer = [eleve]
    while a_explorer:
        for suite in a_explorer.pop().reinscriptions.all():
            if suite.id not in vus:
                vus.add(suite.id)
                fiches.append(suite)
                a_explorer.append(suite)
    return fiches


def fiches_du_meme_eleve(eleve):
    """Toutes les fiches de cet enfant, de la plus ancienne à la plus récente."""
    ids = {f.id for f in _chaine(eleve)}
    if eleve.matricule:
        ids |= set(Eleve.objects.filter(tenant=eleve.tenant, matricule=eleve.matricule)
                                .values_list('id', flat=True))

    qs = annoter(
        Eleve.objects.filter(tenant=eleve.tenant, id__in=ids)
                     .select_related('section', 'classe', 'exercice',
                                     'reliquat_exercice_origine')
                     .prefetch_related('abonnements__service'))
    return sorted(qs, key=lambda f: f.exercice.date_debut)


def _ligne_annee(fiche):
    fiche._total_paye_cache = fiche.total_paye_sql
    return {
        'eleve_id':       str(fiche.id),
        'exercice_id':    str(fiche.exercice_id),
        'annee':          fiche.exercice.annee_scolaire,
        'date_debut':     fiche.exercice.date_debut,
        'cloture':        fiche.exercice.cloture,
        'section':        fiche.section.nom if fiche.section else '',
        'classe':         fiche.classe.nom if fiche.classe_id else '',
        'statut':         fiche.statut,
        'statut_libelle': dict(Eleve.STATUT_CHOICES).get(fiche.statut, fiche.statut),
        'fiche_creance':  fiche.fiche_creance,
        'total_attendu':  round(float(fiche.total_attendu), 2),
        'total_paye':     round(float(fiche.total_paye_sql), 2),
        'reste':          fiche.reste_a_payer,
        'reliquat':       round(float(fiche.reliquat_anterieur or 0), 2),
        'reliquat_restant': fiche.reliquat_restant,
        'du_global':      fiche.reste_a_payer_global,
    }


def construire_parcours(eleve):
    """Rend le parcours complet de l'enfant.

    Les totaux méritent une explication :
      - `total_paye` est un cumul sur toutes les années, il s'additionne ;
      - la dette, NON. Un impayé est reconduit d'une année sur l'autre en
        reliquat : sommer les restes annuels compterait la même ardoise
        autant de fois qu'elle a traversé d'exercices. La dette réelle est
        celle de la DERNIÈRE fiche, qui porte déjà tout l'historique.
    """
    fiches = fiches_du_meme_eleve(eleve)
    if not fiches:
        fiches = [eleve]

    annees = [_ligne_annee(f) for f in fiches]
    premiere, derniere = fiches[0], fiches[-1]

    return {
        'eleve_id':         str(derniere.id),
        'nom_complet':      derniere.nom_complet,
        'matricule':        derniere.matricule or '',
        'matricule_ancien': derniere.matricule_ancien or '',
        'genre':            derniere.genre,
        'date_naissance':   derniere.date_naissance,
        'lieu_naissance':   derniere.lieu_naissance,
        'nom_pere':         derniere.nom_pere,
        'nom_mere':         derniere.nom_mere,
        'nom_tuteur':       derniere.nom_tuteur,
        'telephone_pere':   derniere.telephone_pere,
        'telephone_mere':   derniere.telephone_mere,
        # L'entrée est figée sur la fiche ; à défaut (base d'avant le rebasage)
        # on retombe sur la première fiche connue.
        'annee_entree':     derniere.annee_entree or premiere.exercice.annee_scolaire,
        'date_entree':      derniere.date_entree or premiere.date_inscription,
        'annee_sortie':     derniere.exercice.annee_scolaire,
        'statut':           derniere.statut,
        'statut_libelle':   dict(Eleve.STATUT_CHOICES).get(derniere.statut, derniere.statut),
        'est_sorti':        derniere.statut in STATUTS_SORTIE,
        'section':          derniere.section.nom if derniere.section else '',
        'classe':           derniere.classe.nom if derniere.classe_id else '',
        'nb_annees':        len(annees),
        'annees':           annees,
        'total_attendu':    round(sum(a['total_attendu'] for a in annees), 2),
        'total_paye':       round(sum(a['total_paye'] for a in annees), 2),
        # Dette réelle aujourd'hui — surtout PAS la somme des restes annuels.
        'du_actuel':        annees[-1]['du_global'],
    }


def anciens_eleves(tenant, recherche='', statut=''):
    """Les élèves qui ont quitté l'établissement, un par enfant.

    Indépendant de l'exercice actif : c'est la base historique, on doit y
    retrouver un diplômé de 2019 comme un transféré de l'an dernier. Le
    statut retenu est celui de la DERNIÈRE fiche — un élève réinscrit après
    un abandon n'est plus un ancien.
    """
    fiches = list(annoter(
        Eleve.objects.filter(tenant=tenant)
                     .select_related('section', 'classe', 'exercice')
    ).order_by('exercice__date_debut'))

    q = (recherche or '').strip().lower()
    lignes = []
    for groupe in grouper_par_eleve(fiches):
        groupe.sort(key=lambda f: f.exercice.date_debut)
        derniere = groupe[-1]
        if derniere.statut not in STATUTS_SORTIE:
            continue
        if statut and derniere.statut != statut:
            continue
        if q and q not in derniere.nom_complet.lower() \
              and q not in (derniere.matricule or '').lower() \
              and q not in (derniere.matricule_ancien or '').lower():
            continue

        premiere = groupe[0]
        derniere._total_paye_cache = derniere.total_paye_sql
        lignes.append({
            'eleve_id':       str(derniere.id),
            'matricule':      derniere.matricule or '',
            'matricule_ancien': derniere.matricule_ancien or '',
            'nom_complet':    derniere.nom_complet,
            'genre':          derniere.genre,
            'annee_entree':   derniere.annee_entree or premiere.exercice.annee_scolaire,
            'date_entree':    derniere.date_entree or premiere.date_inscription,
            'annee_sortie':   derniere.exercice.annee_scolaire,
            'statut':         derniere.statut,
            'statut_libelle': dict(Eleve.STATUT_CHOICES).get(derniere.statut, derniere.statut),
            'derniere_classe': (derniere.classe.nom if derniere.classe_id
                                else (derniere.section.nom if derniere.section else '')),
            'nb_annees':      len(groupe),
            'total_paye':     round(sum(float(f.total_paye_sql) for f in groupe), 2),
            'solde_du':       derniere.reste_a_payer_global,
        })

    lignes.sort(key=lambda l: (l['annee_sortie'], l['nom_complet']), reverse=True)
    return {
        'lignes':      lignes,
        'nb':          len(lignes),
        'nb_diplomes': sum(1 for l in lignes if l['statut'] == 'DIPLOME'),
        'total_du':    round(sum(l['solde_du'] for l in lignes), 2),
    }
