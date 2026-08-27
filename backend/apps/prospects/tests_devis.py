"""Tests des devis produits par le serveur.

Ce que ces tests cherchent à rendre impossible, ce sont les deux fautes qui
coûtent cher sur une pièce que le client signe :

- **un montant que personne n'a fixé** — le chiffrage vient du catalogue, et un
  devis déjà remis ne doit pas se réécrire quand le catalogue change ;
- **une pièce partie sans avoir été relue** — aucun chemin ne doit mener du
  brouillon à l'envoi.

Et une troisième, propre à cette maison : **promettre une fonctionnalité qui
n'existe pas.** Le catalogue commercial annonce une gestion des emplois du
temps ; le devis liste ce que le CODE ouvre.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import override_settings
from rest_framework.test import APITestCase

from apps.licences.catalogue import chiffrer, tarif_mensuel
from apps.prospects.devis import etablir, prochain_numero, rendre_pdf
from apps.prospects.enregistrement import enregistrer_demande
from apps.prospects.models import Devis, InteractionProspect, Prospect
from apps.tenants.models import Tenant
from apps.users.models import User

FICHE = {
    'etablissement': 'Daara Serigne Fallou',
    'ville': 'Rufisque',
    'telephone': '+221 77 123 45 67',
    'contact_nom': 'Moussa Diop',
    'contact_fonction': 'Directeur',
}


class CatalogueTest(APITestCase):
    """Les tarifs du serveur doivent être ceux des documents officiels."""

    def test_les_tarifs_sont_ceux_du_catalogue_officiel(self):
        """Catalogue 2026-2027 et Annexe A HG-COM-006-V01 concordent."""
        for licence, attendu in (('BASIC', 25000), ('PRO', 50000),
                                 ('AVANCE', 90000), ('TAXAWU_DAARA', 20000)):
            self.assertEqual(tarif_mensuel(licence), Decimal(attendu))

    def test_l_essai_est_gratuit(self):
        self.assertEqual(tarif_mensuel('ESSAI'), Decimal('0'))

    @override_settings(REMISE_ANNUELLE='0.10')
    def test_le_chiffrage_montre_comment_on_arrive_au_montant(self):
        """Un total seul, c'est un prix à croire."""
        c = chiffrer('PRO', 'ANNUEL', 12)
        self.assertEqual(c['montant_brut'], 600000)
        self.assertEqual(c['montant_remise'], 60000)
        self.assertEqual(c['montant_net'], 540000)

    @override_settings(REMISE_ANNUELLE='0.10')
    def test_le_paiement_mensuel_n_est_pas_remise(self):
        self.assertEqual(chiffrer('PRO', 'MENSUEL', 1)['montant_net'], 50000)
        self.assertEqual(chiffrer('PRO', 'MENSUEL', 1)['montant_remise'], 0)

    @override_settings(REMISE_ANNUELLE='0')
    def test_la_remise_peut_etre_ramenee_aux_tarifs_publies(self):
        """Elle ne figure dans aucun document officiel : la direction doit
        pouvoir s'en tenir à la grille publiée."""
        self.assertEqual(chiffrer('PRO', 'ANNUEL', 12)['montant_net'], 600000)

    def test_une_licence_inconnue_ne_vaut_pas_un_prix_invente(self):
        self.assertEqual(chiffrer('PREMIUM_PLUS', 'ANNUEL', 12)['montant_net'], 0)


class NumerotationTest(APITestCase):

    def setUp(self):
        self.prospect, _ = enregistrer_demande(FICHE)

    def test_la_sequence_demarre_au_dessus_des_devis_etablis_a_la_main(self):
        """HG-DEV-2026-0001 existe déjà : deux pièces ne peuvent pas porter la
        même référence."""
        self.assertTrue(prochain_numero(2026).endswith('-0002'))

    def test_la_sequence_avance_d_un_devis_a_l_autre(self):
        premier = etablir(self.prospect, 'PRO')
        second = etablir(self.prospect, 'PRO')
        self.assertNotEqual(premier.numero, second.numero)
        self.assertTrue(second.numero > premier.numero)

    def test_la_sequence_est_par_annee(self):
        self.assertIn('2027', prochain_numero(2027))


class EtablissementTest(APITestCase):

    def setUp(self):
        self.prospect, _ = enregistrer_demande(FICHE)

    def test_le_devis_recopie_les_coordonnees_plutot_que_de_les_referencer(self):
        """Le client corrige parfois son nom après coup : une pièce déjà remise
        ne doit pas se réécrire toute seule."""
        devis = etablir(self.prospect, 'PRO')
        self.prospect.etablissement = 'Nouveau nom'
        self.prospect.save()
        devis.refresh_from_db()
        self.assertEqual(devis.etablissement, 'Daara Serigne Fallou')

    @override_settings(REMISE_ANNUELLE='0.10')
    def test_les_montants_sont_figes_a_l_etablissement(self):
        """Une révision tarifaire ne doit pas changer un devis déjà remis."""
        devis = etablir(self.prospect, 'PRO', mois=12)
        with override_settings(REMISE_ANNUELLE='0.50'):
            devis.refresh_from_db()
            self.assertEqual(devis.montant_remise, 60000)
            self.assertEqual(devis.montant_net, 540000)

    def test_le_total_additionne_la_licence_et_ce_qu_un_humain_a_saisi(self):
        devis = etablir(self.prospect, 'TAXAWU_DAARA', mois=12,
                        frais_installation=75000, montant_prestations=120000)
        self.assertEqual(devis.montant_net, 216000)          # 240 000 − 10 %
        self.assertEqual(devis.montant_total, 411000)

    def test_un_devis_nait_en_brouillon(self):
        self.assertEqual(etablir(self.prospect, 'PRO').statut, 'BROUILLON')

    def test_la_validite_est_de_trente_jours(self):
        """« Les devis sont valables trente (30) jours » — catalogue officiel."""
        devis = etablir(self.prospect, 'PRO')
        self.assertEqual(devis.date_validite,
                         devis.date_emission + timedelta(days=30))

    def test_le_devis_fait_avancer_la_fiche_et_laisse_une_trace(self):
        etablir(self.prospect, 'PRO', auteur='Ousseynou')
        self.prospect.refresh_from_db()
        self.assertEqual(self.prospect.statut, 'DEVIS')
        trace = InteractionProspect.objects.latest('created_at')
        self.assertIn('HG-DEV', trace.resume)
        self.assertIn('540 000 F', trace.resume)

    def test_une_affaire_deja_gagnee_ne_retombe_pas_au_stade_devis(self):
        self.prospect.statut = 'GAGNE'
        self.prospect.save()
        etablir(self.prospect, 'PRO')
        self.prospect.refresh_from_db()
        self.assertEqual(self.prospect.statut, 'GAGNE')


class PdfTest(APITestCase):

    def setUp(self):
        self.prospect, _ = enregistrer_demande(FICHE)

    def test_le_pdf_se_genere(self):
        octets, erreur = rendre_pdf(etablir(self.prospect, 'AVANCE'))
        self.assertIsNone(erreur)
        self.assertTrue(octets.startswith(b'%PDF'))

    def test_le_pdf_ne_promet_pas_les_emplois_du_temps(self):
        """Le catalogue commercial les annonce en licence Avancée. Le devis
        liste ce que le CODE ouvre — c'est lui qui engage à la livraison."""
        from apps.prospects.devis import contexte_pdf

        contexte = contexte_pdf(etablir(self.prospect, 'AVANCE'))
        modules = contexte['modules_gauche'] + contexte['modules_droite']
        texte = ' '.join(f'{nom} {detail}' for nom, detail in modules).lower()
        self.assertNotIn('emploi du temps', texte)
        self.assertIn('ressources humaines', texte)

    def test_les_montants_sont_lisibles_sur_la_piece(self):
        """« 240000 F » sur un document que le client vérifie est une faute."""
        from apps.prospects.devis import contexte_pdf, francs

        self.assertEqual(francs(240000), '240 000 F')
        contexte = contexte_pdf(etablir(self.prospect, 'TAXAWU_DAARA', mois=12))
        self.assertEqual(contexte['montants']['brut'], '240 000 F')


class ApiDevisTest(APITestCase):
    """Le parcours complet, et la barrière de validation humaine."""

    def setUp(self):
        self.tenant = Tenant.objects.create(nom='École Test',
                                            code_etablissement='TEST')
        self.super_admin = User.objects.create_user(
            email='super@hadygesman.com', password='x', nom='Super',
            role='SUPER_ADMIN')
        self.admin_ecole = User.objects.create_user(
            email='dir@ecole.sn', password='x', nom='Dir',
            role='ADMIN_ECOLE', tenant=self.tenant)
        self.prospect, _ = enregistrer_demande(FICHE)
        self.client.force_authenticate(self.super_admin)

    def _creer(self, **surcharges):
        charge = {'prospect': str(self.prospect.id), 'type_licence': 'PRO',
                  'cycle': 'ANNUEL', 'mois': 12, **surcharges}
        return self.client.post('/api/devis/', charge, format='json')

    def test_un_admin_d_ecole_ne_voit_pas_les_devis(self):
        self.client.force_authenticate(self.admin_ecole)
        self.assertEqual(self.client.get('/api/devis/').status_code, 403)

    def test_etablir_un_devis_depuis_une_fiche(self):
        r = self._creer()
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data['statut'], 'BROUILLON')
        self.assertEqual(r.data['montant_total'], 540000)
        self.assertIn('HG-DEV', r.data['numero'])

    def test_une_licence_hors_catalogue_est_refusee(self):
        """Sans quoi le devis porterait un montant de zéro sans le dire."""
        r = self._creer(type_licence='PREMIUM_PLUS')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Devis.objects.exists())

    def test_une_duree_absurde_est_refusee(self):
        self.assertEqual(self._creer(mois=600).status_code, 400)

    def test_aucun_chemin_ne_mene_du_brouillon_a_l_envoi(self):
        """C'est l'arbitrage de la direction, appliqué par une transition et
        non par une consigne."""
        devis = self._creer().data
        r = self.client.post(f"/api/devis/{devis['id']}/envoyer/")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(Devis.objects.get().statut, 'BROUILLON')

    def test_le_parcours_complet_valider_envoyer_accepter(self):
        devis = self._creer().data
        chemin = f"/api/devis/{devis['id']}/"

        valide = self.client.post(chemin + 'valider/').data
        self.assertEqual(valide['statut'], 'VALIDE')
        self.assertEqual(valide['valide_par'], str(self.super_admin))
        self.assertIsNotNone(valide['valide_le'])

        envoye = self.client.post(chemin + 'envoyer/').data
        self.assertEqual(envoye['statut'], 'ENVOYE')

        tranche = self.client.post(chemin + 'trancher/',
                                   {'reponse': 'ACCEPTE'}, format='json').data
        self.assertEqual(tranche['statut'], 'ACCEPTE')

    def test_un_devis_accepte_ne_fait_pas_du_prospect_un_client(self):
        """L'école existe le jour où sa licence est créée, pas avant."""
        devis = self._creer().data
        chemin = f"/api/devis/{devis['id']}/"
        self.client.post(chemin + 'valider/')
        self.client.post(chemin + 'envoyer/')
        self.client.post(chemin + 'trancher/', {'reponse': 'ACCEPTE'},
                         format='json')
        self.prospect.refresh_from_db()
        self.assertEqual(self.prospect.statut, 'DEVIS')

    def test_un_devis_valide_ne_se_modifie_plus(self):
        """Deux versions d'une même référence, dont l'une est chez le client."""
        devis = self._creer().data
        self.client.post(f"/api/devis/{devis['id']}/valider/")
        r = self.client.patch(f"/api/devis/{devis['id']}/",
                              {'observations': 'Ajout après coup'}, format='json')
        self.assertEqual(r.status_code, 409)

    def test_les_montants_de_la_licence_ne_sont_pas_retouchables(self):
        """Les rendre modifiables rouvrirait la porte au tarif inventé."""
        devis = self._creer().data
        self.client.patch(f"/api/devis/{devis['id']}/",
                          {'montant_net': 1, 'prix_mensuel': 1,
                           'observations': 'ok'}, format='json')
        enregistre = Devis.objects.get()
        self.assertEqual(enregistre.montant_net, 540000)
        self.assertEqual(enregistre.prix_mensuel, 50000)
        self.assertEqual(enregistre.observations, 'ok')

    def test_un_devis_expire_ne_part_pas(self):
        devis = self._creer().data
        self.client.post(f"/api/devis/{devis['id']}/valider/")
        Devis.objects.update(date_validite=date.today() - timedelta(days=1))
        r = self.client.post(f"/api/devis/{devis['id']}/envoyer/")
        self.assertEqual(r.status_code, 409)
        self.assertIn('trente jours', r.data['error'])

    def test_un_devis_envoye_ne_se_supprime_pas(self):
        devis = self._creer().data
        self.client.post(f"/api/devis/{devis['id']}/valider/")
        self.client.post(f"/api/devis/{devis['id']}/envoyer/")
        self.assertEqual(
            self.client.delete(f"/api/devis/{devis['id']}/").status_code, 409)

    def test_un_brouillon_se_supprime(self):
        devis = self._creer().data
        self.assertEqual(
            self.client.delete(f"/api/devis/{devis['id']}/").status_code, 204)
        self.assertFalse(Devis.objects.exists())

    def test_le_pdf_d_un_brouillon_s_annonce_comme_tel(self):
        """Un brouillon qui fuit doit ressembler à un brouillon."""
        devis = self._creer().data
        r = self.client.get(f"/api/devis/{devis['id']}/pdf/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')
        self.assertIn('BROUILLON', r['Content-Disposition'])

        self.client.post(f"/api/devis/{devis['id']}/valider/")
        valide = self.client.get(f"/api/devis/{devis['id']}/pdf/")
        self.assertNotIn('BROUILLON', valide['Content-Disposition'])

    def test_chaque_etape_laisse_une_trace_dans_l_historique(self):
        devis = self._creer().data
        self.client.post(f"/api/devis/{devis['id']}/valider/")
        self.client.post(f"/api/devis/{devis['id']}/envoyer/")
        resumes = ' '.join(InteractionProspect.objects.values_list('resume', flat=True))
        self.assertIn('établi', resumes)
        self.assertIn('validé', resumes)
        self.assertIn('envoyé', resumes)

    def test_la_fiche_prospect_montre_ses_devis(self):
        self._creer()
        fiche = self.client.get(f'/api/prospects/{self.prospect.id}/').data
        self.assertEqual(len(fiche['devis']), 1)
        self.assertEqual(fiche['devis'][0]['statut'], 'BROUILLON')


class CatalogueApiTest(APITestCase):
    """Le frontend lit la grille au lieu de la recopier."""

    def setUp(self):
        self.tenant = Tenant.objects.create(nom='École Test',
                                            code_etablissement='TEST')
        self.user = User.objects.create_user(
            email='dir@ecole.sn', password='x', nom='Dir',
            role='ADMIN_ECOLE', tenant=self.tenant)

    def test_le_catalogue_sert_les_memes_tarifs_que_les_devis(self):
        """Deux sources finissent toujours par diverger — et ici la divergence
        se verrait sur une pièce signée."""
        self.client.force_authenticate(self.user)
        catalogue = self.client.get('/api/licences/catalogue/').data
        prix = {l['code']: l['prix_mensuel'] for l in catalogue['licences']}
        for code, montant in prix.items():
            self.assertEqual(Decimal(montant), tarif_mensuel(code))

    def test_le_catalogue_decrit_les_licences_par_le_code(self):
        self.client.force_authenticate(self.user)
        catalogue = self.client.get('/api/licences/catalogue/').data
        avance = next(l for l in catalogue['licences'] if l['code'] == 'AVANCE')
        noms = [m['nom'] for m in avance['modules']]
        self.assertIn('Ressources humaines', noms)
        self.assertNotIn('Emplois du temps', noms)

    def test_le_catalogue_n_est_pas_public(self):
        self.assertIn(self.client.get('/api/licences/catalogue/').status_code,
                      (401, 403))
