from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('eleves', '0013_section_composition_inscription'),
    ]

    operations = [
        migrations.AddField(
            model_name='service',
            name='mois_unique',
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
    ]
