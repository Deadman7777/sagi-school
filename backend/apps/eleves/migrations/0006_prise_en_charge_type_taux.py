from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('eleves', '0005_prise_en_charge_statut'),
    ]

    operations = [
        migrations.AddField(
            model_name='eleve',
            name='type_pec',
            field=models.CharField(
                max_length=20,
                blank=True,
                null=True,
                choices=[
                    ('INSCRIPTION', "Frais d'inscription uniquement"),
                    ('MENSUALITES', 'Mensualités uniquement'),
                    ('TOTALE',      'Prise en charge totale'),
                ],
            ),
        ),
        migrations.AddField(
            model_name='eleve',
            name='taux_pec_inscription',
            field=models.DecimalField(
                max_digits=5, decimal_places=2, default=0,
                help_text='% réduction sur frais inscription',
            ),
        ),
        migrations.AddField(
            model_name='eleve',
            name='taux_pec_mensualite',
            field=models.DecimalField(
                max_digits=5, decimal_places=2, default=0,
                help_text='% réduction sur mensualités',
            ),
        ),
    ]
