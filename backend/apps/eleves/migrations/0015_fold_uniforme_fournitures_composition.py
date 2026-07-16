from django.db import migrations


def fold_uniforme_fournitures(apps, schema_editor):
    """Les frais de section n'affichent plus que Inscription et Mensualité :
    l'uniforme et les fournitures deviennent des éléments de la composition
    de l'inscription. Total inchangé : (insc + unif + fourn) + mens×n avant,
    (insc·composé) + 0 + 0 + mens×n après.

    Piège évité : si la composition était vide, le montant d'inscription de
    base doit y entrer aussi, sinon le prochain save recalculerait
    frais_inscription = somme(composition) et perdrait la base."""
    Section = apps.get_model('eleves', 'Section')
    for s in Section.objects.all():
        unif  = float(s.frais_uniforme or 0)
        fourn = float(s.frais_fournitures or 0)
        if unif <= 0 and fourn <= 0:
            continue
        compo = list(s.composition_inscription or [])
        if not compo and float(s.frais_inscription or 0) > 0:
            compo.append({'libelle': "Frais d'inscription",
                          'montant': float(s.frais_inscription)})
        if unif > 0:
            compo.append({'libelle': 'Uniforme', 'montant': unif})
        if fourn > 0:
            compo.append({'libelle': 'Fournitures', 'montant': fourn})
        s.composition_inscription = compo
        s.frais_inscription  = sum(e['montant'] for e in compo)
        s.frais_uniforme     = 0
        s.frais_fournitures  = 0
        s.save(update_fields=['composition_inscription', 'frais_inscription',
                              'frais_uniforme', 'frais_fournitures'])


class Migration(migrations.Migration):

    dependencies = [
        ('eleves', '0014_service_mois_unique'),
    ]

    operations = [
        migrations.RunPython(fold_uniforme_fournitures, migrations.RunPython.noop),
    ]
