"""Tests : boursiers et organismes payeurs.

La distinction qui structure tout : une prise en charge SOCIALE est une remise
— l'école renonce, personne ne paie. Une prise en charge par un ORGANISME
change le débiteur — un tiers doit cet argent à l'école.

Les confondre ferait disparaître des créances réelles du suivi financier. Pour
un centre de formation dont la moitié des étudiants sont boursiers de l'État,
c'est la moitié de ses recettes qui deviendrait invisible.
"""
import datetime

from rest_framework.test import APITestCase

from apps.eleves.models import Eleve, Organisme, PriseEnChargeOrganisme, Section
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User


class OrganismeBase(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Centre', code_etablissement='CFP')
        self.user = User.objects.create_user(
            'a@a.sn', 'x', nom='Admin', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', nb_mensualites=10,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='BTS', frais_inscription=100000,
            frais_mensualite=50000, frais_uniforme=0, frais_fournitures=0)
        self.eleve = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, section=self.section,
            nom_complet='Awa NDIAYE', date_inscription=self.ex.date_debut)
        self.etat = Organisme.objects.create(
            tenant=self.tenant, nom='Ministère de la Formation', type='ETAT',
            reference='Arrêté 2026-118')

    def _boursier(self, inscription=100000, mensualite=50000):
        return PriseEnChargeOrganisme.objects.create(
            tenant=self.tenant, eleve=self.eleve, organisme=self.etat,
            exercice=self.ex, montant_inscription=inscription,
            montant_mensualite=mensualite)

    def _payer(self, montant, organisme=None):
        return Paiement.objects.create(
            tenant=self.tenant, exercice=self.ex, eleve=self.eleve,
            no_piece=f'REC-{Paiement.objects.count() + 1}', mode_paiement='ESPECE',
            montant_mensualite=montant, organisme=organisme, statut='ACTIF')

    def _relire(self):
        return Eleve.objects.get(pk=self.eleve.pk)


class RepartitionDuTest(OrganismeBase):
    def test_sans_organisme_tout_est_a_la_charge_de_la_famille(self):
        e = self._relire()
        self.assertEqual(e.part_organisme, 0)
        self.assertEqual(e.part_famille, e.total_attendu)

    def test_une_bourse_totale_decharge_la_famille(self):
        self._boursier()                       # 100 000 + 50 000 × 10

        e = self._relire()

        self.assertEqual(e.total_attendu, 600000)
        self.assertEqual(e.part_organisme, 600000)
        self.assertEqual(e.part_famille, 0)

    def test_une_bourse_partielle_partage_le_du(self):
        self._boursier(inscription=100000, mensualite=30000)   # 400 000

        e = self._relire()

        self.assertEqual(e.part_organisme, 400000)
        self.assertEqual(e.part_famille, 200000)

    def test_la_bourse_ne_reduit_PAS_le_du_total(self):
        """C'est toute la différence avec une remise sociale : l'école attend
        toujours 600 000, simplement pas de la même personne."""
        avant = self._relire().total_attendu
        self._boursier()
        self.assertEqual(self._relire().total_attendu, avant)

    def test_une_convention_trop_genereuse_ne_cree_pas_de_creance_fantome(self):
        self._boursier(inscription=900000, mensualite=0)
        self.assertEqual(self._relire().part_organisme, 600000)   # plafonné

    def test_la_remise_sociale_reduit_le_du_elle(self):
        """Contraste : la prise en charge de la fiche, elle, fait disparaître
        la somme — personne ne la paiera jamais."""
        self.eleve.pec_inscription = 100000
        self.eleve.save()
        self.assertEqual(self._relire().total_attendu, 500000)


class QuiDoitQuoiTest(OrganismeBase):
    def test_un_versement_de_l_organisme_solde_sa_part_seule(self):
        self._boursier(inscription=100000, mensualite=30000)     # 400 000
        self._payer(400000, organisme=self.etat)

        e = self._relire()

        self.assertEqual(e.reste_organisme, 0)
        self.assertEqual(e.reste_famille, 200000)

    def test_un_versement_de_la_famille_ne_solde_pas_l_organisme(self):
        self._boursier(inscription=100000, mensualite=30000)
        self._payer(200000)                                      # la famille

        e = self._relire()

        self.assertEqual(e.reste_famille, 0)
        self.assertEqual(e.reste_organisme, 400000)

    def test_le_total_paye_reste_la_somme_de_tout(self):
        self._boursier(inscription=100000, mensualite=30000)
        self._payer(400000, organisme=self.etat)
        self._payer(200000)

        e = self._relire()

        self.assertEqual(e.total_paye, 600000)
        self.assertEqual(e.reste_a_payer, 0)


class AlerteTest(OrganismeBase):
    """L'alerte juge la FAMILLE, jamais l'organisme."""

    JUIN = datetime.date(2026, 6, 15)

    def test_une_famille_a_jour_reste_verte_meme_si_l_etat_n_a_pas_paye(self):
        self._boursier(inscription=100000, mensualite=30000)
        self._payer(200000)                     # la famille a tout réglé

        niveau, arrieres = self._relire().niveau_alerte_detail(
            600000 - 400000, 200000, today=self.JUIN)

        self.assertEqual((niveau, arrieres), ('A_JOUR', 0))

    def test_un_boursier_integral_n_est_jamais_en_alerte(self):
        self._boursier()                        # bourse totale
        niveau, _ = self._relire().niveau_alerte_detail(0, 0, today=self.JUIN)
        self.assertEqual(niveau, 'A_JOUR')

    def test_sans_bourse_le_calcul_est_inchange(self):
        niveau, _ = self._relire().niveau_alerte_detail(0, 0, today=self.JUIN)
        self.assertNotEqual(niveau, 'A_JOUR')   # elle doit bien 600 000


class ContraintesTest(OrganismeBase):
    def test_un_seul_organisme_par_eleve_et_par_exercice(self):
        from django.db import IntegrityError
        self._boursier()
        autre = Organisme.objects.create(tenant=self.tenant, nom='ONG X', type='ONG')
        with self.assertRaises(IntegrityError):
            PriseEnChargeOrganisme.objects.create(
                tenant=self.tenant, eleve=self.eleve, organisme=autre,
                exercice=self.ex, montant_mensualite=1000)

    def test_un_organisme_qui_a_des_boursiers_ne_se_supprime_pas(self):
        from django.db.models import ProtectedError
        self._boursier()
        with self.assertRaises(ProtectedError):
            self.etat.delete()

    def test_nom_d_organisme_unique_par_ecole(self):
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            Organisme.objects.create(tenant=self.tenant,
                                     nom='Ministère de la Formation', type='ETAT')
