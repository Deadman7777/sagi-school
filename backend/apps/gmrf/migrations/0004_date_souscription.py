from django.db import migrations, models
from django.db.models import F


def reprendre_dates(apps, schema_editor):
    """Jusqu'ici la souscription se confondait avec la 1ʳᵉ échéance (NATT) et
    avec le déblocage (prêt) : on reprend ces dates comme date de souscription."""
    apps.get_model('gmrf', 'NattCycle').objects.update(date_souscription=F('date_debut'))
    apps.get_model('gmrf', 'Pret').objects.update(date_souscription=F('date_deblocage'))


class Migration(migrations.Migration):

    dependencies = [
        ("gmrf", "0003_categories_apport_avance"),
    ]

    operations = [
        migrations.AddField(
            model_name="nattcycle",
            name="date_souscription",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="pret",
            name="date_souscription",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.RunPython(reprendre_dates, migrations.RunPython.noop),
    ]
