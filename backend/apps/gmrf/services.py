"""
Moteur de comptabilisation automatique du module GMRF.

Chaque opération de mobilisation de ressources génère des écritures SYSCOHADA
dans `comptabilite.JournalEntry`, sans aucune saisie manuelle. Les écritures
sont taggées `source='GMRF_*'` + `source_id` pour la traçabilité et l'extourne.
Les annulations produisent des contre-écritures (débit ↔ crédit), jamais de
suppression, conformément aux bonnes pratiques comptables.
"""
import datetime
import re
from decimal import Decimal

from django.db.models import Sum, Max


def _d(v):
    return Decimal(str(v or 0))


def _exercice_actif(tenant):
    from apps.paiements.models import Exercice
    return Exercice.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()


def _next_piece(tenant, source, prefix):
    """Numéro de pièce séquentiel par tenant et par source (ex. GMRF-0001)."""
    from apps.comptabilite.models import JournalEntry
    last = JournalEntry.objects.filter(tenant=tenant, source=source).aggregate(m=Max('no_piece'))['m']
    nums = re.findall(r'\d+', last or f'{prefix}-0000')
    n = int(nums[-1]) + 1 if nums else 1
    return f"{prefix}-{n:04d}"


def _cotisations_versees(cycle):
    """Cumul des cotisations déjà payées sur le cycle (créance accumulée envers
    le groupe), utilisé pour ventiler créance / dette à la réception."""
    from .models import NattCotisation
    qs = NattCotisation.objects.filter(tenant=cycle.tenant, cycle=cycle, statut='PAYE')
    return _d(qs.aggregate(s=Sum('montant'))['s'])


# ── Financement simple (dons, subventions, partenariats, revenus…) ───────────
def generer_ecriture_financement(financement, tenant):
    """Réception de fonds : D compte_tresorerie / C compte_ressource."""
    from apps.comptabilite.models import JournalEntry

    exercice = _exercice_actif(tenant)
    if not exercice:
        return
    if JournalEntry.objects.filter(tenant=tenant, source='GMRF_FIN', source_id=financement.id).exists():
        return

    ref   = _next_piece(tenant, 'GMRF_FIN', 'GRF')
    date  = financement.date_reception or datetime.date.today()
    label = f"{financement.type_financement.libelle} — {financement.libelle}"
    m     = _d(financement.montant)

    JournalEntry.objects.bulk_create([
        JournalEntry(tenant=tenant, exercice=exercice, no_piece=ref, date_ecriture=date,
                     no_compte=financement.compte_tresorerie, libelle=label,
                     debit=m, credit=0, source='GMRF_FIN', source_id=financement.id, ordre=1),
        JournalEntry(tenant=tenant, exercice=exercice, no_piece=ref, date_ecriture=date,
                     no_compte=financement.compte_ressource, libelle=label,
                     debit=0, credit=m, source='GMRF_FIN', source_id=financement.id, ordre=2),
    ])


def annuler_ecriture_financement(financement, tenant):
    """Extourne les écritures d'un financement annulé."""
    _extourner(tenant, source='GMRF_FIN', source_annul='GMRF_ANNUL_FIN',
               source_id=financement.id, prefix='ANN-GRF',
               libelle_prefix=f"Annulation {financement.reference}")


# ── NATT / Tontine ───────────────────────────────────────────────────────────
def generer_ecriture_cotisation(cotisation, tenant):
    """Comptabilise une cotisation payée.

    Avant la réception de la cagnotte : D compte_creance / C trésorerie.
    Après la réception : D compte_dette / C trésorerie (remboursement du groupe)."""
    from apps.comptabilite.models import JournalEntry
    from .models import NattReception

    exercice = _exercice_actif(tenant)
    if not exercice:
        return
    if JournalEntry.objects.filter(tenant=tenant, source='GMRF_COTIS', source_id=cotisation.id).exists():
        return

    cycle = cotisation.cycle
    # Tant que la cagnotte n'a pas été perçue, chaque cotisation constitue une
    # créance envers le groupe. Une fois la cagnotte reçue, chaque cotisation
    # rembourse la dette (avance consentie par le groupe).
    apres_reception = NattReception.objects.filter(tenant=tenant, cycle=cycle).exists()
    compte_contrepartie = cycle.compte_dette if apres_reception else cycle.compte_creance

    treso = cotisation.compte_tresorerie or cycle.compte_tresorerie
    ref   = _next_piece(tenant, 'GMRF_COTIS', 'NATT-C')
    date  = cotisation.date_paiement or datetime.date.today()
    label = f"NATT {cycle.reference} — cotisation {cotisation.numero}/{cycle.duree}"
    m     = _d(cotisation.montant)

    JournalEntry.objects.bulk_create([
        JournalEntry(tenant=tenant, exercice=exercice, no_piece=ref, date_ecriture=date,
                     no_compte=compte_contrepartie, libelle=label,
                     debit=m, credit=0, source='GMRF_COTIS', source_id=cotisation.id, ordre=1),
        JournalEntry(tenant=tenant, exercice=exercice, no_piece=ref, date_ecriture=date,
                     no_compte=treso, libelle=label,
                     debit=0, credit=m, source='GMRF_COTIS', source_id=cotisation.id, ordre=2),
    ])


def annuler_ecriture_cotisation(cotisation, tenant):
    _extourner(tenant, source='GMRF_COTIS', source_annul='GMRF_ANNUL_COTIS',
               source_id=cotisation.id, prefix='ANN-NATT-C',
               libelle_prefix=f"Annulation cotisation {cotisation.numero}")


def generer_ecriture_reception(reception, tenant):
    """Réception de la cagnotte : D trésorerie / C créance (cotisations déjà
    versées) + C dette (avance du groupe restant à rembourser)."""
    from apps.comptabilite.models import JournalEntry

    exercice = _exercice_actif(tenant)
    if not exercice:
        return
    if JournalEntry.objects.filter(tenant=tenant, source='GMRF_RECEP', source_id=reception.id).exists():
        return

    cycle   = reception.cycle
    montant = _d(reception.montant_recu)
    # Créance à solder = total des cotisations déjà versées à ce jour.
    creance = _cotisations_versees(cycle)
    creance = min(creance, montant)          # jamais plus que la cagnotte reçue
    dette   = montant - creance              # avance du groupe à rembourser

    # Traçabilité de la ventilation
    reception.montant_creance_soldee = creance
    reception.montant_dette = dette
    reception.save(update_fields=['montant_creance_soldee', 'montant_dette', 'updated_at'])

    ref   = _next_piece(tenant, 'GMRF_RECEP', 'NATT-R')
    date  = reception.date_reception
    label = f"NATT {cycle.reference} — réception cagnotte (échéance {reception.numero_echeance})"

    rows = [JournalEntry(tenant=tenant, exercice=exercice, no_piece=ref, date_ecriture=date,
                         no_compte=reception.compte_tresorerie, libelle=label,
                         debit=montant, credit=0, source='GMRF_RECEP', source_id=reception.id, ordre=1)]
    ordre = 2
    if creance > 0:
        rows.append(JournalEntry(tenant=tenant, exercice=exercice, no_piece=ref, date_ecriture=date,
                                 no_compte=cycle.compte_creance, libelle=f"{label} — cotisations versées",
                                 debit=0, credit=creance, source='GMRF_RECEP', source_id=reception.id, ordre=ordre))
        ordre += 1
    if dette > 0:
        rows.append(JournalEntry(tenant=tenant, exercice=exercice, no_piece=ref, date_ecriture=date,
                                 no_compte=cycle.compte_dette, libelle=f"{label} — avance du groupe",
                                 debit=0, credit=dette, source='GMRF_RECEP', source_id=reception.id, ordre=ordre))
    JournalEntry.objects.bulk_create(rows)


def annuler_ecriture_reception(reception, tenant):
    _extourner(tenant, source='GMRF_RECEP', source_annul='GMRF_ANNUL_RECEP',
               source_id=reception.id, prefix='ANN-NATT-R',
               libelle_prefix=f"Annulation réception {reception.cycle.reference}")


# ── Extourne générique (contre-écritures) ────────────────────────────────────
def _extourner(tenant, source, source_annul, source_id, prefix, libelle_prefix):
    """Génère les contre-écritures (débit ↔ crédit) d'une opération GMRF."""
    from apps.comptabilite.models import JournalEntry

    if JournalEntry.objects.filter(tenant=tenant, source=source_annul, source_id=source_id).exists():
        return
    exercice = _exercice_actif(tenant)
    if not exercice:
        return
    origines = JournalEntry.objects.filter(tenant=tenant, source=source, source_id=source_id).order_by('ordre')
    if not origines.exists():
        return

    no_piece = _next_piece(tenant, source_annul, prefix)
    contre = []
    for i, e in enumerate(origines, start=1):
        contre.append(JournalEntry(
            tenant=tenant, exercice=exercice, no_piece=no_piece,
            date_ecriture=datetime.date.today(), no_compte=e.no_compte,
            libelle=f"{libelle_prefix} — {e.libelle}",
            debit=e.credit, credit=e.debit,
            source=source_annul, source_id=source_id, ordre=i,
        ))
    JournalEntry.objects.bulk_create(contre)
