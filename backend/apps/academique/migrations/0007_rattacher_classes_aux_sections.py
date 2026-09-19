"""Rattache les classes existantes à leur section, et la section à son niveau.

Jusqu'ici le lien n'existait qu'en apparence : le front rapprochait une classe
et une section quand `classe.niveau.nom == section.nom`. On reprend exactement
cette convention pour poser la vraie clé étrangère — aucune école ne voit son
rangement changer — puis la section hérite du niveau de ses classes.

Rien n'est créé : une classe dont le niveau ne correspond à aucune section
reste sans section, et l'école la rangera elle-même.
"""
from django.db import migrations


def rattacher(apps, schema_editor):
    Classe = apps.get_model('academique', 'Classe')
    Section = apps.get_model('eleves', 'Section')

    sections = {}
    for s in Section.objects.all():
        sections[(s.tenant_id, s.nom.strip().lower())] = s

    for classe in Classe.objects.select_related('niveau').filter(section__isnull=True,
                                                                 niveau__isnull=False):
        section = sections.get((classe.tenant_id, classe.niveau.nom.strip().lower()))
        if section is None:
            continue
        classe.section = section
        classe.save(update_fields=['section'])
        # La section prend le niveau de ses classes — c'est la seule
        # information de niveau qui existait jusqu'ici.
        if section.niveau_id is None:
            section.niveau_id = classe.niveau_id
            section.save(update_fields=['niveau'])


def detacher(apps, schema_editor):
    apps.get_model('academique', 'Classe').objects.update(section=None)
    apps.get_model('eleves', 'Section').objects.update(niveau=None)


class Migration(migrations.Migration):
    dependencies = [
        ('academique', '0006_classe_section'),
        ('eleves', '0037_section_niveau'),
    ]
    operations = [migrations.RunPython(rattacher, detacher)]
