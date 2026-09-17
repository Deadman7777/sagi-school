"""Garderie facturée à la journée : l'appel du jour, et le dû qui en découle.

Une crèche accueille dans la même classe des enfants au mois et d'autres à la
journée (½ journée, journée). Pour ces derniers, rien n'est dû d'avance, et les
familles ne paient pas au même rythme : chaque soir, le vendredi pour la
semaine, en fin de mois sur relevé. Une seule règle tient pour tous :

**Le dû naît de la présence.** Chaque jour coché à l'appel ajoute son tarif au
mois où il tombe. Le mois devient alors une ligne ordinaire de l'échéancier
(`Eleve.du_du_mois`) : le guichet, la fiche, les alertes, le cahier mensuel et
les relances le lisent là, sans calcul à part. Un paiement s'y impute comme une
mensualité — sur les mois cochés au guichet, sinon sur les plus anciens.

**Le montant est figé à la saisie** (`PresenceGarderie.montant`) : réviser un
tarif ne réécrit pas les jours déjà gardés.
"""
import datetime
from collections import defaultdict
from decimal import Decimal

from django.db import transaction

from .models import Eleve, PresenceGarderie

# Attribut où `echeancier.precharger` dépose les présences d'un élève : une
# requête pour toute l'école au lieu d'une par fiche.
PREFETCH_PRESENCES = 'presences_echeancier'

FORMULES = dict(PresenceGarderie.FORMULE_CHOICES)


class GarderieErreur(ValueError):
    """Opération refusée, avec un message destiné à l'utilisateur."""


def _presences(eleve):
    cache = getattr(eleve, PREFETCH_PRESENCES, None)
    if cache is not None:
        return cache
    if not eleve.pk:
        return []
    return list(PresenceGarderie.objects.filter(tenant_id=eleve.tenant_id, eleve=eleve)
                .only('date', 'formule', 'montant'))


def _par_mois(eleve):
    """{mois: [présences]} — calculé une fois par instance d'élève."""
    cache = getattr(eleve, '_garderie_par_mois', None)
    if cache is None:
        cache = defaultdict(list)
        for p in _presences(eleve):
            cache[p.date.month].append(p)
        eleve._garderie_par_mois = cache
    return cache


def _jours_du_mois(eleve, mois):
    """Présences du mois `mois` de l'exercice de la fiche, année civile vérifiée."""
    from .echeancier import _annee_du_mois
    jours = _par_mois(eleve).get(int(mois), [])
    if not eleve.exercice_id:
        return jours
    annee = _annee_du_mois(eleve.exercice, int(mois))
    return [p for p in jours if p.date.year == annee]


def du_presences_du_mois(eleve, mois):
    """Somme des jours de garde du mois (numéro 1..12 de l'exercice de la fiche)."""
    return float(sum((p.montant for p in _jours_du_mois(eleve, mois)), Decimal('0')))


def mois_avec_presences(eleve):
    return sorted(m for m, jours in _par_mois(eleve).items() if jours)


def detail_du_mois(eleve, mois):
    """{'demi': n, 'journee': n, 'montant': total, 'jours': [dates]} pour un mois."""
    jours = sorted(_jours_du_mois(eleve, mois), key=lambda p: p.date)
    return {
        'demi':    sum(1 for p in jours if p.formule == 'DEMI_JOURNEE'),
        'journee': sum(1 for p in jours if p.formule == 'JOURNEE'),
        'montant': float(sum((p.montant for p in jours), Decimal('0'))),
        'jours':   [p.date for p in jours],
    }


def libelle_detail(detail):
    """« 3 × ½ journée, 2 × journée » — vide s'il n'y a aucun jour."""
    parties = []
    if detail['demi']:
        parties.append(f"{detail['demi']} × ½ journée")
    if detail['journee']:
        parties.append(f"{detail['journee']} × journée")
    return ', '.join(parties)


# ── L'appel du jour ──────────────────────────────────────────────────────

def exercice_courant(tenant):
    from apps.paiements.models import Exercice
    return Exercice.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()


def enfants_a_la_journee(tenant, exercice, classe_id=None):
    from .parcours import eleves_presents
    qs = eleves_presents(Eleve.objects.filter(
        tenant=tenant, exercice=exercice, section__mode_tarif='JOURNEE'))
    if classe_id:
        qs = qs.filter(classe_id=classe_id)
    return qs.select_related('section', 'classe')


def _verifier_date(exercice, jour):
    if exercice is None:
        raise GarderieErreur("Aucun exercice ouvert : créez l'année scolaire avant l'appel.")
    if jour > datetime.date.today():
        raise GarderieErreur("On ne fait pas l'appel d'un jour à venir.")
    if not exercice.date_debut <= jour <= exercice.date_fin:
        raise GarderieErreur(
            f"Le {jour:%d/%m/%Y} est hors de l'année scolaire {exercice.annee_scolaire} "
            f"({exercice.date_debut:%d/%m/%Y} – {exercice.date_fin:%d/%m/%Y}).")


def appel_du_jour(tenant, jour, classe_id=None):
    """Les enfants à la journée et leur présence ce jour-là."""
    exercice = exercice_courant(tenant)
    _verifier_date(exercice, jour)
    from .tri import cle_nom
    # Ordre alphabétique d'une liste d'école : nom de famille, puis prénoms.
    enfants = sorted(enfants_a_la_journee(tenant, exercice, classe_id), key=lambda e: cle_nom(e.nom_complet))
    presences = {p.eleve_id: p for p in PresenceGarderie.objects.filter(
        tenant=tenant, date=jour, eleve__in=enfants)}
    lignes = []
    for e in enfants:
        p = presences.get(e.id)
        lignes.append({
            'eleve': str(e.id), 'nom_complet': e.nom_complet, 'matricule': e.matricule or '',
            'classe': e.classe.nom if e.classe_id else '',
            'section': e.section.nom,
            'tarif_demi_journee': float(e.section.tarif_demi_journee),
            'tarif_journee': float(e.section.tarif_journee),
            'formule': p.formule if p else None,
            'montant': float(p.montant) if p else 0.0,
            # Hors de sa période de présence dans l'école : pas d'appel possible.
            'hors_periode': not _dans_sa_periode(e, jour),
        })
    return {'date': jour, 'exercice': exercice.annee_scolaire, 'enfants': lignes}


def _dans_sa_periode(eleve, jour):
    # Entrée dans l'année de CETTE fiche ; `date_entree` est celle de la
    # première arrivée dans l'école, des années plus tôt parfois.
    entree = eleve.date_inscription or eleve.date_entree
    if entree and jour < entree:
        return False
    if eleve.date_sortie and jour > eleve.date_sortie:
        return False
    return True


def enregistrer_appel(tenant, jour, lignes, auteur=''):
    """Enregistre l'appel : [{eleve, formule: DEMI_JOURNEE|JOURNEE|None}].

    None retire la présence. Le tarif est celui de la section AUJOURD'HUI pour
    une nouvelle présence ou un changement de formule ; une présence inchangée
    garde son montant d'origine.
    """
    exercice = exercice_courant(tenant)
    _verifier_date(exercice, jour)
    enfants = {str(e.id): e for e in enfants_a_la_journee(tenant, exercice)}
    ajoutes = modifies = retires = 0
    with transaction.atomic():
        existantes = {str(p.eleve_id): p for p in PresenceGarderie.objects.select_for_update()
                      .filter(tenant=tenant, date=jour, eleve_id__in=list(enfants))}
        for ligne in lignes:
            eid = str(ligne.get('eleve') or '')
            eleve = enfants.get(eid)
            if eleve is None:
                raise GarderieErreur("Un enfant de l'appel n'est pas gardé à la journée cette année.")
            formule = ligne.get('formule') or None
            if formule is not None and formule not in FORMULES:
                raise GarderieErreur('Formule inconnue.')
            actuelle = existantes.get(eid)
            if formule is None:
                if actuelle:
                    actuelle.delete()
                    retires += 1
                continue
            if not _dans_sa_periode(eleve, jour):
                raise GarderieErreur(
                    f"{eleve.nom_complet} n'était pas inscrit(e) à la garderie le {jour:%d/%m/%Y}.")
            tarif = eleve.section.tarif_formule(formule)
            if tarif <= 0:
                raise GarderieErreur(
                    f"La section « {eleve.section.nom} » n'a pas de tarif « {FORMULES[formule]} ». "
                    "Renseignez-le dans Paramètres → Frais Sections.")
            if actuelle is None:
                PresenceGarderie.objects.create(tenant=tenant, eleve=eleve, date=jour,
                                                formule=formule, montant=tarif, saisi_par=auteur)
                ajoutes += 1
            elif actuelle.formule != formule:
                actuelle.formule, actuelle.montant, actuelle.saisi_par = formule, tarif, auteur
                actuelle.save(update_fields=['formule', 'montant', 'saisi_par', 'updated_at'])
                modifies += 1
    return {'ajoutes': ajoutes, 'modifies': modifies, 'retires': retires}


def recap_du_mois(tenant, mois, classe_id=None):
    """Par enfant : jours du mois, dû, versé, reste — lus dans l'échéancier."""
    from .echeancier import construire_echeancier, precharger
    exercice = exercice_courant(tenant)
    if exercice is None:
        raise GarderieErreur("Aucun exercice ouvert.")
    from .tri import cle_nom
    enfants = sorted(precharger(enfants_a_la_journee(tenant, exercice, classe_id)),
                     key=lambda e: cle_nom(e.nom_complet))
    lignes = []
    for e in enfants:
        detail = detail_du_mois(e, mois)
        ligne = next((l for l in construire_echeancier(e)['lignes'] if l['mois'] == int(mois)), None)
        lignes.append({
            'eleve': str(e.id), 'nom_complet': e.nom_complet,
            'classe': e.classe.nom if e.classe_id else '',
            'demi': detail['demi'], 'journee': detail['journee'],
            'du': ligne['du'] if ligne else 0.0,
            'paye': ligne['paye'] if ligne else 0.0,
            'reste': ligne['reste'] if ligne else 0.0,
        })
    return {'mois': int(mois), 'exercice': exercice.annee_scolaire, 'enfants': lignes,
            'totaux': {k: round(sum(l[k] for l in lignes), 2) for k in ('du', 'paye', 'reste')}}
