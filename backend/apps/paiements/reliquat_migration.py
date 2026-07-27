"""Impayé antérieur saisi à la main — migration d'une école endettée.

Le report automatique (report_reliquats) suppose que l'année précédente
existe dans SAGI SCHOOL. À l'installation d'une école qui arrive avec un
historique, ce n'est justement pas le cas : les élèves traînent une ardoise
née avant la migration, dont l'école ne sait souvent donner qu'un montant
global. Ce module permet de la saisir directement sur la fiche.

Comptablement, c'est le même geste que le report — une créance née d'un
exercice antérieur, dont le produit a déjà été constaté à l'époque :

    411 D / 890 C     (créance ancienne / bilan d'ouverture)

Aucun 706 : rejouer le produit gonflerait le résultat de l'année en cours
avec des frais qui ne lui appartiennent pas.

Le montant se corrige — c'est même attendu, une migration se nettoie
progressivement. La synchronisation est donc AUTO-RÉPARATRICE : elle
recalcule l'écriture en entier plutôt que d'empiler des ajustements. Trois
corrections successives ne laissent qu'une seule pièce au journal, celle du
dernier montant, et remettre 0 la fait disparaître.
"""
from django.db import transaction

from .report_reliquats import SOURCE_REPORT, _prochain_no_piece

SOURCE_MIGRATION = 'RELIQUAT_MIGRATION'

# Les deux sources qui portent un à-nouveaux de reliquat sur une fiche. La
# synchronisation les possède toutes les deux : corriger à la main un montant
# issu du report automatique doit remplacer son écriture, pas s'y ajouter —
# sinon le journal porterait deux créances pour une seule dette.
SOURCES_RELIQUAT = (SOURCE_REPORT, SOURCE_MIGRATION)


def _ecritures_existantes(eleve):
    from apps.comptabilite.models import JournalEntry
    return JournalEntry.objects.filter(
        tenant=eleve.tenant, exercice=eleve.exercice,
        source__in=SOURCES_RELIQUAT, source_id=eleve.id,
    )


def synchroniser_ecritures(eleve):
    """Recale l'à-nouveaux du reliquat de la fiche sur `reliquat_anterieur`.

    Rend le no_piece écrit, ou '' si le reliquat est nul (aucune écriture).
    Le numéro de pièce déjà attribué est réutilisé quand il y en a un : une
    correction de montant ne doit pas faire défiler la séquence RAN.
    """
    from apps.comptabilite.models import JournalEntry

    montant = round(float(eleve.reliquat_anterieur or 0), 2)
    anciennes = _ecritures_existantes(eleve)
    no_piece = next((e.no_piece for e in anciennes.order_by('created_at')), None)
    anciennes.delete()

    if montant <= 0:
        return ''

    exercice = eleve.exercice
    origine = eleve.reliquat_origine_libelle
    no_piece = no_piece or _prochain_no_piece(eleve.tenant)
    libelle = (f"Reliquat {origine} — " if origine else 'Reliquat antérieur — ')
    libelle += f"{eleve.nom_complet} ({no_piece})"
    source = (SOURCE_REPORT if eleve.reliquat_exercice_origine_id
              else SOURCE_MIGRATION)

    for ordre, (compte, debit, credit) in enumerate((
        ('411', montant, 0),
        ('890', 0, montant),
    ), start=1):
        JournalEntry.objects.create(
            tenant=eleve.tenant, exercice=exercice,
            no_piece=no_piece, date_ecriture=exercice.date_debut,
            no_compte=compte, debit=debit, credit=credit, libelle=libelle,
            source=source, source_id=eleve.id, ordre=ordre,
        )
    return no_piece


def definir_impaye_anterieur(eleve, montant, note=None):
    """Fixe l'impayé antérieur d'un élève et recale son écriture.

    `note` à None laisse la note existante intacte (permet de corriger le seul
    montant). Rend {'montant', 'no_piece'}.

    Refuse un exercice clôturé : une année fermée reste en lecture seule, on
    n'y passe plus d'à-nouveaux (même règle que le report).
    """
    montant = round(float(montant or 0), 2)
    if montant < 0:
        raise ValueError("L'impayé antérieur ne peut pas être négatif.")
    if not eleve.exercice_id:
        raise ValueError("L'élève n'est rattaché à aucun exercice.")
    if eleve.exercice.cloture:
        raise ValueError(
            f"L'exercice {eleve.exercice.annee_scolaire} est clôturé : "
            "l'impayé antérieur ne peut plus y être modifié.")

    # Garde-fou : on ne descend pas sous ce qui a déjà été encaissé sur ce
    # reliquat, sinon la fiche afficherait un trop-perçu fantôme.
    deja_paye = eleve.reliquat_paye
    if montant and montant < deja_paye:
        raise ValueError(
            f"Montant inférieur aux {deja_paye:,.0f} FCFA déjà encaissés sur "
            "cet impayé antérieur. Annulez d'abord les encaissements concernés.")

    champs = ['reliquat_anterieur']
    eleve.reliquat_anterieur = montant
    if note is not None:
        eleve.reliquat_note = str(note)[:120]
        champs.append('reliquat_note')

    with transaction.atomic():
        eleve.save(update_fields=champs)
        no_piece = synchroniser_ecritures(eleve)
    return {'montant': montant, 'no_piece': no_piece}


def resume_impayes_anterieurs(tenant, exercice):
    """Photo des impayés antérieurs d'un exercice — sert à piloter la migration."""
    from django.db.models import Count, Sum

    from apps.eleves.models import Eleve

    agg = Eleve.objects.filter(
        tenant=tenant, exercice=exercice, reliquat_anterieur__gt=0
    ).aggregate(nb=Count('id'), total=Sum('reliquat_anterieur'))
    return {
        'exercice':      exercice.annee_scolaire,
        'nb_eleves':     agg['nb'] or 0,
        'montant_total': round(float(agg['total'] or 0), 2),
    }
