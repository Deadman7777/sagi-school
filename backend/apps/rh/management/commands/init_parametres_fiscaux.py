import datetime
from decimal import Decimal
from django.core.management.base import BaseCommand
from apps.rh.models import ParametresFiscaux, TRANCHES_IR_DEFAULT


DEFAULTS = {
    'taux_ipres_general_salarie':      Decimal('5.6'),
    'taux_ipres_general_patronal':     Decimal('8.4'),
    'plafond_ipres_general':           Decimal('300000'),
    'taux_ipres_cadre_salarie':        Decimal('2.4'),
    'taux_ipres_cadre_patronal':       Decimal('3.6'),
    'plafond_ipres_cadre':             Decimal('900000'),
    'taux_css_prestations_familiales': Decimal('7.0'),
    'plafond_css':                     Decimal('63000'),
    'taux_atmp':                       Decimal('1.0'),
    'taux_cfce':                       Decimal('1.0'),
    'prime_transport':                 Decimal('20800'),
    'allocation_salaire_unique_base':  Decimal('5000'),
    'allocation_par_enfant':           Decimal('800'),
    'plafond_allocation':              Decimal('6400'),
    'tranches_ir':                     TRANCHES_IR_DEFAULT,
}


class Command(BaseCommand):
    help = 'Initialise les paramètres fiscaux SYSCOHADA pour une année (défaut : année courante)'

    def add_arguments(self, parser):
        parser.add_argument('--annee', type=int, default=datetime.date.today().year,
                            help='Année fiscale à initialiser')
        parser.add_argument('--force', action='store_true',
                            help='Écraser les paramètres existants')

    def handle(self, *args, **options):
        annee = options['annee']
        force = options['force']

        exists = ParametresFiscaux.objects.filter(annee=annee).exists()
        if exists and not force:
            self.stdout.write(
                self.style.WARNING(
                    f'Paramètres fiscaux {annee} déjà présents. '
                    'Utilisez --force pour écraser.'
                )
            )
            return

        obj, created = ParametresFiscaux.objects.update_or_create(
            annee=annee,
            defaults=DEFAULTS,
        )
        action = 'Créés' if created else 'Mis à jour'
        self.stdout.write(
            self.style.SUCCESS(f'{action} : paramètres fiscaux SYSCOHADA {annee}')
        )
        self.stdout.write(f'  IPRES général salarié : {obj.taux_ipres_general_salarie} %')
        self.stdout.write(f'  IPRES général patronal: {obj.taux_ipres_general_patronal} %')
        self.stdout.write(f'  CSS prest. familiales : {obj.taux_css_prestations_familiales} %')
        self.stdout.write(f'  CFCE                  : {obj.taux_cfce} %')
        self.stdout.write(f'  Prime de transport    : {obj.prime_transport} FCFA')
