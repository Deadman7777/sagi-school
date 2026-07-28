"""Créance sur un organisme payeur — constatation comptable de la bourse.

Une convention de bourse est un engagement ferme : dès qu'elle est signée,
l'organisme DOIT la somme à l'établissement. La créance est donc constatée à
l'attribution, pas à l'encaissement :

    4112 D / 706 C      (créance sur l'organisme / produit de scolarité)

C'est ce qui permet à un bilan de répondre à « combien nos partenaires
institutionnels nous doivent-ils ? ». Noyée dans le 411 avec les créances des
familles, l'information est introuvable — et c'est la première question d'un
bailleur ou d'un contrôleur devant un centre de formation public.

Le versement de l'organisme, lui, ne reconstate aucun produit : il solde le
4112 (voir paiements.ecritures.lignes_paiement). Recréditer 706 à ce
moment-là compterait la subvention deux fois.

Asymétrie assumée avec les familles, dont le produit n'est constaté qu'au
règlement : la promesse d'une famille n'est pas une créance acquise, une
convention signée avec l'État l'est.

La synchronisation est AUTO-RÉPARATRICE, comme celle des reliquats : elle
recalcule l'écriture en entier au lieu d'empiler des ajustements. Corriger dix
fois le montant d'une bourse ne laisse qu'une pièce, et retirer la bourse
efface tout.
"""
from django.db import transaction

SOURCE_CREANCE = 'CREANCE_ORGANISME'
COMPTE_CREANCE = '4112'
COMPTE_PRODUIT = '706'


def _ecritures_existantes(pec):
    from apps.comptabilite.models import JournalEntry
    return JournalEntry.objects.filter(
        tenant=pec.tenant, exercice=pec.exercice,
        source=SOURCE_CREANCE, source_id=pec.id)


def synchroniser_creance(pec):
    """Recale la créance sur l'organisme d'après la bourse en vigueur.

    Rend le montant constaté. Le no_piece déjà attribué est réutilisé : une
    correction de montant ne doit pas faire défiler la séquence.
    """
    from apps.comptabilite.models import JournalEntry

    anciennes = _ecritures_existantes(pec)
    no_piece = next((e.no_piece for e in anciennes.order_by('created_at')), None)
    anciennes.delete()

    # Plafonné au dû réel de l'élève : une convention plus généreuse que la
    # scolarité ne crée pas une créance sur la différence.
    montant = round(min(pec.montant_annuel, float(pec.eleve.total_attendu)), 2)
    if montant <= 0:
        return 0.0

    no_piece = no_piece or _prochain_no_piece(pec.tenant)
    libelle = f"Bourse {pec.organisme.nom} — {pec.eleve.nom_complet}"
    if pec.reference:
        libelle += f" ({pec.reference})"

    for ordre, (compte, debit, credit) in enumerate((
        (COMPTE_CREANCE, montant, 0),
        (COMPTE_PRODUIT, 0, montant),
    ), start=1):
        JournalEntry.objects.create(
            tenant=pec.tenant, exercice=pec.exercice,
            no_piece=no_piece, date_ecriture=pec.exercice.date_debut,
            no_compte=compte, debit=debit, credit=credit, libelle=libelle,
            source=SOURCE_CREANCE, source_id=pec.id, ordre=ordre,
        )
    return montant


def supprimer_creance(pec):
    """Efface la créance quand la bourse est retirée : le dû revient
    entièrement à la famille, plus rien n'est attendu de l'organisme."""
    _ecritures_existantes(pec).delete()


def _prochain_no_piece(tenant):
    """Séquence BRS-xxxx, par école (jamais globale : une nouvelle école
    doit repartir de 1 sans buter sur l'unicité)."""
    import re

    from apps.comptabilite.models import JournalEntry

    dernier = 0
    for piece in (JournalEntry.objects
                  .filter(tenant=tenant, source=SOURCE_CREANCE)
                  .values_list('no_piece', flat=True).distinct()):
        if nums := re.findall(r'\d+', piece or ''):
            dernier = max(dernier, int(nums[-1]))
    return f"BRS-{dernier + 1:04d}"


@transaction.atomic
def appliquer(pec):
    """Point d'entrée unique après création ou modification d'une bourse."""
    return synchroniser_creance(pec)
