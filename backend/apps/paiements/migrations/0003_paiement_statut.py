from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('paiements', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='paiement',
            name='statut',
            field=models.CharField(
                choices=[('ACTIF', 'Actif'), ('ANNULE', 'Annulé')],
                default='ACTIF',
                max_length=10,
            ),
        ),
    ]
