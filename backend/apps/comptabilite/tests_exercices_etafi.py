"""Exercices antérieurs, continuité comptable, ETAFI.

Cas de la démonstration d'octobre 2026 : une école arrive sur SAGI SCHOOL en
cours d'année 2025-2026 ; son exercice 2024-2025 n'est pas régularisé et ses
ETAFI ne sont pas produits. Elle importe la balance de son comptable, produit
les ETAFI 2024-2025, enchaîne sur 2025-2026 par les à-nouveaux, régularise
encore 2024-2025, puis le clôture — sans jamais bloquer l'année courante.

Ce que ces tests rendent impossible :
- un bilan d'ouverture qui ne reprend pas le bilan de clôture précédent ;
- une régularisation de l'année antérieure qui ne se répercute pas ;
- un bilan, un compte de résultat et une liasse qui disent trois résultats ;
- un TFT dont la trésorerie finale n'est pas celle du bilan ;
- un dossier ETAFI incomplet, ou un dossier définitif qu'on peut supprimer.
"""
import datetime
import io
import zipfile
from io import BytesIO

from django.db.models import Sum
from pypdf import PdfReader
from rest_framework.test import APITestCase

from apps.comptabilite.models import JournalEntry
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant
from apps.users.models import User

BALANCE_2024 = [
    ('2441', 'Matériel et mobilier de bureau', 1500000, 0),
    ('2844', 'Amortissements du matériel', 0, 300000),
    ('411', 'Familles', 400000, 0),
    ('521', 'Banque', 900000, 0),
    ('571', 'Caisse', 100000, 0),
    ('401', 'Fournisseurs', 0, 250000),
    ('101', 'Capital', 0, 1000000),
    ('706', 'Scolarité', 0, 5000000),
    ('661', 'Salaires', 2500000, 0),
    ('605', 'Autres achats', 1150000, 0),
]


class Base(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Cours Privés Les Baobabs', code_etablissement='BAO',
                                            ninea='0012345', rccm='SN-DKR-2019-B-1')
        self.user = User.objects.create_user('dir@baobabs.sn', 'x', nom='Directeur', role='ADMIN_ECOLE',
                                             tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.courant = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2025-2026', date_debut=datetime.date(2025, 10, 1),
            date_fin=datetime.date(2026, 9, 30), solde_initial_caisse=50000)

    def creer_anterieur(self):
        r = self.client.post('/api/paiements/exercices/', {
            'annee_scolaire': '2024-2025', 'date_debut': '2024-10-01', 'date_fin': '2025-09-30',
            'solde_initial_caisse': 0, 'solde_initial_banque': 0, 'solde_initial_mobile': 0},
            format='json')
        self.assertEqual(r.status_code, 201, r.content)
        return Exercice.objects.get(id=r.json()['id'])

    def importer(self, exercice, nature='CLOTURE', lignes=BALANCE_2024):
        contenu = 'Compte;Libellé;Débit;Crédit\n' + '\n'.join(
            f'{c};{l};{d};{cr}' for c, l, d, cr in lignes)
        f = io.BytesIO(contenu.encode('utf-8'))
        f.name = 'balance.csv'
        return self.client.post('/api/comptabilite/import-balance/',
                                {'fichier': f, 'exercice_id': str(exercice.id), 'nature': nature},
                                format='multipart')

    def recette_courante(self, montant=200000):
        for compte, d, c in (('571', montant, 0), ('706', 0, montant)):
            JournalEntry.objects.create(tenant=self.tenant, exercice=self.courant, no_piece='REC-1',
                                        date_ecriture=datetime.date(2025, 11, 5), no_compte=compte,
                                        debit=d, credit=c, libelle='Scolarité', source='PAIEMENT')

    def get(self, url, ex):
        r = self.client.get(url, {'exercice': str(ex.id)})
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()


class ExerciceAnterieurTest(Base):
    def test_chevauchement_refuse(self):
        r = self.client.post('/api/paiements/exercices/', {
            'annee_scolaire': '2025-B', 'date_debut': '2026-01-01', 'date_fin': '2026-12-31',
            'solde_initial_caisse': 0, 'solde_initial_banque': 0, 'solde_initial_mobile': 0}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('chevauche', str(r.content))

    def test_parcours_complet(self):
        ant = self.creer_anterieur()
        r = self.importer(ant)
        self.assertEqual(r.status_code, 201, r.content)

        # ETAFI de l'exercice antérieur, sans rien bloquer.
        bilan = self.get('/api/comptabilite/bilan/', ant)
        self.assertTrue(bilan['equilibre'])
        self.assertEqual(bilan['passif']['capitaux_propres']['resultat_net'], 1350000)
        cr = self.get('/api/comptabilite/compte-resultat/', ant)
        self.assertEqual(cr['resultat_net'], 1350000)
        e = self.get('/api/comptabilite/etafi/', ant)
        refs = {l['ref']: l for l in e['bilan']['actif']}
        self.assertEqual((refs['AM']['brut'], refs['AM']['amort'], refs['AM']['net']),
                         (1500000, 300000, 1200000))
        self.assertTrue(e['bilan']['equilibre'])
        self.assertEqual(e['cr']['resultat'], 1350000)
        self.assertTrue(all(c['ok'] is not False for c in e['controles']), e['controles'])

        # L'année courante continue de tourner.
        self.recette_courante()

        # À-nouveaux 2024-2025 → 2025-2026.
        r = self.client.post('/api/comptabilite/a-nouveaux/', {'source': str(ant.id)}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.json()['provisoire'])
        self.courant.refresh_from_db()
        self.assertEqual((float(self.courant.solde_initial_caisse), float(self.courant.solde_initial_banque)),
                         (100000, 900000))
        b = self.get('/api/comptabilite/bilan/', self.courant)
        self.assertTrue(b['equilibre'])
        self.assertEqual(b['actif']['total_actif'], 2800000)
        self.assertEqual(b['passif']['capitaux_propres']['resultat_net'], 200000)
        etafi_c = self.get('/api/comptabilite/etafi/', self.courant)
        p = {l['ref']: l['net'] for l in etafi_c['bilan']['passif']}
        self.assertEqual((p['CA'], p['CH'], p['CJ'], p['DJ']), (1000000, 1350000, 200000, 250000))
        # La colonne N-1 de la liasse courante = la clôture 2024-2025.
        a = {l['ref']: l for l in etafi_c['bilan']['actif']}
        self.assertEqual(a['AM']['net_n1'], 1200000)
        # Journal courant équilibré malgré l'ouverture.
        agg = JournalEntry.objects.filter(exercice=self.courant).aggregate(d=Sum('debit'), c=Sum('credit'))
        self.assertEqual(agg['d'], agg['c'])
        # TFT : trésorerie d'ouverture = clôture précédente, sans écart.
        tft = self.get('/api/comptabilite/tableau-flux/', self.courant)
        self.assertEqual((tft['tresorerie']['tn_debut'], tft['tresorerie']['tn_fin'],
                          tft['tresorerie']['ecart']), (1000000, 1200000, 0))

        # Régularisation de 2024-2025 : une facture oubliée.
        r = self.client.post('/api/comptabilite/ecritures-diverses/', {
            'exercice_id': str(ant.id), 'date': '2025-09-30', 'libelle': 'Facture électricité oubliée',
            'lignes': [{'no_compte': '6052', 'debit': 100000}, {'no_compte': '401', 'credit': 100000}]},
            format='json')
        self.assertEqual(r.status_code, 201, r.content)
        sit = {x['annee_scolaire']: x for x in self.client.get('/api/comptabilite/exercices-situation/').json()['exercices']}
        self.assertTrue(sit['2024-2025']['anterieur_ouvert'])
        self.assertFalse(sit['2025-2026']['continuite_ok'])            # à régénérer

        # Clôture de l'antérieur : aucun exercice créé, à-nouveaux régénérés.
        nb = Exercice.objects.filter(tenant=self.tenant).count()
        r = self.client.post('/api/paiements/cloturer-exercice/', {
            'exercice_id': str(ant.id), 'confirme': True, 'a_nouveaux': True}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(Exercice.objects.filter(tenant=self.tenant).count(), nb)
        ant.refresh_from_db()
        self.assertTrue(ant.cloture)
        sit = {x['annee_scolaire']: x for x in self.client.get('/api/comptabilite/exercices-situation/').json()['exercices']}
        self.assertTrue(sit['2025-2026']['continuite_ok'])
        p = {l['ref']: l['net'] for l in self.get('/api/comptabilite/etafi/', self.courant)['bilan']['passif']}
        self.assertEqual((p['CH'], p['DJ']), (1250000, 350000))

        # Exercice clôturé : lecture seule.
        r = self.client.post('/api/comptabilite/ecritures-diverses/', {
            'exercice_id': str(ant.id), 'date': '2025-09-30', 'libelle': 'x',
            'lignes': [{'no_compte': '605', 'debit': 1}, {'no_compte': '401', 'credit': 1}]}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_ecriture_desequilibree_refusee(self):
        r = self.client.post('/api/comptabilite/ecritures-diverses/', {
            'date': '2025-12-01', 'libelle': 'x',
            'lignes': [{'no_compte': '605', 'debit': 100}, {'no_compte': '401', 'credit': 90}]}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('déséquilibrée', r.json()['error'])

    def test_balance_d_ouverture_alimente_les_soldes_initiaux(self):
        r = self.importer(self.courant, 'OUVERTURE', [
            ('2441', '', 800000, 0), ('521', '', 300000, 0), ('571', '', 20000, 0), ('101', '', 0, 1120000)])
        self.assertEqual(r.status_code, 201, r.content)
        self.courant.refresh_from_db()
        self.assertEqual((float(self.courant.solde_initial_banque), float(self.courant.solde_initial_caisse)),
                         (300000, 20000))
        b = self.get('/api/comptabilite/bilan/', self.courant)
        self.assertTrue(b['equilibre'])
        self.assertEqual(b['actif']['total_actif'], 1120000)
        # Une balance d'ouverture ne contient pas de charges.
        r = self.importer(self.courant, 'OUVERTURE', [('605', '', 10, 0), ('101', '', 0, 10)])
        self.assertEqual(r.status_code, 400)


class BilanResultatCoherenceTest(Base):
    def test_le_890_n_est_plus_un_resultat_au_bilan(self):
        # Impayé reporté : 411 D / 890 C (à-nouveau), puis une recette.
        for compte, d, c in (('411', 100000, 0), ('890', 0, 100000)):
            JournalEntry.objects.create(tenant=self.tenant, exercice=self.courant, no_piece='REP-1',
                                        date_ecriture=self.courant.date_debut, no_compte=compte, debit=d,
                                        credit=c, libelle='Reliquat', source='REPORT_RELIQUAT')
        self.recette_courante(300000)
        b = self.get('/api/comptabilite/bilan/', self.courant)
        cr = self.get('/api/comptabilite/compte-resultat/', self.courant)
        e = self.get('/api/comptabilite/etafi/', self.courant)
        self.assertEqual(b['passif']['capitaux_propres']['resultat_net'], cr['resultat_net'])
        self.assertEqual(e['cr']['resultat'], cr['resultat_net'])
        self.assertEqual(e['bilan']['resultat'], cr['resultat_net'])
        self.assertTrue(b['equilibre'])
        self.assertTrue(e['bilan']['equilibre'])
        # Capitaux d'ouverture : caisse initiale + impayé reporté.
        self.assertEqual(b['passif']['capitaux_propres']['capital'], 150000)


class DossierEtafiTest(Base):
    def test_documents_zip_archive(self):
        ant = self.creer_anterieur()
        self.importer(ant)
        # Document seul
        r = self.client.get('/api/comptabilite/etafi/document/bilan_actif/', {'exercice': str(ant.id),
                                                                                'systeme': 'SN'})
        self.assertEqual(r.status_code, 200)
        texte = PdfReader(BytesIO(r.content)).pages[0].extract_text()
        self.assertIn('1 200 000', texte)
        self.assertIn('PROVISOIRE', texte)
        # Dossier complet archivé
        r = self.client.post('/api/comptabilite/etafi/archiver/', {'exercice_id': str(ant.id),
                                                                    'systeme': 'SN'}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        meta = r.json()
        self.assertEqual((meta['version'], meta['statut']), (1, 'PROVISOIRE'))
        self.assertTrue(meta['resume']['controles_ok'])
        z = self.client.get(f"/api/comptabilite/etafi/archives/{meta['id']}/")
        self.assertEqual(z.status_code, 200)
        noms = zipfile.ZipFile(BytesIO(z.content)).namelist()
        for attendu in ('03_bilan_actif.pdf', '05_compte_de_resultat.pdf', '06_tableau_des_flux.pdf',
                        '07_notes_annexes.pdf', 'liasse_complete.pdf', 'balance_generale.csv', 'controles.json'):
            self.assertTrue(any(n.endswith(attendu) for n in noms), (attendu, noms))
        liasse = next(n for n in noms if n.endswith('liasse_complete.pdf'))
        self.assertGreaterEqual(len(PdfReader(BytesIO(zipfile.ZipFile(BytesIO(z.content)).read(liasse))).pages), 10)
        # Version provisoire supprimable ; définitive non.
        self.assertEqual(self.client.delete(f"/api/comptabilite/etafi/archives/{meta['id']}/").status_code, 204)
        ant.cloture = True
        ant.save()
        meta = self.client.post('/api/comptabilite/etafi/archiver/', {'exercice_id': str(ant.id)},
                                format='json').json()
        self.assertEqual(meta['statut'], 'DEFINITIF')
        self.assertEqual(self.client.delete(f"/api/comptabilite/etafi/archives/{meta['id']}/").status_code, 409)

    def test_systeme_minimal(self):
        self.recette_courante(1000000)
        e = self.get('/api/comptabilite/etafi/', self.courant)
        self.assertEqual(e['systeme_conseille'], 'SMT')
        codes = [d['code'] for d in e['documents']]
        self.assertIn('tresorerie_smt', codes)
        r = self.client.get('/api/comptabilite/etafi/document/resultat_smt/', {'exercice': str(self.courant.id)})
        self.assertEqual(r.status_code, 200)
        self.assertIn('1 000 000', PdfReader(BytesIO(r.content)).pages[0].extract_text())
