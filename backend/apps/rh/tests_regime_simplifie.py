"""Test : en régime SIMPLIFIÉ, le bulletin ne porte que ce qui a été saisi.

L'allocation de salaire unique est une prestation familiale, financée par la
cotisation CSS de l'employeur. Un établissement non affilié ne verse pas cette
cotisation, ne perçoit rien de la Caisse, et n'a donc aucune allocation à
servir. Elle était pourtant ajoutée au brut quel que soit le régime : un
salarié marié d'une structure non affiliée touchait plus que le montant
convenu avec lui.
"""
from decimal import Decimal

from django.test import TestCase

from apps.tenants.models import Tenant
from apps.rh.models import Employe, ParametresFiscaux
from apps.rh.services import PaieCalculateur


class RegimeSimplifieTest(TestCase):
    def setUp(self):
        self.params = ParametresFiscaux.objects.create(
            annee=2026,
            allocation_salaire_unique_base=Decimal('1800'),
            allocation_par_enfant=Decimal('1200'),
            plafond_allocation=Decimal('12000'),
        )

    def _tenant(self, regime):
        return Tenant.objects.create(nom=f'École {regime}', regime_paie=regime)

    def _employe(self, tenant, **kw):
        defauts = dict(nom_complet='Moussa DIOP', type_employe='ENSEIGNANT',
                       poste='Enseignant', type_contrat='CDI',
                       date_embauche='2025-10-01', salaire_base=Decimal('200000'),
                       situation_matrimoniale='MARIE', nb_enfants=3)
        defauts.update(kw)
        return Employe.objects.create(tenant=tenant, **defauts)

    def _bulletin(self, employe):
        return PaieCalculateur.calculer_bulletin(employe, mois=1, annee=2026)

    # ── Régime simplifié ──────────────────────────────────────────────────
    def test_aucune_allocation_pour_un_salarie_marie_avec_enfants(self):
        e = self._employe(self._tenant('SIMPLIFIE'))
        b = self._bulletin(e)
        self.assertEqual(b['allocation_salaire_unique'], Decimal('0'))

    def test_le_brut_est_exactement_le_salaire_declare(self):
        e = self._employe(self._tenant('SIMPLIFIE'))
        b = self._bulletin(e)
        self.assertEqual(b['salaire_brut'], Decimal('200000'))

    def test_le_net_est_exactement_le_salaire_declare(self):
        """Ni cotisation retenue, ni prestation ajoutée."""
        e = self._employe(self._tenant('SIMPLIFIE'))
        b = self._bulletin(e)
        self.assertEqual(b['net_a_payer'], Decimal('200000'))

    def test_la_situation_matrimoniale_ne_change_rien(self):
        tenant = self._tenant('SIMPLIFIE')
        nets = set()
        for situation, enfants in [('CELIBATAIRE', 0), ('MARIE', 4),
                                   ('VEUF', 2), ('DIVORCE', 1)]:
            e = self._employe(tenant, situation_matrimoniale=situation,
                              nb_enfants=enfants,
                              nom_complet=f'Agent {situation}')
            nets.add(self._bulletin(e)['net_a_payer'])
        self.assertEqual(nets, {Decimal('200000')},
                         "le net doit être le même quelle que soit la situation")

    def test_les_primes_saisies_restent_versees(self):
        """Le régime simplifié retire les prestations, pas ce que l'école décide."""
        e = self._employe(self._tenant('SIMPLIFIE'))
        b = PaieCalculateur.calculer_bulletin(e, mois=1, annee=2026,
                                              primes_diverses=50000)
        self.assertEqual(b['salaire_brut'], Decimal('250000'))
        self.assertEqual(b['net_a_payer'], Decimal('250000'))

    # ── Régime complet : le comportement ne bouge pas ─────────────────────
    def test_le_regime_complet_sert_toujours_l_allocation(self):
        e = self._employe(self._tenant('COMPLET'))
        b = self._bulletin(e)
        # 1 800 de base + 3 × 1 200, sous le plafond de 12 000
        self.assertEqual(b['allocation_salaire_unique'], Decimal('5400'))
        self.assertGreater(b['salaire_brut'], Decimal('200000'))

    def test_le_regime_complet_ne_sert_rien_a_un_celibataire_sans_enfant(self):
        e = self._employe(self._tenant('COMPLET'),
                          situation_matrimoniale='CELIBATAIRE', nb_enfants=0)
        b = self._bulletin(e)
        self.assertEqual(b['allocation_salaire_unique'], Decimal('0'))
