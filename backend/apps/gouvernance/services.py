"""Moteur de comptabilisation du socle Gouvernance.

Comme GMRF, ce module ne fait AUCUNE saisie comptable manuelle : chaque
opération génère automatiquement des écritures dans `comptabilite.JournalEntry`
(taggées `source='TRANSFERT'`). Le Grand Livre, la Balance, les soldes de
trésorerie et le tableau de flux lisent ces écritures : la synchronisation est
donc automatique.
"""
import datetime
from decimal import Decimal, InvalidOperation

from django.db.models import Q, Sum


def _d(v):
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0')


# ── Ressources : consommation & contrôle de disponibilité (Lot 2) ─────────────
def consommation_ressource(tenant, ressource_id):
    """Montant réellement consommé sur une ressource, lu depuis le grand livre.

    Mouvement NET (débit − crédit) des écritures taggées `ressource` sur les
    comptes de charges (classe 6) et d'immobilisations (classe 2). Le net garantit
    qu'une charge extournée (modification/annulation, dont la contre-écriture porte
    la même ressource) revient à zéro. Source de vérité unique : le ledger."""
    from apps.comptabilite.models import JournalEntry
    agg = JournalEntry.objects.filter(
        tenant=tenant, ressource_id=ressource_id,
    ).filter(Q(no_compte__startswith='6') | Q(no_compte__startswith='2')).aggregate(
        d=Sum('debit'), c=Sum('credit'))
    return (agg['d'] or Decimal('0')) - (agg['c'] or Decimal('0'))


def verifier_disponibilite(tenant, ressource, montant):
    """Contrôle qu'une nouvelle dépense de `montant` tient dans l'enveloppe.

    Retourne (ok: bool, message: str, disponible: Decimal). Une ressource annulée
    est refusée. Le disponible = montant initial − déjà consommé."""
    montant = _d(montant)
    if ressource.statut == 'ANNULEE':
        return False, 'Ressource annulée', Decimal('0')
    deja = consommation_ressource(tenant, ressource.id)
    disponible = _d(ressource.montant) - deja
    if montant > disponible:
        return (False,
                f'Dépassement : disponible {disponible:.0f}, demandé {montant:.0f} '
                f'sur « {ressource.libelle} »',
                disponible)
    return True, '', disponible


# ── Rapprochement bancaire (Lot 5) ───────────────────────────────────────────
def solde_comptable_banque(compte_bancaire, date_max, tenant):
    """Solde comptable du compte bancaire = solde initial + (débits − crédits) sur
    le compte comptable jusqu'à `date_max` (inclus)."""
    from apps.comptabilite.models import JournalEntry
    agg = JournalEntry.objects.filter(
        tenant=tenant, no_compte=compte_bancaire.no_compte_comptable,
        date_ecriture__lte=date_max,
    ).aggregate(d=Sum('debit'), c=Sum('credit'))
    return _d(compte_bancaire.solde_initial) + (agg['d'] or Decimal('0')) - (agg['c'] or Decimal('0'))


def _ecritures_liees_ids(compte_bancaire, tenant):
    """Ids des écritures déjà pointées par une ligne de relevé (tout rapprochement
    de ce compte bancaire)."""
    from .models import LigneReleve
    return set(LigneReleve.objects.filter(
        tenant=tenant, rapprochement__compte_bancaire=compte_bancaire,
        journal_entry__isnull=False,
    ).values_list('journal_entry_id', flat=True))


def ecritures_non_rapprochees(compte_bancaire, exercice, tenant):
    """Écritures du compte bancaire dans le ledger non encore pointées (chèques
    émis non débités, dépôts en transit…)."""
    from apps.comptabilite.models import JournalEntry
    liees = _ecritures_liees_ids(compte_bancaire, tenant)
    return JournalEntry.objects.filter(
        tenant=tenant, exercice=exercice,
        no_compte=compte_bancaire.no_compte_comptable,
    ).exclude(id__in=liees).order_by('date_ecriture')


def rapprochement_auto(rapprochement, tenant, tolerance_jours=5):
    """Rapproche automatiquement les lignes du relevé aux écritures du ledger par
    sens + montant + date (± tolérance). Retourne le nombre de rapprochements."""
    compte = rapprochement.compte_bancaire
    dispo = list(ecritures_non_rapprochees(compte, rapprochement.exercice, tenant))
    used = set()
    n = 0
    for ligne in rapprochement.lignes.filter(statut='NON_RAPPROCHEE', journal_entry__isnull=True):
        for e in dispo:
            if e.id in used:
                continue
            montant_e = e.debit if ligne.sens == 'ENTREE' else e.credit
            if (montant_e == ligne.montant and montant_e > 0 and
                    abs((e.date_ecriture - ligne.date_operation).days) <= tolerance_jours):
                ligne.journal_entry = e
                ligne.statut = 'RAPPROCHEE'
                ligne.save(update_fields=['journal_entry', 'statut', 'updated_at'])
                used.add(e.id)
                n += 1
                break
    return n


def generer_ecriture_regularisation(ligne, compte_contrepartie, tenant, libelle_extra=''):
    """Génère l'écriture manquante pour une ligne du relevé absente des livres
    (agios, frais, intérêts reçus…) et pointe la ligne sur l'écriture créée.

      • SORTIE (frais/agios) : D compte_contrepartie / C compte bancaire
      • ENTREE (intérêts…)   : D compte bancaire / C compte_contrepartie
    """
    from apps.comptabilite.models import JournalEntry
    rap = ligne.rapprochement
    compte_banque = rap.compte_bancaire.no_compte_comptable
    # N° de pièce séquentiel dans le rapprochement (RAP-<ref>-Rn) — évite toute
    # collision entre régularisations d'un même rapprochement.
    # .order_by() VIDE avant .distinct() : JournalEntry.Meta déclare un ordering,
    # et Django ajoute les colonnes de tri au SELECT d'un DISTINCT. Sans ce reset,
    # une régularisation multi-lignes est comptée autant de fois qu'elle a de
    # lignes et la séquence saute (R1, R3, R5…).
    n = JournalEntry.objects.filter(
        tenant=tenant, source='RAPPRO_REG', no_piece__startswith=f"RAP-{rap.reference}-R"
    ).order_by().values('no_piece').distinct().count() + 1
    ref = f"RAP-{rap.reference}-R{n}"
    label = f"Régularisation rapprochement — {ligne.libelle}" + (f" {libelle_extra}" if libelle_extra else '')
    m = _d(ligne.montant)
    date = ligne.date_operation

    if ligne.sens == 'SORTIE':
        lignes = [
            (compte_contrepartie, m, Decimal('0'), 1),
            (compte_banque,       Decimal('0'), m, 2),
        ]
    else:
        lignes = [
            (compte_banque,       m, Decimal('0'), 1),
            (compte_contrepartie, Decimal('0'), m, 2),
        ]
    objs = [
        JournalEntry(tenant=tenant, exercice=rap.exercice, no_piece=ref,
                     date_ecriture=date, no_compte=nc, libelle=label,
                     debit=db, credit=cr, source='RAPPRO_REG', source_id=ligne.id, ordre=o)
        for nc, db, cr, o in lignes
    ]
    JournalEntry.objects.bulk_create(objs)
    # Pointe la ligne sur l'écriture bancaire créée.
    ecriture_banque = next(o for o in objs if o.no_compte == compte_banque)
    ligne.journal_entry = ecriture_banque
    ligne.statut = 'REGULARISEE'
    ligne.save(update_fields=['journal_entry', 'statut', 'updated_at'])
    return ecriture_banque


# ── Provisions SYSCOHADA (Lot 4) ─────────────────────────────────────────────
def generer_ecriture_dotation(provision, tenant):
    """Dotation : D compte_dotation (charge) / C compte_provision (bilan)."""
    from apps.comptabilite.models import JournalEntry
    if JournalEntry.objects.filter(tenant=tenant, source='PROVISION', source_id=provision.id).exists():
        return
    ref   = provision.reference
    date  = provision.date_dotation or datetime.date.today()
    m     = _d(provision.montant)
    label = f"Dotation {provision.get_type_provision_display().lower()} — {provision.libelle}"
    JournalEntry.objects.bulk_create([
        JournalEntry(tenant=tenant, exercice=provision.exercice, no_piece=ref, date_ecriture=date,
                     no_compte=provision.compte_dotation, libelle=label,
                     debit=m, credit=0, source='PROVISION', source_id=provision.id, ordre=1),
        JournalEntry(tenant=tenant, exercice=provision.exercice, no_piece=ref, date_ecriture=date,
                     no_compte=provision.compte_provision, libelle=label,
                     debit=0, credit=m, source='PROVISION', source_id=provision.id, ordre=2),
    ])


def generer_ecriture_reprise(provision, montant, tenant, date=None):
    """Reprise (partielle/totale) : D compte_provision / C compte_reprise (produit)."""
    from apps.comptabilite.models import JournalEntry
    from django.db.models import Max
    m = _d(montant)
    if m <= 0:
        return
    # Numéro de pièce séquentiel par provision (REP-<ref>-n).
    n = JournalEntry.objects.filter(
        tenant=tenant, source='PROVISION_REPRISE', source_id=provision.id).count() + 1
    ref = f"REP-{provision.reference}-{n}"
    date = date or datetime.date.today()
    label = f"Reprise provision {provision.reference} — {provision.libelle}"
    JournalEntry.objects.bulk_create([
        JournalEntry(tenant=tenant, exercice=provision.exercice, no_piece=ref, date_ecriture=date,
                     no_compte=provision.compte_provision, libelle=label,
                     debit=m, credit=0, source='PROVISION_REPRISE', source_id=provision.id, ordre=1),
        JournalEntry(tenant=tenant, exercice=provision.exercice, no_piece=ref, date_ecriture=date,
                     no_compte=provision.compte_reprise, libelle=label,
                     debit=0, credit=m, source='PROVISION_REPRISE', source_id=provision.id, ordre=2),
    ])


def annuler_ecriture_provision(provision, tenant):
    """Extourne la dotation ET les reprises d'une provision annulée."""
    from apps.comptabilite.models import JournalEntry
    if JournalEntry.objects.filter(tenant=tenant, source='ANNUL_PROVISION',
                                   source_id=provision.id).exists():
        return
    origines = JournalEntry.objects.filter(
        tenant=tenant, source__in=('PROVISION', 'PROVISION_REPRISE'),
        source_id=provision.id).order_by('created_at', 'ordre')
    if not origines.exists():
        return
    ref = f"ANN-{provision.reference}"
    contre = [
        JournalEntry(
            tenant=tenant, exercice=e.exercice, no_piece=ref,
            date_ecriture=datetime.date.today(), no_compte=e.no_compte,
            libelle=f"Annulation {provision.reference} — {e.libelle}",
            debit=e.credit, credit=e.debit,
            source='ANNUL_PROVISION', source_id=provision.id, ordre=i)
        for i, e in enumerate(origines, start=1)
    ]
    JournalEntry.objects.bulk_create(contre)


# ── Transferts internes de trésorerie ────────────────────────────────────────
def generer_ecriture_transfert(transfert, tenant):
    """Comptabilise un transfert interne via le compte de virements (585).

      • D compte_virement / C compte_source        (montant — sortie)
      • D compte_destination / C compte_virement    (montant — entrée)
      • D compte_frais / C compte_source            (frais éventuels)
    Le compte 585 se solde à zéro : neutre pour la trésorerie totale et le flux.
    """
    from apps.comptabilite.models import JournalEntry

    if JournalEntry.objects.filter(tenant=tenant, source='TRANSFERT', source_id=transfert.id).exists():
        return

    # Le n° de pièce du journal = la référence du transfert (traçabilité 1:1).
    ref     = transfert.reference
    date    = transfert.date_transfert or datetime.date.today()
    montant = _d(transfert.montant)
    frais   = _d(transfert.frais)
    motif   = transfert.motif or 'Transfert interne'
    label   = f"Virement interne {transfert.compte_source}→{transfert.compte_destination} — {motif}"

    lignes = [
        # Sortie du compte source vers le compte de virements internes
        JournalEntry(tenant=tenant, exercice=transfert.exercice, no_piece=ref, date_ecriture=date,
                     no_compte=transfert.compte_virement, libelle=label,
                     debit=montant, credit=0, source='TRANSFERT', source_id=transfert.id, ordre=1),
        JournalEntry(tenant=tenant, exercice=transfert.exercice, no_piece=ref, date_ecriture=date,
                     no_compte=transfert.compte_source, libelle=label,
                     debit=0, credit=montant, source='TRANSFERT', source_id=transfert.id, ordre=2),
        # Entrée du compte de virements internes vers le compte destination
        JournalEntry(tenant=tenant, exercice=transfert.exercice, no_piece=ref, date_ecriture=date,
                     no_compte=transfert.compte_destination, libelle=label,
                     debit=montant, credit=0, source='TRANSFERT', source_id=transfert.id, ordre=3),
        JournalEntry(tenant=tenant, exercice=transfert.exercice, no_piece=ref, date_ecriture=date,
                     no_compte=transfert.compte_virement, libelle=label,
                     debit=0, credit=montant, source='TRANSFERT', source_id=transfert.id, ordre=4),
    ]
    if frais > 0:
        # Les frais/commissions sont supportés par le compte source (charge).
        lignes += [
            JournalEntry(tenant=tenant, exercice=transfert.exercice, no_piece=ref, date_ecriture=date,
                         no_compte=transfert.compte_frais,
                         libelle=f"Frais sur {label}",
                         debit=frais, credit=0, source='TRANSFERT', source_id=transfert.id,
                         ordre=5, projet=transfert.projet),
            JournalEntry(tenant=tenant, exercice=transfert.exercice, no_piece=ref, date_ecriture=date,
                         no_compte=transfert.compte_source,
                         libelle=f"Frais sur {label}",
                         debit=0, credit=frais, source='TRANSFERT', source_id=transfert.id, ordre=6),
        ]
    JournalEntry.objects.bulk_create(lignes)


def annuler_ecriture_transfert(transfert, tenant):
    """Extourne les écritures d'un transfert annulé (débit ↔ crédit)."""
    from apps.comptabilite.models import JournalEntry

    if JournalEntry.objects.filter(tenant=tenant, source='ANNUL_TRANSFERT',
                                   source_id=transfert.id).exists():
        return
    origines = JournalEntry.objects.filter(
        tenant=tenant, source='TRANSFERT', source_id=transfert.id).order_by('ordre')
    if not origines.exists():
        return

    ref = f"ANN-{transfert.reference}"
    contre = [
        JournalEntry(
            tenant=tenant, exercice=e.exercice, no_piece=ref,
            date_ecriture=datetime.date.today(), no_compte=e.no_compte,
            libelle=f"Annulation {transfert.reference} — {e.libelle}",
            debit=e.credit, credit=e.debit,
            source='ANNUL_TRANSFERT', source_id=transfert.id, ordre=i, projet=e.projet,
        )
        for i, e in enumerate(origines, start=1)
    ]
    JournalEntry.objects.bulk_create(contre)
