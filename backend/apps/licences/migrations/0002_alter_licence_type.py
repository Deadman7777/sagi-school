from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('licences', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='licence',
            name='type',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('ESSAI',        'Essai 30 jours'),
                    ('BASIC',        'Basic'),
                    ('PRO',          'Pro'),
                    ('AVANCE',       'Avancé'),
                    ('TAXAWU_DAARA', 'Taxawu Daara'),
                ],
                default='ESSAI',
            ),
        ),
    ]
