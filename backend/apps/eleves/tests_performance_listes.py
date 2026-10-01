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
