from django.db import migrations

ROLE_MAP = {
    'LECTURE':    'LECTEUR',
    'COMPTABLE':  'ADMIN_COMPTABLE',
    'CAISSIER':   'ADMIN_SCOLARITE',
}


def migrate_old_roles(apps, schema_editor):
    User = apps.get_model('users', 'User')
    for old, new in ROLE_MAP.items():
        User.objects.filter(role=old).update(role=new)


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_alter_user_role'),
    ]

    operations = [
        migrations.RunPython(migrate_old_roles, migrations.RunPython.noop),
    ]
