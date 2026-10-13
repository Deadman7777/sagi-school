"""Annulation d'un reçu élève — contre-écritures SYSCOHADA.

Source unique : l'annulation depuis l'écran Paiements et l'annulation d'un
reçu réglé par un chèque revenu impayé (apps.paiements.cheques) doivent
écrire exactement la même chose.
"""
import re

from apps.comptabilite.models import JournalEntry


def _exercice_extourne(paiement, tenant):
    """L'exercice où passer l'annulation d'un règlement : le SIEN tant qu'il
    est ouvert, comme à l'encaissement (voir perform_create).

    Prendre « le dernier exercice ouvert » envoyait l'extourne sur un autre
    exercice dès qu'une école en avait deux ouverts : le règlement annulé
    restait entier dans le 411, le 706 et la caisse de son exercice.
    """
    if paiement.exercice_id and not paiement.exercice.cloture:
        return paiement.exercice
    from .models import Exercice
    return Exercice.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()


def _date_extourne(exercice):
    """Aujourd'hui, ramené dans les bornes de l'exercice de l'extourne."""
    import datetime
    return min(datetime.date.today(), exercice.date_fin)


def prochain_no_annulation(tenant):
    last_ann = JournalEntry.objects.filter(
        tenant=tenant, source='ANNUL_PAIEMENT'
    ).values_list('no_piece', flat=True).order_by('-no_piece')
    nums = [re.findall(r'\d+', p) for p in last_ann if re.findall(r'\d+', p)]
    next_n = int(nums[0][-1]) + 1 if nums else 1
    return f"ANN-REC-{next_n:04d}"


def annuler_paiement(paiement, exercice, date_annul, prefixe='ANNUL'):
    """Extourne les écritures du reçu et le marque ANNULE.

    Rend le numéro de pièce de l'annulation, '' si le reçu n'avait plus
    d'écriture à extourner (contre-écritures déjà passées). Lève ValueError
    si le reçu n'a aucune écriture."""
    tenant = paiement.tenant
    if JournalEntry.objects.filter(tenant=tenant, source='ANNUL_PAIEMENT',
                                   source_id=paiement.id).exists():
        paiement.statut = 'ANNULE'
        paiement.save()
        return ''

    ecritures_orig = list(JournalEntry.objects.filter(
        tenant=tenant, source='PAIEMENT', source_id=paiement.id).order_by('ordre'))
    if not ecritures_orig:
        raise ValueError('Aucune écriture comptable trouvée pour ce paiement.')

    no_piece_annul = prochain_no_annulation(tenant)
    JournalEntry.objects.bulk_create([
        JournalEntry(
            tenant=tenant, exercice=exercice, no_piece=no_piece_annul,
            date_ecriture=date_annul, no_compte=e.no_compte,
            libelle=f"{prefixe} — {e.libelle}",
            debit=e.credit, credit=e.debit,
            source='ANNUL_PAIEMENT', source_id=paiement.id, ordre=i,
        )
        for i, e in enumerate(ecritures_orig, start=1)
    ])
    paiement.statut = 'ANNULE'
    paiement.save()
    return no_piece_annul
