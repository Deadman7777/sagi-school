"""Test : prise en charge exprimée en MONTANT direct (au lieu du taux %)."""
import datetime
from django.test import TestCase

from apps.tenants.models import Tenant
from apps.paiements.models import Exercice
from apps.eleves.models import Eleve, Section


class PecMontantTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='T')
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', nb_mensualites=12,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='S', frais_inscription=185000, frais_mensualite=60000)

    def _e(self, **pec):
        return Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, nom_complet='X', section=self.section,
            date_inscription=datetime.date(2026, 1, 1), **pec)

    def test_pec_montant_reduit_le_du(self):
        e = self._e(pec_inscription=100000, pec_mensualite=20000)
        self.assertEqual(e.frais_mensualite_effectif, 40000)      # 60000 - 20000
        self.assertEqual(e.montant_pec_annuel, 340000)            # 100000 + 20000*12
        self.assertEqual(e.total_attendu, 565000)                 # 905000 - 340000

    def test_montant_plafonne_aux_frais(self):
        e = self._e(pec_mensualite=90000)                        # > 60000
        self.assertEqual(e.montant_pec_mensualite_mensuel, 60000)  # plafonné
        self.assertEqual(e.frais_mensualite_effectif, 0)

    def test_le_montant_est_la_seule_source_le_taux_ne_reprend_pas_la_main(self):
        """Le repli sur le taux a été retiré (migration 0024).

        Il rendait 0 insaisissable : une école qui retirait une prise en charge
        en remettant le montant à zéro la voyait revenir par le taux, et la
        correction était impossible depuis l'application. Les taux existants
        ont été matérialisés en montants une fois pour toutes ; ils ne pilotent
        plus le calcul et ne restent que pour l'historique.
        """
        e = self._e(type_pec='MENSUALITES', taux_pec_mensualite=50)
        self.assertEqual(e.montant_pec_mensualite_mensuel, 0)
        self.assertEqual(e.frais_mensualite_effectif, 60000)

    def test_le_montant_materialise_par_la_migration_pilote_le_calcul(self):
        """Après 0024, une fiche historiquement à 50 % porte le montant."""
        e = self._e(pec_mensualite=30000, type_pec='MENSUALITES',
                    taux_pec_mensualite=0)
        self.assertEqual(e.montant_pec_mensualite_mensuel, 30000)
        self.assertEqual(e.frais_mensualite_effectif, 30000)
