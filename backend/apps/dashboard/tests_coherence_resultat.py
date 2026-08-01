"""Test : le tableau de bord et le compte de résultat annoncent le MÊME résultat.

Le tableau de bord ne totalisait que les écritures source CHARGE/BUDGET/
MIGRATION. Une école dont la paie, les amortissements et les intérêts
d'emprunt pèsent l'essentiel des charges lisait donc un bénéfice très
supérieur au vrai, pendant que le compte de résultat, lui, était juste.

On n'assied pas ce test sur des montants en dur : on vérifie que les deux
écrans répondent la même chose sur les mêmes écritures.
"""
import datetime

from rest_framework.test import APITestCase

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.paiements.models import Exercice
from apps.comptabilite.models import JournalEntry


class CoherenceResultatTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Les Palmiers')
        self.user = User.objects.create_user(
            'dir@palmiers.sn', 'x', nom='Directrice', role='ADMIN_ECOLE',
            tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2025-2026', cloture=False,
            date_debut=datetime.date(2025, 10, 1), date_fin=datetime.date(2026, 7, 31))

    def _je(self, compte, debit, credit, source):
        return JournalEntry.objects.create(
            tenant=self.tenant, exercice=self.ex, no_piece='X',
            date_ecriture=self.ex.date_debut, no_compte=compte,
            debit=debit, credit=credit, source=source, ordre=1)

    def _ecritures_d_une_annee(self):
        # Scolarité encaissée
        self._je('571', 40000000, 0, 'PAIEMENT')
        self._je('706', 0, 40000000, 'PAIEMENT')
        # Charges de fonctionnement — la seule famille que l'ancien calcul voyait
        self._je('622', 3500000, 0, 'CHARGE')
        self._je('571', 0, 3500000, 'CHARGE')
        # Paie : source PAIE, ignorée par l'ancien calcul
        self._je('661', 25000000, 0, 'PAIE')
        self._je('571', 0, 25000000, 'PAIE')
        # Dotation aux amortissements : source AMORTISSEMENT, ignorée elle aussi
        self._je('681', 2400000, 0, 'AMORTISSEMENT')
        self._je('2845', 0, 2400000, 'AMORTISSEMENT')
        # Intérêts d'emprunt : source GMRF
        self._je('671', 410000, 0, 'GMRF_PRET')
        self._je('521', 0, 410000, 'GMRF_PRET')

    def test_meme_resultat_net_sur_les_deux_ecrans(self):
        self._ecritures_d_une_annee()

        kpis = self.client.get('/api/dashboard/kpis/')
        cr = self.client.get('/api/comptabilite/compte-resultat/')
        self.assertEqual(kpis.status_code, 200, kpis.content)
        self.assertEqual(cr.status_code, 200, cr.content)

        self.assertEqual(kpis.data['kpis']['total_charges'], cr.data['total_charges'])
        self.assertEqual(kpis.data['kpis']['total_recettes'], cr.data['total_produits'])
        self.assertEqual(kpis.data['kpis']['resultat_net'], cr.data['resultat_net'])

    def test_l_ecran_de_cloture_annonce_le_meme_resultat(self):
        """L'écran où le directeur valide sa fin d'année doit dire la vérité."""
        from apps.paiements.cloturer import verifier_avant_cloture
        self._ecritures_d_une_annee()

        stats = verifier_avant_cloture(self.ex)['stats']
        cr = self.client.get('/api/comptabilite/compte-resultat/')

        self.assertEqual(stats['total_charges'], cr.data['total_charges'])
        self.assertEqual(stats['total_recettes'], cr.data['total_produits'])
        self.assertEqual(stats['resultat_net'], cr.data['resultat_net'])

    def test_la_cloture_ne_compte_pas_les_charges_en_double(self):
        """Une charge écrit 4 lignes : sommer le débit brut la doublait."""
        from apps.paiements.cloturer import verifier_avant_cloture
        # Une charge complète : constatation puis règlement.
        self._je('622', 1000000, 0, 'CHARGE')      # charge
        self._je('401', 0, 1000000, 'CHARGE')      # dette fournisseur
        self._je('401', 1000000, 0, 'CHARGE')      # règlement de la dette
        self._je('571', 0, 1000000, 'CHARGE')      # sortie de caisse

        stats = verifier_avant_cloture(self.ex)['stats']
        self.assertEqual(stats['total_charges'], 1000000)

    def test_les_charges_du_tableau_de_bord_contiennent_la_paie(self):
        """Le point précis qui faussait le bénéfice affiché à l'école."""
        self._ecritures_d_une_annee()

        kpis = self.client.get('/api/dashboard/kpis/')
        charges = kpis.data['kpis']['total_charges']
        # 3 500 000 de loyer seuls = l'ancien comportement.
        self.assertGreater(charges, 3500000)
        # Loyer + paie + dotation + intérêts
        self.assertEqual(charges, 3500000 + 25000000 + 2400000 + 410000)
