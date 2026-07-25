"""Imputation des avances sur salaire et types de contrat.

Règle métier : une avance accordée est de l'argent déjà sorti de la caisse
(D 421). Elle doit être retranchée dès le prochain bulletin établi, sans que
sa date ait à « tomber » dans le mois de paie.
"""
import datetime
from decimal import Decimal

from django.test import TestCase

from apps.rh.models import AvanceSalaire, Employe, ParametresFiscaux
from apps.rh.services import PaieCalculateur
from apps.tenants.models import Tenant


class AvancesBase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='École')
        ParametresFiscaux.objects.create(annee=2026, tranches_ir=[])
        self.employe = Employe.objects.create(
            tenant=self.tenant, nom_complet='Moussa DIOP',
            type_employe='ENSEIGNANT', poste='Professeur',
            salaire_base=Decimal('200000'),
            date_embauche=datetime.date(2025, 1, 1))

    def _avance(self, montant, jour):
        return AvanceSalaire.objects.create(
            tenant=self.tenant, employe=self.employe,
            montant=Decimal(str(montant)), date_avance=jour)

    def _bulletin(self, mois, annee=2026, **kwargs):
        return PaieCalculateur.calculer_bulletin(self.employe, mois, annee, **kwargs)


class ImputationAvancesTest(AvancesBase):
    def test_avance_du_mois_retranchee(self):
        self._avance(30000, datetime.date(2026, 3, 15))
        self.assertEqual(self._bulletin(3)['avance_sur_salaire'], Decimal('30000'))

    def test_avance_posterieure_au_mois_retranchee(self):
        """Le cœur de la règle : une avance datée APRÈS le mois de paie doit
        quand même être retranchée du bulletin qu'on établit."""
        self._avance(30000, datetime.date(2026, 8, 20))
        self.assertEqual(self._bulletin(3)['avance_sur_salaire'], Decimal('30000'))

    def test_avance_anterieure_retranchee(self):
        self._avance(25000, datetime.date(2025, 11, 4))
        self.assertEqual(self._bulletin(3)['avance_sur_salaire'], Decimal('25000'))

    def test_cumul_de_plusieurs_avances(self):
        self._avance(10000, datetime.date(2025, 12, 1))
        self._avance(15000, datetime.date(2026, 3, 10))
        self._avance(20000, datetime.date(2026, 9, 30))
        self.assertEqual(self._bulletin(3)['avance_sur_salaire'], Decimal('45000'))

    def test_avance_deja_imputee_ignoree(self):
        a = self._avance(30000, datetime.date(2026, 3, 15))
        a.statut = 'IMPUTE'
        a.save()
        self.assertEqual(self._bulletin(4)['avance_sur_salaire'], Decimal('0'))

    def test_avance_annulee_ignoree(self):
        a = self._avance(30000, datetime.date(2026, 3, 15))
        a.statut = 'ANNULE'
        a.save()
        self.assertEqual(self._bulletin(3)['avance_sur_salaire'], Decimal('0'))

    def test_selection_explicite_prime(self):
        """La sélection manuelle reste maîtresse : elle peut n'en retenir
        qu'une, ou aucune."""
        a1 = self._avance(10000, datetime.date(2026, 3, 5))
        self._avance(20000, datetime.date(2026, 3, 6))
        self.assertEqual(self._bulletin(3, avance_ids=[a1.id])['avance_sur_salaire'],
                         Decimal('10000'))
        self.assertEqual(self._bulletin(3, avance_ids=[])['avance_sur_salaire'],
                         Decimal('0'))

    def test_avance_d_un_autre_employe_ignoree(self):
        autre = Employe.objects.create(
            tenant=self.tenant, nom_complet='Awa FALL',
            type_employe='APPUI', poste='Secrétaire',
            salaire_base=Decimal('150000'),
            date_embauche=datetime.date(2025, 1, 1))
        AvanceSalaire.objects.create(tenant=self.tenant, employe=autre,
                                     montant=Decimal('40000'),
                                     date_avance=datetime.date(2026, 3, 1))
        self.assertEqual(self._bulletin(3)['avance_sur_salaire'], Decimal('0'))

    def test_avance_diminue_le_net_a_payer(self):
        sans = self._bulletin(3)['net_a_payer']
        self._avance(30000, datetime.date(2026, 8, 20))
        avec = self._bulletin(3)['net_a_payer']
        self.assertEqual(sans - avec, Decimal('30000'))


class PlafonnementAvancesTest(AvancesBase):
    """Une avance plus lourde que le salaire se retient sur plusieurs mois :
    à concurrence du net disponible, jamais au-delà — sinon le net devient
    négatif et les écritures comptables portent des montants négatifs."""

    def _net_avant_avances(self):
        return self._bulletin(3)['net_a_payer']

    def test_retenue_plafonnee_au_net_disponible(self):
        dispo = self._net_avant_avances()
        self._avance(float(dispo) + 70000, datetime.date(2026, 3, 1))
        data = self._bulletin(3)
        self.assertEqual(data['avance_sur_salaire'], dispo)
        self.assertEqual(data['net_a_payer'], Decimal('0'))

    def test_le_solde_reste_du_le_mois_suivant(self):
        dispo = self._net_avant_avances()
        avance = self._avance(float(dispo) + 70000, datetime.date(2026, 3, 1))

        bulletin = PaieCalculateur.creer_bulletin(self.employe, 3, 2026)
        from apps.rh.services import _appliquer_imputation_avances
        _appliquer_imputation_avances(bulletin)

        avance.refresh_from_db()
        self.assertEqual(avance.montant_impute, dispo)
        self.assertEqual(avance.montant_restant, Decimal('70000'))
        # Non soldée → toujours en attente, donc reprise au bulletin suivant
        self.assertEqual(avance.statut, 'EN_ATTENTE')
        self.assertEqual(self._bulletin(4)['avance_sur_salaire'], Decimal('70000'))

    def test_avance_soldee_passe_impute(self):
        avance = self._avance(30000, datetime.date(2026, 3, 1))
        bulletin = PaieCalculateur.creer_bulletin(self.employe, 3, 2026)
        from apps.rh.services import _appliquer_imputation_avances
        _appliquer_imputation_avances(bulletin)

        avance.refresh_from_db()
        self.assertEqual(avance.statut, 'IMPUTE')
        self.assertEqual(avance.montant_restant, Decimal('0'))
        self.assertEqual(self._bulletin(4)['avance_sur_salaire'], Decimal('0'))

    def test_annulation_rend_la_part_retenue(self):
        dispo = self._net_avant_avances()
        avance = self._avance(float(dispo) + 70000, datetime.date(2026, 3, 1))
        bulletin = PaieCalculateur.creer_bulletin(self.employe, 3, 2026)
        from apps.rh.services import (_annuler_imputation_avances,
                                      _appliquer_imputation_avances)
        _appliquer_imputation_avances(bulletin)
        _annuler_imputation_avances(bulletin)

        avance.refresh_from_db()
        self.assertEqual(avance.montant_impute, Decimal('0'))
        self.assertEqual(avance.montant_restant, avance.montant)
        self.assertEqual(avance.statut, 'EN_ATTENTE')

    def test_les_plus_anciennes_se_soldent_d_abord(self):
        dispo = self._net_avant_avances()
        vieille = self._avance(50000, datetime.date(2025, 12, 1))
        recente = self._avance(float(dispo), datetime.date(2026, 3, 1))

        bulletin = PaieCalculateur.creer_bulletin(self.employe, 3, 2026)
        from apps.rh.services import _appliquer_imputation_avances
        _appliquer_imputation_avances(bulletin)

        vieille.refresh_from_db()
        recente.refresh_from_db()
        self.assertEqual(vieille.statut, 'IMPUTE')
        self.assertEqual(recente.montant_impute, dispo - Decimal('50000'))
        self.assertEqual(recente.statut, 'EN_ATTENTE')

    def test_net_jamais_negatif(self):
        for montant in (500000, 1000000):
            self._avance(montant, datetime.date(2026, 3, 1))
        self.assertGreaterEqual(self._bulletin(3)['net_a_payer'], Decimal('0'))


class TypeContratTest(TestCase):
    def test_prestataire_accepte(self):
        tenant = Tenant.objects.create(nom='École')
        e = Employe.objects.create(
            tenant=tenant, nom_complet='Ibrahima SOW',
            type_employe='APPUI', poste='Maintenance',
            type_contrat='PRESTATAIRE', salaire_base=Decimal('100000'),
            date_embauche=datetime.date(2026, 1, 1))
        e.full_clean()          # valide le choix contre CONTRAT_CHOICES
        e.refresh_from_db()
        self.assertEqual(e.type_contrat, 'PRESTATAIRE')
        self.assertEqual(e.get_type_contrat_display(), 'Prestataire')
