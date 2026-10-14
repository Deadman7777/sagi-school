"""Tests : le nombre de requêtes des écrans « toute l'école » ne grandit pas
avec l'effectif.

Signalé le 01/10/2026 (« des lenteurs quand on change un paramétrage ») :
la liste des élèves faisait trois requêtes de plus PAR élève (classe, gardes
du soir, total payé) — 333 pour 110 élèves, des milliers pour une école de
900 —, le tableau de bord deux. Chaque rechargement après un réglage payait
ce prix. Tous passent désormais par `echeancier.precharger`.

Le test compare deux effectifs : un écran correct fait autant de requêtes
pour 3 élèves que pour 12.
"""
import datetime

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from apps.academique.models import Classe
from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User


class NombreDeRequetesTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='LPE', code_etablissement='LPE')
        self.user = User.objects.create_user('d@lpe.sn', 'x', nom='Dir', role='ADMIN_ECOLE',
                                             tenant=self.tenant)
        self.client.force_authenticate(self.user)
        today = datetime.date.today()
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026-2027', nb_mensualites=10,
            date_debut=today - datetime.timedelta(days=60), date_fin=today + datetime.timedelta(days=240))
        self.section = Section.objects.create(tenant=self.tenant, nom='CP', frais_inscription=20000,
                                              frais_mensualite=10000)
        self.classe = Classe.objects.create(tenant=self.tenant, nom='CP A', section=self.section)
        self.n = 0

    def _ajouter(self, nb):
        for _ in range(nb):
            self.n += 1
            e = Eleve.objects.create(tenant=self.tenant, exercice=self.ex, section=self.section,
                                     classe=self.classe, nom_complet=f'Élève {self.n}',
                                     date_inscription=self.ex.date_debut)
            Paiement.objects.create(tenant=self.tenant, exercice=self.ex, eleve=e,
                                    no_piece=f'REC-{self.n:04d}', montant_inscription=20000)

    def _requetes(self, url):
        with CaptureQueriesContext(connection) as q:
            r = self.client.get(url)
        self.assertEqual(r.status_code, 200, r.content[:300])
        return len(q)

    def _constant(self, url):
        self._ajouter(3)
        self._requetes(url)          # chauffe : le premier appel remplit le cache de l'école
        peu = self._requetes(url)
        self._ajouter(9)
        beaucoup = self._requetes(url)
        self.assertEqual(peu, beaucoup, f"{url} : {peu} requêtes pour 3 élèves, {beaucoup} pour 12")

    def test_liste_des_eleves(self):
        self._constant('/api/eleves/')

    def test_tableau_de_bord(self):
        self._constant('/api/dashboard/kpis/')

    def test_etat_des_impayes(self):
        self._constant('/api/eleves/etat-impayes/')

    def test_sante_de_la_migration(self):
        self._constant('/api/eleves/sante-migration/')

    def test_modifier_un_seul_frais_d_une_section(self):
        """Un PATCH partiel laissait un float à côté des Decimal : erreur 500."""
        r = self.client.patch(f'/api/eleves/sections/{self.section.id}/',
                              {'frais_mensualite': 12500}, format='json')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(float(r.data['total_annuel']), 20000 + 12500 * 10)


class AlleguementsTest(NombreDeRequetesTest):
    """08/10/2026 (« lenteur en entrant dans Paiements et Élèves », cloud)."""

    def test_liste_memes_montants_que_la_fiche(self):
        """total_attendu n'est plus calculé qu'une fois par élève dans la
        liste : les montants doivent rester ceux de la fiche."""
        self._ajouter(3)
        liste = {e['id']: e for e in self.client.get('/api/eleves/liste/').data['results']}
        for e in Eleve.objects.filter(tenant=self.tenant):
            fiche = self.client.get(f'/api/eleves/liste/{e.id}/').data
            for champ in ('total_attendu', 'reste_a_payer', 'part_famille', 'reste_famille'):
                self.assertEqual(float(liste[str(e.id)][champ]), float(fiche[champ]), champ)
            self.assertEqual(float(fiche['total_attendu']), e.total_attendu)

    def test_resume_du_cahier_mensuel(self):
        self._ajouter(3)
        complet = self.client.get('/api/paiements/cahier-mensuel/').data
        resume = self.client.get('/api/paiements/cahier-mensuel/?resume=1').data
        self.assertEqual(resume['synthese'], complet['synthese'])
        self.assertEqual(resume['scolarite'], {'totaux': complet['scolarite']['totaux']})
        self.assertEqual(resume['charges'], {'totaux': complet['charges']['totaux']})


class ListeEntiereTest(NombreDeRequetesTest):
    """14/10/2026 : la liste s'arrêtait à la première page de 500 élèves ;
    l'écran ne demande jamais la suivante, les autres étaient introuvables."""

    @override_settings(REST_FRAMEWORK={
        'DEFAULT_AUTHENTICATION_CLASSES': (
            'rest_framework_simplejwt.authentication.JWTAuthentication',),
        'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
        'PAGE_SIZE': 2})
    def test_toute_l_ecole_au_dela_d_une_page(self):
        self._ajouter(5)
        r = self.client.get('/api/eleves/liste/')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(r.data['count'], 5)
        self.assertEqual(len(r.data['results']), 5)
        self.assertIsNone(r.data['next'])


class ListeLegereTest(NombreDeRequetesTest):
    """14/10/2026 : la ligne du tableau Élèves (?leger=1) ne porte que ce que
    l'écran affiche — mêmes valeurs que la fiche, un tiers du poids."""

    def test_memes_valeurs_que_la_liste_complete(self):
        self._ajouter(4)
        complet = {e['id']: e for e in self.client.get('/api/eleves/liste/').data['results']}
        r = self.client.get('/api/eleves/liste/', {'leger': '1'})
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(len(r.data['results']), 4)
        for ligne in r.data['results']:
            self.assertTrue(ligne.pop('fiche_partielle'))
            for champ, valeur in ligne.items():
                self.assertEqual(valeur, complet[ligne['id']][champ], champ)
            self.assertNotIn('mois_calendrier', ligne)

    def test_beaucoup_plus_leger(self):
        self._ajouter(4)
        complet = len(self.client.get('/api/eleves/liste/').content)
        leger = len(self.client.get('/api/eleves/liste/', {'leger': '1'}).content)
        self.assertLess(leger * 2, complet)

    def test_requetes_constantes(self):
        self._constant('/api/eleves/liste/?leger=1')

    def test_la_fiche_reste_complete(self):
        self._ajouter(1)
        e = Eleve.objects.get(tenant=self.tenant)
        fiche = self.client.get(f'/api/eleves/liste/{e.id}/', {'leger': '1'}).data
        self.assertIn('mois_calendrier', fiche)
        self.assertNotIn('fiche_partielle', fiche)


class MemoSerialisationTest(NombreDeRequetesTest):
    """14/10/2026 : le dû des mois est mémorisé le temps d'UNE sérialisation
    (total_attendu et l'échéancier le lisaient chacun). Hors de là, rien ne
    doit rester figé."""

    def test_le_memo_ne_survit_pas_a_la_serialisation(self):
        from apps.eleves.serializers import EleveSerializer
        self._ajouter(1)
        e = Eleve.objects.get(tenant=self.tenant)
        EleveSerializer(e).data
        self.assertFalse(hasattr(e, '_memo_calculs'))
        # Un tarif changé ensuite se voit aussitôt sur la même instance.
        avant = e.total_attendu
        self.section.frais_mensualite = 15000
        self.section.save()
        e.section = self.section
        self.assertGreater(e.total_attendu, avant)
