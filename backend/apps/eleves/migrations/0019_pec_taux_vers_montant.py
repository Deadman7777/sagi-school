"""Convertit les PEC existantes exprimées en taux (%) vers des montants directs.

pec_inscription = frais_inscription × taux_pec_inscription / 100 (si INSCRIPTION/TOTALE)
pec_mensualite  = frais_mensualite  × taux_pec_mensualite  / 100 (si MENSUALITES/TOTALE)
"""
from decimal import Decimal, ROUND_HALF_UP
from django.db import migrations


def _r(v):
    return Decimal(str(v)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def taux_vers_montant(apps, schema_editor):
    Eleve = apps.get_model('eleves', 'Eleve')
    for e in Eleve.objects.select_related('section').filter(type_pec__isnull=False):
        if not e.section:
            continue
        # ne pas écraser un montant déjà saisi
        if e.pec_inscription or e.pec_mensualite:
            continue
        if e.type_pec in ('INSCRIPTION', 'TOTALE') and e.taux_pec_inscription:
            e.pec_inscription = _r(e.section.frais_inscription * e.taux_pec_inscription / 100)
        if e.type_pec in ('MENSUALITES', 'TOTALE') and e.taux_pec_mensualite:
            e.pec_mensualite = _r(e.section.frais_mensualite * e.taux_pec_mensualite / 100)
        if e.pec_inscription or e.pec_mensualite:
            e.save(update_fields=['pec_inscription', 'pec_mensualite'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('eleves', '0018_eleve_pec_inscription_eleve_pec_mensualite'),
    ]
    operations = [migrations.RunPython(taux_vers_montant, noop)]
