from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('comptabilite', '0007_immobilisation'),
    ]

    operations = [
        migrations.AddField(
            model_name='immobilisation',
            name='compte_fournisseur',
            field=models.CharField(
                max_length=5,
                choices=[('404', "404 — Fournisseurs d'immobilisations"),
                         ('481', '481 — Fournisseurs d\'immo. (autre tiers)')],
                default='404',
            ),
        ),
        migrations.AddField(
            model_name='immobilisation',
            name='mode_reglement',
            field=models.CharField(
                max_length=20,
                blank=True,
                default='',
                choices=[('', 'Non réglé (à payer)'), ('ESPECE', 'Espèce'),
                         ('WAVE', 'Wave'), ('ORANGE_MONEY', 'Orange Money'),
                         ('FREE_MONEY', 'Free Money'), ('VIREMENT', 'Virement'),
                         ('CHEQUE', 'Chèque')],
            ),
        ),
        migrations.AddField(
            model_name='immobilisation',
            name='compte_tresorerie',
            field=models.CharField(max_length=10, blank=True, default=''),
        ),
    ]
