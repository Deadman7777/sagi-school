"""Création d'un employé depuis le formulaire RH.

Le formulaire envoie des chaînes vides pour les dates non renseignées. Seules
`autorisation_date` et `date_fin_contrat` étaient converties en None ; la date
d'embauche, elle, partait en '' sur un champ obligatoire — l'API répondait 400
et l'écran n'affichait rien (le handler d'erreur était muet).
"""
import datetime

from rest_framework.test import APITestCase

from apps.rh.models import Employe
from apps.tenants.models import Tenant
from apps.users.models import User


class CreationEmployeTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='École')
        self.user = User.objects.create_user('a@a.sn', 'x', nom='A',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)

    def _payload(self, **extra):
        """Exactement ce que pose le formulaire à l'ouverture du dialogue."""
        base = {
            'nom_complet': 'Moussa DIOP', 'type_employe': 'ENSEIGNANT',
            'poste': 'Professeur', 'type_contrat': 'CDI',
            'date_embauche': '', 'salaire_base': 0, 'telephone': '', 'email': '',
            'niveau_enseignement': '', 'nb_enfants': 0,
            'situation_matrimoniale': 'CELIBATAIRE', 'est_cadre': False,
            'mode_paiement': 'CAISSE', 'numero_compte': '',
            'autorisation_numero': '', 'autorisation_date': '',
            'autorisation_autorite': '', 'autorisation_obs': '',
        }
        base.update(extra)
        return base

    def test_creation_nominale(self):
        r = self.client.post('/api/rh/employes/',
                             self._payload(date_embauche='2026-01-15'), format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Employe.objects.count(), 1)
        self.assertEqual(Employe.objects.first().matricule, 'EMP-0001')

    def test_date_embauche_vide_refusee_avec_message_clair(self):
        """Sans date d'embauche, la création est refusée — mais le message doit
        désigner le champ, sinon l'utilisateur ne sait pas quoi corriger."""
        r = self.client.post('/api/rh/employes/', self._payload(), format='json')
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn('date_embauche', r.data)
        self.assertEqual(Employe.objects.count(), 0)

    def test_dates_optionnelles_vides_acceptees(self):
        r = self.client.post('/api/rh/employes/',
                             self._payload(date_embauche='2026-01-15',
                                           date_fin_contrat='',
                                           autorisation_date=''), format='json')
        self.assertEqual(r.status_code, 201, r.content)
        e = Employe.objects.first()
        self.assertIsNone(e.date_fin_contrat)
        self.assertIsNone(e.autorisation_date)

    def test_contrat_prestataire(self):
        r = self.client.post('/api/rh/employes/',
                             self._payload(date_embauche='2026-01-15',
                                           type_contrat='PRESTATAIRE'), format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Employe.objects.first().type_contrat, 'PRESTATAIRE')

    def test_matricule_sequentiel_par_ecole(self):
        """Deux écoles doivent pouvoir avoir chacune leur EMP-0001."""
        autre = Tenant.objects.create(nom='Autre école')
        Employe.objects.create(tenant=autre, nom_complet='X', type_employe='APPUI',
                               poste='P', date_embauche=datetime.date(2026, 1, 1),
                               matricule='EMP-0001')
        r = self.client.post('/api/rh/employes/',
                             self._payload(date_embauche='2026-01-15'), format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Employe.objects.get(tenant=self.tenant).matricule, 'EMP-0001')

    def test_salaire_vide_accepte(self):
        r = self.client.post('/api/rh/employes/',
                             self._payload(date_embauche='2026-01-15',
                                           salaire_base=''), format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(float(Employe.objects.first().salaire_base), 0)
