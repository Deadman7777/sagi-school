from decimal import Decimal
import django.db.models.deletion
import uuid
from django.db import migrations, models

TRANCHES_IR_DEFAULT = [
    {"min": 0,       "max": 630000,  "taux": 0},
    {"min": 630001,  "max": 1500000, "taux": 20},
    {"min": 1500001, "max": 4000000, "taux": 30},
    {"min": 4000001, "max": 8000000, "taux": 35},
    {"min": 8000001, "max": None,    "taux": 40},
]


class Migration(migrations.Migration):

    dependencies = [
        ('rh', '0001_initial'),
        ('tenants', '0001_initial'),
    ]

    operations = [
        # ── 1. Nouveaux champs Employe ──────────────────────────────────────────
        migrations.AddField(
            model_name='employe',
            name='niveau_enseignement',
            field=models.CharField(
                blank=True, default='', max_length=15,
                choices=[
                    ('PRESCOLAIRE', 'Préscolaire'), ('ELEMENTAIRE', 'Élémentaire'),
                    ('MOYEN', 'Moyen'), ('SECONDAIRE', 'Secondaire'), ('SUPERIEUR', 'Supérieur'),
                ],
            ),
        ),
        migrations.AddField(
            model_name='employe',
            name='nb_enfants',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='employe',
            name='situation_matrimoniale',
            field=models.CharField(
                default='CELIBATAIRE', max_length=15,
                choices=[
                    ('CELIBATAIRE', 'Célibataire'), ('MARIE', 'Marié(e)'),
                    ('DIVORCE', 'Divorcé(e)'), ('VEUF', 'Veuf/Veuve'),
                ],
            ),
        ),
        migrations.AddField(
            model_name='employe',
            name='est_cadre',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='employe',
            name='mode_paiement',
            field=models.CharField(
                default='CAISSE', max_length=15,
                choices=[
                    ('BANQUE', 'Banque (virement)'), ('CAISSE', 'Caisse (espèces)'),
                    ('WAVE', 'Wave'), ('ORANGE_MONEY', 'Orange Money'),
                    ('FREE_MONEY', 'Free Money'), ('WIZALL', 'Wizall'), ('AUTRE', 'Autre'),
                ],
            ),
        ),
        migrations.AddField(
            model_name='employe',
            name='numero_compte',
            field=models.CharField(blank=True, max_length=50),
        ),

        # ── 2. ParametresFiscaux ────────────────────────────────────────────────
        migrations.CreateModel(
            name='ParametresFiscaux',
            fields=[
                ('id',    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('annee', models.IntegerField(unique=True)),
                ('taux_ipres_general_salarie',      models.DecimalField(decimal_places=3, default=Decimal('5.6'),   max_digits=6)),
                ('taux_ipres_general_patronal',     models.DecimalField(decimal_places=3, default=Decimal('8.4'),   max_digits=6)),
                ('plafond_ipres_general',           models.DecimalField(decimal_places=2, default=Decimal('300000'), max_digits=12)),
                ('taux_ipres_cadre_salarie',        models.DecimalField(decimal_places=3, default=Decimal('2.4'),   max_digits=6)),
                ('taux_ipres_cadre_patronal',       models.DecimalField(decimal_places=3, default=Decimal('3.6'),   max_digits=6)),
                ('plafond_ipres_cadre',             models.DecimalField(decimal_places=2, default=Decimal('900000'), max_digits=12)),
                ('taux_css_prestations_familiales', models.DecimalField(decimal_places=3, default=Decimal('7.0'),   max_digits=6)),
                ('plafond_css',                     models.DecimalField(decimal_places=2, default=Decimal('63000'), max_digits=12)),
                ('taux_atmp',                       models.DecimalField(decimal_places=3, default=Decimal('1.0'),   max_digits=6)),
                ('taux_cfce',                       models.DecimalField(decimal_places=3, default=Decimal('1.0'),   max_digits=6)),
                ('prime_transport',                 models.DecimalField(decimal_places=2, default=Decimal('20800'), max_digits=10)),
                ('allocation_salaire_unique_base',  models.DecimalField(decimal_places=2, default=Decimal('5000'),  max_digits=10)),
                ('allocation_par_enfant',           models.DecimalField(decimal_places=2, default=Decimal('800'),   max_digits=10)),
                ('plafond_allocation',              models.DecimalField(decimal_places=2, default=Decimal('6400'),  max_digits=10)),
                ('tranches_ir', models.JSONField(default=list)),
            ],
            options={'db_table': 'parametres_fiscaux', 'ordering': ['-annee'],
                     'verbose_name': 'Paramètres fiscaux',
                     'verbose_name_plural': 'Paramètres fiscaux'},
        ),

        # ── 3. AvanceSalaire ────────────────────────────────────────────────────
        migrations.CreateModel(
            name='AvanceSalaire',
            fields=[
                ('id',           models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at',   models.DateTimeField(auto_now_add=True)),
                ('updated_at',   models.DateTimeField(auto_now=True)),
                ('montant',      models.DecimalField(decimal_places=2, max_digits=12)),
                ('date_avance',  models.DateField()),
                ('mode_paiement', models.CharField(
                    default='CAISSE', max_length=15,
                    choices=[
                        ('BANQUE', 'Banque'), ('WAVE', 'Wave'), ('ORANGE_MONEY', 'Orange Money'),
                        ('FREE_MONEY', 'Free Money'), ('WIZALL', 'Wizall'), ('CAISSE', 'Caisse'),
                    ],
                )),
                ('no_piece',     models.CharField(blank=True, max_length=30)),
                ('statut',       models.CharField(
                    default='EN_ATTENTE', max_length=15,
                    choices=[('EN_ATTENTE', 'En attente'), ('IMPUTE', 'Imputé sur bulletin'), ('ANNULE', 'Annulé')],
                )),
                ('observations', models.TextField(blank=True)),
                ('employe',      models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                                   related_name='avances', to='rh.employe')),
                ('tenant',       models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                                   related_name='rh_avancesalaire_set', to='tenants.tenant')),
            ],
            options={'db_table': 'avances_salaire', 'ordering': ['-date_avance']},
        ),

        # ── 4. BulletinPaie ─────────────────────────────────────────────────────
        migrations.CreateModel(
            name='BulletinPaie',
            fields=[
                ('id',         models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('mois',       models.IntegerField()),
                ('annee',      models.IntegerField()),
                # gains
                ('salaire_base',              models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('nb_heures_sup',             models.DecimalField(decimal_places=2, default=0, max_digits=6)),
                ('heures_sup_montant',        models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('indemnite_sujetion',        models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('indemnite_logement',        models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('allocation_salaire_unique', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('prime_transport',           models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('primes_diverses',           models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('avantages_nature',          models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('salaire_brut',              models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                # retenues salariales
                ('ipres_general_salarie',     models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('ipres_cadre_salarie',       models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('ir_retenu',                 models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('avance_sur_salaire',        models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('opposition_saisie',         models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('autres_retenues',           models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('total_retenues_salariales', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                # charges patronales
                ('ipres_general_patronal',      models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('ipres_cadre_patronal',        models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('css_prestations_familiales',  models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('atmp',                        models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('cfce',                        models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('total_charges_patronales',    models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                # résultat
                ('net_a_payer',            models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('cout_total_employeur',   models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('statut',                 models.CharField(
                    default='BROUILLON', max_length=15,
                    choices=[('BROUILLON', 'Brouillon'), ('VALIDE', 'Validé'), ('PAYE', 'Payé')],
                )),
                ('date_validation',        models.DateTimeField(blank=True, null=True)),
                ('date_paiement',          models.DateTimeField(blank=True, null=True)),
                ('mode_paiement_effectif', models.CharField(
                    default='CAISSE', max_length=15,
                    choices=[
                        ('BANQUE', 'Banque (virement)'), ('CAISSE', 'Caisse (espèces)'),
                        ('WAVE', 'Wave'), ('ORANGE_MONEY', 'Orange Money'),
                        ('FREE_MONEY', 'Free Money'), ('WIZALL', 'Wizall'), ('AUTRE', 'Autre'),
                    ],
                )),
                # FK
                ('employe', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                              related_name='bulletins', to='rh.employe')),
                ('parametres_fiscaux', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    to='rh.parametresfiscaux',
                )),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                             related_name='rh_bulletinpaie_set', to='tenants.tenant')),
                ('avances', models.ManyToManyField(blank=True, related_name='bulletins', to='rh.avancesalaire')),
            ],
            options={
                'db_table': 'bulletins_paie',
                'ordering': ['-annee', '-mois'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='bulletinpaie',
            unique_together={('tenant', 'employe', 'mois', 'annee')},
        ),
    ]
