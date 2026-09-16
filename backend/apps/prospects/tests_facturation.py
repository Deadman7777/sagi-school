"""Facturation commerciale de HADY GESMAN.

Ce que ces tests rendent impossible :
- **un trou ou un doublon dans la numérotation** — un numéro n'existe qu'à l'émission ;
- **une pièce émise qui change** — la correction passe par un avoir ;
- **un montant que personne ne sait refaire** — HT, TVA arrondie au franc, TTC ;
- **encaisser plus que dû**, ou corriger plus que facturé.
"""
import datetime
import io
from decimal import Decimal

from django.template.loader import render_to_string
from django.test import TestCase, override_settings
from rest_framework.test import APITestCase

from apps.licences.models import Licence
from apps.prospects import facturation as F
from apps.prospects.devis import etablir
from apps.prospects.models import (DocumentCommercial, Encaissement, InteractionProspect,
                                   ParametresFacturation, Prospect)
from apps.tenants.models import Tenant
from apps.users.models import User


def _lignes(*paires):
    return [{'designation': d, 'quantite': q, 'prix_unitaire': p} for d, q, p in paires]


class CalculEtNumerotationTest(TestCase):
    def setUp(self):
        self.prospect = Prospect.objects.create(etablissement='Daara Serigne Fallou', ville='Rufisque',
                                                contact_nom='Moussa Diop', telephone='771234567')

    def _facture(self, *paires, type_doc='FACTURE'):
        return F.creer_brouillon(type_doc, prospect=self.prospect,
                                 lignes=_lignes(*(paires or [('Licence Pro', 12, 50000)])))

    def test_totaux_avec_tva_18(self):
        d = self._facture(('Licence Pro', 12, 50000), ('Remise annuelle', 1, -60000))
        self.assertEqual(d.total_ht, 540000)
        self.assertEqual(d.montant_tva, 97200)
        self.assertEqual(d.total_ttc, 637200)

    def test_tva_arrondie_au_franc(self):
        d = self._facture(('Prestation', 1, 33333))
        self.assertEqual(d.montant_tva, 6000)          # 5 999,94 → 6 000
        self.assertEqual(d.total_ttc, 39333)

    def test_sans_tva_regime_cgu(self):
        p = ParametresFacturation.actuels()
        p.tva_applicable = False
        p.save()
        d = self._facture()
        self.assertEqual(d.montant_tva, 0)
        self.assertEqual(d.total_ttc, 600000)
        self.assertIn('Contribution globale unique', d.mention_tva)

    def test_le_brouillon_n_a_pas_de_numero(self):
        self.assertEqual(self._facture().numero, '')

    def test_numerotation_continue_malgre_un_brouillon_supprime(self):
        a = F.emettre(self._facture())
        self._facture().delete()
        b = F.emettre(self._facture())
        annee = datetime.date.today().year
        self.assertEqual(a.numero, f'HG-FAC-{annee}-0001')
        self.assertEqual(b.numero, f'HG-FAC-{annee}-0002')

    def test_une_sequence_par_type(self):
        F.emettre(self._facture())
        pro = F.emettre(self._facture(type_doc='PROFORMA'))
        self.assertTrue(pro.numero.startswith('HG-PRO-'))
        self.assertTrue(pro.numero.endswith('-0001'))

    def test_emission_fixe_echeance_et_validite(self):
        f = F.emettre(self._facture())
        p = F.emettre(self._facture(type_doc='PROFORMA'))
        self.assertEqual(f.date_echeance, datetime.date.today() + datetime.timedelta(days=30))
        self.assertEqual(p.date_validite, datetime.date.today() + datetime.timedelta(days=30))

    def test_piece_emise_non_modifiable(self):
        f = F.emettre(self._facture())
        with self.assertRaises(F.FacturationErreur):
            F.remplacer_lignes(f, _lignes(('Autre', 1, 1)))

    def test_emission_refusee_sans_ligne(self):
        d = F.creer_brouillon('FACTURE', prospect=self.prospect)
        with self.assertRaisesMessage(F.FacturationErreur, 'au moins une ligne'):
            F.emettre(d)

    def test_la_tva_changee_apres_coup_ne_touche_pas_une_piece_emise(self):
        f = F.emettre(self._facture())
        p = ParametresFacturation.actuels()
        p.tva_applicable = False
        p.save()
        f.refresh_from_db()
        self.assertEqual(f.total_ttc, 708000)

    def test_trace_dans_l_historique_du_prospect(self):
        f = F.emettre(self._facture())
        self.assertTrue(InteractionProspect.objects.filter(
            prospect=self.prospect, resume__contains=f.numero).exists())

    def test_montant_en_lettres(self):
        self.assertEqual(F.montant_en_lettres(637200),
                         'six cent trente-sept mille deux cents francs CFA')
        self.assertEqual(F.montant_en_lettres(1000000), 'un million de francs CFA')
        self.assertEqual(F.montant_en_lettres(280000), 'deux cent quatre-vingt mille francs CFA')


class EncaissementsEtAvoirsTest(TestCase):
    def setUp(self):
        prospect = Prospect.objects.create(etablissement='École Al Falah')
        self.facture = F.emettre(F.creer_brouillon(
            'FACTURE', prospect=prospect, lignes=_lignes(('Licence Basic', 12, 25000))))  # 354 000 TTC

    def test_paiement_partiel_puis_solde(self):
        self.assertEqual(self.facture.statut_paiement, 'A_PAYER')
        r1 = F.encaisser(self.facture, 154000, mode='WAVE')
        self.assertEqual(self.facture.statut_paiement, 'PARTIELLE')
        self.assertEqual(self.facture.solde, 200000)
        r2 = F.encaisser(self.facture, 200000)
        self.assertEqual(self.facture.statut_paiement, 'PAYEE')
        annee = datetime.date.today().year
        self.assertEqual((r1.numero, r2.numero), (f'HG-REC-{annee}-0001', f'HG-REC-{annee}-0002'))

    def test_on_n_encaisse_pas_plus_que_du(self):
        with self.assertRaisesMessage(F.FacturationErreur, 'reste à payer'):
            F.encaisser(self.facture, 354001)

    def test_pas_d_encaissement_sur_proforma_ou_brouillon(self):
        brouillon = F.creer_brouillon('FACTURE', client={'client_nom': 'X'},
                                      lignes=_lignes(('A', 1, 1000)))
        with self.assertRaises(F.FacturationErreur):
            F.encaisser(brouillon, 100)

    def test_annuler_un_recu_rend_le_montant_du(self):
        r = F.encaisser(self.facture, 354000)
        F.annuler_encaissement(r, 'Chèque rejeté')
        self.assertEqual(self.facture.solde, 354000)
        with self.assertRaises(F.FacturationErreur):
            F.annuler_encaissement(r, 'encore')

    def test_avoir_total_solde_la_facture(self):
        avoir = F.preparer_avoir(self.facture, motif='Erreur de licence')
        self.assertEqual(avoir.total_ttc, 354000)
        F.emettre(avoir)
        self.assertTrue(avoir.numero.startswith('HG-AV-'))
        self.assertEqual(self.facture.solde, 0)
        self.assertEqual(self.facture.statut_paiement, 'PAYEE')

    def test_avoir_partiel_puis_depassement_refuse(self):
        avoir = F.preparer_avoir(self.facture, motif='Geste commercial')
        F.remplacer_lignes(avoir, _lignes(('Geste commercial', 1, 50000)))    # 59 000 TTC
        F.emettre(avoir)
        self.assertEqual(self.facture.solde, 354000 - 59000)
        second = F.preparer_avoir(self.facture, motif='Doublon')             # 354 000 : trop
        with self.assertRaisesMessage(F.FacturationErreur, 'dépasse'):
            F.emettre(second)

    def test_avoir_sans_motif_refuse(self):
        avoir = F.preparer_avoir(self.facture)
        with self.assertRaisesMessage(F.FacturationErreur, 'motif'):
            F.emettre(avoir)

    def test_avoir_garde_la_tva_de_sa_facture(self):
        p = ParametresFacturation.actuels()
        p.tva_applicable = False
        p.save()
        avoir = F.preparer_avoir(self.facture, motif='x')
        self.assertTrue(avoir.tva_applicable)
        self.assertEqual(avoir.total_ttc, 354000)

    def test_facture_en_retard(self):
        self.facture.date_echeance = datetime.date.today() - datetime.timedelta(days=1)
        self.facture.save()
        self.assertTrue(self.facture.en_retard)
        s = F.synthese()
        self.assertEqual((s['nb_en_retard'], s['en_retard'], s['restant']), (1, 354000, 354000))


@override_settings(REMISE_ANNUELLE='0.10')
class DepuisDevisProformaEtLicenceTest(TestCase):
    def setUp(self):
        self.prospect = Prospect.objects.create(etablissement='Daara Touba', ville='Mbacké',
                                                contact_nom='Serigne Mbaye')
        self.devis = etablir(self.prospect, 'PRO', 'ANNUEL', 12, frais_installation=75000)

    def test_facture_refusee_sur_devis_non_accepte(self):
        self.devis.statut = 'ENVOYE'
        self.devis.save()
        with self.assertRaisesMessage(F.FacturationErreur, 'proforma'):
            F.depuis_devis(self.devis, 'FACTURE')
        pro = F.depuis_devis(self.devis, 'PROFORMA')
        self.assertEqual(pro.type, 'PROFORMA')

    def test_facture_reprend_le_devis_avec_la_remise_sur_sa_ligne(self):
        self.devis.statut = 'ACCEPTE'
        self.devis.save()
        f = F.depuis_devis(self.devis, 'FACTURE')
        designations = [l.designation for l in f.lignes.all()]
        self.assertEqual(designations[1], 'Remise paiement annuel (10 %)')
        # HT = total du devis ; la TVA s'ajoute (tarifs HT)
        self.assertEqual(f.total_ht, self.devis.montant_total)
        self.assertEqual(f.total_ht, 540000 + 75000)
        self.assertEqual(f.client_nom, 'Daara Touba')

    def test_proforma_convertie_en_facture(self):
        self.devis.statut = 'VALIDE'
        self.devis.save()
        pro = F.emettre(F.depuis_devis(self.devis, 'PROFORMA'))
        facture = F.convertir_proforma(pro)
        self.assertEqual(facture.total_ttc, pro.total_ttc)
        self.assertEqual(pro.statut, 'EMIS')
        F.emettre(facture)
        pro.refresh_from_db()
        self.assertEqual(pro.statut, 'CONVERTI')
        with self.assertRaises(F.FacturationErreur):
            F.convertir_proforma(pro)

    def test_renouvellement_d_une_ecole_cliente(self):
        tenant = Tenant.objects.create(nom='Groupe Scolaire Shoumoul', ville='Rufisque', ninea='00123')
        fin = datetime.date.today() + datetime.timedelta(days=20)
        Licence.objects.create(tenant=tenant, cle_licence=Licence.generer_cle('SHOUM'), type='AVANCE',
                               statut='ACTIVE', date_debut=fin - datetime.timedelta(days=365), date_fin=fin)
        f = F.creer_brouillon('FACTURE', tenant=tenant, lignes=F.lignes_renouvellement(tenant, 12))
        self.assertEqual(f.client_ninea, '00123')
        self.assertEqual(f.total_ht, 90000 * 12 - 108000)
        debut = fin + datetime.timedelta(days=1)
        self.assertIn(f'du {debut:%d/%m/%Y}', f.lignes.first().detail)

    def test_ecole_en_essai_sans_renouvellement(self):
        tenant = Tenant.objects.create(nom='Essai')
        Licence.objects.create(tenant=tenant, cle_licence=Licence.generer_cle('ESS'), type='ESSAI',
                               statut='ESSAI', date_debut=datetime.date.today(),
                               date_fin=datetime.date.today())
        with self.assertRaises(F.FacturationErreur):
            F.lignes_renouvellement(tenant, 12)


class ApiFacturationTest(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(email='super@hadygesman.com', password='x', nom='Super',
                                              role='SUPER_ADMIN')
        self.client.force_authenticate(self.admin)
        self.prospect = Prospect.objects.create(etablissement='École Les Rosiers', ville='Thiès')

    def _creer(self, **extra):
        data = {'type': 'FACTURE', 'prospect': str(self.prospect.id),
                'lignes': [{'designation': 'Licence Basic', 'quantite': 12, 'unite': 'mois',
                            'prix_unitaire': 25000}]}
        data.update(extra)
        r = self.client.post('/api/facturation/documents/', data, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        return r.data

    def test_cycle_complet_facture_encaissement_pdf(self):
        d = self._creer()
        self.assertEqual((d['total_ht'], d['total_ttc']), (300000, 354000))
        r = self.client.patch(f"/api/facturation/documents/{d['id']}/",
                              {'objet': 'Licence 2026-2027', 'client_ninea': '0045'}, format='json')
        self.assertEqual(r.data['client_ninea'], '0045')
        r = self.client.post(f"/api/facturation/documents/{d['id']}/emettre/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.data['numero'].startswith('HG-FAC-'))
        # figée
        r = self.client.patch(f"/api/facturation/documents/{d['id']}/", {'objet': 'x'}, format='json')
        self.assertEqual(r.status_code, 409)
        r = self.client.delete(f"/api/facturation/documents/{d['id']}/")
        self.assertEqual(r.status_code, 409)
        # paiement
        r = self.client.post(f"/api/facturation/documents/{d['id']}/encaisser/",
                             {'montant': 100000, 'mode': 'WAVE', 'reference': 'TX123'}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data['facture']['statut_paiement'], 'PARTIELLE')
        recu = r.data['recu']
        # PDF facture + reçu
        for url in (f"/api/facturation/documents/{d['id']}/pdf/",
                    f"/api/facturation/encaissements/{recu['id']}/pdf/"):
            p = self.client.get(url)
            self.assertEqual(p.status_code, 200, p.content[:200])
            self.assertTrue(p.content.startswith(b'%PDF'))
        s = self.client.get('/api/facturation/documents/synthese/').data
        self.assertEqual((s['facture'], s['encaisse'], s['restant']), (354000, 100000, 254000))
        impayees = self.client.get('/api/facturation/documents/', {'impayees': 1}).data
        self.assertEqual(len(impayees), 1)

    def test_pdf_brouillon_marque(self):
        d = self._creer(type='PROFORMA')
        r = self.client.get(f"/api/facturation/documents/{d['id']}/pdf/")
        self.assertIn('BROUILLON', r['Content-Disposition'])

    def test_gabarits_sans_balise_residuelle(self):
        d = DocumentCommercial.objects.get(pk=self._creer()['id'])
        F.emettre(d)
        avoir = F.preparer_avoir(d, motif='Erreur')
        recu = F.encaisser(d, 54000)
        for gabarit, ctx in (('pdf/document_commercial.html', F.contexte_document(d)),
                             ('pdf/document_commercial.html', F.contexte_document(avoir)),
                             ('pdf/recu_encaissement.html', F.contexte_recu(recu))):
            html = render_to_string(gabarit, ctx)
            self.assertNotIn('{%', html)
            self.assertNotIn('{#', html)
        html = render_to_string('pdf/document_commercial.html', F.contexte_document(d))
        self.assertIn('trois cent cinquante-quatre mille francs CFA', html)
        self.assertIn('TVA 18 %', html)

    def test_parametres_tva(self):
        r = self.client.patch('/api/facturation/parametres/',
                              {'tva_applicable': False, 'rccm': 'SN-DKR-2024-A-1'}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(r.data['tva_applicable'])
        d = self._creer()
        self.assertEqual(d['total_ttc'], 300000)
        r = self.client.patch('/api/facturation/parametres/', {'taux_tva': 150}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_avoir_via_api(self):
        d = self._creer()
        self.client.post(f"/api/facturation/documents/{d['id']}/emettre/")
        r = self.client.post(f"/api/facturation/documents/{d['id']}/avoir/", {'motif': 'Doublon'},
                             format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data['type'], 'AVOIR')
        self.assertEqual(r.data['origine'], d['id'])
        r = self.client.post('/api/facturation/documents/', {'type': 'AVOIR', 'prospect': str(self.prospect.id)},
                             format='json')
        self.assertEqual(r.status_code, 400)

    def test_reserve_au_super_admin(self):
        tenant = Tenant.objects.create(nom='École')
        self.client.force_authenticate(User.objects.create_user(
            email='dir@ecole.sn', password='x', nom='Dir', role='ADMIN_ECOLE', tenant=tenant))
        for url in ('/api/facturation/documents/', '/api/facturation/parametres/',
                    '/api/facturation/encaissements/'):
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_clients_ecoles(self):
        tenant = Tenant.objects.create(nom='Shoumoul')
        Licence.objects.create(tenant=tenant, cle_licence=Licence.generer_cle('S'), type='PRO',
                               statut='ACTIVE', date_debut=datetime.date(2026, 1, 1),
                               date_fin=datetime.date(2026, 12, 31))
        r = self.client.get('/api/facturation/documents/clients/')
        shoumoul = next(c for c in r.data if c['nom'] == 'Shoumoul')
        self.assertEqual(shoumoul['licence_type'], 'PRO')
        r = self.client.post('/api/facturation/documents/',
                             {'type': 'FACTURE', 'tenant': str(tenant.id), 'renouvellement_mois': 12},
                             format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data['objet'], 'Renouvellement de licence SAGI SCHOOL')


class ReleveEtEtatTest(APITestCase):
    """Relevé de compte d'un client et état de la facturation, en PDF."""

    def setUp(self):
        self.client.force_authenticate(User.objects.create_user(
            email='super@hadygesman.com', password='x', nom='Super', role='SUPER_ADMIN'))
        self.prospect = Prospect.objects.create(etablissement='Daara Touba', ville='Mbacké')
        self.autre = Prospect.objects.create(etablissement='Autre école')
        lignes = _lignes(('Licence Basic', 12, 25000))                       # 354 000 TTC
        self.f1 = F.emettre(F.creer_brouillon('FACTURE', prospect=self.prospect, lignes=lignes))
        self.f2 = F.emettre(F.creer_brouillon('FACTURE', prospect=self.prospect, lignes=lignes))
        F.emettre(F.creer_brouillon('FACTURE', prospect=self.autre, lignes=lignes))
        F.emettre(F.creer_brouillon('PROFORMA', prospect=self.prospect, lignes=lignes))
        F.encaisser(self.f1, 354000)
        F.annuler_encaissement(F.encaisser(self.f2, 100000), 'Chèque rejeté')
        F.encaisser(self.f2, 54000)
        avoir = F.preparer_avoir(self.f2, motif='Geste')
        F.remplacer_lignes(avoir, _lignes(('Geste', 1, 100000)))            # 118 000 TTC
        F.emettre(avoir)

    def test_releve_ne_compte_que_ce_client_ni_proforma_ni_recu_annule(self):
        docs = F.documents_du_client(prospect=self.prospect)
        r = F.releve_compte(docs)
        self.assertEqual(r['total_debit'], 708000)                  # 2 factures, pas la proforma
        self.assertEqual(r['total_credit'], 354000 + 54000 + 118000)  # reçu annulé exclu
        self.assertEqual(r['solde'], 182000)
        self.assertEqual(r['solde'], sum(f.solde for f in docs if f.type == 'FACTURE'))
        self.assertEqual([f.numero for f in r['ouvertes']], [self.f2.numero])
        self.assertEqual(r['mouvements'][-1]['solde'], r['solde'])

    def test_releve_par_nom_pour_un_client_libre(self):
        F.emettre(F.creer_brouillon('FACTURE', client={'client_nom': 'Cabinet Ndiaye'},
                                    lignes=_lignes(('Formation', 1, 50000))))
        r = F.releve_compte(F.documents_du_client(client_nom='cabinet ndiaye'))
        self.assertEqual(r['total_debit'], 59000)

    def test_releve_pdf(self):
        r = self.client.get(f'/api/facturation/documents/{self.f2.id}/releve-pdf/')
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertTrue(r.content.startswith(b'%PDF'))
        self.assertIn('releve-Daara-Touba', r['Content-Disposition'])
        html = render_to_string('pdf/releve_compte_client.html', F.contexte_releve(
            F.documents_du_client(prospect=self.prospect), {'nom': 'Daara Touba'}))
        self.assertNotIn('{%', html)
        self.assertIn('SOLDE RESTANT DÛ', html)
        self.assertIn('182 000 F', html)

    def test_etat_pdf_suit_les_filtres(self):
        ctx = F.contexte_etat([self.f2], 'Factures impayées')
        self.assertEqual(ctx['totaux']['restant'], '182 000 F')
        r = self.client.get('/api/facturation/documents/etat-pdf/', {'impayees': 1})
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertTrue(r.content.startswith(b'%PDF'))
        self.assertIn('attachment', r['Content-Disposition'])
        html = render_to_string('pdf/etat_facturation.html', F.contexte_etat(
            [d for d in DocumentCommercial.objects.all()], 'Toutes les pièces'))
        self.assertNotIn('{%', html)
        # Totaux = synthèse de l'écran : un seul calcul
        s = F.synthese()
        tout = F.contexte_etat(list(DocumentCommercial.objects.all()), '')
        self.assertEqual(tout['totaux']['restant'], F.francs(s['restant']))
        self.assertEqual(tout['totaux']['encaisse'], F.francs(s['encaisse']))
