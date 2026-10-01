"""État des impayés par statut — le document du comité de gestion.

Demandé le 01/10/2026 : pour organiser le recouvrement, le comité veut savoir
combien d'élèves sont dans chaque statut et pour quelle somme, en commençant
par les plus critiques, avec des sous-totaux.

Ordre de recouvrement :
  1. CRITIQUE — 3 mois échus ou plus ;
  2. URGENT   — 2 mois ;
     → sous-total « prioritaires » (critique + urgent) ;
  3. ATTENTION — mois en retard : un mois passé non réglé, ou des frais
     d'entrée, ou une ardoise d'une année antérieure ;
  4. ATTENTION — mois en cours seulement : la mensualité du mois vient
     d'échoir. Au premier jour exigible du mois, tous les élèves « à jour »
     basculent ici — c'est normal, et il faut le voir à part pour ne pas
     confondre une échéance du jour avec un vrai retard ;
     → sous-total « attention » ;
  → total général.

Les statuts et les montants sont ceux de la liste des élèves : même
échéancier, même alerte (`alerte_depuis_echeancier`). Le montant d'un élève est
ce qu'on réclame aujourd'hui à la FAMILLE, ardoise antérieure comprise.
"""
import datetime

from .echeancier import SEUIL_ALERTE, alerte_depuis_echeancier, construire_echeancier, precharger
from .familles import contact_effectif
from .models import Eleve
from .parcours import STATUTS_SORTIE

GROUPES = [
    ('CRITIQUE',         'Critique — 3 mois de retard ou plus'),
    ('URGENT',           'Urgent — 2 mois de retard'),
    ('ATTENTION_RETARD', 'Attention — mois en retard'),
    ('ATTENTION_MOIS',   'Attention — mois en cours seulement'),
]
SOUS_TOTAUX = {
    'URGENT':         ('PRIORITAIRES', 'Sous-total prioritaires (critique + urgent)',
                       ('CRITIQUE', 'URGENT')),
    'ATTENTION_MOIS': ('ATTENTION', 'Sous-total attention',
                       ('ATTENTION_RETARD', 'ATTENTION_MOIS')),
}


def groupe_de(alerte, ech, today):
    """Le groupe de recouvrement d'un élève, ou None s'il ne doit rien d'exigible."""
    niveau = alerte['niveau']
    if niveau in ('CRITIQUE', 'URGENT'):
        return niveau
    if niveau != 'ATTENTION':
        return None
    impayes = [l for l in ech['lignes'] if l['reste_echu'] >= SEUIL_ALERTE]
    hors = ech['hors_mensualite'] or {}
    seul_le_mois = (
        len(impayes) == 1
        and (impayes[0]['annee'], impayes[0]['mois']) == (today.year, today.month)
        and ech['synthese']['impaye_anterieur'] < SEUIL_ALERTE
        and not (hors.get('echu') and hors.get('reste', 0) >= SEUIL_ALERTE))
    return 'ATTENTION_MOIS' if seul_le_mois else 'ATTENTION_RETARD'


def _mois_courts(mois):
    """« Octobre, Novembre » ; au-delà de trois : « Octobre → Juillet (10 mois) »."""
    if len(mois) <= 3:
        return ', '.join(mois)
    return f"{mois[0]} → {mois[-1]} ({len(mois)} mois)"


def _vide(code, libelle):
    return {'code': code, 'libelle': libelle, 'nb': 0, 'montant': 0.0,
            'anterieur': 0.0, 'annee': 0.0, 'eleves': []}


def etat_impayes(tenant, exercice, today=None):
    today = today or datetime.date.today()
    qs = precharger(Eleve.objects.filter(tenant=tenant, exercice=exercice, fiche_creance=False)
                    .exclude(statut__in=STATUTS_SORTIE)
                    .select_related('section', 'classe', 'famille')
                    .prefetch_related('famille__responsables'))

    groupes = {code: _vide(code, libelle) for code, libelle in GROUPES}
    nb_eleves = nb_a_jour = 0
    for e in qs:
        nb_eleves += 1
        ech = construire_echeancier(e, today=today)
        alerte = alerte_depuis_echeancier(ech)
        code = groupe_de(alerte, ech, today)
        if code is None:
            nb_a_jour += 1
            continue
        s = ech['synthese']
        anterieur = round(s['impaye_anterieur'], 2)
        montant = round(alerte['montant'], 2)
        contact = contact_effectif(e)
        g = groupes[code]
        g['eleves'].append({
            'id':          str(e.id),
            'matricule':   e.matricule or '',
            'nom_complet': e.nom_complet,
            'classe':      e.classe.nom if e.classe_id else (e.section.nom if e.section_id else ''),
            'contact':     contact.get('nom') or '',
            'telephone':   contact.get('telephone') or '',
            'nb_mois':     alerte['nb_mois'],
            'mois':        _mois_courts(alerte['mois']),
            'anterieur':   anterieur,
            'annee':       round(max(montant - anterieur, 0.0), 2),
            'montant':     montant,
        })

    resultat, cumul = [], {}
    for code, _ in GROUPES:
        g = groupes[code]
        g['eleves'].sort(key=lambda x: (-x['montant'], x['nom_complet']))
        g['nb'] = len(g['eleves'])
        for k in ('montant', 'anterieur', 'annee'):
            g[k] = round(sum(x[k] for x in g['eleves']), 2)
        resultat.append({'type': 'groupe', **g})
        cumul[code] = g
        if code in SOUS_TOTAUX:
            st_code, st_libelle, membres = SOUS_TOTAUX[code]
            resultat.append({
                'type': 'sous_total', 'code': st_code, 'libelle': st_libelle,
                'nb': sum(cumul[m]['nb'] for m in membres),
                **{k: round(sum(cumul[m][k] for m in membres), 2)
                   for k in ('montant', 'anterieur', 'annee')},
            })

    total = {
        'nb': sum(g['nb'] for g in groupes.values()),
        **{k: round(sum(g[k] for g in groupes.values()), 2) for k in ('montant', 'anterieur', 'annee')},
    }
    return {
        'exercice':    exercice.annee_scolaire,
        'date':        today.isoformat(),
        'nb_eleves':   nb_eleves,
        'nb_a_jour':   nb_a_jour,
        'lignes':      resultat,
        'total':       total,
    }
