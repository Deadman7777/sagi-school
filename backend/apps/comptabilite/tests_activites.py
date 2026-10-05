"""Comptabilité multi-activité.

Cas réel (démonstration d'octobre 2026) : une école loue ses bus à des clients
extérieurs, sans lien avec le ramassage des élèves. Recettes et dépenses du
transport doivent se lire à part, sans sortir de la comptabilité générale.

Ce que ces tests rendent impossible :
- une facture validée qui n'alimente pas le grand livre (ou le déséquilibre) ;
- une activité dont le résultat ne se retrouve pas dans le résultat de
  l'exercice (la somme des activités = le compte de résultat, au franc près) ;
- une école qui voit les activités ou les factures d'une autre ;
- deux écoles qui se disputent le numéro FA-0001.
"""
import datetime
from io import BytesIO

from django.db.models import Sum
from pypdf import PdfReader
from rest_framework.test import APITestCase

from apps.comptabilite.models import Activite, FactureActivite, JournalEntry
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant
from apps.users.models import User


class Base(APITestCase):
    def ecole(self, nom):
        tenant = Tenant.objects.create(nom=nom, code_etablissement=nom[:3].upper(), ninea='123', rccm='SN')
        user = User.objects.create_user(f'dir@{nom.lower().replace(" ", "")}.sn', 'x', nom='Dir',
                                        role='ADMIN_ECOLE', tenant=tenant)
        ex = Exercice.objects.create(tenant=tenant, annee_scolaire='2025-2026',
                                     date_debut=datetime.date(2025, 10, 1),
                                     date_fin=datetime.date(2026, 9, 30))
        return tenant, user, ex

    def setUp(self):
        self.tenant, self.user, self.ex = self.ecole('Les Pédagogues')
        self.client.force_authenticate(self.user)
        r = self.client.post('/api/comptabilite/activites/', {
            'code': 'TRANSPORT', 'libelle': 'Transport', 'type_activite': 'TRANSPORT',
            'compte_produit': '7062', 'compte_charge': '618', 'regime_tva': 'TAXABLE'},
            format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.transport = Activite.objects.get(id=r.json()['id'])

    def facture(self, lignes=None, **champs):
        corps = {'activite': str(self.transport.id), 'date_facture': '2026-03-10',
                 'client_nom': 'Agence Teranga Voyages',
                 'lignes': lignes or [{'libelle': 'Location bus 30 places — 2 jours',
                                       'quantite': 2, 'prix_unitaire': 75000}], **champs}
        r = self.client.post('/api/comptabilite/factures-activite/', corps, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()

    def solde(self, compte, **filtres):
        agg = JournalEntry.objects.filter(tenant=self.tenant, no_compte=compte, **filtres) \
            .aggregate(d=Sum('debit'), c=Sum('credit'))
        return float(agg['d'] or 0) - float(agg['c'] or 0)


class FactureActiviteTest(Base):
    def test_facture_taxable_comptabilisee(self):
        f = self.facture()
        self.assertEqual((f['montant_ht'], f['montant_tva'], f['montant_ttc']),
                         ('150000.00', '27000.00', '177000.00'))
        self.assertEqual(JournalEntry.objects.filter(tenant=self.tenant).count(), 0)  # brouillon
        r = self.client.post(f"/api/comptabilite/factures-activite/{f['id']}/valider/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['numero'], 'FA-0001')
        self.assertEqual(self.solde('4111'), 177000)
        self.assertEqual(self.solde('7062'), -150000)
        self.assertEqual(self.solde('4432'), -27000)
        # Toutes les lignes portent l'activité.
        self.assertFalse(JournalEntry.objects.filter(tenant=self.tenant, activite__isnull=True).exists())

    def test_reglement_par_cheque_puis_impaye(self):
        f = self.facture()
        self.client.post(f"/api/comptabilite/factures-activite/{f['id']}/valider/")
        r = self.client.post(f"/api/comptabilite/factures-activite/{f['id']}/regler/",
                             {'montant': 100000, 'mode': 'CHEQUE', 'reference': 'CHQ 0045871',
                              'date': '2026-03-20'}, format='json').json()
        self.assertEqual(r['statut'], 'PARTIEL')
        self.assertEqual(self.solde('4111'), 77000)
        self.assertEqual(self.solde('521'), 100000)
        # Trop-perçu refusé.
        r2 = self.client.post(f"/api/comptabilite/factures-activite/{f['id']}/regler/",
                              {'montant': 90000}, format='json')
        self.assertEqual(r2.status_code, 400)
        # Le chèque revient impayé : extourne.
        reg_id = r['reglements'][0]['id']
        r3 = self.client.post(f'/api/comptabilite/factures-activite/reglements/{reg_id}/annuler/').json()
        self.assertEqual(r3['statut'], 'VALIDEE')
        self.assertEqual(self.solde('4111'), 177000)
        self.assertEqual(self.solde('521'), 0)

    def test_facture_validee_ne_se_modifie_pas_et_s_annule_par_extourne(self):
        f = self.facture()
        self.client.post(f"/api/comptabilite/factures-activite/{f['id']}/valider/")
        r = self.client.patch(f"/api/comptabilite/factures-activite/{f['id']}/",
                              {'client_nom': 'Autre'}, format='json')
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.client.delete(f"/api/comptabilite/factures-activite/{f['id']}/").status_code, 409)
        r = self.client.post(f"/api/comptabilite/factures-activite/{f['id']}/annuler/",
                             {'motif': 'Erreur de client'}, format='json')
        self.assertEqual(r.json()['statut'], 'ANNULEE')
        for compte in ('4111', '7062', '4432'):
            self.assertEqual(self.solde(compte), 0)

    def test_activite_exoneree_sans_tva(self):
        cantine = Activite.objects.create(tenant=self.tenant, code='RESTO', libelle='Restauration',
                                          compte_produit='7061', regime_tva='EXONERE')
        f = self.facture(activite=str(cantine.id))
        self.assertEqual(f['montant_tva'], '0.00')
        self.assertEqual(f['montant_ttc'], '150000.00')

    def test_pdf(self):
        f = self.facture()
        self.client.post(f"/api/comptabilite/factures-activite/{f['id']}/valider/")
        r = self.client.get(f"/api/comptabilite/factures-activite/{f['id']}/pdf/")
        self.assertEqual(r.status_code, 200)
        texte = PdfReader(BytesIO(r.content)).pages[0].extract_text()
        self.assertIn('FA-0001', texte)
        self.assertIn('177 000', texte)
        self.assertIn('Agence Teranga Voyages', texte)


class ResultatParActiviteTest(Base):
    def test_somme_des_activites_egale_le_resultat_de_l_exercice(self):
        # Scolarité (activité principale, écriture non marquée, comme un reçu)
        JournalEntry.objects.create(tenant=self.tenant, exercice=self.ex, no_piece='P1',
                                    date_ecriture=datetime.date(2026, 1, 5), no_compte='571',
                                    debit=500000, libelle='Scolarité')
        JournalEntry.objects.create(tenant=self.tenant, exercice=self.ex, no_piece='P1',
                                    date_ecriture=datetime.date(2026, 1, 5), no_compte='706',
                                    credit=500000, libelle='Scolarité')
        f = self.facture()
        self.client.post(f"/api/comptabilite/factures-activite/{f['id']}/valider/")
        # Carburant du bus : charge affectée au transport (compte par défaut 618).
        r = self.client.post('/api/comptabilite/charges/', {
            'montant': 40000, 'libelle': 'Gasoil bus', 'activite_id': str(self.transport.id),
            'date': '2026-03-11'}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(self.solde('618'), 40000)
        # Salaire enseignant, non affecté.
        self.client.post('/api/comptabilite/charges/', {
            'montant': 200000, 'no_compte': '661', 'libelle': 'Salaire', 'date': '2026-03-30'},
            format='json')

        res = self.client.get('/api/comptabilite/activites-resultats/').json()
        par = {a['code']: a for a in res['activites']}
        self.assertEqual((par['TRANSPORT']['produits'], par['TRANSPORT']['charges'],
                          par['TRANSPORT']['resultat']), (150000, 40000, 110000))
        self.assertEqual(par['ENSEIGNEMENT']['resultat'], 300000)
        self.assertEqual(par['TRANSPORT']['creances'], 177000)
        self.assertEqual(res['total_resultat'], res['resultat_exercice'])
        cr = self.client.get('/api/comptabilite/compte-resultat/').json()
        self.assertEqual(res['total_resultat'], cr['resultat_net'])


class CloisonnementTest(Base):
    def test_une_ecole_ne_voit_pas_les_activites_d_une_autre(self):
        f = self.facture()
        self.client.post(f"/api/comptabilite/factures-activite/{f['id']}/valider/")
        autre, user2, _ = self.ecole('École Voisine')
        self.client.force_authenticate(user2)
        codes = [a['code'] for a in self.client.get('/api/comptabilite/activites/').json()['results']]
        self.assertEqual(codes, ['ENSEIGNEMENT'])
        self.assertEqual(self.client.get(f"/api/comptabilite/factures-activite/{f['id']}/").status_code, 404)
        # Facturer avec l'activité d'une autre école : refusé.
        r = self.client.post('/api/comptabilite/factures-activite/', {
            'activite': str(self.transport.id), 'date_facture': '2026-03-10', 'client_nom': 'X',
            'lignes': [{'libelle': 'a', 'quantite': 1, 'prix_unitaire': 10}]}, format='json')
        self.assertEqual(r.status_code, 400)
        # Numérotation propre à chaque école.
        mien = Activite.objects.create(tenant=autre, code='TR', libelle='Transport',
                                       compte_produit='7062')
        r = self.client.post('/api/comptabilite/factures-activite/', {
            'activite': str(mien.id), 'date_facture': '2026-03-10', 'client_nom': 'Y',
            'lignes': [{'libelle': 'a', 'quantite': 1, 'prix_unitaire': 10}]}, format='json').json()
        v = self.client.post(f"/api/comptabilite/factures-activite/{r['id']}/valider/").json()
        self.assertEqual(v['numero'], 'FA-0001')
