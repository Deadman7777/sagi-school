from django.db import migrations


def installer(apps, schema_editor):
    from apps.fiscal.referentiel import installer as installer_referentiel
    installer_referentiel(apps.get_model('fiscal', 'ParametreFiscal'),
                          apps.get_model('fiscal', 'ObligationFiscale'))


class Migration(migrations.Migration):
    dependencies = [('fiscal', '0001_initial')]
    operations = [migrations.RunPython(installer, migrations.RunPython.noop)]
