"""Tests : envoi automatique des rappels de paiement.

Un message parti par erreur à des centaines de familles ne se rattrape pas.
Ces tests portent donc surtout sur ce que le système REFUSE de faire : envoyer
hors de la fenêtre, envoyer deux fois, et surtout envoyer quoi que ce soit
tant que l'école ne l'a pas explicitement demandé.
"""
import datetime
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from rest_framework.test import APITestCase

from apps.eleves.models import Eleve, RappelEnvoye, Section
from apps.eleves.rappels import composer_message, envoyer_rappels
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant
from apps.users.models import User


class EnvoiBase(APITestCase):
    JUILLET = datetime.date(2026, 7, 5)          # dans la fenêtre 1→10

    def setUp(self):
        self.tenant = Tenant.objects.create(
            nom='Shoumoul', code_etablissement='CSE',
            rappel_jour_debut=1, rappel_jour_limite=10)
        self.user = User.objects.create_user(
            'a@a.sn', 'x', nom='Admin', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', nb_mensualites=12,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='INTERNAT', frais_inscription=0,
            frais_mensualite=60000, frais_uniforme=0, frais_fournitures=0)
        self.eleve = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, section=self.section,
            nom_complet='Awa NDIAYE', date_inscription=self.ex.date_debut,
            date_entree=self.ex.date_debut, mois_dus=[6, 7],
            telephone_tuteur='770000000', nom_tuteur='Tuteur')

    def _activer_passerelle(self):
        self.tenant.sms_actif = True
        self.tenant.sms_url = 'https://passerelle.example/envoi'
        self.tenant.sms_gabarit = {'to': '{destinataire}', 'text': '{message}'}
        self.tenant.save()


class SecuriteEnvoiTest(EnvoiBase):
    """Ce que le système refuse de faire — le cœur du sujet."""

    def test_par_defaut_rien_n_est_reellement_envoye(self):
        """Sans activation explicite, tout est simulé."""
        with patch('apps.eleves.rappels._envoyer_sms') as faux:
            r = envoyer_rappels(self.tenant, self.ex, today=self.JUILLET)

        faux.assert_not_called()
        self.assertEqual(r['simules'], 1)
        self.assertEqual(r['envoyes'], 0)
        self.assertFalse(r['reel'])

    def test_sms_actif_sans_passerelle_reste_en_simulation(self):
        self.tenant.sms_actif = True         # mais sms_url vide
        self.tenant.save()

        with patch('apps.eleves.rappels._envoyer_sms') as faux:
            r = envoyer_rappels(self.tenant, self.ex, today=self.JUILLET)

        faux.assert_not_called()
        self.assertEqual(r['simules'], 1)

    def test_hors_fenetre_rien_ne_part(self):
        r = envoyer_rappels(self.tenant, self.ex,
                            today=datetime.date(2026, 7, 25))   # après le 10

        self.assertEqual(r['envoyes'] + r['simules'], 0)
        self.assertIn('fenêtre', r['motif'])
        self.assertEqual(RappelEnvoye.objects.count(), 0)

    def test_jamais_deux_fois_le_meme_mois(self):
        envoyer_rappels(self.tenant, self.ex, today=self.JUILLET)

        r = envoyer_rappels(self.tenant, self.ex, today=datetime.date(2026, 7, 8))

        self.assertEqual(r['ignores'], 1)
        self.assertEqual(r['simules'], 0)
        self.assertEqual(RappelEnvoye.objects.count(), 1)

    def test_un_echec_est_trace_et_ne_sera_pas_retente_le_meme_mois(self):
        """Sinon une passerelle en panne relancerait l'élève toute la journée."""
        self._activer_passerelle()
        with patch('apps.eleves.rappels._envoyer_sms', return_value=(False, 'HTTP 500')):
            envoyer_rappels(self.tenant, self.ex, today=self.JUILLET)

        self.assertEqual(RappelEnvoye.objects.get().statut, 'ECHEC')
        r = envoyer_rappels(self.tenant, self.ex, today=datetime.date(2026, 7, 9))
        self.assertEqual(r['ignores'], 1)

    def test_un_eleve_sans_telephone_est_ignore_pas_perdu(self):
        self.eleve.telephone_tuteur = ''
        self.eleve.save()

        r = envoyer_rappels(self.tenant, self.ex, today=self.JUILLET)

        self.assertEqual(r['ignores'], 1)
        self.assertEqual(r['lignes'][0]['statut'], 'SANS_CONTACT')

    def test_un_mois_suivant_permet_un_nouveau_rappel(self):
        envoyer_rappels(self.tenant, self.ex, today=self.JUILLET)
        r = envoyer_rappels(self.tenant, self.ex, today=datetime.date(2026, 8, 5))
        self.assertEqual(r['simules'], 1)


class EnvoiReelTest(EnvoiBase):
    def test_la_passerelle_est_appelee_avec_le_bon_numero(self):
        self._activer_passerelle()

        with patch('apps.eleves.rappels._envoyer_sms',
                   return_value=(True, 'HTTP 200')) as faux:
            r = envoyer_rappels(self.tenant, self.ex, today=self.JUILLET)

        faux.assert_called_once()
        self.assertEqual(faux.call_args[0][1], '770000000')
        self.assertEqual(r['envoyes'], 1)
        self.assertEqual(RappelEnvoye.objects.get().statut, 'ENVOYE')

    def test_forcer_sort_de_la_fenetre_mais_pas_du_verrou_mensuel(self):
        r = envoyer_rappels(self.tenant, self.ex,
                            today=datetime.date(2026, 7, 25), forcer=True)
        self.assertEqual(r['simules'], 1)

        r2 = envoyer_rappels(self.tenant, self.ex,
                             today=datetime.date(2026, 7, 26), forcer=True)
        self.assertEqual(r2['ignores'], 1)


class MessageTest(EnvoiBase):
    def _ligne(self):
        from apps.eleves.rappels import eleves_a_rappeler
        return eleves_a_rappeler(self.tenant, self.ex, self.JUILLET)['lignes'][0]

    def test_le_message_par_defaut_porte_le_nom_et_le_montant(self):
        msg = composer_message(self.tenant, self._ligne(), self.JUILLET)
        self.assertIn('Awa NDIAYE', msg)
        self.assertIn('Shoumoul', msg)

    def test_le_gabarit_de_l_ecole_prime(self):
        self.tenant.rappel_message = 'Bonjour, {eleve} doit {montant} FCFA.'
        msg = composer_message(self.tenant, self._ligne(), self.JUILLET)
        self.assertTrue(msg.startswith('Bonjour, Awa NDIAYE doit'))

    def test_un_gabarit_fautif_ne_bloque_pas_la_campagne(self):
        """Une variable inconnue ne doit pas faire échouer tous les envois."""
        self.tenant.rappel_message = 'Solde {inexistant} pour {eleve}'
        msg = composer_message(self.tenant, self._ligne(), self.JUILLET)
        self.assertIn('Awa NDIAYE', msg)


class ApiEtCommandeTest(EnvoiBase):
    def test_endpoint_envoi(self):
        # Fenêtre ouverte tout le mois : le test ne doit pas dépendre du jour
        # réel où il tourne.
        self.tenant.rappel_jour_debut, self.tenant.rappel_jour_limite = 1, 28
        self.tenant.save()

        r = self.client.post('/api/eleves/rappels/envoyer/', {}, format='json')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(r.data['simules'] + r.data['envoyes'] + r.data['ignores'], 1)

    def test_endpoint_historique(self):
        envoyer_rappels(self.tenant, self.ex, today=self.JUILLET)
        r = self.client.get('/api/eleves/rappels/historique/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['lignes'][0]['eleve'], 'Awa NDIAYE')

    def test_commande_hors_fenetre_ne_fait_rien(self):
        out = StringIO()
        with patch('apps.eleves.rappels.datetime') as faux_dt:
            faux_dt.date.today.return_value = datetime.date(2026, 7, 25)
            faux_dt.date.side_effect = datetime.date
            call_command('envoyer_rappels', stdout=out)
        self.assertEqual(RappelEnvoye.objects.count(), 0)

    def test_commande_simuler_n_envoie_rien_meme_activee(self):
        self._activer_passerelle()
        out = StringIO()
        with patch('apps.eleves.rappels._envoyer_sms') as faux, \
             patch('apps.eleves.rappels.datetime') as faux_dt:
            faux_dt.date.today.return_value = self.JUILLET
            faux_dt.date.side_effect = datetime.date
            call_command('envoyer_rappels', '--simuler', stdout=out)
        faux.assert_not_called()
