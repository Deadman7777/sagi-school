"""Mois saisis sur un exercice qui ne commence pas en janvier.

Les Petits Érudits (15/10/2026) : exercice du 01/10/2026 au 30/06/2027, mois
cochés octobre → juin. Les mois étaient triés par numéro : janvier passait en
tête, devenait le « premier mois » payable à l'inscription, et la fiche le
marquait EN RETARD dès octobre — avec une ligne Janvier 2027 avant Octobre 2026.
"""
import datetime

from rest_framework.test import APITestCase

from apps.eleves.echeancier import construire_echeancier, mois_factures
from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant

OCT_JUIN = [1, 2, 3, 4, 5, 6, 10, 11, 12]


class OrdreMoisExerciceTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Les Petits Érudits', code_etablissement='LPE',
                                            premier_mois_a_inscription=True)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026-2027', cloture=False, nb_mensualites=9,
            date_debut=datetime.date(2026, 10, 1), date_fin=datetime.date(2027, 6, 30))
        section = Section.objects.create(tenant=self.tenant, nom='Moyenne Section',
                                         frais_inscription=33000, frais_mensualite=17000,
                                         frais_uniforme=0, frais_fournitures=0)
        self.eleve = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, section=section, nom_complet='Fatou LOUM',
            date_inscription=datetime.date(2026, 10, 1), mois_dus=OCT_JUIN)

    def test_mois_dans_l_ordre_de_l_annee_scolaire(self):
        self.assertEqual(mois_factures(self.eleve), [10, 11, 12, 1, 2, 3, 4, 5, 6])

    def test_janvier_n_est_pas_en_retard_en_octobre(self):
        ech = construire_echeancier(self.eleve, today=datetime.date(2026, 10, 15))
        lignes = {(l['annee'], l['mois']): l for l in ech['lignes']}
        self.assertEqual([(l['annee'], l['mois']) for l in ech['lignes']][:2],
                         [(2026, 10), (2026, 11)])
        self.assertFalse(lignes[(2027, 1)]['echu'])
        self.assertEqual(lignes[(2027, 1)]['reste_echu'], 0)

    def test_crèche_toute_l_annee_septembre_en_dernier(self):
        """Enfant présent douze mois : septembre est celui de 2027, en fin d'année."""
        self.eleve.mois_dus = OCT_JUIN + [7, 8, 9]
        self.eleve.save()
        self.eleve._mois_base_cache = None
        ech = construire_echeancier(self.eleve, today=datetime.date(2026, 10, 15))
        self.assertEqual((ech['lignes'][-1]['annee'], ech['lignes'][-1]['mois']), (2027, 9))


class AnneeFacturationAvantRentreeTest(APITestCase):
    """Crèche facturée dès septembre 2026, rentrée du primaire le 1er octobre.

    `Exercice.mois_debut_annee` = 9 : septembre est celui de 2026, en tête ;
    juillet et août ceux de 2027. Sans réglage, rien ne change.
    """
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Les Petits Érudits', code_etablissement='LPE')
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026-2027', cloture=False, nb_mensualites=9,
            date_debut=datetime.date(2026, 10, 1), date_fin=datetime.date(2027, 6, 30),
            mois_debut_annee=9)
        self.section = Section.objects.create(tenant=self.tenant, nom='Crèche',
                                              frais_inscription=0, frais_mensualite=17000,
                                              frais_uniforme=0, frais_fournitures=0)

    def _eleve(self, **kw):
        return Eleve.objects.create(tenant=self.tenant, exercice=self.ex, section=self.section,
                                    nom_complet='Enfant', date_inscription=datetime.date(2026, 9, 1),
                                    **kw)

    def test_annees_des_mois(self):
        self.assertEqual([self.ex.annee_du_mois(m) for m in (9, 10, 12, 1, 6, 7, 8)],
                         [2026, 2026, 2026, 2027, 2027, 2027, 2027])
        self.assertEqual(self.ex.debut_facturation, datetime.date(2026, 9, 1))

    def test_creche_douze_mois_septembre_2026_en_tete(self):
        e = self._eleve(mois_dus=list(range(1, 13)))
        ech = construire_echeancier(e, today=datetime.date(2026, 10, 15))
        cles = [(l['annee'], l['mois']) for l in ech['lignes']]
        self.assertEqual(cles[0], (2026, 9))
        self.assertEqual(cles[-1], (2027, 8))
        self.assertTrue(ech['lignes'][0]['echu'])            # septembre 2026 : échu
        self.assertFalse({l['mois']: l for l in ech['lignes']}[1]['echu'])   # janvier 2027

    def test_eleve_ordinaire_reste_facture_depuis_la_rentree(self):
        e = self._eleve()
        e.date_inscription = datetime.date(2026, 10, 1)
        e.save()
        self.assertEqual(mois_factures(e), [10, 11, 12, 1, 2, 3, 4, 5, 6])

    def test_reglage_qui_laisserait_la_fin_hors_des_douze_mois_refuse(self):
        from apps.paiements.serializers import ExerciceSerializer
        # Juillet 2026 → juin 2027 : douze mois, la fin y est.
        self.assertTrue(ExerciceSerializer(self.ex, data={'mois_debut_annee': 7}, partial=True).is_valid())
        # Juin 2026 → mai 2027 : juin 2027 resterait dehors.
        s = ExerciceSerializer(self.ex, data={'mois_debut_annee': 6}, partial=True)
        self.assertFalse(s.is_valid())
        self.assertIn('mois_debut_annee', s.errors)
