"""Liaison Ressources financières (GMRF) ↔ Gouvernance, sans double saisie.

Les deux modules restent distincts, chacun dans son rôle :

* **GMRF encaisse et comptabilise.** Un financement reçu ou un prêt débloqué
  y écrit l'encaissement : débit du compte de trésorerie (571, 5521, 521…),
  crédit du compte de ressource (7588, 71, 14, 101, 162…).
* **Gouvernance suit l'emploi des fonds.** Une ressource y porte l'enveloppe,
  ses affectations et sa consommation, lue au grand livre.

Avant, rien ne reliait les deux : une subvention saisie dans GMRF devait être
ressaisie à la main dans Gouvernance (double enregistrement), et une ressource
créée dans Gouvernance n'entrait ni en trésorerie ni en comptabilité — son
compte de trésorerie n'était qu'une mention facultative.

Désormais il n'y a qu'un chemin :

* GMRF → Gouvernance : tout financement reçu et tout prêt débloqué crée (ou
  met à jour) SA ressource, avec le compte de trésorerie qui a reçu les fonds.
* Gouvernance → GMRF : mobiliser une ressource depuis Gouvernance crée le
  financement GMRF correspondant, donc l'écriture d'encaissement, puis la
  ressource reliée. Un prêt, qui a besoin de son tableau d'amortissement, se
  saisit dans GMRF › Prêts et apparaît ensuite ici tout seul.

Une contrainte d'unicité (une ressource par financement, une par prêt) rend
la double saisie impossible au niveau de la base.
"""
from decimal import Decimal

from django.db import transaction

# Type de ressource (Gouvernance) → code du type de financement GMRF qui
# l'encaisse. Le type GMRF porte le compte de ressource crédité.
TYPE_VERS_GMRF = {
    'DON':               'DON',
    'SUBVENTION':        'SUBV_EXPLOIT',
    'PARTENAIRE':        'PARTENARIAT',
    'PROJET':            'SUBV_EXPLOIT',
    'COTISATION_EXCEPT': 'REVENU_EXCEPT',
    'FONDS_PROPRES':     'APPORT',
    'AVANCE_TRESO':      'AVANCE',
    'AUTRE':             'AUTRE',
}
# Catégorie GMRF → type de ressource affiché dans Gouvernance.
CATEGORIE_VERS_TYPE = {
    'DON': 'DON', 'SUBV_INVEST': 'SUBVENTION', 'SUBV_EXPLOIT': 'SUBVENTION',
    'PARTENARIAT': 'PARTENAIRE', 'CROWDFUNDING': 'PARTENAIRE',
    'REVENU_EXCEPT': 'COTISATION_EXCEPT', 'APPORT': 'FONDS_PROPRES',
    'AVANCE': 'AVANCE_TRESO', 'PRET': 'PRET', 'NATT': 'AUTRE', 'AUTRE': 'AUTRE',
}
# Déjà encaissées par le module Paiements : une enveloppe de suivi, sans
# nouvel encaissement (sinon l'argent des familles serait compté deux fois).
SANS_ENCAISSEMENT = {'RECETTES_SCOLAIRES'}


class LiaisonRefusee(ValueError):
    """Opération refusée, avec le message à montrer à l'utilisateur."""


def _prochaine_reference(tenant):
    from .models import Ressource
    from .views import _next_code
    return _next_code(tenant, Ressource, 'RES', field='reference')


def type_financement_pour(tenant, type_ressource):
    """Type de financement GMRF qui encaisse ce type de ressource.

    Les types APPORT et AVANCE sont récents : une école installée avant eux
    ne les a pas encore, on les crée à la demande avec leur compte par défaut.
    """
    from apps.gmrf.models import TypeFinancement
    from apps.gmrf.views import TYPES_DEFAUT, _seed_types

    code = TYPE_VERS_GMRF.get(type_ressource, 'AUTRE')
    _seed_types(tenant)
    tf = TypeFinancement.objects.filter(tenant=tenant, code=code).first()
    if tf is None:
        ligne = next(l for l in TYPES_DEFAUT if l[0] == code)
        _, libelle, categorie, nature, compte = ligne
        tf = TypeFinancement.objects.create(
            tenant=tenant, code=code, libelle=libelle, categorie=categorie,
            nature_comptable=nature, compte_ressource=compte, est_systeme=True)
    return tf


def _etiqueter_ecritures(tenant, source, source_id, ressource):
    """Relie l'écriture d'encaissement à la ressource (traçabilité).

    Seules les lignes de trésorerie et de ressource sont étiquetées : une ligne
    de charge (frais de dossier d'un prêt) compterait sinon comme consommation
    de la ressource.
    """
    from apps.comptabilite.models import JournalEntry
    (JournalEntry.objects.filter(tenant=tenant, source=source, source_id=source_id)
     .exclude(no_compte__startswith='6').exclude(no_compte__startswith='2')
     .update(ressource=ressource))


def _statut_si_annule(tenant, ressource):
    """Une ressource déjà consommée reste lisible (clôturée) ; sinon annulée."""
    from .services import consommation_ressource
    return 'CLOTUREE' if consommation_ressource(tenant, ressource.id) else 'ANNULEE'


@transaction.atomic
def suivre_financement(financement, **complements):
    """Crée ou met à jour la ressource qui suit ce financement GMRF.

    Appelé à chaque changement d'état du financement (reçu, annulé). Un
    financement seulement attendu n'a pas encore de ressource : il n'y a
    pas encore d'argent à suivre.
    """
    from .models import Ressource

    tenant = financement.tenant
    ressource = Ressource.objects.filter(tenant=tenant, financement=financement).first()
    if financement.statut == 'ATTENDU' and ressource is None:
        return None
    if ressource is None:
        ressource = Ressource(tenant=tenant, financement=financement,
                              reference=complements.pop('reference', None) or _prochaine_reference(tenant))
    ressource.type_ressource = complements.pop(
        'type_ressource', CATEGORIE_VERS_TYPE.get(financement.type_financement.categorie, 'AUTRE'))
    ressource.libelle = financement.libelle
    ressource.organisme = financement.source
    ressource.montant = financement.montant
    ressource.date_ressource = financement.date_reception
    ressource.compte_tresorerie = financement.compte_tresorerie
    for champ, valeur in complements.items():
        setattr(ressource, champ, valeur)
    if not ressource.observations:
        ressource.observations = f'Suivi du financement {financement.reference} (Ressources financières).'
    if financement.statut == 'ANNULE' and ressource.pk:
        ressource.statut = _statut_si_annule(tenant, ressource)
    elif financement.statut == 'RECU' and ressource.statut == 'ANNULEE':
        ressource.statut = 'ACTIVE'
    ressource.save()
    _etiqueter_ecritures(tenant, 'GMRF_FIN', financement.id, ressource)
    return ressource


@transaction.atomic
def suivre_pret(pret):
    """Crée ou met à jour la ressource qui suit ce prêt GMRF (déblocage)."""
    from .models import Ressource

    tenant = pret.tenant
    ressource = Ressource.objects.filter(tenant=tenant, pret=pret).first()
    if ressource is None:
        ressource = Ressource(tenant=tenant, pret=pret, reference=_prochaine_reference(tenant),
                              observations=f'Suivi du prêt {pret.reference} (Ressources financières).')
    ressource.type_ressource = 'PRET'
    ressource.libelle = pret.objet or f'Prêt {pret.organisme_preteur}'
    ressource.organisme = pret.organisme_preteur
    ressource.montant = pret.montant
    ressource.date_ressource = pret.date_deblocage
    ressource.compte_tresorerie = pret.compte_tresorerie
    ressource.taux = pret.taux_interet or Decimal('0')
    ressource.save()
    _etiqueter_ecritures(tenant, 'GMRF_PRET', pret.id, ressource)
    return ressource


@transaction.atomic
def mobiliser(tenant, donnees):
    """Mobilise une ressource depuis Gouvernance, par le chemin de GMRF.

    `donnees` : type_ressource, libelle, organisme, montant, date_ressource,
    compte_tresorerie, encaissement ('RECU' par défaut, ou 'ATTENDU'),
    convention, observations, projet, reference.

    Retourne (ressource, financement) ; ressource vaut None tant que les fonds
    sont seulement attendus. Lève LiaisonRefusee avec un message clair quand l'opération doit se
    faire ailleurs ou manque d'une information.
    """
    from apps.gmrf import services as gmrf
    from .models import Ressource

    type_ressource = donnees.get('type_ressource') or 'AUTRE'
    complements = {k: donnees[k] for k in ('convention', 'observations', 'projet', 'reference')
                   if donnees.get(k) not in (None, '')}

    if type_ressource == 'PRET':
        raise LiaisonRefusee(
            "Un prêt s'enregistre dans Ressources financières › Prêts, avec son tableau "
            "d'amortissement. Il apparaît ensuite ici automatiquement, avec son compte de trésorerie.")

    if type_ressource in SANS_ENCAISSEMENT:
        # Enveloppe de suivi : l'argent est déjà entré par les paiements des familles.
        return Ressource.objects.create(
            tenant=tenant, reference=complements.pop('reference', None) or _prochaine_reference(tenant),
            type_ressource=type_ressource, libelle=donnees['libelle'],
            organisme=donnees.get('organisme', ''), montant=donnees['montant'],
            date_ressource=donnees.get('date_ressource'),
            compte_tresorerie=donnees.get('compte_tresorerie', ''),
            taux=donnees.get('taux') or Decimal('0'), **complements), None

    encaissement = donnees.get('encaissement') or 'RECU'
    compte = (donnees.get('compte_tresorerie') or '').strip()
    if encaissement == 'RECU' and not compte.startswith('5'):
        raise LiaisonRefusee(
            "Indiquez le compte de trésorerie qui reçoit les fonds (caisse, banque, Wave…) : "
            "l'encaissement est comptabilisé sur ce compte.")

    tf = type_financement_pour(tenant, type_ressource)
    try:
        financement = gmrf.creer_financement(
            tenant, tf, donnees['montant'], libelle=donnees['libelle'],
            source=donnees.get('organisme', ''), statut=encaissement,
            date_reception=donnees.get('date_ressource'),
            compte_tresorerie=compte or tf.compte_tresorerie_defaut,
            observations=donnees.get('observations', ''))
    except ValueError as exc:
        raise LiaisonRefusee(str(exc))

    if encaissement == 'ATTENDU':
        # Pas d'argent reçu : la ressource naîtra à l'encaissement, dans GMRF.
        return None, financement
    return suivre_financement(financement, type_ressource=type_ressource, **complements), financement


def origine(ressource):
    """D'où vient la ressource, pour l'affichage : (code, référence, statut)."""
    if ressource.financement_id:
        f = ressource.financement
        return 'FINANCEMENT', f.reference, f.get_statut_display()
    if ressource.pret_id:
        p = ressource.pret
        return 'PRET', p.reference, p.get_statut_display()
    return 'SAISIE', '', ''
