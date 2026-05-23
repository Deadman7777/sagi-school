import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('tenants', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id',          models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('utilisateur', models.CharField(blank=True, max_length=200)),
                ('action',      models.CharField(choices=[('CREATE','Création'),('UPDATE','Modification'),('DELETE','Suppression'),('VALIDATE','Validation'),('ANNULER','Annulation')], max_length=20)),
                ('modele',      models.CharField(max_length=100)),
                ('objet_id',    models.CharField(blank=True, max_length=100)),
                ('description', models.TextField(blank=True)),
                ('created_at',  models.DateTimeField(auto_now_add=True)),
                ('tenant',      models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='tenants.tenant')),
            ],
            options={'db_table': 'audit_logs', 'ordering': ['-created_at']},
        ),
    ]
