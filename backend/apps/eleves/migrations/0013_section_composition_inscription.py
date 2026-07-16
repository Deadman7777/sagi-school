from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('eleves', '0012_eleve_nb_mois_passager_eleve_regime'),
    ]

    operations = [
        migrations.AddField(
            model_name='section',
            name='composition_inscription',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
