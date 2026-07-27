"""Mois dus saisissables + les montants de PEC deviennent la seule source.

Deux choses liées par le même besoin : permettre à l'école de corriger la
situation d'un élève et que la correction TIENNE.

1. `mois_dus` — les mois réellement facturés, saisis par l'école. Vide = le
   prorata automatique continue de s'appliquer, donc aucune école existante
   ne change de comportement.

2. Matérialisation des prises en charge. `montant_pec_*` repliait sur
   `type_pec` / `taux_pec_*` quand le montant valait 0 — et 0 est falsy. Une
   école qui retirait une prise en charge en remettant le montant à zéro la
   voyait revenir par le taux : la correction était impossible à saisir.

   On calcule donc une dernière fois le montant effectif (montant s'il existe,
   sinon taux × frais), on l'écrit, puis on neutralise les taux. Après ça, le
   montant dit la vérité, y compris quand il vaut zéro.

   Les taux ne sont pas supprimés du modèle : ils restent lisibles pour
   l'historique, ils ne pilotent simplement plus rien.
"""
from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations, models


def _r(v):
    return Decimal(str(v)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def materialiser_pec(apps, schema_editor):
    Eleve = apps.get_model('eleves', 'Eleve')
    for e in Eleve.objects.select_related('section').filter(type_pec__isnull=False):
        if not e.section:
            continue
        change = False
        if not e.pec_inscription and e.type_pec in ('INSCRIPTION', 'TOTALE') \
                and e.taux_pec_inscription:
            e.pec_inscription = _r(
                e.section.frais_inscription * e.taux_pec_inscription / 100)
            change = True
        if not e.pec_mensualite and e.type_pec in ('MENSUALITES', 'TOTALE') \
                and e.taux_pec_mensualite:
            e.pec_mensualite = _r(
                e.section.frais_mensualite * e.taux_pec_mensualite / 100)
            change = True
        # Les taux ne doivent plus pouvoir reprendre la main, que la fiche ait
        # été convertie maintenant ou par la migration 0019.
        e.taux_pec_inscription = 0
        e.taux_pec_mensualite = 0
        e.save(update_fields=['pec_inscription', 'pec_mensualite',
                              'taux_pec_inscription', 'taux_pec_mensualite']
               if change else ['taux_pec_inscription', 'taux_pec_mensualite'])


def noop(apps, schema_editor):
    """Irréversible par nature : les taux d'origine ne sont pas conservés.
    Le montant matérialisé reste, il porte la même information."""


class Migration(migrations.Migration):
    dependencies = [
        ('eleves', '0023_eleve_fiche_creance'),
    ]
    operations = [
        migrations.AddField(
            model_name='eleve',
            name='mois_dus',
            field=models.JSONField(
                blank=True, default=list,
                help_text='Mois facturés (1-12) — vide = prorata automatique'),
        ),
        migrations.RunPython(materialiser_pec, noop),
    ]
