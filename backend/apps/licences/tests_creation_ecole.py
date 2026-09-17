"""Création d'une école par HADY GESMAN.

Ce que ces tests rendent impossible :
- **une erreur 500 muette** sur un champ trop long — le message dit quel champ corriger ;
- **une école orpheline** (sans licence ni exercice) après un échec ;
- **refuser deux numéros de téléphone**, cas réel du 17/09/2026 sur une installation.
"""
from rest_framework.test import APITestCase

from apps.licences.models import Licence
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant
from apps.users.models import User

URL = '/api/licences/creer_ecole/'


class CreationEcoleTest(APITestCase):
    def setUp(self):
        admin = User.objects.create_user(email='super@hadygesman.com', password='x', nom='Super',
                                         role='SUPER_ADMIN')
        self.client.force_authenticate(admin)

    def _data(self, **extra):
        data = {'nom': 'Crèche Les Poussins', 'ville': 'Dakar', 'telephone': '77 123 45 67',
                'type_licence': 'PRO', 'mois_licence': 12, 'code_etablissement': 'ETB',
                'annee_scolaire': '2026-2027', 'date_debut': '2026-10-01', 'date_fin': '2027-07-31'}
        data.update(extra)
        return data

    def test_ecole_licence_et_exercice_crees_ensemble(self):
        r = self.client.post(URL, self._data(), format='json')
        self.assertEqual(r.status_code, 201, r.content)
        tenant = Tenant.objects.get(pk=r.data['tenant_id'])
        self.assertEqual(Licence.objects.get(tenant=tenant).statut, 'ACTIVE')
        self.assertEqual(Exercice.objects.get(tenant=tenant).annee_scolaire, '2026-2027')

    def test_deux_numeros_de_telephone_acceptes(self):
        deux = '+221 77 123 45 67 / +221 78 765 43 21'
        r = self.client.post(URL, self._data(telephone=deux), format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Tenant.objects.get(pk=r.data['tenant_id']).telephone, deux)

    def test_champ_trop_long_nomme_et_rien_n_est_cree(self):
        for champ, valeur, attendu in (('telephone', '7' * 61, 'Téléphone'),
                                       ('ninea', '1' * 21, 'NINEA'),
                                       ('code_etablissement', 'ETABLISSEMENT', 'Code établissement')):
            r = self.client.post(URL, self._data(**{champ: valeur}), format='json')
            self.assertEqual(r.status_code, 400, champ)
            self.assertIn(attendu, r.data['error'])
        self.assertFalse(Tenant.objects.exists())

    def test_echec_tardif_ne_laisse_pas_d_ecole_orpheline(self):
        # La date se valide avant l'écriture ; une fin avant le début est refusée.
        r = self.client.post(URL, self._data(date_debut='2027-10-01', date_fin='2027-07-31'), format='json')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Tenant.objects.exists())
        self.assertFalse(Licence.objects.exists())

    def test_nom_email_et_type_verifies(self):
        for extra, attendu in (({'nom': '  '}, 'nom'), ({'email': 'pas-une-adresse'}, 'Email'),
                               ({'type_licence': 'PLATINE'}, 'licence')):
            r = self.client.post(URL, self._data(**extra), format='json')
            self.assertEqual(r.status_code, 400, extra)
            self.assertIn(attendu, r.data['error'])
