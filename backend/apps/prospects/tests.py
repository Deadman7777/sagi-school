"""Tests du fichier prospects.

Ce que ces tests cherchent à rendre impossible, c'est le défaut auquel le
fichier répond : **une demande reçue qui n'existe nulle part.** D'où les cas
volontairement hostiles — SMTP muet, courriel qui lève, formulaire renvoyé deux
fois, numéro écrit autrement, champ numérique rempli en toutes lettres.
"""
from datetime import date, timedelta
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.prospects.enregistrement import (enregistrer_demande, extraire,
                                           normaliser_telephone)
from apps.prospects.models import InteractionProspect, Prospect
from apps.tenants.models import Tenant
from apps.users.models import User

DEMANDE = {
    'etablissement': 'Daara Serigne Fallou',
    'type_organisation': 'Daara',
    'ville': 'Rufisque',
    'telephone': '+221 77 123 45 67',
    'contact_nom': 'Moussa Diop',
    'contact_fonction': 'Directeur',
    'contact_email': 'moussa@example.sn',
    'origines': ['Site internet', 'Recommandation client'],
    'nb_eleves': '180',
    'disponibilites': 'Mardi matin',
    'message': 'Nous voulons voir la gestion des mémorisations.',
}


class NormalisationTest(APITestCase):
    """Les formes d'un même numéro doivent se rejoindre."""

    def test_un_meme_numero_ecrit_de_quatre_facons_donne_une_seule_cle(self):
        formes = ['+221 77 123 45 67', '00221771234567', '77 123 45 67',
                  '77-123-45-67']
        self.assertEqual({normaliser_telephone(f) for f in formes}, {'771234567'})

    def test_un_numero_trop_court_n_est_pas_rapproche_a_tort(self):
        """Mieux vaut deux fiches qu'un mauvais rapprochement."""
        self.assertEqual(normaliser_telephone('33 1234'), '331234')
        self.assertNotEqual(normaliser_telephone('33 1234'),
                            normaliser_telephone('77 123 45 67'))

    def test_un_effectif_ecrit_en_toutes_lettres_est_recupere(self):
        """« environ 300 élèves » vaut 300, et non une erreur de saisie."""
        self.assertEqual(extraire({'nb_eleves': 'environ 300 élèves'})['nb_eleves'], 300)
        self.assertIsNone(extraire({'nb_eleves': 'beaucoup'})['nb_eleves'])

    def test_un_champ_demesure_est_tronque_et_non_rejete(self):
        champs = extraire({'etablissement': 'A' * 5000, 'ville': 'B' * 5000})
        self.assertEqual(len(champs['etablissement']), 200)
        self.assertEqual(len(champs['ville']), 120)


class EnregistrementTest(APITestCase):

    def test_une_demande_cree_une_fiche_et_son_premier_echange(self):
        prospect, cree = enregistrer_demande(DEMANDE)
        self.assertTrue(cree)
        self.assertEqual(prospect.etablissement, 'Daara Serigne Fallou')
        self.assertEqual(prospect.telephone_cle, '771234567')
        self.assertEqual(prospect.nb_eleves, 180)
        self.assertEqual(prospect.statut, 'NOUVEAU')
        self.assertEqual(prospect.interactions.count(), 1)
        self.assertEqual(prospect.interactions.first().canal, 'SITE')

    def test_la_soumission_brute_est_conservee_telle_quelle(self):
        """Un champ que le modèle ne connaît pas ne doit pas disparaître."""
        prospect, _ = enregistrer_demande({**DEMANDE, 'budget_envisage': '500 000 F'})
        self.assertEqual(prospect.donnees_brutes['budget_envisage'], '500 000 F')

    def test_un_meme_prospect_qui_reecrit_ne_cree_pas_de_seconde_fiche(self):
        enregistrer_demande(DEMANDE)
        prospect, cree = enregistrer_demande({**DEMANDE, 'telephone': '77-123-45-67'})
        self.assertFalse(cree)
        self.assertEqual(Prospect.objects.count(), 1)
        self.assertEqual(prospect.interactions.count(), 2)

    def test_une_seconde_demande_complete_les_vides_sans_ecraser_le_connu(self):
        premier, _ = enregistrer_demande(DEMANDE)
        enregistrer_demande({**DEMANDE, 'contact_nom': 'Quelqu\'un d\'autre',
                             'email': 'contact@daara.sn'})
        premier.refresh_from_db()
        self.assertEqual(premier.contact_nom, 'Moussa Diop')   # vérifié, on garde
        self.assertEqual(premier.email, 'contact@daara.sn')    # vide, on remplit

    def test_une_relance_du_formulaire_ne_defait_pas_le_travail_commercial(self):
        """Le cas qui compte : une affaire qualifiée ne retombe pas à « Nouveau »."""
        prospect, _ = enregistrer_demande(DEMANDE)
        prospect.statut = 'DEVIS'
        prospect.save()
        enregistrer_demande(DEMANDE)
        prospect.refresh_from_db()
        self.assertEqual(prospect.statut, 'DEVIS')

    def test_le_rapprochement_par_courriel_quand_le_telephone_change(self):
        enregistrer_demande(DEMANDE)
        _, cree = enregistrer_demande({**DEMANDE, 'telephone': '78 999 88 77',
                                       'email': 'moussa@example.sn'})
        self.assertFalse(cree)

    def test_une_demande_sans_etablissement_est_refusee(self):
        with self.assertRaises(ValueError):
            enregistrer_demande({**DEMANDE, 'etablissement': '   '})


# La vue n'envoie que si le backend courriel est un SMTP réellement configuré
# (`'smtp' in EMAIL_BACKEND` et un `EMAIL_HOST` renseigné). On reproduit donc
# ces conditions, et c'est `send` qui est simulé — aucun test n'ouvre de
# connexion réseau.
@override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
                   EMAIL_HOST='smtp.example.com')
class EndpointPublicTest(APITestCase):
    """Le formulaire du site vitrine, vu de l'extérieur."""

    URL = '/api/public/demande-demo/'

    def test_la_demande_est_enregistree_et_notifiee(self):
        with patch('apps.licences.site_public.EmailMessage.send',
                   return_value=1) as envoi:
            reponse = self.client.post(self.URL, DEMANDE, format='json')
        self.assertEqual(reponse.status_code, 200)
        self.assertTrue(reponse.data['envoye'])
        self.assertTrue(reponse.data['notifie'])
        self.assertEqual(envoi.call_count, 1)
        self.assertEqual(Prospect.objects.count(), 1)
        self.assertTrue(Prospect.objects.first().courriel_envoye)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
                       EMAIL_HOST='')
    def test_sans_smtp_la_demande_est_gardee_quand_meme(self):
        """C'est exactement la situation qui faisait perdre les demandes."""
        reponse = self.client.post(self.URL, DEMANDE, format='json')
        self.assertTrue(reponse.data['envoye'])
        self.assertFalse(reponse.data['notifie'])
        self.assertEqual(Prospect.objects.count(), 1)

    def test_un_courriel_qui_echoue_ne_perd_pas_la_demande(self):
        with patch('apps.licences.site_public.EmailMessage.send',
                   side_effect=OSError('boom')):
            reponse = self.client.post(self.URL, DEMANDE, format='json')
        self.assertTrue(reponse.data['envoye'])
        self.assertFalse(reponse.data['notifie'])
        self.assertEqual(Prospect.objects.count(), 1)
        self.assertFalse(Prospect.objects.first().courriel_envoye)

    def test_le_piege_a_robots_ne_cree_aucune_fiche(self):
        with patch('apps.licences.site_public.EmailMessage.send', return_value=1):
            self.client.post(self.URL, {**DEMANDE, 'site_web_confirmation': 'x'},
                             format='json')
        self.assertEqual(Prospect.objects.count(), 0)

    def test_une_demande_incomplete_est_refusee_sans_creer_de_fiche(self):
        reponse = self.client.post(self.URL, {'etablissement': 'X'}, format='json')
        self.assertEqual(reponse.status_code, 400)
        self.assertEqual(Prospect.objects.count(), 0)


class ApiProspectsTest(APITestCase):
    """L'écran de suivi — réservé à HADY GESMAN."""

    def setUp(self):
        self.tenant = Tenant.objects.create(nom='École Test', code_etablissement='TEST')
        self.super_admin = User.objects.create_user(
            email='super@hadygesman.com', password='x', nom='Super',
            role='SUPER_ADMIN')
        self.admin_ecole = User.objects.create_user(
            email='dir@ecole.sn', password='x', nom='Dir',
            role='ADMIN_ECOLE', tenant=self.tenant)
        self.prospect, _ = enregistrer_demande(DEMANDE)

    def test_un_admin_d_ecole_ne_voit_pas_le_fichier_prospects(self):
        """Le fichier commercial de HADY GESMAN n'est pas celui des clients."""
        self.client.force_authenticate(self.admin_ecole)
        self.assertEqual(self.client.get('/api/prospects/').status_code, 403)

    def test_un_visiteur_anonyme_non_plus(self):
        self.assertIn(self.client.get('/api/prospects/').status_code, (401, 403))

    def test_le_super_admin_liste_les_prospects(self):
        self.client.force_authenticate(self.super_admin)
        reponse = self.client.get('/api/prospects/')
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.data[0]['etablissement'], 'Daara Serigne Fallou')
        self.assertEqual(reponse.data[0]['nb_interactions'], 1)

    def test_la_recherche_par_telephone_ignore_la_mise_en_forme(self):
        self.client.force_authenticate(self.super_admin)
        reponse = self.client.get('/api/prospects/?q=+221 77 123 45 67')
        self.assertEqual(len(reponse.data), 1)

    def test_une_recherche_sans_chiffre_ne_ramene_pas_toute_la_table(self):
        """Le filtre téléphone ne doit pas dégénérer en « contient rien »."""
        self.client.force_authenticate(self.super_admin)
        self.assertEqual(len(self.client.get('/api/prospects/?q=zzzz').data), 0)

    def test_consigner_un_echange_fait_sortir_le_prospect_de_nouveau(self):
        self.client.force_authenticate(self.super_admin)
        demain = date.today() + timedelta(days=1)
        reponse = self.client.post(
            f'/api/prospects/{self.prospect.id}/interaction/',
            {'canal': 'APPEL', 'resume': 'Rappelé, intéressé.',
             'relance_le': demain.isoformat()}, format='json')
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.data['statut'], 'CONTACTE')
        self.assertEqual(len(reponse.data['interactions']), 2)
        self.prospect.refresh_from_db()
        self.assertEqual(self.prospect.relance_le, demain)

    def test_un_echange_sans_resume_est_refuse(self):
        self.client.force_authenticate(self.super_admin)
        reponse = self.client.post(
            f'/api/prospects/{self.prospect.id}/interaction/',
            {'canal': 'APPEL', 'resume': '  '}, format='json')
        self.assertEqual(reponse.status_code, 400)
        self.assertEqual(InteractionProspect.objects.count(), 1)

    def test_une_affaire_gagnee_datee_et_sans_relance_en_attente(self):
        self.client.force_authenticate(self.super_admin)
        self.prospect.relance_le = date.today()
        self.prospect.save()
        reponse = self.client.patch(f'/api/prospects/{self.prospect.id}/',
                                    {'statut': 'GAGNE'}, format='json')
        self.assertEqual(reponse.data['statut'], 'GAGNE')
        self.assertIsNone(reponse.data['relance_le'])
        self.assertEqual(reponse.data['date_conversion'], date.today())

    def test_la_trace_de_ce_qui_a_ete_recu_n_est_pas_reecrivable(self):
        self.client.force_authenticate(self.super_admin)
        self.client.patch(f'/api/prospects/{self.prospect.id}/',
                          {'donnees_brutes': {}, 'source': 'MANUEL'},
                          format='json')
        self.prospect.refresh_from_db()
        self.assertEqual(self.prospect.source, 'SITE')
        self.assertTrue(self.prospect.donnees_brutes)

    def test_changer_le_telephone_met_la_cle_de_rapprochement_a_jour(self):
        """Sinon la fiche cesse d'être retrouvée par les demandes suivantes."""
        self.client.force_authenticate(self.super_admin)
        self.client.patch(f'/api/prospects/{self.prospect.id}/',
                          {'telephone': '78 999 88 77'}, format='json')
        self.prospect.refresh_from_db()
        self.assertEqual(self.prospect.telephone_cle, '789998877')

    def test_la_saisie_manuelle_rejoint_une_fiche_deja_connue(self):
        self.client.force_authenticate(self.super_admin)
        reponse = self.client.post('/api/prospects/', DEMANDE, format='json')
        self.assertEqual(reponse.status_code, 200)      # 200 = rattaché, 201 = créé
        self.assertFalse(reponse.data['cree'])
        self.assertEqual(Prospect.objects.count(), 1)

    def test_les_statistiques_comptent_les_demandes_jamais_rappelees(self):
        self.client.force_authenticate(self.super_admin)
        Prospect.objects.filter(pk=self.prospect.pk).update(
            created_at=timezone.now() - timedelta(days=10))
        stats = self.client.get('/api/prospects/stats/').data
        self.assertEqual(stats['total'], 1)
        self.assertEqual(stats['nouveaux'], 1)
        self.assertEqual(stats['jamais_contactes'], 1)
        self.assertEqual(stats['taux_conversion'], 0.0)

    def test_le_taux_de_conversion_ignore_les_affaires_en_cours(self):
        """Compter les dossiers ouverts comme des échecs fausserait la mesure."""
        self.client.force_authenticate(self.super_admin)
        # Établissement, téléphone ET courriel distincts : sans quoi le
        # rapprochement — à raison — les fondrait dans la fiche de setUp.
        autre = {**DEMANDE, 'contact_email': '', 'email': ''}
        gagne, cree_g = enregistrer_demande({**autre, 'etablissement': 'B',
                                             'telephone': '76 111 22 33'})
        perdu, cree_p = enregistrer_demande({**autre, 'etablissement': 'C',
                                             'telephone': '76 111 22 34'})
        self.assertTrue(cree_g and cree_p)
        gagne.statut = 'GAGNE'; gagne.save()
        perdu.statut = 'PERDU'; perdu.save()
        stats = self.client.get('/api/prospects/stats/').data
        self.assertEqual(stats['taux_conversion'], 50.0)   # 1 gagné sur 2 tranchés
        self.assertEqual(stats['en_cours'], 1)
