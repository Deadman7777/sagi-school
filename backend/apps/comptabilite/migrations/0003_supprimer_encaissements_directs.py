from django.db import migrations
from decimal import Decimal


COMPTE_MAP = {
    'ESPECE':       ('571',  'Caisse'),
    'WAVE':         ('5521', 'WAVE'),
    'ORANGE_MONEY': ('5522', 'Orange Money'),
    'FREE_MONEY':   ('5523', 'Free Money'),
    'VIREMENT':     ('521',  'Banque'),
    'CHEQUE':       ('521',  'Banque'),
}


def restaurer_et_nettoyer(apps, schema_editor):
    """
    1. Pour chaque paiement sans écritures source='PAIEMENT' dans le journal,
       crée les 4 écritures SYSCOHADA correctes (créance 411/706 + règlement 5xx/411).
    2. Supprime ensuite toutes les entrées source='RECETTE' (encaissements directs
       créés par l'ancienne méthode Paiement._generer_ecriture).
    """
    Paiement    = apps.get_model('paiements',     'Paiement')
    JournalEntry = apps.get_model('comptabilite', 'JournalEntry')

    created_count = 0

    for paiement in Paiement.objects.select_related('eleve', 'exercice', 'tenant').all():
        # Déjà des écritures PAIEMENT pour ce numéro de pièce ?
        if JournalEntry.objects.filter(no_piece=paiement.no_piece, source='PAIEMENT').exists():
            continue

        montant = (paiement.montant_inscription + paiement.montant_mensualite +
                   paiement.montant_uniforme    + paiement.montant_fournitures +
                   paiement.montant_cantine     + paiement.montant_divers)

        if montant <= 0:
            continue

        compte_reglement, libelle_compte = COMPTE_MAP.get(
            paiement.mode_paiement, ('571', 'Caisse')
        )
        eleve_nom = paiement.eleve.nom_complet if hasattr(paiement.eleve, 'nom_complet') else str(paiement.eleve)
        libelle   = f"{eleve_nom} - {paiement.no_piece}"

        # Écriture 1 — Constatation créance (débit 411 / crédit 706)
        # Écriture 2 — Règlement          (débit 5xx / crédit 411)
        # Note : le champ 'ordre' est ajouté par la migration 0004.
        # On ne l'inclut pas ici — migration 0004 renumérotera ces entrées.
        ecritures = [
            dict(no_compte='411',           debit=montant,      credit=Decimal('0'),
                 libelle=f"Créance scolarité — {libelle}"),
            dict(no_compte='706',           debit=Decimal('0'), credit=montant,
                 libelle=f"Créance scolarité — {libelle}"),
            dict(no_compte=compte_reglement, debit=montant,     credit=Decimal('0'),
                 libelle=f"Règlement {libelle_compte} — {libelle}"),
            dict(no_compte='411',           debit=Decimal('0'), credit=montant,
                 libelle=f"Règlement {libelle_compte} — {libelle}"),
        ]

        for e in ecritures:
            JournalEntry.objects.create(
                tenant=paiement.tenant,
                exercice=paiement.exercice,
                no_piece=paiement.no_piece,
                date_ecriture=paiement.date_paiement,
                source='PAIEMENT',
                source_id=paiement.id,
                **e
            )
        created_count += 4

    print(f"\n  -> {created_count} ecriture(s) PAIEMENT reconstituee(s).")

    # Supprimer les encaissements directs (source='RECETTE')
    deleted, _ = JournalEntry.objects.filter(source='RECETTE').delete()
    print(f"  -> {deleted} ecriture(s) 'Encaissement' en double supprimee(s).")


class Migration(migrations.Migration):

    dependencies = [
        ('comptabilite', '0002_initial'),
        ('paiements',    '0001_initial'),
    ]

    operations = [
        migrations.RunPython(
            restaurer_et_nettoyer,
            migrations.RunPython.noop
        ),
    ]
