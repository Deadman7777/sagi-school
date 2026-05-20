import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('comptabilite', '0005_alter_journalentry_options'),
        ('paiements',    '0002_initial'),
        ('tenants',      '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='CompteComptable',
            fields=[
                ('id',          models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at',  models.DateTimeField(auto_now_add=True)),
                ('updated_at',  models.DateTimeField(auto_now=True)),
                ('no_compte',   models.CharField(max_length=10)),
                ('libelle',     models.CharField(max_length=200)),
                ('type',        models.CharField(
                    choices=[('BILAN', 'Compte de bilan'), ('CHARGE', 'Compte de charge'), ('PRODUIT', 'Compte de produit')],
                    default='CHARGE', max_length=10,
                )),
                ('classe',      models.IntegerField()),
                ('est_actif',   models.BooleanField(default=True)),
                ('est_systeme', models.BooleanField(default=False)),
                ('tenant',      models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='comptabilite_comptecomptable_set',
                    to='tenants.tenant',
                )),
            ],
            options={'db_table': 'comptes_comptables', 'ordering': ['no_compte']},
        ),
        migrations.AlterUniqueTogether(
            name='comptecomptable',
            unique_together={('tenant', 'no_compte')},
        ),
        migrations.CreateModel(
            name='BudgetLigne',
            fields=[
                ('id',          models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at',  models.DateTimeField(auto_now_add=True)),
                ('updated_at',  models.DateTimeField(auto_now=True)),
                ('no_compte',   models.CharField(max_length=10)),
                ('libelle',     models.CharField(max_length=200)),
                ('type_charge', models.CharField(
                    choices=[('FIXE', 'Charge fixe'), ('VARIABLE', 'Charge variable')],
                    default='FIXE', max_length=10,
                )),
                ('m01', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('m02', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('m03', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('m04', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('m05', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('m06', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('m07', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('m08', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('m09', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('m10', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('m11', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('m12', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('exercice', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='budget_lignes', to='paiements.exercice',
                )),
                ('tenant', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='comptabilite_budgetligne_set',
                    to='tenants.tenant',
                )),
            ],
            options={'db_table': 'budget_lignes', 'ordering': ['no_compte']},
        ),
        migrations.AlterUniqueTogether(
            name='budgetligne',
            unique_together={('tenant', 'exercice', 'no_compte')},
        ),
    ]
