"""Tests de SAMA : ce qu'il sait, ce qu'il ne doit pas inventer, et le cache.

L'appel au modèle est simulé. Ce qui est vérifié ici, c'est tout le reste — et
c'est là que se logent les vraies fautes : un corpus qui promet une
fonctionnalité absente, un prompt système qui change à chaque requête et fait
tomber le cache, une école qui lit les conversations d'une autre.
"""
from unittest.mock import patch

from rest_framework.test import APITestCase

from apps.assistant.connaissance import corpus
from apps.assistant.models import Conversation, Message
from apps.assistant.perimetre import modules_de, texte_perimetre
from apps.assistant.prompt import prompt_systeme
from apps.licences.models import Licence
from apps.tenants.models import Tenant
from apps.users.models import User


class PerimetreTest(APITestCase):
    """Le périmètre vient du code : il ne peut pas mentir sur le produit."""

    def test_le_module_fiscal_n_est_pas_dans_la_licence_pro(self):
        """Le catalogue commercial l'y annonçait. Le code, non."""
        noms = [nom for nom, _ in modules_de('PRO')]
        self.assertNotIn('Fiscal', noms)
        self.assertIn('Fiscal', [nom for nom, _ in modules_de('AVANCE')])

    def test_taxawu_daara_ouvre_bien_tous_les_modules_metier(self):
        """Le catalogue le sous-décrivait : on vend moins que ce qu'on livre."""
        noms = [nom for nom, _ in modules_de('TAXAWU_DAARA')]
        for attendu in ('Gestion académique', 'Ressources humaines', 'Fiscal',
                        'Gouvernance'):
            self.assertIn(attendu, noms)

    def test_les_emplois_du_temps_sont_annonces_comme_absents(self):
        """Le catalogue les annonçait en licence Avancée. Ils n'existent pas."""
        texte = texte_perimetre()
        self.assertIn('ne fait pas', texte)
        self.assertIn('Emplois du temps', texte)
        # Et surtout : jamais présentés comme une fonctionnalité d'une licence.
        avant_negatif = texte.split('ne fait pas')[0]
        self.assertNotIn('emploi du temps', avant_negatif.lower())

    def test_le_perimetre_suit_le_code_sans_intervention(self):
        """Si MODULES_PAR_TYPE change, le texte change — c'est tout l'intérêt."""
        with patch.dict(Licence.MODULES_PAR_TYPE, {'BASIC': ['/dashboard', '/rh']}):
            noms = [nom for nom, _ in modules_de('BASIC')]
        self.assertEqual(noms, ['Tableau de bord', 'Ressources humaines'])


class CorpusTest(APITestCase):
    def test_les_tarifs_officiels_sont_dans_le_corpus(self):
        t = corpus()
        for tarif in ('25 000', '50 000', '90 000', '20 000'):
            self.assertIn(tarif, t, f"tarif {tarif} absent du corpus")

    def test_le_perimetre_ferme_le_corpus(self):
        """Placé en dernier : c'est lui qui doit l'emporter sur les plaquettes."""
        t = corpus()
        self.assertIn('Périmètre réel des licences', t)
        self.assertGreater(t.index('Périmètre réel des licences'),
                           t.index('Catalogue officiel'))

    def test_les_contrats_et_modeles_sont_disponibles(self):
        t = corpus().lower()
        for attendu in ('contrat de prestation', 'bon de commande', 'devis'):
            self.assertIn(attendu, t)


class CacheDuPromptTest(APITestCase):
    """Le prompt système est mis en cache une heure. Il doit être IDENTIQUE
    d'un appel à l'autre, sinon le cache ne sert jamais et chaque question
    repaie 28 000 jetons."""

    def test_le_prompt_systeme_est_stable_entre_deux_appels(self):
        self.assertEqual(prompt_systeme(), prompt_systeme())

    def test_le_prompt_systeme_ne_contient_aucune_donnee_variable(self):
        """Une date, un nom d'école ou un identifiant ici = cache mort."""
        import datetime
        p = prompt_systeme()
        aujourdhui = datetime.date.today()
        for interdit in (aujourdhui.strftime('%d/%m/%Y'),
                         aujourdhui.strftime('%Y-%m-%d')):
            self.assertNotIn(interdit, p,
                             "une date du jour dans le prompt système "
                             "invalide le cache à chaque requête")


class ConversationAPITest(APITestCase):
    def setUp(self):
        self.ecole = Tenant.objects.create(nom='École A')
        self.autre = Tenant.objects.create(nom='École B')
        self.user = User.objects.create_user('a@a.sn', 'x', nom='Aminata',
                                             role='ADMIN_ECOLE', tenant=self.ecole)
        self.client.force_authenticate(self.user)

    def _flux_simule(self, texte='Bonjour, je suis SAMA.'):
        def faux(messages, systeme):
            yield ('texte', texte)
            yield ('fin', {'jetons_entree': 100, 'jetons_sortie': 20,
                           'jetons_cache': 28000, 'tronque': False})
        return faux

    def test_envoyer_un_message_ouvre_une_conversation_et_garde_la_reponse(self):
        with patch('apps.assistant.views.repondre', self._flux_simule()):
            r = self.client.post('/api/assistant/conversations/message/',
                                 {'contenu': 'Quel est le tarif de la licence Pro ?'},
                                 format='json')
            corps = b''.join(r.streaming_content).decode()

        self.assertEqual(r.status_code, 200)
        self.assertIn('SAMA', corps)
        conv = Conversation.objects.get()
        self.assertEqual(conv.tenant, self.ecole)
        self.assertEqual([m.role for m in conv.messages.all()],
                         ['user', 'assistant'])
        self.assertEqual(conv.messages.last().jetons_cache, 28000)

    def test_le_contexte_de_l_ecole_precede_la_question(self):
        """SAMA doit savoir à qui il parle sans le redemander."""
        vus = {}

        def espion(messages, systeme):
            vus['premier'] = messages[0]['content']
            yield ('texte', 'ok')
            yield ('fin', {})

        with patch('apps.assistant.views.repondre', espion):
            r = self.client.post('/api/assistant/conversations/message/',
                                 {'contenu': 'Bonjour'}, format='json')
            b''.join(r.streaming_content)

        self.assertIn('École A', vus['premier'])
        self.assertIn('Aminata', vus['premier'])
        self.assertIn("c'est un client, pas un prospect", vus['premier'])

    def test_une_panne_du_modele_est_dite_a_l_utilisateur(self):
        from apps.assistant.client import AssistantIndisponible

        def tombe(messages, systeme):
            raise AssistantIndisponible("L'assistant n'est pas joignable.")
            yield  # noqa — générateur

        with patch('apps.assistant.views.repondre', tombe):
            r = self.client.post('/api/assistant/conversations/message/',
                                 {'contenu': 'Bonjour'}, format='json')
            corps = b''.join(r.streaming_content).decode()

        self.assertIn('erreur', corps)
        self.assertIn("pas joignable", corps)
        # Rien d'incomplet ne reste dans l'historique.
        self.assertFalse(Message.objects.filter(role='assistant').exists())

    def test_un_message_vide_est_refuse(self):
        r = self.client.post('/api/assistant/conversations/message/',
                             {'contenu': '   '}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_une_ecole_ne_voit_pas_les_conversations_d_une_autre(self):
        autre_user = User.objects.create_user('b@b.sn', 'x', nom='Bineta',
                                              role='ADMIN_ECOLE', tenant=self.autre)
        Conversation.objects.create(tenant=self.autre, utilisateur=autre_user,
                                    titre='Secret de B')

        r = self.client.get('/api/assistant/conversations/')
        self.assertEqual(r.data, [])

    def test_un_collegue_ne_lit_pas_mes_conversations(self):
        collegue = User.objects.create_user('c@a.sn', 'x', nom='Cheikh',
                                            role='ADMIN_SCOLARITE', tenant=self.ecole)
        conv = Conversation.objects.create(tenant=self.ecole, utilisateur=collegue,
                                           titre='Question du collègue')
        r = self.client.get(f'/api/assistant/conversations/{conv.id}/')
        self.assertEqual(r.status_code, 404)
