"""Test : le compte de résultat retient la contribution NETTE des comptes.

Sommer le seul sens naturel (crédit pour un produit, débit pour une charge)
ignore les annulations et les neutralisations de migration. Chez Shoumoul, la
ligne « Prestations de services — Scolarité » affichait 29 877 500 (crédit
brut) alors que le net valait 13 410 500.
"""
import datetime

from rest_framework.test import APITestCase

from apps.comptabilite.models import JournalEntry
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant
from apps.users.models import User


class CompteResultatNetTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul', code_etablissement='SHE')
        self.user = User.objects.create_user(
            'a@a.sn', 'x', nom='Admin', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', cloture=False,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))

    def _je(self, compte, debit, credit, source='MIGRATION'):
        return JournalEntry.objects.create(
            tenant=self.tenant, exercice=self.ex, no_piece='X',
            date_ecriture=self.ex.date_debut, no_compte=compte,
            debit=debit, credit=credit, source=source, ordre=1)

    def _resultat(self):
        r = self.client.get('/api/comptabilite/compte-resultat/')
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.data

    def test_produits_nets_de_la_neutralisation(self):
        # Agrégats migrés + reprises créditées puis neutralisées
        self._je('571', 13337500, 0)
        self._je('706', 0, 13337500)
        self._je('706', 0, 16540000, 'PAIEMENT')
        self._je('706', 16417000, 0, 'RECAL_MIGRATION')   # neutralisation
        self._je('706', 50000, 0, 'ANNUL_PAIEMENT')       # annulation

        d = self._resultat()

        # 29 877 500 de crédit brut − 16 467 000 de débit = 13 410 500
        self.assertEqual(d['sig']['production_exercice'], 13410500)
        self.assertEqual(d['total_produits'], 13410500)
        # La ligne de détail doit dire la MÊME chose que le total.
        ligne706 = [l for l in d['detail_produits'] if l['compte'] == '706'][0]
        self.assertEqual(ligne706['montant'], 13410500)

    def test_charges_nettes_de_leurs_contre_ecritures(self):
        self._je('658', 500000, 0, 'CHARGE')
        self._je('658', 0, 200000, 'CHARGE')   # contre-écriture d'annulation

        d = self._resultat()

        self.assertEqual(d['sig']['autres_charges'], 300000)
        ligne658 = [l for l in d['detail_charges'] if l['compte'] == '658'][0]
        self.assertEqual(ligne658['montant'], 300000)

    def test_sans_contre_ecriture_le_resultat_est_inchange(self):
        """Garde-fou : le netting ne doit rien changer au cas nominal."""
        self._je('706', 0, 1000000)
        self._je('658', 400000, 0, 'CHARGE')

        d = self._resultat()

        self.assertEqual(d['sig']['production_exercice'], 1000000)
        self.assertEqual(d['sig']['autres_charges'], 400000)


class ANouveauxHorsResultatTest(CompteResultatNetTest):
    """890 est le compte d'À-NOUVEAUX, pas un impôt.

    Le préfixe « 89 » du compte de résultat le ramassait et le présentait en
    « Impôt sur le résultat » : le résultat net s'en trouvait faussé du montant
    des à-nouveaux, et une ligne « 890 | 890 » sans libellé apparaissait dans
    les charges d'un document officiel.
    """

    def test_890_n_entre_ni_dans_les_charges_ni_dans_le_resultat(self):
        self._je('706', 0, 1000000)
        self._je('661', 300000, 0, 'CHARGE')
        # À-nouveaux d'une reprise : 411 D / 890 C, plus un 890 D d'ouverture.
        self._je('890', 115000, 0, 'MIGRATION')

        d = self._resultat()

        self.assertEqual(d['total_charges'], 300000)
        self.assertEqual(d['resultat_net'], 700000)
        self.assertFalse(any(l['compte'] == '890' for l in d['detail_charges']))

    def test_le_total_egale_toujours_la_somme_des_lignes(self):
        """Un total supérieur à la somme affichée est le plus sûr moyen de
        faire douter d'un état financier."""
        self._je('706', 0, 1000000)
        self._je('661', 300000, 0, 'CHARGE')
        self._je('890', 115000, 0, 'MIGRATION')

        d = self._resultat()

        self.assertEqual(d['total_charges'],
                         sum(l['montant'] for l in d['detail_charges']))

    def test_un_vrai_compte_89x_reste_compte(self):
        """Seul 890 est écarté : l'impôt sur le résultat doit rester."""
        self._je('706', 0, 1000000)
        self._je('891', 50000, 0, 'CHARGE')

        d = self._resultat()

        self.assertEqual(d['total_charges'], 50000)
        self.assertTrue(any(l['compte'] == '891' for l in d['detail_charges']))
