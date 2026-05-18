from django.db import migrations, models


def numerote_existants(apps, schema_editor):
    """
    Attribue un numéro d'ordre (1-4) aux écritures déjà en base
    en se basant sur la position naturelle SYSCOHADA :
      1 - Débit de l'écriture 1  (411 D pour créance, 6xx/2xx D pour charge)
      2 - Crédit de l'écriture 1 (706 C pour créance, 401/404/481 C pour charge)
      3 - Débit de l'écriture 2  (5xx D pour règlement)
      4 - Crédit de l'écriture 2 (411 C ou 401/404/481 C)
    """
    JournalEntry = apps.get_model('comptabilite', 'JournalEntry')

    # Grouper par (exercice, no_piece)
    pieces = JournalEntry.objects.values_list(
        'exercice_id', 'no_piece'
    ).distinct()

    COMPTES_TRESORERIE = {'521', '5521', '5522', '5523', '571', '552'}
    COMPTES_FOURNISSEUR = {'401', '404', '481'}
    COMPTES_PRODUIT     = {'706', '706.1', '701', '702', '703', '704', '705'}

    for exercice_id, no_piece in pieces:
        entrees = list(
            JournalEntry.objects.filter(exercice_id=exercice_id, no_piece=no_piece)
        )
        if not entrees:
            continue

        # Trier manuellement : SYSCOHADA convention
        # Ordre attendu : débit_E1, crédit_E1, débit_E2, crédit_E2
        debits  = [e for e in entrees if e.debit  > 0]
        credits = [e for e in entrees if e.credit > 0]

        # Écriture 1 : le débit NON trésorerie (charge ou créance)
        debit_e1 = next(
            (e for e in debits if e.no_compte not in COMPTES_TRESORERIE and
             e.no_compte not in COMPTES_FOURNISSEUR),
            debits[0] if debits else None
        )
        # Crédit E1 : 706 / compte produit, ou fournisseur (401/404/481)
        credit_e1 = next(
            (e for e in credits if e.no_compte in COMPTES_PRODUIT or
             e.no_compte in COMPTES_FOURNISSEUR),
            credits[0] if credits else None
        )
        # Débit E2 : trésorerie ou fournisseur (règlement)
        debit_e2 = next(
            (e for e in debits if e != debit_e1),
            None
        )
        # Crédit E2 : ce qui reste
        credit_e2 = next(
            (e for e in credits if e != credit_e1),
            None
        )

        ordered = [debit_e1, credit_e1, debit_e2, credit_e2]

        # Les entrées non classifiées (si pièce avec nombre différent de 4)
        remaining = [e for e in entrees if e not in ordered]

        ordre = 1
        for entry in ordered:
            if entry is not None:
                entry.ordre = ordre
                entry.save(update_fields=['ordre'])
                ordre += 1
        for entry in remaining:
            entry.ordre = ordre
            entry.save(update_fields=['ordre'])
            ordre += 1


class Migration(migrations.Migration):

    dependencies = [
        ('comptabilite', '0003_supprimer_encaissements_directs'),
    ]

    operations = [
        migrations.AddField(
            model_name='journalentry',
            name='ordre',
            field=models.IntegerField(default=0),
        ),
        migrations.RunPython(numerote_existants, migrations.RunPython.noop),
    ]
