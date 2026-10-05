"""Installe les paramètres et obligations fiscales nationaux manquants.

N'écrase jamais une valeur existante : après une loi de finances, ajoutez le
nouveau taux dans apps/fiscal/referentiel.py avec sa date d'effet, puis
relancez cette commande (ou saisissez-le dans Fiscal → Paramétrage).
"""
from django.core.management.base import BaseCommand

from apps.fiscal.models import ObligationFiscale, ParametreFiscal
from apps.fiscal.referentiel import installer


class Command(BaseCommand):
    help = 'Installe le référentiel fiscal national (sans écraser l’existant).'

    def handle(self, *args, **options):
        n_p, n_o = installer(ParametreFiscal, ObligationFiscale)
        self.stdout.write(self.style.SUCCESS(f'{n_p} paramètre(s), {n_o} obligation(s) ajoutés.'))
