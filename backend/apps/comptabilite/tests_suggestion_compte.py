"""Compte de charge déduit du libellé — une seule table pour l'écran et l'import.

Ce que ces tests rendent impossible :
- une dépense non comprise rangée ailleurs qu'en 658 « Charges diverses »
  (le formulaire proposait 661 Salaires par défaut) ;
- « salaire du gardien » classé en gardiennage, « eau minérale » en facture d'eau ;
- l'import Excel et le formulaire qui classent le même libellé différemment.
"""
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from apps.comptabilite.import_charges import suggerer_compte
from apps.comptabilite.suggestion_compte import suggerer
from apps.tenants.models import Tenant
from apps.users.models import User


class SuggestionTest(SimpleTestCase):
    CAS = {
        'Facture SDE septembre':            '6051',
        "Facture Sen'Eau":                  '6051',
        'Recharge Woyofal':                 '6052',
        'Salaire du gardien - octobre':     '661',
        'Motivation oustaz Moussa':         '661',
        'Prime de fin d\'année':            '663',
        'Cotisation IPRES':                 '662',
        'Gardiennage octobre':              '621',
        'Pack eau minérale Kirène':         '604',
        'Sac de riz cantine':               '604',
        'Achat craies et cahiers':          '6054',
        'Photocopies devoirs':              '6054',
        'Loyer du local':                   '622',
        'Réparation climatiseur':           '624',
        'Crédit téléphonique directeur':    '628',
        'Frais de tenue de compte':         '631',
        'Taxi pour la banque':              '618',
        'Patente 2026':                     '641',
        'Savon et eau de javel':            '605',
        'Formation des enseignants':        '633',
    }

    def test_libelles_courants(self):
        for libelle, attendu in self.CAS.items():
            with self.subTest(libelle=libelle):
                self.assertEqual(suggerer(libelle)['compte'], attendu)

    def test_non_compris_part_en_charges_diverses(self):
        for libelle in ('xyz', 'Divers', '', 'Paiement M. Diallo'):
            r = suggerer(libelle)
            self.assertEqual((r['compte'], r['reconnu']), ('658', False))

    def test_le_mot_decisif_est_rendu(self):
        self.assertEqual(suggerer('Facture SDE septembre')['mot'], 'sde')

    def test_remonte_au_parent_absent_du_plan(self):
        self.assertEqual(suggerer('Facture SDE', {'605', '658'})['compte'], '605')

    def test_import_et_formulaire_meme_table(self):
        for libelle in self.CAS:
            self.assertEqual(suggerer_compte(libelle), suggerer(libelle)['compte'])


class SuggestionApiTest(APITestCase):
    def test_endpoint(self):
        tenant = Tenant.objects.create(nom='École A', code_etablissement='A')
        user = User.objects.create_user('a@a.sn', 'x', nom='A', role='ADMIN_ECOLE', tenant=tenant)
        self.client.force_authenticate(user)
        r = self.client.get('/api/comptabilite/charges/suggerer-compte/', {'libelle': 'loyer mars'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['compte'], '622')
        self.assertTrue(r.data['reconnu'])
        r = self.client.get('/api/comptabilite/charges/suggerer-compte/', {'libelle': 'bidule'})
        self.assertEqual((r.data['compte'], r.data['libelle_compte']), ('658', 'Charges diverses'))
