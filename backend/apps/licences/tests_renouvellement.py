"""Demande de renouvellement de licence — elle ne se perd plus.

Suivi Shoumoul (septembre 2026) : le bouton « Demander un renouvellement »
n'atteignait pas hadygesman@gmail.com, sans que personne ne le sache.
"""
import datetime
import json
from unittest import mock

from django.core import mail
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.licences.models import DemandeRenouvellement, Licence
from apps.tenants.models import Tenant
from apps.users.models import User

SMTP = dict(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
            EMAIL_HOST='smtp.gmail.com', LICENCE_SUPPORT_EMAIL='hadygesman@gmail.com')


class RenouvellementBase(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul Excellence', ville='Rufisque')
        self.licence = Licence.objects.create(
            tenant=self.tenant, cle_licence=Licence.generer_cle('SHOUMOUL'), type='AVANCE',
            statut='ACTIVE', date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 10, 1))
        self.user = User.objects.create_user('dir@shoumoul.sn', 'x', nom='Directrice',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)

    def _demander(self):
        return self.client.post(f'/api/licences/{self.licence.id}/demander_renouvellement/',
                                {'message': 'Renouveler 12 mois'}, format='json')


@override_settings(SAGI_EST_CLOUD=True, **SMTP)
class CloudTest(RenouvellementBase):
    def test_courriel_parti_et_demande_enregistree(self):
        with mock.patch('django.core.mail.backends.smtp.EmailBackend.send_messages', return_value=1) as envoi:
            r = self._demander()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data['recue'])
        message = envoi.call_args[0][0][0]
        self.assertEqual(message.to, ['hadygesman@gmail.com'])
        self.assertEqual(message.reply_to, ['dir@shoumoul.sn'])
        d = DemandeRenouvellement.objects.get()
        self.assertTrue(d.courriel_envoye)

    def test_echec_smtp_n_est_plus_avale(self):
        with mock.patch('django.core.mail.backends.smtp.EmailBackend.send_messages',
                        side_effect=OSError('Application-specific password required')):
            r = self._demander()
        self.assertFalse(r.data['recue'])
        self.assertIn('password', r.data['erreur'])
        d = DemandeRenouvellement.objects.get()      # la demande existe quand même
        self.assertFalse(d.courriel_envoye)
        self.assertIn('password', d.erreur)

    def test_super_admin_voit_les_demandes_meme_en_echec(self):
        with mock.patch('django.core.mail.backends.smtp.EmailBackend.send_messages',
                        side_effect=OSError('boom')):
            self._demander()
        admin = User.objects.create_user('hg@hg.sn', 'x', nom='HG', role='SUPER_ADMIN')
        self.client.force_authenticate(admin)
        liste = self.client.get('/api/licences/demandes-renouvellement/').data
        self.assertEqual(len(liste), 1)
        self.assertEqual(liste[0]['ecole_nom'], 'Shoumoul Excellence (Rufisque)')


@override_settings(SAGI_EST_CLOUD=False, EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend',
                   EMAIL_HOST='', SAGI_CLOUD_URL='https://api.exemple.test')
class LocalTest(RenouvellementBase):
    def test_relayee_au_cloud(self):
        reponse = mock.MagicMock()
        reponse.read.return_value = json.dumps({'recue': True, 'courriel_envoye': True}).encode()
        reponse.__enter__.return_value = reponse
        with mock.patch('urllib.request.urlopen', return_value=reponse) as appel:
            r = self._demander()
        self.assertTrue(r.data['recue'])
        requete = appel.call_args[0][0]
        self.assertEqual(requete.full_url, 'https://api.exemple.test/api/licences/relais-renouvellement/')
        self.assertEqual(requete.headers['X-cle-licence'], self.licence.cle_licence)
        self.assertEqual(DemandeRenouvellement.objects.get().origine, 'RELAIS')

    def test_hors_ligne_ne_pretend_pas_avoir_envoye(self):
        import urllib.error
        with mock.patch('urllib.request.urlopen', side_effect=urllib.error.URLError('hors ligne')):
            r = self._demander()
        self.assertFalse(r.data['recue'])
        self.assertTrue(r.data['enregistree'])
        self.assertIn('hors ligne', r.data['erreur'])


@override_settings(SAGI_EST_CLOUD=True, **SMTP)
class RelaisTest(RenouvellementBase):
    def test_cle_invalide_refusee(self):
        self.client.force_authenticate(None)
        r = self.client.post('/api/licences/relais-renouvellement/', {'ecole_nom': 'X'},
                             format='json', HTTP_X_CLE_LICENCE='HG-FAUX-00000000')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(DemandeRenouvellement.objects.count(), 0)

    def test_relais_enregistre_et_notifie(self):
        self.client.force_authenticate(None)
        with mock.patch('django.core.mail.backends.smtp.EmailBackend.send_messages', return_value=1):
            r = self.client.post('/api/licences/relais-renouvellement/',
                                 {'ecole_nom': 'École locale', 'message': 'svp'}, format='json',
                                 HTTP_X_CLE_LICENCE=self.licence.cle_licence)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data['recue'])
        d = DemandeRenouvellement.objects.get()
        self.assertEqual((d.origine, d.courriel_envoye, d.licence), ('RELAIS', True, self.licence))
