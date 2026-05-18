from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('eleves', '0003_eleve_matricule'),
    ]

    operations = [
        migrations.RemoveField(model_name='eleve', name='nom_parent'),
        migrations.RemoveField(model_name='eleve', name='telephone_parent'),
        migrations.AddField(
            model_name='eleve',
            name='lieu_naissance',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='eleve',
            name='nom_pere',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='eleve',
            name='telephone_pere',
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name='eleve',
            name='nom_mere',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='eleve',
            name='telephone_mere',
            field=models.CharField(blank=True, max_length=20),
        ),
    ]
