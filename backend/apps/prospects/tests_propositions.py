"""Propositions commerciales, bibliothèque de documents, envoi.

Ce que ces tests rendent impossible :
- un montant différent de la proposition HG-IDM-2026 remise à l'Internat
  Daroul Mouminati (le modèle) pour les mêmes conditions ;
- une proposition qui part sans avoir été validée, ou qui se réécrit après ;
- un « envoyé » affiché alors que rien n'est parti.
"""
import base64
from datetime import date, timedelta
from io import BytesIO
from unittest import mock

from django.core import mail
from rest_framework.test import APITestCase

from apps.licences.catalogue import formules
from apps.prospects import proposition as PR
from apps.prospects.models import (DocumentBibliotheque, InteractionProspect, Prospect,
                                   PropositionCommerciale)
from apps.users.models import User

PDF = 'data:application/pdf;base64,' + base64.b64encode(b'%PDF-1.4 brochure').decode()
SMTP_OK = mock.patch('apps.prospects.messagerie.smtp_configure', return_value=True)


class ChiffrageTest(APITestCase):
    def test_les_montants_sont_ceux_de_hg_idm_2026(self):
        c = formules(20000, '0.08', '0.10', 100000, 50000)
        self.assertEqual([c['mensuelle']['total'], c['semestrielle']['total'], c['annuelle']['total']],
                         [120000, 210400, 316000])
        self.assertEqual(c['semestrielle']['remise'], 9600)
        self.assertEqual(c['annuelle']['equivalent'], 18000)
        self.assertEqual(c['tranches'], [158000, 158000])
        self.assertEqual([(x['sans_migration'], x['avec_migration'], x['economie'])
                          for x in c['sur_12_mois']],
                         [(340000, 390000, 0), (320800, 370800, 19200), (316000, 366000, 24000)])

    def test_les_tranches_impaires_tombent_juste(self):
        c = formules(25000, '0.08', '0.10', 100001, 0)
        self.assertEqual(sum(c['tranches']), c['annuelle']['total'])

    def test_la_reference_reprend_les_initiales(self):
        self.assertEqual(PR.sigle('Internat Daroul Mouminati'), 'IDM')
        self.assertEqual(PR.sigle("École de l'Avenir"), 'EA')
        self.assertEqual(PR.sigle(''), 'CLI')


class PropositionApiTest(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user('sa@hady.sn', 'x', nom='SA', role='SUPER_ADMIN')
        self.client.force_authenticate(self.admin)
        self.prospect = Prospect.objects.create(
            etablissement='Internat Daroul Mouminati', type_organisation='Daara',
            ville='Keur Massar', telephone='77 656 76 14', email='daroul@gmail.com',
            contact_nom='Oustaz Ndiaye')
        self.brochure = DocumentBibliotheque.objects.create(
            titre='Brochure SAGI SCHOOL', nom_fichier='brochure.pdf', contenu=PDF, taille=17)
        DocumentBibliotheque.objects.create(titre='Ancienne', nom_fichier='a.pdf', contenu=PDF,
                                            joindre_par_defaut=False)

    def _creer(self, licence='TAXAWU_DAARA'):
        r = self.client.post('/api/commercial/propositions/',
                             {'prospect': str(self.prospect.id), 'type_licence': licence},
                             format='json')
        self.assertEqual(r.status_code, 201, r.content)
        return r.data

    def test_etablie_preremplie_depuis_la_fiche(self):
        d = self._creer()
        self.assertEqual(d['reference'], f'HG-IDM-{date.today().year}')
        self.assertEqual(d['statut'], 'BROUILLON')
        self.assertEqual(d['chiffrage']['annuelle']['total'], 316000)
        self.assertIn('apprenants', d['contexte'] + ' '.join(d['besoins']))
        self.assertEqual(d['programme'], 'Programme TAXAWU DAARA')
        self.assertEqual(d['documents_joints'], [str(self.brochure.id)])   # par défaut seulement
        self.prospect.refresh_from_db()
        self.assertEqual(self.prospect.statut, 'DEVIS')
        self.assertTrue(InteractionProspect.objects.filter(prospect=self.prospect).exists())
        # Une seconde la même année : référence distincte.
        self.assertEqual(self._creer('PRO')['reference'], f'HG-IDM-{date.today().year}-2')

    def test_sans_fiche_le_prospect_est_cree_ou_retrouve(self):
        r = self.client.post('/api/commercial/propositions/',
                             {'etablissement': 'École Nouvelle Vague', 'ville': 'Thiès',
                              'telephone': '77 999 88 77', 'type_licence': 'PRO'}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        cree = Prospect.objects.get(etablissement='École Nouvelle Vague')
        self.assertEqual(r.data['prospect'], str(cree.id))
        self.assertEqual(cree.source, 'MANUEL')
        # Même téléphone : la fiche existante est reprise, pas dupliquée.
        r = self.client.post('/api/commercial/propositions/',
                             {'etablissement': 'Ecole Nouvelle Vague', 'telephone': '+221 77 999 88 77',
                              'type_licence': 'BASIC'}, format='json')
        self.assertEqual(r.data['prospect'], str(cree.id))
        self.assertEqual(Prospect.objects.filter(etablissement__icontains='Nouvelle Vague').count(), 1)
        r = self.client.post('/api/commercial/propositions/', {'type_licence': 'PRO'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_l_essai_ne_se_propose_pas(self):
        r = self.client.post('/api/commercial/propositions/',
                             {'prospect': str(self.prospect.id), 'type_licence': 'ESSAI'},
                             format='json')
        self.assertEqual(r.status_code, 400)

    def test_personnalisation_puis_figee_apres_validation(self):
        d = self._creer()
        r = self.client.patch(f"/api/commercial/propositions/{d['id']}/",
                              {'sous_titre': 'Mémorisation du Coran', 'frais_migration': 75000,
                               'besoins': 'Un\n\nDeux', 'type_licence': 'AVANCE'}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data['besoins'], ['Un', 'Deux'])
        self.assertEqual(r.data['prix_mensuel'], 90000)
        self.assertEqual(r.data['chiffrage']['sur_12_mois'][0]['avec_migration'],
                         90000 * 12 + 100000 + 75000)
        self.client.post(f"/api/commercial/propositions/{d['id']}/valider/")
        r = self.client.patch(f"/api/commercial/propositions/{d['id']}/", {'sous_titre': 'x'},
                              format='json')
        self.assertEqual(r.status_code, 400)
        # Rouvrir tant qu'elle n'est pas partie.
        r = self.client.post(f"/api/commercial/propositions/{d['id']}/rouvrir/")
        self.assertEqual(r.data['statut'], 'BROUILLON')

    def test_un_brouillon_ne_part_pas(self):
        d = self._creer()
        with SMTP_OK:
            r = self.client.post(f"/api/commercial/propositions/{d['id']}/envoyer/", {}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(len(mail.outbox), 0)

    def test_envoi_avec_proposition_et_brochures(self):
        d = self._creer()
        self.client.post(f"/api/commercial/propositions/{d['id']}/valider/")
        c = self.client.get(f"/api/commercial/propositions/{d['id']}/courriel/").data
        self.assertEqual(c['destinataires'], 'daroul@gmail.com')
        self.assertIn('Bonjour Oustaz Ndiaye', c['corps'])
        self.assertTrue(c['whatsapp'].startswith('https://wa.me/221776567614?text='))
        with SMTP_OK:
            r = self.client.post(f"/api/commercial/propositions/{d['id']}/envoyer/",
                                 {'destinataires': 'daroul@gmail.com; dir@daroul.sn'}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data['statut'], 'ENVOYEE')
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ['daroul@gmail.com', 'dir@daroul.sn'])
        noms = [a[0] for a in message.attachments]
        self.assertTrue(noms[0].startswith(f"Proposition_HG-IDM-{date.today().year}"))
        self.assertNotIn('BROUILLON', noms[0])
        self.assertEqual(noms[1:], ['brochure.pdf'])
        self.assertTrue(message.attachments[0][1].startswith(b'%PDF'))
        self.assertTrue(InteractionProspect.objects.filter(prospect=self.prospect, canal='EMAIL').exists())

    def test_sans_smtp_rien_n_est_annonce_envoye(self):
        d = self._creer()
        self.client.post(f"/api/commercial/propositions/{d['id']}/valider/")
        with mock.patch('apps.prospects.messagerie.smtp_configure', return_value=False):
            r = self.client.post(f"/api/commercial/propositions/{d['id']}/envoyer/", {}, format='json')
        self.assertEqual(r.status_code, 400)
        p = PropositionCommerciale.objects.get(pk=d['id'])
        self.assertEqual(p.statut, 'VALIDEE')
        self.assertIn('SMTP', p.erreur_envoi)

    def test_reponse_du_client(self):
        d = self._creer()
        self.client.post(f"/api/commercial/propositions/{d['id']}/valider/")
        r = self.client.post(f"/api/commercial/propositions/{d['id']}/repondre/",
                             {'decision': 'ACCEPTEE'}, format='json')
        self.assertEqual(r.status_code, 400)              # la formule est exigée
        r = self.client.post(f"/api/commercial/propositions/{d['id']}/repondre/",
                             {'decision': 'ACCEPTEE', 'formule': 'ANNUELLE_TRANCHES',
                              'migration': True}, format='json')
        self.assertEqual(r.data['statut'], 'ACCEPTEE')
        self.assertTrue(r.data['migration_choisie'])

    def test_dupliquer_une_proposition_envoyee(self):
        d = self._creer()
        self.client.post(f"/api/commercial/propositions/{d['id']}/valider/")
        r = self.client.post(f"/api/commercial/propositions/{d['id']}/dupliquer/")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data['statut'], 'BROUILLON')
        self.assertNotEqual(r.data['reference'], d['reference'])
        self.assertEqual(r.data['documents_joints'], [str(self.brochure.id)])

    def test_le_pdf_a_les_champs_d_acceptation(self):
        from pypdf import PdfReader
        d = self._creer()
        r = self.client.get(f"/api/commercial/propositions/{d['id']}/pdf/")
        self.assertEqual(r.status_code, 200)
        self.assertIn('BROUILLON', r['Content-Disposition'])
        champs = PdfReader(BytesIO(r.content)).get_fields()
        self.assertEqual(set(champs), {'formule', 'migration', 'client_nom', 'client_fonction',
                                       'client_date'})

    def test_seul_hady_gesman_y_accede(self):
        ecole = User.objects.create_user('dir@ecole.sn', 'x', nom='Dir', role='ADMIN_ECOLE')
        self.client.force_authenticate(ecole)
        self.assertEqual(self.client.get('/api/commercial/propositions/').status_code, 403)
        self.assertEqual(self.client.get('/api/commercial/bibliotheque/').status_code, 403)


class BibliothequeTest(APITestCase):
    def setUp(self):
        self.client.force_authenticate(
            User.objects.create_user('sa@hady.sn', 'x', nom='SA', role='SUPER_ADMIN'))

    def test_depot_d_un_pdf_seulement(self):
        r = self.client.post('/api/commercial/bibliotheque/',
                             {'titre': 'Catalogue', 'categorie': 'CATALOGUE',
                              'nom_fichier': 'catalogue.pdf', 'contenu': PDF}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertNotIn('contenu', r.data)
        f = self.client.get(f"/api/commercial/bibliotheque/{r.data['id']}/fichier/")
        self.assertEqual(f.content, b'%PDF-1.4 brochure')
        image = 'data:image/png;base64,' + base64.b64encode(b'png').decode()
        r = self.client.post('/api/commercial/bibliotheque/',
                             {'nom_fichier': 'x.png', 'contenu': image}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_un_document_deja_remis_est_retire_pas_efface(self):
        doc = DocumentBibliotheque.objects.create(titre='B', nom_fichier='b.pdf', contenu=PDF)
        p = PropositionCommerciale.objects.create(reference='HG-X-2026', etablissement='X',
                                                  type_licence='PRO', statut='ENVOYEE')
        p.documents_joints.add(doc)
        self.client.delete(f'/api/commercial/bibliotheque/{doc.id}/')
        doc.refresh_from_db()
        self.assertFalse(doc.actif)
