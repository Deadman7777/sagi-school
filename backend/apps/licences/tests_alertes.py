"""Alertes de fin de licence dans l'application : J-7, J-3, J-1, J0, expirée, coupée.

Demande du 17/10/2026 (Petits Érudits, licence qui expire le lendemain) :
badge, rappel à la connexion, « Renouveler maintenant », alerte prioritaire
après expiration, statut à jour dès la confirmation.
"""
import datetime
import json
from unittest import mock

from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.licences.alertes import etat, lire_paliers, montant, synchroniser
from apps.licences.models import DemandeRenouvellement, Licence
from apps.prospects.models import ParametresFacturation
from apps.tenants.models import Tenant
from apps.users.models import User

J = datetime.date(2026, 10, 17)


class Base(APITestCase):
    def setUp(self):
        cache.clear()
        self.tenant = Tenant.objects.create(nom='Les Petits Érudits', ville='Dakar')
        self.licence = Licence.objects.create(
            tenant=self.tenant, cle_licence=Licence.generer_cle('PE'), type='PRO',
            statut='ACTIVE', date_debut=datetime.date(2026, 1, 1),
            date_fin=J + datetime.timedelta(days=1))
        self.user = User.objects.create_user('dir@pe.sn', 'x', nom='Directrice',
                                             role='ADMIN_ECOLE', tenant=self.tenant)

    def _a(self, jours):
        self.licence.date_fin = J + datetime.timedelta(days=jours)
        with mock.patch('django.utils.timezone.now',
                        return_value=datetime.datetime(2026, 10, 17, 12, tzinfo=datetime.timezone.utc)):
            return etat(self.licence, J)


class EtatTest(Base):
    def test_paliers_lus(self):
        self.assertEqual(lire_paliers('J-7, 3,1 ,0'), (7, 3, 1, 0))
        self.assertEqual(lire_paliers('15;7;7'), (15, 7))
        self.assertEqual(lire_paliers('n’importe quoi'), (7, 3, 1, 0))

    def test_phases_et_badges(self):
        cas = {10: ('NORMAL', None, None), 7: ('ECHEANCE', 7, 7), 5: ('ECHEANCE', 3 + 4, 5),
               2: ('ECHEANCE', 3, 2), 1: ('ECHEANCE', 1, 1), 0: ('ECHEANCE', 0, '!'),
               -3: ('EXPIREE', 'EXP', '!'), -8: ('COUPEE', 'EXP', '!')}
        for jours, (phase, palier, badge) in cas.items():
            e = self._a(jours)
            self.assertEqual((e['phase'], e['palier'], e['badge']), (phase, palier, badge), jours)
        self.assertFalse(self._a(10)['alerte'])
        self.assertTrue(self._a(-3)['prioritaire'])
        self.assertFalse(self._a(1)['prioritaire'])

    def test_messages(self):
        self.assertEqual(self._a(1)['titre'], 'Votre licence SAGI SCHOOL expire demain')
        self.assertEqual(self._a(0)['titre'], "Votre licence SAGI SCHOOL expire aujourd'hui")
        e = self._a(-1)
        self.assertIn('16 octobre 2026', e['texte'])
        self.assertIn('à partir du 24 octobre 2026 (dans 7 jours)', e['texte'])
        coupee = self._a(-8)
        self.assertEqual(coupee['modules'], ['/ma-licence', '/parametres'])

    def test_paliers_configurables_et_interrupteur(self):
        p = ParametresFacturation.actuels()
        p.paliers_alerte = '15,7,0'
        p.save()
        from apps.licences.alertes import _config_locale
        self.licence.date_fin = J + datetime.timedelta(days=12)
        self.assertEqual(etat(self.licence, J, _config_locale())['palier'], 15)
        p.alertes_ecoles = False
        p.save()
        e = etat(self.licence, J, _config_locale())
        self.assertFalse(e['alerte'])
        self.assertIsNone(e['badge'])

    def test_offres_chiffrees_par_le_serveur(self):
        e = self._a(1)
        self.assertEqual([o['type'] for o in e['offres']], ['PRO'])
        self.assertEqual([f['mois'] for f in e['offres'][0]['formules']], [1, 6, 12])
        self.assertEqual(e['offres'][0]['formules'][0]['montant'], montant('PRO', 1))
        self.licence.type = 'ESSAI'
        self.assertGreater(len(etat(self.licence, J)['offres']), 1)


class ApiTest(Base):
    def test_alerte_de_l_ecole(self):
        self.client.force_authenticate(self.user)
        r = self.client.get('/api/licences/alerte/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['licence'], str(self.licence.id))
        self.assertIn(r.data['phase'], ('ECHEANCE', 'EXPIREE', 'COUPEE', 'NORMAL'))

    @override_settings(SAGI_EST_CLOUD=True, EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_renouveler_maintenant_puis_confirmation(self):
        self.client.force_authenticate(self.user)
        r = self.client.post(f'/api/licences/{self.licence.id}/demander_renouvellement/', {
            'mois': 12, 'type': 'PRO', 'montant': 1, 'moyen_paiement': 'Wave',
            'reference_paiement': 'TX-123'}, format='json')
        self.assertEqual(r.status_code, 200)
        d = DemandeRenouvellement.objects.get()
        self.assertEqual((d.mois, d.montant, d.reference_paiement), (12, montant('PRO', 12), 'TX-123'))
        alerte = self.client.get('/api/licences/alerte/').data
        self.assertEqual(alerte['demande_en_attente']['reference_paiement'], 'TX-123')

        # L'école ne peut pas confirmer elle-même.
        url = f'/api/licences/demandes-renouvellement/{d.id}/confirmer/'
        self.assertEqual(self.client.post(url, {}, format='json').status_code, 403)

        admin = User.objects.create_user('hg@hady.sn', 'x', nom='HG', role='SUPER_ADMIN')
        self.client.force_authenticate(admin)
        fin_avant = self.licence.date_fin
        r = self.client.post(url, {}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.licence.refresh_from_db()
        self.assertGreater(self.licence.date_fin, fin_avant)
        d.refresh_from_db()
        self.assertTrue(d.confirmee and d.traitee)
        self.assertEqual(self.client.post(url, {}, format='json').status_code, 400)

    def test_etat_distant(self):
        r = self.client.post('/api/licences/etat-distant/', {}, format='json',
                             HTTP_X_CLE_LICENCE=self.licence.cle_licence)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['licence']['date_fin'], str(self.licence.date_fin))
        self.assertIn('paliers', r.data['config'])
        r = self.client.post('/api/licences/etat-distant/', {}, format='json',
                             HTTP_X_CLE_LICENCE='HG-FAUX-1')
        self.assertEqual(r.status_code, 403)


class SynchroLocaleTest(Base):
    def test_prolonge_jamais_ne_raccourcit(self):
        DemandeRenouvellement.objects.create(licence=self.licence, tenant=self.tenant, ecole_nom='PE')
        plus_tard = self.licence.date_fin + datetime.timedelta(days=365)
        self.assertTrue(synchroniser(self.licence, {'licence': {'date_fin': str(plus_tard), 'type': 'PRO'}}))
        self.licence.refresh_from_db()
        self.assertEqual(self.licence.date_fin, plus_tard)
        self.assertFalse(DemandeRenouvellement.objects.filter(traitee=False).exists())
        self.assertFalse(synchroniser(self.licence, {'licence': {'date_fin': '2026-01-01'}}))
        self.licence.refresh_from_db()
        self.assertEqual(self.licence.date_fin, plus_tard)

    @override_settings(SAGI_EST_CLOUD=False)
    def test_poste_local_lit_le_cloud(self):
        plus_tard = self.licence.date_fin + datetime.timedelta(days=30)
        reponse = mock.MagicMock()
        reponse.__enter__.return_value.read.return_value = json.dumps({
            'licence': {'date_fin': str(plus_tard), 'type': 'PRO', 'statut': 'ACTIVE'},
            'config': {'paliers': [10, 2], 'lien_paiement': 'https://pay.wave.com/m/HG'}}).encode()
        self.client.force_authenticate(self.user)
        with mock.patch('urllib.request.urlopen', return_value=reponse):
            r = self.client.get('/api/licences/alerte/')
        self.assertEqual(r.data['date_fin'], plus_tard)
        self.assertEqual(r.data['paliers'], [10, 2])
        self.assertEqual(r.data['paiement']['lien'], 'https://pay.wave.com/m/HG')

    @override_settings(SAGI_EST_CLOUD=False)
    def test_hors_connexion(self):
        import urllib.error
        self.client.force_authenticate(self.user)
        with mock.patch('urllib.request.urlopen', side_effect=urllib.error.URLError('hors ligne')):
            r = self.client.get('/api/licences/alerte/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['paliers'], [7, 3, 1, 0])
