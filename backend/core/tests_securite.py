"""Sécurité : cloisonnement des écoles, droits par rôle, comptes utilisateurs.

Ce que ces tests rendent impossible :
- un administrateur d'école qui se fabrique un compte SUPER_ADMIN ou déplace
  un compte vers une autre école ;
- un compte « Lecteur » ou « Responsable RH » qui enregistre un paiement ou
  une charge en appelant l'API directement ;
- un paiement rattaché, par son identifiant, à l'élève d'une autre école ;
- l'essai de mots de passe en série sans frein.
"""
import datetime

from django.core.cache import cache
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User


class Base(APITestCase):
    def setUp(self):
        cache.clear()
        self.a = Tenant.objects.create(nom='École A', code_etablissement='SA')
        self.b = Tenant.objects.create(nom='École B', code_etablissement='SB')
        self.admin_a = self._user('admin@a.sn', 'ADMIN_ECOLE', self.a)
        today = datetime.date.today()
        self.ex_a = Exercice.objects.create(tenant=self.a, annee_scolaire='2026', nb_mensualites=10,
                                            date_debut=today.replace(day=1),
                                            date_fin=today.replace(day=1) + datetime.timedelta(days=360))
        self.ex_b = Exercice.objects.create(tenant=self.b, annee_scolaire='2026', nb_mensualites=10,
                                            date_debut=today.replace(day=1),
                                            date_fin=today.replace(day=1) + datetime.timedelta(days=360))
        self.section_a = Section.objects.create(tenant=self.a, nom='CI', frais_mensualite=10000)
        self.section_b = Section.objects.create(tenant=self.b, nom='CI', frais_mensualite=10000)
        self.eleve_a = Eleve.objects.create(tenant=self.a, exercice=self.ex_a, section=self.section_a,
                                            nom_complet='Awa A', date_inscription=today)
        self.eleve_b = Eleve.objects.create(tenant=self.b, exercice=self.ex_b, section=self.section_b,
                                            nom_complet='Bineta B', date_inscription=today)

    def _user(self, email, role, tenant):
        return User.objects.create_user(email, 'motdepasse1', nom=email, role=role, tenant=tenant)

    def _jwt(self, user):
        """Vrai jeton : le garde-fou des rôles lit l'en-tête Authorization,
        ce que force_authenticate ne pose pas."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}')


class ComptesUtilisateursTest(Base):
    def test_admin_ecole_ne_cree_pas_de_super_admin(self):
        self._jwt(self.admin_a)
        r = self.client.post('/api/auth/users/', {'nom': 'X', 'email': 'x@a.sn', 'role': 'SUPER_ADMIN',
                                                  'password': 'motdepasse1'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(User.objects.filter(email='x@a.sn').exists())

    def test_admin_ecole_ne_promeut_pas_un_compte(self):
        u = self._user('compta@a.sn', 'ADMIN_COMPTABLE', self.a)
        self._jwt(self.admin_a)
        r = self.client.patch(f'/api/auth/users/{u.id}/', {'role': 'SUPER_ADMIN'}, format='json')
        self.assertEqual(r.status_code, 400)
        u.refresh_from_db()
        self.assertEqual(u.role, 'ADMIN_COMPTABLE')

    def test_admin_ecole_ne_deplace_pas_un_compte_vers_une_autre_ecole(self):
        u = self._user('compta@a.sn', 'ADMIN_COMPTABLE', self.a)
        self._jwt(self.admin_a)
        r = self.client.patch(f'/api/auth/users/{u.id}/', {'tenant': str(self.b.id)}, format='json')
        self.assertEqual(r.status_code, 400)
        u.refresh_from_db()
        self.assertEqual(u.tenant_id, self.a.id)

    def test_admin_ne_change_pas_son_propre_role(self):
        self._jwt(self.admin_a)
        r = self.client.patch(f'/api/auth/users/{self.admin_a.id}/', {'role': 'LECTEUR'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_mot_de_passe_trop_court_refuse(self):
        self._jwt(self.admin_a)
        r = self.client.post('/api/auth/users/', {'nom': 'Y', 'email': 'y@a.sn', 'role': 'LECTEUR',
                                                  'password': 'court'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_connexion_freinee_apres_dix_essais(self):
        codes = [self.client.post('/api/auth/login/', {'email': 'admin@a.sn', 'password': 'faux'},
                                  format='json').status_code for _ in range(11)]
        self.assertEqual(codes[-1], 429)
        self.assertNotIn(429, codes[:10])


class DroitsParRoleTest(Base):
    def _payer(self):
        return self.client.post('/api/paiements/paiements/', {
            'eleve': str(self.eleve_a.id), 'montant_inscription': 5000, 'mode_paiement': 'ESPECE'},
            format='json')

    def test_lecteur_ne_peut_pas_encaisser(self):
        self._jwt(self._user('lect@a.sn', 'LECTEUR', self.a))
        self.assertEqual(self._payer().status_code, 403)
        self.assertFalse(Paiement.objects.exists())
        # Il lit toujours son tableau de bord.
        self.assertEqual(self.client.get('/api/dashboard/tresorerie-canaux/').status_code, 200)

    def test_rh_ne_peut_pas_saisir_de_charge(self):
        self._jwt(self._user('rh@a.sn', 'ADMIN_RH', self.a))
        r = self.client.post('/api/comptabilite/charges/', {'libelle': 'x', 'montant': 100,
                                                           'no_compte': '658'}, format='json')
        self.assertEqual(r.status_code, 403)

    def test_scolarite_encaisse(self):
        self._jwt(self._user('sco@a.sn', 'ADMIN_SCOLARITE', self.a))
        self.assertEqual(self._payer().status_code, 201)

    def test_modules_ouverts_par_l_ecole_font_foi(self):
        u = self._user('lect2@a.sn', 'LECTEUR', self.a)
        u.modules_autorises = ['paiements']
        u.save()
        self._jwt(u)
        self.assertEqual(self._payer().status_code, 201)


class CloisonnementTest(Base):
    def test_paiement_sur_l_eleve_d_une_autre_ecole_refuse(self):
        self._jwt(self.admin_a)
        r = self.client.post('/api/paiements/paiements/', {
            'eleve': str(self.eleve_b.id), 'montant_inscription': 5000, 'mode_paiement': 'ESPECE'},
            format='json')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Paiement.objects.filter(eleve=self.eleve_b).exists())
