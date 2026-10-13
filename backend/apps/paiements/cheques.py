"""Registre des chèques reçus — de la réception à l'encaissement.

Cycle d'un chèque et ses écritures :

  réception   D 513 « Chèques à encaisser »  (dans l'écriture du reçu)
  remise      D 521 Banque / C 513           (pièce RCH-xxxx, à la date de remise)
  encaissé    — rien : le crédit lu sur le relevé confirme la remise
  impayé      D 513 / C 521 si le chèque était remis (retour de la banque),
              puis annulation des reçus qu'il réglait : la famille redoit.

Un chèque peut régler plusieurs reçus (encaissement groupé d'une famille) :
ses parts sont des AffectationCheque. Un chèque reçu avant le registre est
déjà porté au 521 (`compte_reception='521'`) : sa remise n'écrit rien, son
impayé se contente d'annuler les reçus (leur extourne recrédite le 521).
"""
import datetime
import re
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

COMPTE_CHEQUES = '513'
COMPTE_BANQUE = '521'
_EPS = Decimal('0.01')


def _d(v):
    return Decimal(str(v or 0)).quantize(Decimal('0.01'))


def _date(v):
    if not v:
        return None
    if isinstance(v, datetime.date):
        return v
    try:
        return datetime.date.fromisoformat(str(v)[:10])
    except ValueError:
        raise ValueError(f"Date invalide : {v}")


def part_cheque(modes_reglement, mode_paiement=None, total=None):
    """Part d'un règlement payée par chèque."""
    if modes_reglement:
        return sum((_d(l.get('montant')) for l in modes_reglement
                    if (l or {}).get('mode') == 'CHEQUE'), Decimal('0'))
    if mode_paiement == 'CHEQUE' and total is not None:
        return _d(total)
    return Decimal('0')


def montant_affecte(cheque):
    """Ce que le chèque règle sur des reçus encore actifs = ce qui est au 513."""
    return _d(cheque.affectations.filter(paiement__statut='ACTIF')
              .aggregate(t=Sum('montant'))['t'])


# ── Réception ────────────────────────────────────────────────────────────────

def _trouver_ou_creer(paiement, detail, part, user):
    from .models import ChequeRecu
    numero = (detail.get('numero') or '').strip()
    banque = (detail.get('banque') or '').strip()
    montant_titre = _d(detail.get('montant')) if detail.get('montant') else None

    # Le même chèque réglant plusieurs reçus (un par enfant) : on le retrouve
    # par son numéro et sa banque, ou — saisi sans numéro — par le versement
    # groupé auquel il appartient.
    qs = ChequeRecu.objects.filter(tenant=paiement.tenant, statut='EN_PORTEFEUILLE')
    cheque = None
    if numero:
        cheque = qs.filter(numero=numero, banque__iexact=banque).first()
    elif paiement.reference_groupe:
        cheque = qs.filter(numero='', reference_groupe=paiement.reference_groupe).first()

    if cheque is None:
        return ChequeRecu.objects.create(
            tenant=paiement.tenant, exercice=paiement.exercice,
            numero=numero, banque=banque,
            tireur=(detail.get('tireur') or '').strip(),
            date_emission=_date(detail.get('date_emission')),
            date_reception=paiement.date_paiement,
            montant=montant_titre or part,
            reference_groupe=paiement.reference_groupe,
            recu_par=user,
        )

    deja = montant_affecte(cheque)
    if deja + part > cheque.montant + _EPS:
        if montant_titre is not None:
            raise ValueError(
                f"Le chèque n° {numero or '?'} ({cheque.montant:,.0f} FCFA) règle déjà "
                f"{deja:,.0f} FCFA : il n'en reste que {cheque.montant - deja:,.0f}.")
        cheque.montant = deja + part
        cheque.save(update_fields=['montant', 'updated_at'])
    return cheque


def enregistrer_cheques(paiement, details, user=None):
    """Inscrit au registre le ou les chèques qui règlent ce reçu.

    `details` : [{numero, banque, tireur, date_emission, montant?}] saisis à
    l'encaissement. Sans détail, le chèque est inscrit « à compléter » : il ne
    doit pas échapper au suivi parce que le formulaire était incomplet."""
    from .models import AffectationCheque
    part = part_cheque(paiement.modes_reglement, paiement.mode_paiement, paiement.total)
    if part <= 0:
        return []
    details = [d for d in (details or []) if isinstance(d, dict)] or [{}]

    if len(details) == 1:
        parts = [part]
    else:
        parts = [_d(d.get('montant')) for d in details]
        if any(p <= 0 for p in parts) or abs(sum(parts) - part) > _EPS:
            raise ValueError(
                f"Les chèques saisis ({sum(parts):,.0f} FCFA) doivent couvrir exactement "
                f"la part payée par chèque ({part:,.0f} FCFA).")

    cheques = []
    for detail, montant in zip(details, parts):
        cheque = _trouver_ou_creer(paiement, detail, montant, user)
        AffectationCheque.objects.create(tenant=paiement.tenant, cheque=cheque,
                                         paiement=paiement, montant=montant)
        cheques.append(cheque)
    return cheques


# ── Annulation / modification du reçu ────────────────────────────────────────

def _deja_en_banque(cheque):
    return cheque.compte_reception == COMPTE_CHEQUES and cheque.statut in ('REMIS', 'ENCAISSE')


def verifier_cheques_modifiables(paiement, nouvelle_part=None):
    """Message d'erreur si le reçu ne peut pas être annulé (nouvelle_part
    None) ou si sa part chèque ne peut pas passer à `nouvelle_part`."""
    affs = list(paiement.affectations_cheque.select_related('cheque'))
    if not affs:
        return None
    actuelle = sum((a.montant for a in affs), Decimal('0'))
    if nouvelle_part is not None and abs(_d(nouvelle_part) - actuelle) <= _EPS:
        return None
    for a in affs:
        if _deja_en_banque(a.cheque):
            return (f"Le chèque n° {a.cheque.numero or '?'} a déjà été remis en banque le "
                    f"{a.cheque.date_remise:%d/%m/%Y} : la part payée par chèque ne peut plus "
                    f"changer. S'il revient impayé, déclarez-le depuis le registre des chèques.")
    if nouvelle_part is not None and nouvelle_part > 0 and len(affs) > 1:
        return ("Ce reçu est réglé par plusieurs chèques : annulez-le puis ressaisissez-le "
                "pour changer la part payée par chèque.")
    return None


def liberer_cheques(paiement):
    """Le reçu est annulé : ses chèques encore en portefeuille ne règlent plus
    rien ; un chèque qui ne règle plus aucun reçu est annulé."""
    for a in list(paiement.affectations_cheque.select_related('cheque')):
        cheque = a.cheque
        a.delete()
        if cheque.statut == 'EN_PORTEFEUILLE' and not cheque.affectations.exists():
            cheque.statut = 'ANNULE'
            cheque.save(update_fields=['statut', 'updated_at'])


def transferer_cheques(ancien, nouveau, details=None, user=None):
    """Modification d'un reçu : le nouveau reçu reprend les chèques de l'ancien.

    Part chèque inchangée : les chèques suivent tels quels, quel que soit leur
    statut (l'extourne et la nouvelle écriture se compensent au 513).
    Part modifiée (contrôlée par verifier_cheques_modifiables) : le chèque
    unique en portefeuille prend le nouveau montant ; une part nouvelle crée
    un chèque ; une part supprimée libère les chèques."""
    affs = list(ancien.affectations_cheque.select_related('cheque'))
    nouvelle = part_cheque(nouveau.modes_reglement, nouveau.mode_paiement, nouveau.total)
    actuelle = sum((a.montant for a in affs), Decimal('0'))

    if not affs:
        if nouvelle > 0:
            enregistrer_cheques(nouveau, details, user)
        return
    if abs(nouvelle - actuelle) <= _EPS:
        for a in affs:
            a.paiement = nouveau
            a.save(update_fields=['paiement', 'updated_at'])
        return
    if nouvelle <= 0:
        liberer_cheques(ancien)
        return
    a = affs[0]
    cheque = a.cheque
    # L'ancien reçu est déjà annulé : sa part ne compte plus dans l'affecté.
    if cheque.montant == montant_affecte(cheque) + a.montant:
        cheque.montant = cheque.montant - a.montant + nouvelle
        cheque.save(update_fields=['montant', 'updated_at'])
    a.paiement = nouveau
    a.montant = nouvelle
    a.save(update_fields=['paiement', 'montant', 'updated_at'])


# ── Remise, encaissement, impayé ─────────────────────────────────────────────

def prochain_no_remise(tenant):
    from .models import ChequeRecu
    pieces = ChequeRecu.objects.filter(tenant=tenant).exclude(no_piece_remise='') \
        .values_list('no_piece_remise', flat=True)
    nums = [int(m.group(1)) for p in pieces if (m := re.search(r'(\d+)$', p))]
    return f"RCH-{max(nums, default=0) + 1:04d}"


def _exercice_ouvert(cheque):
    from .models import Exercice
    if not cheque.exercice.cloture:
        return cheque.exercice
    ex = Exercice.objects.filter(tenant=cheque.tenant, cloture=False).order_by('-date_debut').first()
    if ex is None:
        raise ValueError("Aucun exercice ouvert pour enregistrer l'opération.")
    return ex


def _libelle(cheque):
    return (f"chèque n° {cheque.numero or '?'}"
            + (f" {cheque.banque}" if cheque.banque else '')
            + (f" — {cheque.tireur}" if cheque.tireur else ''))


@transaction.atomic
def remettre_en_banque(cheques, date_remise, bordereau='', user=None):
    """Remise d'un lot de chèques à la banque : une pièce RCH pour le lot,
    D 521 / C 513 par chèque. Rend le numéro de pièce."""
    from apps.comptabilite.models import JournalEntry
    date_remise = _date(date_remise)
    if not date_remise:
        raise ValueError("Date de remise requise.")
    if not cheques:
        raise ValueError("Aucun chèque sélectionné.")
    tenant = cheques[0].tenant
    for c in cheques:
        if c.statut != 'EN_PORTEFEUILLE':
            raise ValueError(f"Le {_libelle(c)} n'est pas en portefeuille ({c.get_statut_display()}).")
        if date_remise < c.date_reception:
            raise ValueError(f"Le {_libelle(c)} a été reçu le {c.date_reception:%d/%m/%Y} : "
                             f"il ne peut pas être remis avant.")
        affecte = montant_affecte(c)
        if abs(affecte - c.montant) > _EPS:
            raise ValueError(
                f"Le {_libelle(c)} est de {c.montant:,.0f} FCFA mais ne règle que "
                f"{affecte:,.0f} FCFA de reçus : corrigez son montant ou complétez les reçus.")

    no_piece = prochain_no_remise(tenant)
    lignes = []
    for c in cheques:
        if c.compte_reception == COMPTE_CHEQUES:
            ex = _exercice_ouvert(c)
            if date_remise > ex.date_fin:
                raise ValueError(f"Le {date_remise:%d/%m/%Y} est après la fin de l'exercice "
                                 f"{ex.annee_scolaire}.")
            lib = f"Remise en banque {_libelle(c)}" + (f" (bordereau {bordereau})" if bordereau else '')
            for ordre, (compte, debit, credit) in enumerate(
                    ((COMPTE_BANQUE, c.montant, 0), (COMPTE_CHEQUES, 0, c.montant)), start=1):
                lignes.append(JournalEntry(
                    tenant=tenant, exercice=ex, no_piece=no_piece, date_ecriture=date_remise,
                    no_compte=compte, libelle=lib, debit=debit, credit=credit,
                    source='REMISE_CHEQUE', source_id=c.id, ordre=ordre))
        c.statut = 'REMIS'
        c.date_remise = date_remise
        c.bordereau = bordereau or ''
        c.no_piece_remise = no_piece
        c.remis_par = user
        c.save()
    JournalEntry.objects.bulk_create(lignes)
    return no_piece


@transaction.atomic
def confirmer_encaissement(cheques, date_encaissement, user=None):
    """Le crédit est lu sur le relevé. Un chèque encore en portefeuille est
    d'abord remis à la même date (remise oubliée)."""
    date_encaissement = _date(date_encaissement)
    if not date_encaissement:
        raise ValueError("Date d'encaissement requise.")
    a_remettre = [c for c in cheques if c.statut == 'EN_PORTEFEUILLE']
    if a_remettre:
        remettre_en_banque(a_remettre, date_encaissement, '', user)
    for c in cheques:
        c.refresh_from_db()
        if c.statut != 'REMIS':
            raise ValueError(f"Le {_libelle(c)} ne peut pas être encaissé ({c.get_statut_display()}).")
        if c.date_remise and date_encaissement < c.date_remise:
            raise ValueError(f"Le {_libelle(c)} a été remis le {c.date_remise:%d/%m/%Y} : "
                             f"il ne peut pas être crédité avant.")
        c.statut = 'ENCAISSE'
        c.date_encaissement = date_encaissement
        c.encaisse_par = user
        c.save()


@transaction.atomic
def declarer_impaye(cheque, date_impaye, motif='', user=None):
    """Le chèque revient impayé : la banque reprend l'argent, les reçus qu'il
    réglait sont annulés, la famille redoit.

    Rend {'no_piece_retour', 'recus_annules': [...], 'autres_modes': [...]} —
    `autres_modes` : reçus multi-mode dont une part (espèces, Wave…) a bien été
    payée et doit être ressaisie sur un nouveau reçu."""
    from apps.comptabilite.models import JournalEntry
    from .annulation import _exercice_extourne, annuler_paiement
    date_impaye = _date(date_impaye) or datetime.date.today()
    if cheque.statut not in ('EN_PORTEFEUILLE', 'REMIS', 'ENCAISSE'):
        raise ValueError(f"Le {_libelle(cheque)} est {cheque.get_statut_display().lower()}.")

    no_retour = ''
    if _deja_en_banque(cheque):
        ex = _exercice_ouvert(cheque)
        no_retour = f"IMP-{cheque.no_piece_remise or prochain_no_remise(cheque.tenant)}"
        lib = f"Chèque impayé {_libelle(cheque)}" + (f" ({motif})" if motif else '')
        d = min(max(date_impaye, ex.date_debut), ex.date_fin)
        JournalEntry.objects.bulk_create([
            JournalEntry(tenant=cheque.tenant, exercice=ex, no_piece=no_retour, date_ecriture=d,
                         no_compte=COMPTE_CHEQUES, libelle=lib, debit=cheque.montant, credit=0,
                         source='IMPAYE_CHEQUE', source_id=cheque.id, ordre=1),
            JournalEntry(tenant=cheque.tenant, exercice=ex, no_piece=no_retour, date_ecriture=d,
                         no_compte=COMPTE_BANQUE, libelle=lib, debit=0, credit=cheque.montant,
                         source='IMPAYE_CHEQUE', source_id=cheque.id, ordre=2),
        ])

    recus, autres = [], []
    for a in cheque.affectations.select_related('paiement', 'paiement__eleve', 'paiement__exercice'):
        p = a.paiement
        if p.statut != 'ACTIF':
            continue
        ex = _exercice_extourne(p, p.tenant)
        if ex is None:
            raise ValueError("Aucun exercice ouvert pour annuler les reçus.")
        d = min(max(date_impaye, ex.date_debut), ex.date_fin)
        no_annul = annuler_paiement(p, ex, d, prefixe='CHÈQUE IMPAYÉ')
        recus.append({'no_piece': p.no_piece, 'eleve': p.eleve.nom_complet,
                      'montant': float(p.total), 'no_piece_annulation': no_annul})
        reste = _d(p.total) - a.montant
        if reste > _EPS:
            autres.append({'no_piece': p.no_piece, 'eleve': p.eleve.nom_complet,
                           'montant': float(reste)})

    cheque.statut = 'IMPAYE'
    cheque.date_impaye = date_impaye
    cheque.motif_impaye = motif or ''
    cheque.impaye_par = user
    cheque.save()
    return {'no_piece_retour': no_retour, 'recus_annules': recus, 'autres_modes': autres}
