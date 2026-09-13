"""« Mon cahier de notes mensuel » — la page de pilotage du mois.

Demande de la directrice de Shoumoul (septembre 2026) : savoir, pour un mois
donné et à l'instant présent,
  - qui a payé la mensualité du mois, qui ne l'a pas encore payée, et combien ;
  - ce qui DEVAIT entrer, ce qui est entré, ce qui reste ;
  - côté dépenses, les charges budgétées déjà payées et celles qui ne le sont
    pas encore, avec leurs écarts.

Ce module ne calcule rien de neuf. Il LIT :
  - l'échéancier de chaque élève (`apps.eleves.echeancier`), qui fait déjà foi
    sur la fiche, les relances et le suivi mensuel — le cahier ne peut donc pas
    réclamer à une famille ce que sa fiche ne réclame pas ;
  - le réalisé budgétaire (`apps.comptabilite.budget`), celui de l'écran Budget.

Deux calculs d'une même grandeur divergent toujours : le tableau de bord lit
la synthèse de ce module au lieu d'en recalculer une.
"""
import datetime

from django.db.models import Sum
from django.utils import timezone

from apps.comptabilite.budget import MOIS_CHAMPS, realise_par_mois
from apps.comptabilite.models import BudgetLigne, JournalEntry
from apps.eleves.echeancier import (NOMS_MOIS, construire_echeancier, lignes_retenues,
                                    precharger)
from apps.eleves.models import Eleve
from apps.eleves.parcours import STATUTS_SORTIE

from .models import Paiement

SEUIL = 1.0   # sous 1 FCFA, c'est un arrondi, pas une dette


def mois_de_l_exercice(exercice):
    """[(annee, mois)] du premier au dernier mois de l'exercice."""
    a, m = exercice.date_debut.year, exercice.date_debut.month
    fin = (exercice.date_fin.year, exercice.date_fin.month)
    sortie = []
    while (a, m) <= fin and len(sortie) < 24:
        sortie.append((a, m))
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return sortie


def mois_par_defaut(exercice, today=None):
    """Le mois en cours s'il appartient à l'exercice, sinon le plus proche."""
    today = today or timezone.now().date()
    mois = mois_de_l_exercice(exercice)
    courant = (today.year, today.month)
    if courant in mois:
        return courant
    return mois[-1] if mois and courant > mois[-1] else (mois[0] if mois else courant)


def _telephone(e):
    return e.telephone_tuteur or e.telephone_pere or e.telephone_mere or ''


def _eleves_du_mois(tenant, exercice):
    """Élèves concernés : présents, et sortants encore là à l'échéance.

    Un enfant parti en mars n'a rien à faire dans le cahier d'avril. Mais celui
    qui part le 20 d'un mois dont la mensualité était exigible le 5 la devait
    bien : il est retenu, et filtré par `lignes_retenues`.
    """
    return precharger(
        Eleve.objects.filter(tenant=tenant, exercice=exercice, fiche_creance=False)
        .select_related('section', 'classe', 'exercice', 'tenant'))


def scolarite_du_mois(tenant, exercice, annee, mois, today=None):
    today = today or timezone.now().date()
    payes, partiels, impayes = [], [], []
    nb_exoneres = 0

    for e in _eleves_du_mois(tenant, exercice):
        ech = construire_echeancier(e, today=today)
        ligne = next((l for l in lignes_retenues(e, ech['lignes'])
                      if l['mois'] == mois and l['annee'] == annee), None)
        if ligne is None:
            continue
        sorti = e.statut in STATUTS_SORTIE
        if ligne['du'] < SEUIL:
            nb_exoneres += 1
            continue
        item = {
            'eleve_id':    str(e.id),
            'matricule':   e.matricule or '',
            'nom_complet': e.nom_complet,
            'classe':      (e.classe.nom if e.classe_id else
                            (e.section.nom if e.section else '')),
            'telephone':   _telephone(e),
            'du':          round(ligne['du'], 2),
            'paye':        round(ligne['paye'], 2),
            'reste':       round(ligne['reste'], 2),
            'exigible_le': ligne['exigible_le'],
            'echu':        ligne['echu'],
            'sorti':       sorti,
        }
        if ligne['reste'] < SEUIL:
            payes.append(item)
        elif ligne['paye'] >= SEUIL:
            partiels.append(item)
        else:
            impayes.append(item)

    for liste in (payes, partiels, impayes):
        liste.sort(key=lambda x: (x['classe'], x['nom_complet']))

    tous = payes + partiels + impayes
    attendu = round(sum(x['du'] for x in tous), 2)
    encaisse = round(sum(x['paye'] for x in tous), 2)
    reste = round(sum(x['reste'] for x in tous), 2)
    return {
        'payes':    payes,
        'partiels': partiels,
        'impayes':  impayes,
        'totaux': {
            'nb_eleves':   len(tous),
            'nb_payes':    len(payes),
            'nb_partiels': len(partiels),
            'nb_impayes':  len(impayes),
            'nb_exoneres': nb_exoneres,
            'attendu':     attendu,
            'encaisse':    encaisse,
            'reste':       reste,
            'taux':        round(encaisse / attendu * 100, 1) if attendu else 0.0,
        },
    }


def charges_du_mois(tenant, exercice, mois):
    """Charges budgétées du mois : payées, partiellement, pas encore, dépassées."""
    lignes = []
    for l in (BudgetLigne.objects.filter(tenant=tenant, exercice=exercice)
              .order_by('no_compte', 'libelle')):
        prevu = float(getattr(l, MOIS_CHAMPS[mois - 1]))
        realise = round(realise_par_mois(tenant, exercice, l).get(mois, 0.0), 2)
        if prevu < SEUIL and abs(realise) < SEUIL:
            continue
        if prevu < SEUIL:
            etat = 'HORS_PREVISION'
        elif realise >= prevu + SEUIL:
            etat = 'DEPASSEMENT'
        elif realise >= prevu - SEUIL:
            etat = 'PAYEE'
        elif realise >= SEUIL:
            etat = 'PARTIELLE'
        else:
            etat = 'NON_PAYEE'
        lignes.append({
            'id':          str(l.id),
            'no_compte':   l.no_compte,
            'libelle':     l.libelle or l.no_compte,
            'type_charge': l.type_charge,
            'prevu':       round(prevu, 2),
            'realise':     realise,
            'reste':       round(max(prevu - realise, 0.0), 2),
            'ecart':       round(prevu - realise, 2),
            'etat':        etat,
        })

    prevu = round(sum(l['prevu'] for l in lignes), 2)
    realise = round(sum(l['realise'] for l in lignes), 2)
    return {
        'lignes': lignes,
        'totaux': {
            'prevu':        prevu,
            'realise':      realise,
            'reste':        round(sum(l['reste'] for l in lignes), 2),
            'ecart':        round(prevu - realise, 2),
            'nb_payees':    sum(1 for l in lignes if l['etat'] in ('PAYEE', 'DEPASSEMENT')),
            'nb_non_payees': sum(1 for l in lignes if l['etat'] in ('NON_PAYEE', 'PARTIELLE')),
            'nb_depassements': sum(1 for l in lignes if l['etat'] == 'DEPASSEMENT'),
        },
    }


def caisse_du_mois(tenant, exercice, annee, mois):
    """Ce qui est RÉELLEMENT entré et sorti de la trésorerie pendant le mois.

    Différent de la scolarité « encaissée pour le mois » : un parent qui règle
    en septembre la mensualité d'août fait entrer de l'argent en septembre, mais
    il solde août. Les deux chiffres ont un sens, ils ne doivent pas se
    confondre.
    """
    debut = datetime.date(annee, mois, 1)
    fin = (datetime.date(annee + 1, 1, 1) if mois == 12
           else datetime.date(annee, mois + 1, 1))
    entrees = Paiement.objects.filter(
        tenant=tenant, exercice=exercice, statut='ACTIF',
        date_paiement__gte=debut, date_paiement__lt=fin,
    ).aggregate(t=Sum('montant_inscription') + Sum('montant_mensualite')
                + Sum('montant_uniforme') + Sum('montant_fournitures')
                + Sum('montant_cantine') + Sum('montant_divers')
                + Sum('montant_reliquat'))['t'] or 0
    charges = JournalEntry.objects.filter(
        tenant=tenant, exercice=exercice, no_compte__startswith='6',
        date_ecriture__gte=debut, date_ecriture__lt=fin,
    ).aggregate(d=Sum('debit'), c=Sum('credit'))
    return {
        'entrees': round(float(entrees), 2),
        'charges': round(float(charges['d'] or 0) - float(charges['c'] or 0), 2),
    }


def cahier_mensuel(tenant, exercice, annee, mois, today=None):
    today = today or timezone.now().date()
    scol = scolarite_du_mois(tenant, exercice, annee, mois, today)
    chg = charges_du_mois(tenant, exercice, mois)
    caisse = caisse_du_mois(tenant, exercice, annee, mois)

    # Le mois en cours est-il terminé ? Un impayé du 3 du mois n'a pas le
    # même poids qu'un impayé du 30.
    debut = datetime.date(annee, mois, 1)
    fin = (datetime.date(annee + 1, 1, 1) if mois == 12
           else datetime.date(annee, mois + 1, 1)) - datetime.timedelta(days=1)
    if today > fin:
        periode, jours_restants = 'PASSE', 0
    elif today < debut:
        periode, jours_restants = 'A_VENIR', (fin - debut).days + 1
    else:
        periode, jours_restants = 'EN_COURS', (fin - today).days

    return {
        'exercice':       exercice.annee_scolaire,
        'exercice_id':    str(exercice.id),
        'annee':          annee,
        'mois':           mois,
        'libelle_mois':   f"{NOMS_MOIS.get(mois, mois)} {annee}",
        'periode':        periode,
        'jours_restants': jours_restants,
        'genere_le':      timezone.now(),
        'mois_disponibles': [
            {'annee': a, 'mois': m, 'libelle': f"{NOMS_MOIS.get(m, m)} {a}"}
            for a, m in mois_de_l_exercice(exercice)],
        'scolarite':      scol,
        'charges':        chg,
        'caisse':         caisse,
        'synthese': {
            # Ce qui devait entrer pour le mois, ce qui est entré, ce qui reste.
            'attendu':          scol['totaux']['attendu'],
            'encaisse':         scol['totaux']['encaisse'],
            'reste_a_encaisser': scol['totaux']['reste'],
            'charges_prevues':  chg['totaux']['prevu'],
            'charges_payees':   chg['totaux']['realise'],
            'charges_a_payer':  chg['totaux']['reste'],
            # Solde prévisionnel du mois si tout ce qui est dû entre et que
            # toutes les charges budgétées sont réglées.
            'solde_previsionnel': round(scol['totaux']['attendu'] - chg['totaux']['prevu'], 2),
            # Solde constaté à ce jour sur le mois.
            'solde_constate':   round(scol['totaux']['encaisse'] - chg['totaux']['realise'], 2),
        },
    }
