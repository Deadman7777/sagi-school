"""Tests de SAMA sur le site vitrine.

L'appel au modèle est simulé. Ce qui est vérifié ici, c'est tout le reste — et
c'est là que se logent les vraies fautes d'un assistant public :

- **un document confidentiel qui se retrouve dans le corpus**, donc en ligne,
  parce qu'un modèle restitue tout ce qu'on lui confie à qui le lui demande ;
- **un corpus qui promet une fonctionnalité absente**, parce que la plaquette
  la promettait ;
- **un prompt système qui change à chaque requête**, et fait payer le corpus
  entier à chaque question au lieu d'un dixième ;
- **un garde-fou qui ne garde rien**, et laisse une nuit d'activité anormale
  consommer le budget du mois.
"""
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.assistant.client import cout_fcfa
from apps.assistant.connaissance import CONFIDENTIELS, DOSSIER, PUBLICS, corpus
from apps.assistant.garde_fous import cle_visiteur, etat_budget
from apps.assistant.models import (ConsommationJournaliere, Conversation,
                                   Message)
from apps.assistant.perimetre import modules_de, texte_perimetre
from apps.assistant.prompt import prompt_systeme
from apps.assistant.views import MessageThrottle
from apps.licences.models import Licence

URL_MESSAGE = '/api/assistant/message/'
URL_ETAT    = '/api/assistant/etat/'


def flux_simule(texte='Bonjour, je suis SAMA.', **usage):
    """Un `repondre` de remplacement, avec la consommation qu'on veut."""
    consommation = {'jetons_entree': 200, 'jetons_sortie': 150,
                    'jetons_cache_lecture': 15000, 'jetons_cache_ecriture': 0,
                    'tronque': False, **usage}

    def faux(messages, systeme):
        yield ('texte', texte)
        yield ('fin', consommation)
    return faux


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


class CorpusPublicTest(APITestCase):
    """Le test le plus important du module.

    Tout ce que contient le corpus est publiable : un visiteur n'a qu'à le
    demander poliment pour l'obtenir. Ces vérifications sont donc la seule
    protection réelle de nos documents confidentiels — les consignes du prompt
    n'en sont pas une.
    """

    def test_aucun_document_confidentiel_n_est_dans_le_corpus(self):
        t = corpus()
        for nom, motif in CONFIDENTIELS:
            fichier = DOSSIER / f'{nom}.txt'
            if not fichier.exists():
                continue
            lignes = [l.strip() for l in fichier.read_text(encoding='utf-8').splitlines()]
            # Les lignes longues sont propres à un document : si l'une d'elles
            # apparaît dans le corpus, le document y est.
            distinctives = sorted((l for l in lignes if len(l) > 60),
                                  key=len, reverse=True)[:5]
            for ligne in distinctives:
                self.assertNotIn(ligne, t,
                                 f"{nom} ({motif}) se retrouve dans le corpus public")

    def test_les_references_internes_ne_fuitent_pas(self):
        t = corpus()
        for reference in ('HG-DEV-2026-0001', 'HG-COM-002', 'HG-COM-008',
                          'HG-OPS-002', 'HG-OPS-003'):
            self.assertNotIn(reference, t)

    def test_la_mention_confidentiel_n_apparait_nulle_part(self):
        """Un « Confidentiel » dans le corpus est, par définition, une fuite."""
        self.assertNotIn('confidentiel', corpus().lower())

    def test_les_tarifs_officiels_restent_dans_le_corpus(self):
        """Retirer les documents internes ne doit pas amputer le discours."""
        t = corpus()
        for tarif in ('25 000', '50 000', '90 000', '20 000'):
            self.assertIn(tarif, t, f"tarif {tarif} absent du corpus")

    def test_le_perimetre_ferme_le_corpus(self):
        """Placé en dernier : c'est lui qui doit l'emporter sur les plaquettes."""
        t = corpus()
        self.assertIn('Périmètre réel des licences', t)
        self.assertGreater(t.index('Périmètre réel des licences'),
                           t.index('Catalogue officiel'))

    def test_les_deux_listes_ne_se_recouvrent_pas(self):
        publics = {nom for nom, _ in PUBLICS}
        confidentiels = {nom for nom, _ in CONFIDENTIELS}
        self.assertEqual(publics & confidentiels, set())

    def test_tous_les_documents_sont_classes(self):
        """Un fichier déposé dans `connaissances/` sans être classé serait
        soit oublié, soit — pire — publié sans décision."""
        sur_disque = {f.stem for f in DOSSIER.glob('*.txt')}
        classes = {nom for nom, _ in PUBLICS} | {nom for nom, _ in CONFIDENTIELS}
        self.assertEqual(sur_disque - classes, set(),
                         "document non classé : public ou confidentiel ?")


class PromptTest(APITestCase):
    """Le prompt est mis en cache. Il doit être IDENTIQUE d'un appel à l'autre,
    sinon le cache ne sert jamais et chaque question repaie le corpus entier."""

    def test_le_prompt_systeme_est_stable_entre_deux_appels(self):
        self.assertEqual(prompt_systeme(), prompt_systeme())

    def test_le_prompt_systeme_ne_contient_aucune_donnee_variable(self):
        """Une date ou un identifiant ici = cache mort pour tout le monde."""
        aujourdhui = date.today()
        p = prompt_systeme()
        for interdit in (aujourdhui.strftime('%d/%m/%Y'),
                         aujourdhui.strftime('%Y-%m-%d')):
            self.assertNotIn(interdit, p,
                             "une date du jour dans le prompt système "
                             "invalide le cache à chaque requête")

    def test_l_assistant_sait_qu_il_ne_connait_pas_son_interlocuteur(self):
        """La faute que la mise en ligne rend possible : accepter sur parole
        une identité déclarée, et répondre en conséquence."""
        p = prompt_systeme()
        self.assertIn('Tu ne sais pas qui te parle', p)
        self.assertIn('invérifiable', p)

    def test_l_assistant_ne_redige_ni_devis_ni_contrat(self):
        """Le principe validé par la direction : il recueille, nous rédigeons."""
        p = prompt_systeme()
        self.assertIn('Tu ne rédiges ni devis, ni contrat', p)


class CoutTest(APITestCase):
    """Un seul calcul du coût, celui de `client.cout_fcfa`. Le coupe-circuit et
    l'écran de suivi doivent additionner exactement la même chose."""

    @override_settings(SAMA_TAUX_USD_FCFA=610)
    def test_le_cache_coute_dix_fois_moins_que_l_entree(self):
        plein = cout_fcfa({'jetons_entree': 1_000_000})
        cache_ = cout_fcfa({'jetons_cache_lecture': 1_000_000})
        self.assertEqual(plein, Decimal('610.0000'))
        self.assertEqual(cache_, Decimal('61.0000'))

    @override_settings(SAMA_TAUX_USD_FCFA=610)
    def test_une_conversation_type_coute_quelques_dizaines_de_francs(self):
        """L'ordre de grandeur sur lequel le budget a été proposé. S'il change,
        c'est que le modèle ou le corpus a changé — et le plafond avec."""
        six_tours = sum(
            cout_fcfa({'jetons_entree': 1500, 'jetons_sortie': 400,
                       'jetons_cache_lecture': 15000,
                       'jetons_cache_ecriture': 15000 if tour == 0 else 0})
            for tour in range(6))
        self.assertGreater(six_tours, Decimal('10'))
        self.assertLess(six_tours, Decimal('80'))

    def test_un_usage_vide_ne_coute_rien(self):
        self.assertEqual(cout_fcfa({}), Decimal('0.0000'))


class CleVisiteurTest(APITestCase):
    """On compte les visiteurs, on ne les identifie pas."""

    def _requete(self, ip, transmise=None):
        from django.test import RequestFactory
        entetes = {'REMOTE_ADDR': ip}
        if transmise:
            entetes['HTTP_X_FORWARDED_FOR'] = transmise
        return RequestFactory().post('/', **entetes)

    def test_l_empreinte_ne_contient_pas_l_adresse(self):
        cle = cle_visiteur(self._requete('41.82.13.7'))
        self.assertNotIn('41.82', cle)
        self.assertEqual(len(cle), 64)

    def test_deux_adresses_donnent_deux_empreintes(self):
        self.assertNotEqual(cle_visiteur(self._requete('41.82.13.7')),
                            cle_visiteur(self._requete('41.82.13.8')))

    def test_derriere_un_proxy_c_est_l_adresse_reelle_qui_compte(self):
        """Sinon tous les visiteurs partagent la limite de nginx."""
        derriere = self._requete('10.0.0.1', transmise='41.82.13.7, 10.0.0.1')
        direct = self._requete('41.82.13.7')
        self.assertEqual(cle_visiteur(derriere), cle_visiteur(direct))


class ApiPubliqueTest(APITestCase):
    """L'assistant vu du site vitrine — sans compte, sans jeton, sans école."""

    def setUp(self):
        # La limitation de débit de DRF s'appuie sur le cache, partagé entre
        # les tests d'un même processus : sans ce nettoyage, le compteur d'un
        # test ferait échouer le suivant.
        cache.clear()

    def _envoyer(self, contenu='Combien coûte la licence Pro ?', ip='41.82.13.7',
                 conversation=None, texte='Bonjour, je suis SAMA.'):
        charge = {'contenu': contenu}
        if conversation:
            charge['conversation'] = str(conversation)
        with patch('apps.assistant.views.repondre', flux_simule(texte)):
            r = self.client.post(URL_MESSAGE, charge, format='json',
                                 REMOTE_ADDR=ip)
            if r.status_code == 200:
                r.corps = b''.join(r.streaming_content).decode()
        return r

    def test_un_visiteur_anonyme_peut_ecrire(self):
        r = self._envoyer()
        self.assertEqual(r.status_code, 200)
        self.assertIn('SAMA', r.corps)
        conv = Conversation.objects.get()
        self.assertEqual([m.role for m in conv.messages.all()],
                         ['user', 'assistant'])

    def test_la_consommation_est_enregistree_apres_la_reponse(self):
        self._envoyer()
        jour = ConsommationJournaliere.objects.get(jour=date.today())
        self.assertEqual(jour.nb_messages, 1)
        self.assertEqual(jour.nb_conversations, 1)
        self.assertEqual(jour.jetons_cache_lecture, 15000)
        self.assertGreater(jour.cout_fcfa, 0)
        # Le même montant des deux côtés : c'est ce qui rend le plafond juste.
        self.assertEqual(jour.cout_fcfa,
                         Message.objects.get(role='assistant').cout_fcfa)

    def test_un_message_vide_est_refuse(self):
        self.assertEqual(self._envoyer('   ').status_code, 400)

    def test_un_message_demesure_est_refuse(self):
        """Sur un site public, un message énorme n'est pas un usage."""
        self.assertEqual(self._envoyer('a' * 3000).status_code, 400)

    def test_un_visiteur_n_ecrit_pas_dans_la_conversation_d_un_autre(self):
        premiere = self._envoyer(ip='41.82.13.7')
        conv_id = Conversation.objects.get().id
        self.assertEqual(premiere.status_code, 200)

        self._envoyer(ip='197.5.1.1', conversation=conv_id)
        # L'identifiant fourni est ignoré : une NOUVELLE conversation s'ouvre,
        # et rien n'est ajouté au fil du premier visiteur.
        self.assertEqual(Conversation.objects.count(), 2)
        self.assertEqual(Conversation.objects.get(pk=conv_id).messages.count(), 2)

    def test_une_panne_du_modele_est_dite_au_visiteur(self):
        from apps.assistant.client import AssistantIndisponible

        def tombe(messages, systeme):
            raise AssistantIndisponible("L'assistant n'est pas joignable.")
            yield  # noqa — générateur

        with patch('apps.assistant.views.repondre', tombe):
            r = self.client.post(URL_MESSAGE, {'contenu': 'Bonjour'},
                                 format='json', REMOTE_ADDR='41.82.13.7')
            corps = b''.join(r.streaming_content).decode()

        self.assertIn('erreur', corps)
        self.assertIn('pas joignable', corps)
        # Rien d'incomplet ne reste dans l'historique, et rien n'est facturé.
        self.assertFalse(Message.objects.filter(role='assistant').exists())
        self.assertFalse(ConsommationJournaliere.objects.exists())

    @override_settings(ANTHROPIC_API_KEY='')
    def test_sans_cle_le_site_est_prie_de_ne_pas_afficher_l_assistant(self):
        """Mieux vaut aucun bouton qu'un bouton mort."""
        self.assertFalse(self.client.get(URL_ETAT).data['disponible'])

    @override_settings(ANTHROPIC_API_KEY='sk-test')
    def test_avec_une_cle_l_assistant_est_annonce_disponible(self):
        self.assertTrue(self.client.get(URL_ETAT).data['disponible'])


@override_settings(ANTHROPIC_API_KEY='sk-test')
class GardeFousTest(APITestCase):
    """Les bornes de dépense — ce qui remplace le contrôle d'accès perdu."""

    def setUp(self):
        cache.clear()

    def _envoyer(self, ip='41.82.13.7', conversation=None):
        charge = {'contenu': 'Bonjour'}
        if conversation:
            charge['conversation'] = str(conversation)
        with patch('apps.assistant.views.repondre', flux_simule()):
            r = self.client.post(URL_MESSAGE, charge, format='json',
                                 REMOTE_ADDR=ip)
            if r.status_code == 200:
                b''.join(r.streaming_content)
        return r

    @override_settings(SAMA_PLAFOND_JOUR_FCFA=100)
    def test_le_coupe_circuit_journalier_arrete_le_service(self):
        ConsommationJournaliere.objects.create(jour=date.today(), cout_fcfa=150)
        r = self._envoyer()
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r.data['raison'], 'coupe_circuit_journalier')
        self.assertFalse(Conversation.objects.exists())

    @override_settings(SAMA_PLAFOND_JOUR_FCFA=100000, SAMA_PLAFOND_MOIS_FCFA=500)
    def test_le_plafond_mensuel_cumule_les_jours_du_mois(self):
        """Une dépense étalée doit couper aussi sûrement qu'une pointe."""
        premier = date.today().replace(day=1)
        for décalage in range(3):
            jour = premier + timedelta(days=décalage)
            if jour <= date.today():
                ConsommationJournaliere.objects.create(jour=jour, cout_fcfa=200)
        r = self._envoyer()
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r.data['raison'], 'plafond_mensuel')

    @override_settings(SAMA_PLAFOND_MOIS_FCFA=500)
    def test_la_depense_du_mois_dernier_ne_compte_pas(self):
        """Le plafond est mensuel : il se remet à zéro, sinon le service
        s'éteindrait définitivement au bout de quelques mois."""
        veille_du_mois = date.today().replace(day=1) - timedelta(days=1)
        ConsommationJournaliere.objects.create(jour=veille_du_mois, cout_fcfa=9000)
        self.assertEqual(self._envoyer().status_code, 200)

    @override_settings(SAMA_MAX_CONVERSATIONS_VISITEUR_JOUR=2)
    def test_un_visiteur_ne_peut_pas_ouvrir_des_conversations_sans_fin(self):
        self.assertEqual(self._envoyer().status_code, 200)
        self.assertEqual(self._envoyer().status_code, 200)
        r = self._envoyer()
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r.data['raison'], 'limite_visiteur')

    @override_settings(SAMA_MAX_CONVERSATIONS_VISITEUR_JOUR=1)
    def test_la_limite_d_un_visiteur_n_affecte_pas_les_autres(self):
        self.assertEqual(self._envoyer(ip='41.82.13.7').status_code, 200)
        self.assertEqual(self._envoyer(ip='41.82.13.7').status_code, 429)
        self.assertEqual(self._envoyer(ip='197.5.1.1').status_code, 200)

    @override_settings(SAMA_MAX_MESSAGES_CONVERSATION=2)
    def test_une_conversation_est_bornee_et_ne_repart_pas(self):
        """Sans cette borne, un fil sans fin renvoie tout son historique au
        modèle à chaque tour : la note croît en carré."""
        self.assertEqual(self._envoyer().status_code, 200)
        conv = Conversation.objects.get()
        conv.refresh_from_db()
        self.assertTrue(conv.close)

        r = self._envoyer(conversation=conv.id)
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r.data['raison'], 'conversation_bornee')
        self.assertEqual(conv.messages.count(), 2)

    @override_settings(SAMA_PLAFOND_JOUR_FCFA=100)
    def test_le_site_cesse_d_annoncer_l_assistant_quand_le_budget_est_atteint(self):
        ConsommationJournaliere.objects.create(jour=date.today(), cout_fcfa=150)
        self.assertFalse(self.client.get(URL_ETAT).data['disponible'])
        self.assertTrue(etat_budget()['suspendu'])

    @override_settings(SAMA_PLAFOND_JOUR_FCFA=100)
    def test_la_commande_de_controle_dit_que_le_service_est_suspendu(self):
        """Sur le VPS, on constate la consommation en ligne de commande — pas
        en ouvrant une session d'administration dans un navigateur."""
        from io import StringIO

        from django.core.management import call_command

        ConsommationJournaliere.objects.create(
            jour=date.today(), cout_fcfa=150, nb_messages=4, nb_conversations=2)
        sortie = StringIO()
        call_command('sama_budget', stdout=sortie)
        texte = sortie.getvalue()
        self.assertIn('SERVICE SUSPENDU', texte)
        self.assertIn('150 F', texte)

    def test_la_limitation_de_debit_precede_les_plafonds(self):
        """Première barrière : elle protège le serveur, pas le budget."""
        with patch.object(MessageThrottle, 'rate', '2/hour'):
            self.assertEqual(self._envoyer().status_code, 200)
            self.assertEqual(self._envoyer().status_code, 200)
            self.assertEqual(self._envoyer().status_code, 429)
