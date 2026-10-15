"""Relances de fin de licence : J-7, J-3, J-1, J0 — jamais deux fois le même palier."""
import datetime
from io import StringIO
from unittest import mock

from django.core import mail
from django.core.management import call_command
from rest_framework.test import APITestCase

from apps.licences.models import Licence, RelanceLicence
from apps.licences.relances import destinataires, executer, palier_courant
from apps.prospects.models import ParametresFacturation
from apps.tenants.models import Tenant
from apps.users.models import User

AUJOURDHUI = datetime.date(2026, 10, 14)
SMTP_OK = mock.patch('apps.prospects.messagerie.smtp_configure', return_value=True)


class PalierTest(APITestCase):
    def test_paliers(self):
        self.assertEqual([palier_courant(j) for j in (8, 7, 5, 3, 2, 1, 0, -1)],
                         [None, 7, 7, 3, 3, 1, 0, None])


class RelancesTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul', email='ecole@shoumoul.sn',
                                            telephone='77 111 22 33', directeur_civilite='MME',
                                            directeur_nom='Awa DIOP')
        User.objects.create_user('dir@shoumoul.sn', 'x', nom='Dir', role='ADMIN_ECOLE',
                                 tenant=self.tenant)
        self.licence = Licence.objects.create(
            tenant=self.tenant, cle_licence=Licence.generer_cle('SHM'), type='PRO',
            statut='ACTIVE', date_debut=datetime.date(2026, 1, 1),
            date_fin=AUJOURDHUI + datetime.timedelta(days=7))

    def _executer(self, jour):
        with SMTP_OK:
            return executer(jour)

    def test_administrateurs_seulement_sans_email_d_ecole(self):
        self.assertEqual(destinataires(self.licence), ['ecole@shoumoul.sn'])
        Tenant.objects.filter(pk=self.tenant.pk).update(email='')
        self.licence.tenant.refresh_from_db()
        self.assertEqual(destinataires(self.licence), ['dir@shoumoul.sn'])

    def test_un_message_par_palier_jamais_deux_fois(self):
        r = self._executer(AUJOURDHUI)                       # J-7
        self.assertEqual(len(r['envoyees']), 1)
        self.assertEqual(len(mail.outbox), 1)
        m = mail.outbox[0]
        self.assertEqual(m.to, ['ecole@shoumoul.sn'])
        self.assertIn('expire dans 7 jours', m.subject)
        self.assertIn('Bonjour Madame Awa DIOP', m.body)
        self.assertIn('6 mois : 276 000 FCFA', m.body.replace(' ', ' '))
        # Rejouée le même jour, puis à J-5 : rien (palier J-7 déjà fait).
        self._executer(AUJOURDHUI)
        self._executer(AUJOURDHUI + datetime.timedelta(days=2))
        self.assertEqual(len(mail.outbox), 1)
        # J-3, J-1, J0.
        for decalage in (4, 6, 7):
            self._executer(AUJOURDHUI + datetime.timedelta(days=decalage))
        self.assertEqual(len(mail.outbox), 4)
        self.assertEqual(sorted(RelanceLicence.objects.values_list('palier', flat=True)), [0, 1, 3, 7])
        self.assertIn("expire aujourd'hui", mail.outbox[-1].subject)

    def test_tache_manquee_pas_de_rattrapage_en_rafale(self):
        """La tâche n'a pas tourné de J-7 à J-2 : seul le palier J-3 part."""
        self._executer(AUJOURDHUI + datetime.timedelta(days=5))
        self.assertEqual(list(RelanceLicence.objects.values_list('palier', flat=True)), [3])

    def test_un_renouvellement_relance_un_nouveau_cycle(self):
        self._executer(AUJOURDHUI)
        self.licence.date_fin = self.licence.date_fin + datetime.timedelta(days=30)
        self.licence.save()
        self._executer(self.licence.date_fin - datetime.timedelta(days=7))
        self.assertEqual(len(mail.outbox), 2)

    def test_echec_trace_puis_retente(self):
        with mock.patch('apps.prospects.messagerie.smtp_configure', return_value=False):
            r = executer(AUJOURDHUI)
        self.assertEqual(len(r['echecs']), 1)
        self.assertFalse(RelanceLicence.objects.get().succes)
        self._executer(AUJOURDHUI)                           # le lendemain matin, SMTP revenu
        self.assertEqual(len(mail.outbox), 1)

    def test_suspendue_ou_lointaine_ignoree_et_interrupteur(self):
        self.licence.statut = 'SUSPENDUE'
        self.licence.save()
        self.assertEqual(self._executer(AUJOURDHUI)['envoyees'], [])
        self.licence.statut = 'ACTIVE'
        self.licence.save()
        params = ParametresFacturation.actuels()
        params.relances_auto = False
        params.save()
        self.assertIn('désactivées', self._executer(AUJOURDHUI)['motif'])
        self.assertEqual(len(mail.outbox), 0)

    def test_fin_d_essai_presente_les_licences(self):
        self.licence.type = 'ESSAI'
        self.licence.save()
        self._executer(AUJOURDHUI)
        self.assertIn('essai', mail.outbox[0].subject)
        self.assertIn('TAXAWU DAARA', mail.outbox[0].body)

    def test_ecran_et_relance_manuelle(self):
        sa = User.objects.create_user('sa@hady.sn', 'x', nom='SA', role='SUPER_ADMIN')
        self.client.force_authenticate(sa)
        with mock.patch('apps.licences.relances.timezone.localdate', return_value=AUJOURDHUI):
            r = self.client.get('/api/licences/relances/')
            self.assertEqual(r.status_code, 200)
            ligne = r.data['lignes'][0]
            self.assertEqual((ligne['jours'], ligne['palier'], ligne['a_envoyer']), (7, 7, True))
            self.assertTrue(ligne['whatsapp'].startswith('https://wa.me/221771112233'))
            with SMTP_OK:
                r = self.client.post(f'/api/licences/{self.licence.id}/relancer/')
            self.assertEqual(r.status_code, 200, r.content)
            self.assertEqual(RelanceLicence.objects.get().declenchee_par, str(sa))

    def test_commande_simulee_n_envoie_rien(self):
        sortie = StringIO()
        with mock.patch('apps.licences.relances.timezone.localdate', return_value=AUJOURDHUI):
            call_command('relancer_licences', '--simuler', stdout=sortie)
        self.assertIn('[simulée] Shoumoul (J-7)', sortie.getvalue())
        self.assertEqual(len(mail.outbox), 0)
