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
from apps.assistant.outils import (MAX_APPELS_PAR_TOUR, NOM_OUTIL,
                                   definition_outil, executer)
from apps.assistant.perimetre import modules_de, texte_perimetre
from apps.assistant.prompt import prompt_systeme
from apps.assistant.views import MessageThrottle
from apps.licences.models import Licence
from apps.prospects.models import InteractionProspect, Prospect

URL_MESSAGE = '/api/assistant/message/'
URL_ETAT    = '/api/assistant/etat/'


def flux_simule(texte='Bonjour, je suis SAMA.', **usage):
    """Un `repondre` de remplacement, avec la consommation qu'on veut."""
    consommation = {'jetons_entree': 200, 'jetons_sortie': 150,
                    'jetons_cache_lecture': 15000, 'jetons_cache_ecriture': 0,
                    'tronque': False, **usage}

    def faux(messages, systeme, **_):
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

        def tombe(messages, systeme, **_):
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


# ─── Étape 3 : le diagnostic conduit ────────────────────────────────────────

class FauxUsage:
    def __init__(self, entree=100, sortie=50, lecture=15000, ecriture=0):
        self.input_tokens = entree
        self.output_tokens = sortie
        self.cache_read_input_tokens = lecture
        self.cache_creation_input_tokens = ecriture


class FauxBloc:
    """Un bloc de contenu tel que le SDK le rendrait."""

    def __init__(self, type, texte='', nom='', identifiant='', entree=None):
        self.type = type
        self.text = texte
        self.name = nom
        self.id = identifiant
        self.input = entree or {}


class FauxTour:
    """Un tour de réponse scénarisé : du texte, éventuellement un appel d'outil."""

    def __init__(self, texte='', appel=None, usage=None):
        self.texte = texte
        blocs = [FauxBloc('text', texte=texte)] if texte else []
        if appel:
            blocs.append(FauxBloc('tool_use', nom=appel[0],
                                  identifiant=appel[1], entree=appel[2]))
        self.content = blocs
        self.stop_reason = 'tool_use' if appel else 'end_turn'
        self.usage = usage or FauxUsage()


class FauxClientAnthropic:
    """Rejoue une liste de tours et retient les paramètres de chaque appel.

    Ce que ces tests vérifient tient à ces paramètres : que les outils sont
    bien transmis, identiques d'un tour à l'autre (sans quoi le cache tombe),
    et que les résultats d'outils repartent dans UN seul message.
    """

    def __init__(self, tours):
        self.tours = list(tours)
        self.appels = []
        self.messages = self

    def stream(self, **parametres):
        self.appels.append(parametres)
        tour = self.tours.pop(0) if self.tours else FauxTour('Fin.')
        client = self

        class Flux:
            def __enter__(self_):
                return self_

            def __exit__(self_, *_):
                return False

            @property
            def text_stream(self_):
                return iter([tour.texte] if tour.texte else [])

            def get_final_message(self_):
                return tour

        return Flux()


DIAGNOSTIC = {
    'etablissement': 'Daara Serigne Fallou',
    'type_organisation': 'Daara',
    'ville': 'Rufisque',
    'telephone': '77 123 45 67',
    'contact_nom': 'Moussa Diop',
    'contact_fonction': 'Directeur',
    'nb_eleves': 180,
    'situation_actuelle': 'Tout est tenu sur des cahiers.',
    'besoins': "Savoir qui a payé et qui n'a pas payé, sans tout relire.",
    'licence_pressentie': 'TAXAWU_DAARA',
    'accord_rappel': True,
}


class OutilDiagnosticTest(APITestCase):
    """L'assistant recueille, le serveur rédige."""

    def test_le_schema_ne_reclame_que_le_nom_de_l_etablissement(self):
        """Tout exiger reviendrait à ne jamais rien enregistrer : un visiteur
        donne son numéro à la fin d'un échange, ou pas du tout."""
        schema = definition_outil()['input_schema']
        self.assertEqual(schema['required'], ['etablissement'])

    def test_le_schema_est_stable_entre_deux_appels(self):
        """Il est rendu AVANT le prompt système : s'il varie, le cache tombe."""
        self.assertEqual(definition_outil(), definition_outil())

    def test_le_schema_couvre_ce_que_le_prompt_fait_demander(self):
        """Les deux se relisent ensemble — une question posée sans champ pour
        la ranger est une question posée pour rien."""
        champs = definition_outil()['input_schema']['properties']
        for attendu in ('etablissement', 'ville', 'telephone', 'nb_eleves',
                        'situation_actuelle', 'besoins', 'accord_rappel'):
            self.assertIn(attendu, champs)

    def test_le_diagnostic_devient_une_fiche_prospect(self):
        texte, prospect = executer(DIAGNOSTIC)
        self.assertIsNotNone(prospect)
        self.assertEqual(prospect.source, 'ASSISTANT')
        self.assertEqual(prospect.etablissement, 'Daara Serigne Fallou')
        self.assertEqual(prospect.nb_eleves, 180)
        self.assertEqual(prospect.telephone_cle, '771234567')
        self.assertIn('transmise', texte)

    def test_le_resume_est_redige_par_le_serveur_pas_par_le_modele(self):
        """Le modèle fournit des champs ; la mise en forme reste chez nous."""
        _, prospect = executer(DIAGNOSTIC)
        echange = prospect.interactions.get()
        self.assertEqual(echange.canal, 'ASSISTANT')
        self.assertEqual(echange.auteur, 'SAMA')
        self.assertIn('Situation actuelle : Tout est tenu sur des cahiers.',
                      echange.resume)
        self.assertIn('Licence pressentie : Taxawu Daara', echange.resume)

    def test_ce_que_le_modele_de_donnees_ignore_est_conserve_quand_meme(self):
        _, prospect = executer(DIAGNOSTIC)
        self.assertEqual(prospect.donnees_brutes['licence_pressentie'],
                         'TAXAWU_DAARA')
        self.assertIn('cahiers', prospect.donnees_brutes['situation_actuelle'])

    def test_un_accord_de_rappel_place_la_fiche_dans_la_pile_a_relancer(self):
        """C'est ce qui transforme une conversation en rendez-vous."""
        _, prospect = executer(DIAGNOSTIC)
        self.assertEqual(prospect.relance_le, date.today() + timedelta(days=1))

    def test_sans_accord_aucune_relance_n_est_programmee(self):
        _, prospect = executer({**DIAGNOSTIC, 'accord_rappel': False})
        self.assertIsNone(prospect.relance_le)
        self.assertIn("n'a pas explicitement accepté",
                      prospect.interactions.get().resume)

    def test_le_diagnostic_rejoint_une_fiche_venue_du_formulaire(self):
        """Le même établissement écrit par le formulaire puis parle à SAMA :
        une seule fiche, un historique continu."""
        from apps.prospects.enregistrement import enregistrer_demande
        enregistrer_demande({'etablissement': 'Daara Serigne Fallou',
                             'telephone': '+221 77 123 45 67',
                             'contact_nom': 'Moussa Diop'})
        _, prospect = executer(DIAGNOSTIC)
        self.assertEqual(Prospect.objects.count(), 1)
        self.assertEqual(prospect.source, 'SITE')      # l'origine d'abord connue
        self.assertEqual(InteractionProspect.objects.count(), 2)

    def test_un_diagnostic_sans_etablissement_ne_cree_rien(self):
        texte, prospect = executer({**DIAGNOSTIC, 'etablissement': '  '})
        self.assertIsNone(prospect)
        self.assertFalse(Prospect.objects.exists())
        self.assertIn("nom de l'établissement", texte)

    def test_une_panne_d_enregistrement_ne_parle_pas_technique_au_visiteur(self):
        """Le texte repart vers le modèle, qui le répétera : il doit être
        présentable."""
        with patch('apps.prospects.enregistrement.enregistrer_demande',
                   side_effect=RuntimeError('base indisponible')):
            texte, prospect = executer(DIAGNOSTIC)
        self.assertIsNone(prospect)
        self.assertNotIn('base indisponible', texte)
        self.assertIn('70 328 61 51', texte)

    def test_la_conversation_garde_le_lien_vers_la_fiche(self):
        """Sans ce lien, on saurait ce que SAMA coûte, jamais ce qu'il rapporte."""
        conv = Conversation.objects.create(titre='Essai')
        _, prospect = executer(DIAGNOSTIC, conversation=conv)
        conv.refresh_from_db()
        self.assertEqual(conv.prospect_id, prospect.id)


class BoucleOutilTest(APITestCase):
    """La boucle d'outils de `client.repondre`, avec un faux SDK."""

    def _repondre(self, tours, **kwargs):
        from apps.assistant.client import repondre
        faux = FauxClientAnthropic(tours)
        with patch('apps.assistant.client._client', return_value=faux):
            evenements = list(repondre(
                [{'role': 'user', 'content': 'Bonjour'}], 'SYSTÈME',
                outils=[definition_outil()], **kwargs))
        return evenements, faux

    def test_le_texte_avant_et_apres_l_appel_est_diffuse(self):
        evenements, _ = self._repondre(
            [FauxTour('Je transmets votre situation.',
                      appel=(NOM_OUTIL, 'tu_1', DIAGNOSTIC)),
             FauxTour("C'est fait, l'équipe vous rappellera.")],
            executer_outil=lambda nom, donnees: 'ok')
        textes = [c for genre, c in evenements if genre == 'texte']
        self.assertEqual(textes, ['Je transmets votre situation.',
                                  "C'est fait, l'équipe vous rappellera."])
        self.assertIn(('outil', NOM_OUTIL), evenements)

    def test_la_consommation_de_TOUS_les_tours_est_additionnee(self):
        """N'en compter qu'un sous-estimerait la dépense — dans le sens qui
        désarme le coupe-circuit."""
        evenements, _ = self._repondre(
            [FauxTour('a', appel=(NOM_OUTIL, 'tu_1', DIAGNOSTIC),
                      usage=FauxUsage(entree=100, sortie=50)),
             FauxTour('b', usage=FauxUsage(entree=300, sortie=70))],
            executer_outil=lambda nom, donnees: 'ok')
        usage = dict(evenements)['fin']
        self.assertEqual(usage['jetons_entree'], 400)
        self.assertEqual(usage['jetons_sortie'], 120)

    def test_les_resultats_repartent_dans_un_seul_message(self):
        """Les séparer apprend au modèle à ne plus appeler ses outils en
        parallèle."""
        _, faux = self._repondre(
            [FauxTour('a', appel=(NOM_OUTIL, 'tu_1', DIAGNOSTIC)),
             FauxTour('b')],
            executer_outil=lambda nom, donnees: 'transmis')
        second_fil = faux.appels[1]['messages']
        self.assertEqual(second_fil[-1]['role'], 'user')
        self.assertEqual([b['type'] for b in second_fil[-1]['content']],
                         ['tool_result'])
        self.assertEqual(second_fil[-1]['content'][0]['tool_use_id'], 'tu_1')
        self.assertEqual(second_fil[-1]['content'][0]['content'], 'transmis')

    def test_les_outils_sont_identiques_a_chaque_tour(self):
        """Ils précèdent le bloc système dans le préfixe mis en cache."""
        _, faux = self._repondre(
            [FauxTour('a', appel=(NOM_OUTIL, 'tu_1', DIAGNOSTIC)),
             FauxTour('b')],
            executer_outil=lambda nom, donnees: 'ok')
        self.assertEqual(faux.appels[0]['tools'], faux.appels[1]['tools'])
        self.assertEqual(faux.appels[0]['system'], faux.appels[1]['system'])

    def test_un_modele_qui_boucle_est_arrete(self):
        """Chaque tour renvoie tout le contexte : sans borne, une seule
        conversation peut coûter le budget d'une journée."""
        bouclant = [FauxTour('encore', appel=(NOM_OUTIL, f'tu_{n}', DIAGNOSTIC))
                    for n in range(20)]
        _, faux = self._repondre(bouclant,
                                 executer_outil=lambda nom, donnees: 'ok',
                                 max_tours_outil=2)
        self.assertEqual(len(faux.appels), 3)   # 2 tours d'outil + le dernier

    def test_sans_executeur_l_appel_d_outil_est_ignore(self):
        evenements, faux = self._repondre(
            [FauxTour('a', appel=(NOM_OUTIL, 'tu_1', DIAGNOSTIC))])
        self.assertEqual(len(faux.appels), 1)
        self.assertIn('fin', dict(evenements))


@override_settings(ANTHROPIC_API_KEY='sk-test')
class DiagnosticParLApiTest(APITestCase):
    """Le chemin complet, vu du site vitrine."""

    def setUp(self):
        cache.clear()

    def _envoyer(self, contenu='Nous sommes un daara à Rufisque.', faux=None,
                 conversation=None):
        charge = {'contenu': contenu}
        if conversation:
            charge['conversation'] = str(conversation)
        with patch('apps.assistant.views.repondre', faux or flux_simule()):
            r = self.client.post(URL_MESSAGE, charge, format='json',
                                 REMOTE_ADDR='41.82.13.7')
            if r.status_code == 200:
                r.corps = b''.join(r.streaming_content).decode()
        return r

    def _faux_avec_outil(self, donnees=None):
        """Un `repondre` qui exécute réellement l'outil qu'on lui confie."""
        def faux(messages, systeme, outils=None, executer_outil=None, **_):
            faux.fil = messages
            faux.outils = outils
            yield ('texte', 'Je transmets votre situation. ')
            resultat = executer_outil(NOM_OUTIL, donnees or DIAGNOSTIC)
            faux.resultat = resultat
            yield ('outil', NOM_OUTIL)
            yield ('texte', "L'équipe vous rappellera.")
            yield ('fin', {'jetons_entree': 400, 'jetons_sortie': 120,
                           'jetons_cache_lecture': 15000,
                           'jetons_cache_ecriture': 0, 'tronque': False})
        return faux

    def test_une_conversation_produit_une_fiche_et_le_dit_au_site(self):
        faux = self._faux_avec_outil()
        r = self._envoyer(faux=faux)
        self.assertEqual(r.status_code, 200)
        self.assertIn('"type": "outil"', r.corps)

        prospect = Prospect.objects.get()
        self.assertEqual(prospect.source, 'ASSISTANT')
        self.assertEqual(prospect.etablissement, 'Daara Serigne Fallou')
        self.assertEqual(Conversation.objects.get().prospect_id, prospect.id)

    def test_l_outil_est_bien_propose_au_modele(self):
        faux = self._faux_avec_outil()
        self._envoyer(faux=faux)
        self.assertEqual([o['name'] for o in faux.outils], [NOM_OUTIL])

    def test_une_fiche_deja_transmise_est_signalee_au_modele(self):
        """Sans ce rappel, SAMA rouvrirait une fiche à chaque message : les
        blocs d'appel d'outil ne sont pas conservés d'un tour à l'autre."""
        self._envoyer(faux=self._faux_avec_outil())
        conv = Conversation.objects.get()

        suite = self._faux_avec_outil()
        self._envoyer(contenu='Une dernière question.', faux=suite,
                      conversation=conv.id)
        self.assertIn('déjà été transmise', suite.fil[-1]['content'])
        self.assertIn('Une dernière question.', suite.fil[-1]['content'])

    def test_la_note_du_serveur_n_apparait_pas_tant_qu_il_n_y_a_pas_de_fiche(self):
        premier = self._faux_avec_outil()
        self._envoyer(faux=premier)
        self.assertNotIn('déjà été transmise', premier.fil[-1]['content'])

    def test_un_outil_inconnu_ne_fait_pas_tomber_la_conversation(self):
        def faux(messages, systeme, outils=None, executer_outil=None, **_):
            faux.resultat = executer_outil('outil_qui_n_existe_pas', {})
            yield ('texte', 'Réponse malgré tout.')
            yield ('fin', {'jetons_entree': 10, 'jetons_sortie': 5,
                           'jetons_cache_lecture': 0, 'jetons_cache_ecriture': 0,
                           'tronque': False})

        r = self._envoyer(faux=faux)
        self.assertEqual(r.status_code, 200)
        self.assertIn('Réponse malgré tout.', r.corps)
        self.assertIn("n'existe pas", faux.resultat)
        self.assertFalse(Prospect.objects.exists())
