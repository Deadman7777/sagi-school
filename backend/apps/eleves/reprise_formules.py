"""Reprise d'une école qui a démarré avec le contournement « une section par formule ».

Avant les formules, une crèche créait une section par horaire (« Crèche
08H-13H », « Crèche 08H-17H »…) et une section « Garderie ponctuelle » à
mensualité nulle, dont les passages s'encaissaient en « Frais divers ». Ce
module fait passer ces données au fonctionnement actuel, sans toucher à
l'argent déjà encaissé.

**Regrouper des sections en formules.** Chaque section source devient une
formule de la section cible ; ses élèves y passent, avec leur ancienne section
comme formule depuis le début de l'année. Le dû de chaque élève doit rester
IDENTIQUE : c'est vérifié élève par élève, et la moindre différence (frais
d'entrée qui ne sont pas les mêmes, par exemple) bloque l'application tant que
l'école ne l'a pas explicitement acceptée.

**La simulation est l'application, annulée.** Même code, même transaction,
défaite à la fin : ce que l'aperçu annonce est exactement ce qui sera fait.

**Reclasser un passage de garderie.** Un montant saisi en « Frais divers » pour
un enfant désormais gardé à la journée passe en garderie sur le mois indiqué.
Le total du reçu, sa date et sa comptabilité ne changent pas : toutes ces
catégories créditent le même produit (706). Seule la lecture mois par mois
change — le paiement solde enfin les jours de présence.
"""
import datetime

from django.db import transaction

from apps.paiements.models import Paiement

from .models import Eleve, FormuleEleve, FormuleSection, Section

# Ce qui doit être identique entre les sections regroupées : ce sont les frais
# que la section cible appliquera désormais à tous.
FRAIS_COMMUNS = {
    'frais_inscription':    "Frais d'inscription",
    'frais_renouvellement': 'Frais de renouvellement',
    'frais_uniforme':       'Uniforme',
    'frais_fournitures':    'Fournitures',
}


class RepriseErreur(ValueError):
    """Opération refusée, avec un message destiné à l'utilisateur."""


class _Annuler(Exception):
    """Défait la transaction de simulation."""


def _eleves_concernes(tenant, sections):
    """Fiches des exercices OUVERTS : une année clôturée ne se réécrit pas."""
    return (Eleve.objects.filter(tenant=tenant, section__in=sections, exercice__cloture=False)
            .select_related('section', 'exercice', 'tenant')
            .prefetch_related('abonnements__service', 'formules_eleve__formule'))


def _du(eleve_id):
    """Dû recalculé depuis la base (aucun cache d'instance)."""
    e = (Eleve.objects.select_related('section', 'exercice', 'tenant')
         .prefetch_related('abonnements__service', 'formules_eleve__formule').get(pk=eleve_id))
    return round(float(e.total_attendu), 2)


def regrouper_en_formules(tenant, cible_id, formules, appliquer=False, forcer=False, auteur=''):
    """Regroupe des sections en formules de la section cible.

    `formules` : [{"section": id, "nom": "08H-13H"}] — la cible peut en faire
    partie (sa propre mensualité devient alors une formule).
    Rend le rapport ; n'écrit rien si `appliquer` est faux ou si un dû change
    sans `forcer`.
    """
    cible = Section.objects.filter(tenant=tenant, pk=cible_id).first()
    if cible is None:
        raise RepriseErreur('Section cible introuvable.')
    if not formules:
        raise RepriseErreur('Choisissez au moins une section à transformer en formule.')
    ids = [str(f.get('section') or '') for f in formules]
    if len(set(ids)) != len(ids):
        raise RepriseErreur('Une même section est choisie deux fois.')
    sources = {str(s.id): s for s in Section.objects.filter(tenant=tenant, pk__in=ids)}
    if len(sources) != len(ids):
        raise RepriseErreur('Une section choisie est introuvable.')
    noms = [str(f.get('nom') or '').strip() or sources[str(f['section'])].nom for f in formules]
    if len({n.lower() for n in noms}) != len(noms):
        raise RepriseErreur('Deux formules porteraient le même nom.')
    for s in [cible, *sources.values()]:
        if s.mode_tarif == 'JOURNEE':
            raise RepriseErreur(f"« {s.nom} » est facturée à la journée : elle ne devient pas une formule.")
    if cible.formules.exists():
        raise RepriseErreur(f"« {cible.nom} » a déjà des formules : regroupez vers une section qui n'en a pas.")

    ecarts_frais = []
    for s in sources.values():
        if s.id == cible.id:
            continue
        for champ, libelle in FRAIS_COMMUNS.items():
            if getattr(s, champ) != getattr(cible, champ):
                ecarts_frais.append(f"{s.nom} — {libelle} : {int(getattr(s, champ))} F "
                                    f"(« {cible.nom} » : {int(getattr(cible, champ))} F)")

    eleves = list(_eleves_concernes(tenant, list(sources.values())))
    avant = {e.id: round(float(e.total_attendu), 2) for e in eleves}

    rapport = {'cible': cible.nom, 'nb_eleves': len(eleves), 'ecarts_frais': ecarts_frais,
               'formules': [], 'differences': [], 'sections_videes': [], 'applique': False}
    try:
        with transaction.atomic():
            par_section = {}
            for ordre, (f, nom) in enumerate(zip(formules, noms)):
                source = sources[str(f['section'])]
                formule = FormuleSection.objects.create(
                    tenant=tenant, section=cible, nom=nom[:100],
                    frais_mensualite=source.frais_mensualite, ordre=ordre)
                par_section[source.id] = formule
                rapport['formules'].append({'nom': formule.nom, 'mensualite': float(formule.frais_mensualite),
                                            'section_source': source.nom,
                                            'nb_eleves': sum(1 for e in eleves if e.section_id == source.id)})
            for e in eleves:
                formule = par_section[e.section_id]
                Eleve.objects.filter(pk=e.pk).update(section=cible)
                FormuleEleve.objects.filter(eleve=e).delete()
                e.section = cible
                from .echeancier import mois_factures
                mois = mois_factures(e, jusqu_a_la_sortie=False)
                debut = mois[0] if mois else e.exercice.date_debut.month
                FormuleEleve.objects.create(tenant=tenant, eleve=e, formule=formule, mois_debut=debut,
                                            saisi_par=auteur or 'Reprise')
            for e in eleves:
                apres = _du(e.pk)
                if abs(apres - avant[e.id]) >= 1:
                    rapport['differences'].append({'eleve': str(e.id), 'nom_complet': e.nom_complet,
                                                   'avant': avant[e.id], 'apres': apres})
            rapport['sections_videes'] = [s.nom for s in sources.values()
                                          if s.id != cible.id and not s.eleves.exists()]
            bloque = bool(rapport['differences']) and not forcer
            rapport['bloque'] = bloque
            if not appliquer or bloque:
                raise _Annuler()
            rapport['applique'] = True
    except _Annuler:
        pass
    return rapport


# ── Garderie saisie en « Frais divers » ──────────────────────────────────

def _divers_manuel(p):
    services = sum(float(s.get('montant') or 0) for s in (p.services_regles or []))
    return round(max(float(p.montant_divers or 0) - services, 0.0), 2)


def paiements_garderie_a_reclasser(tenant):
    """Paiements des enfants à la journée qui portent encore des « Frais divers »."""
    from .garderie import exercice_courant
    exercice = exercice_courant(tenant)
    if exercice is None:
        return []
    qs = (Paiement.objects.filter(tenant=tenant, exercice=exercice, statut='ACTIF',
                                  eleve__section__mode_tarif='JOURNEE', montant_divers__gt=0)
          .select_related('eleve').order_by('date_paiement', 'no_piece'))
    lignes = []
    for p in qs:
        divers = _divers_manuel(p)
        if divers <= 0:
            continue
        lignes.append({'paiement': str(p.id), 'no_piece': p.no_piece, 'date': p.date_paiement,
                       'eleve': str(p.eleve_id), 'nom_complet': p.eleve.nom_complet,
                       'divers': divers, 'observations': p.observations or '',
                       'mois_propose': p.date_paiement.month if p.date_paiement else None})
    return lignes


def reclasser_paiement_garderie(tenant, paiement_id, mois, montant=None, auteur=''):
    """Passe tout ou partie des « Frais divers » d'un paiement en garderie du mois `mois`."""
    with transaction.atomic():
        return _reclasser(tenant, paiement_id, mois, montant)


def _reclasser(tenant, paiement_id, mois, montant):
    p = (Paiement.objects.select_for_update(of=('self',))
         .filter(tenant=tenant, pk=paiement_id, statut='ACTIF')
         .select_related('eleve__section').first())
    if p is None:
        raise RepriseErreur('Paiement introuvable ou annulé.')
    if not p.eleve_id or not p.eleve.a_la_journee:
        raise RepriseErreur("Ce paiement n'est pas celui d'un enfant gardé à la journée.")
    try:
        mois = int(mois)
    except (TypeError, ValueError):
        mois = 0
    if not 1 <= mois <= 12:
        raise RepriseErreur('Mois invalide.')
    divers = _divers_manuel(p)
    montant = divers if montant in (None, '') else round(float(montant), 2)
    if montant <= 0 or montant > divers:
        raise RepriseErreur(f'Le montant doit être compris entre 1 et {int(divers)} F.')
    mois_actuels = [int(m) for m in (p.mois_regles or [])]
    if float(p.montant_mensualite or 0) > 0 and mois_actuels and mois_actuels != [mois]:
        raise RepriseErreur("Ce paiement règle déjà d'autres mois : il ne peut pas être reclassé ici.")
    p.montant_divers = float(p.montant_divers) - montant
    p.montant_mensualite = float(p.montant_mensualite or 0) + montant
    p.mois_regles = [mois]
    trace = f"Reclassé en garderie ({int(montant)} F, mois {mois}) le {datetime.date.today():%d/%m/%Y}"
    p.observations = f"{p.observations}\n{trace}".strip() if p.observations else trace
    p.save(update_fields=['montant_divers', 'montant_mensualite', 'mois_regles', 'observations',
                          'updated_at'])
    return p
