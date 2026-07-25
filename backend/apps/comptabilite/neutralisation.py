"""Neutralisation des reprises de soldes en contexte de migration.

Quand l'historique d'une école a été importé sous forme d'agrégats (journal
de caisse : 571 D / 706 C), les produits de l'année sont DÉJÀ dans le grand
livre. Les reprises par élève re-créditent 706 pour reconstituer le « déjà
payé » de chacun : sans contrepartie, le même produit serait compté deux fois.
On l'annule donc par une écriture de neutralisation 706 D / 890 C.

Règle : cette neutralisation est **recalculée en entier** à chaque appel, et
jamais ajoutée à l'existant. Corriger la reprise d'un élève dix fois laisse
donc toujours UNE paire d'écritures, égale au total des reprises en vigueur —
et toute neutralisation orpheline laissée par une correction antérieure
disparaît au passage.

Historique : les corrections faites depuis l'interface empilaient un débit 706
par passage sans retirer le précédent. Au bout de quelques corrections, ces
débits orphelins dépassaient le produit migré et le total des recettes du
tableau de bord tombait à 0.
"""
from django.db.models import Sum

from .models import JournalEntry

SOURCE_RECAL = 'RECAL_MIGRATION'
# Pièce dédiée à la neutralisation des reprises. Le scope de suppression doit
# rester sur ce no_piece : le recalage de trésorerie (RECAL-TRESO) partage la
# même `source` et ne doit surtout pas être emporté.
PIECE_RECAL = 'RECAL-REP'


def a_agregats_migration(tenant, exercice):
    """L'exercice porte-t-il des produits importés en agrégats (classe 70) ?"""
    return JournalEntry.objects.filter(
        tenant=tenant, exercice=exercice, source='MIGRATION',
        no_compte__startswith='70', credit__gt=0).exists()


def total_produits_reprises(tenant, exercice):
    """Somme des 706 crédités par les reprises actuellement en base."""
    from apps.paiements.models import Paiement
    ids = list(Paiement.objects.filter(
        tenant=tenant, exercice=exercice, mode_paiement='REPRISE'
    ).values_list('id', flat=True))
    if not ids:
        return 0.0
    return float(JournalEntry.objects.filter(
        tenant=tenant, exercice=exercice, source='PAIEMENT', source_id__in=ids,
        no_compte='706', credit__gt=0).aggregate(c=Sum('credit'))['c'] or 0)


def neutraliser_reprises(tenant, exercice):
    """Réaligne la neutralisation sur l'état courant des reprises.

    Rend le montant neutralisé (0 si l'exercice n'a pas d'agrégats migrés ou
    plus aucune reprise). Idempotent et auto-réparateur."""
    JournalEntry.objects.filter(
        tenant=tenant, exercice=exercice,
        source=SOURCE_RECAL, no_piece=PIECE_RECAL).delete()

    if not a_agregats_migration(tenant, exercice):
        return 0.0

    total = total_produits_reprises(tenant, exercice)
    if total <= 0:
        return 0.0

    JournalEntry.objects.bulk_create([
        JournalEntry(tenant=tenant, exercice=exercice, no_piece=PIECE_RECAL,
                     date_ecriture=exercice.date_debut, source=SOURCE_RECAL,
                     no_compte='706', debit=total, credit=0, ordre=1,
                     libelle="Neutralisation des reprises de soldes "
                             "(produits déjà portés par les agrégats migrés)"),
        JournalEntry(tenant=tenant, exercice=exercice, no_piece=PIECE_RECAL,
                     date_ecriture=exercice.date_debut, source=SOURCE_RECAL,
                     no_compte='890', debit=0, credit=total, ordre=2,
                     libelle="Contrepartie neutralisation des reprises de soldes"),
    ])
    return total
