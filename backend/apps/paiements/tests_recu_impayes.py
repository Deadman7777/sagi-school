"""Reçu de paiement : impayés antérieurs, reçus annulés, format et multi-mode.

Ce que ces tests rendent impossible :
- un reçu sans la ligne « Impayés antérieurs » (« Néant » compris) ;
- un « déjà versé » gonflé par un reçu ANNULÉ (reste à payer faux sur le reçu) ;
- un reçu demandé en A4 qui sort en A5 (seconde règle @page oubliée) ;
- un reçu A5 ordinaire qui déborde sur une deuxième page ;
- un règlement multi-mode rangé sous « MIXTE » au lieu d'être réparti.
"""
from io import BytesIO

from pypdf import PdfReader

from apps.comptabilite.tresorerie import encaissements_par_mode
from apps.paiements.models import Paiement
from apps.paiements.report_reliquats import reporter_reliquats
from apps.eleves.models import Eleve

from .tests_report_reliquats import ReportReliquatsBase


class RecuImpayesAnterieursTest(ReportReliquatsBase):
    def setUp(self):
        super().setUp()
        self._payer(self.eleve, self.ex1, montant_inscription=50000, montant_mensualite=100000)
        self._cloturer(self.ex1)
        reporter_reliquats(self.ex1, self.ex2)
        self.fiche = Eleve.objects.get(exercice=self.ex2)

    def _encaisser(self, **data):
        data = {'eleve': str(self.fiche.id), 'mode_paiement': 'ESPECE', **data}
        r = self.client.post('/api/paiements/paiements/', data, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        return Paiement.objects.get(id=r.data['id'])

    def test_le_recu_porte_les_impayes_anterieurs_restants(self):
        p = self._encaisser(montant_inscription=50000, montant_reliquat=30000)
        r = self.client.get(f'/api/paiements/paiements/{p.id}/recu/')
        self.assertEqual(r.data['reliquat_du'], 150000)
        self.assertEqual(r.data['reliquat_restant_apres'], 120000)
        # Le suivi de l'année n'ajoute que la part « année » du reçu.
        self.assertEqual(r.data['part_exercice'], 50000)
        self.assertEqual(r.data['total_paye_apres'], r.data['deja_paye_avant'] + 50000)

    def test_un_recu_annule_ne_compte_pas_dans_le_deja_verse(self):
        annule = self._encaisser(montant_inscription=20000)
        self.client.post(f'/api/paiements/paiements/{annule.id}/annuler/', {}, format='json')
        p = self._encaisser(montant_inscription=50000)
        r = self.client.get(f'/api/paiements/paiements/{p.id}/recu/')
        self.assertEqual(r.data['deja_paye_avant'], 0)

    def _pdf(self, p, taille):
        r = self.client.get(f'/api/paiements/paiements/{p.id}/recu-pdf/?taille={taille}')
        self.assertEqual(r.status_code, 200)
        return PdfReader(BytesIO(r.content))

    def test_formats_et_une_seule_page(self):
        p = self._encaisser(montant_inscription=50000, montant_mensualite=25000,
                            montant_reliquat=30000, mode_paiement='MIXTE',
                            modes_reglement=[{'mode': 'ESPECE', 'montant': 60000},
                                             {'mode': 'WAVE', 'montant': 45000}],
                            observations='Versement du père')
        a4 = self._pdf(p, 'A4')
        self.assertAlmostEqual(float(a4.pages[0].mediabox.width), 595.28, places=1)
        self.assertEqual(len(a4.pages), 1)
        a5 = self._pdf(p, 'A5')
        self.assertAlmostEqual(float(a5.pages[0].mediabox.width), 419.53, places=1)
        self.assertEqual(len(a5.pages), 1)
        texte = a5.pages[0].extract_text()
        self.assertIn('Impayés antérieurs', texte)

    def test_neant_quand_aucun_impaye_anterieur(self):
        autre = Eleve.objects.create(tenant=self.tenant, exercice=self.ex2, nom_complet='Awa SY',
                                     section=self.section, numero=9,
                                     date_inscription=self.ex2.date_debut)
        r = self.client.post('/api/paiements/paiements/', {
            'eleve': str(autre.id), 'montant_inscription': 50000, 'mode_paiement': 'ESPECE'},
            format='json')
        texte = self._pdf(Paiement.objects.get(id=r.data['id']), 'A5').pages[0].extract_text()
        self.assertIn('Néant', texte)

    def test_multi_mode_reparti_par_mode(self):
        mixte = self._encaisser(montant_inscription=50000, mode_paiement='MIXTE',
                                modes_reglement=[{'mode': 'ESPECE', 'montant': 30000},
                                                 {'mode': 'WAVE', 'montant': 20000}])
        wave = self._encaisser(montant_inscription=10000, mode_paiement='WAVE')
        par_mode = encaissements_par_mode(Paiement.objects.filter(
            tenant=self.tenant, exercice=self.ex2, statut='ACTIF'))
        self.assertNotIn('MIXTE', par_mode)
        self.assertEqual(par_mode['ESPECE'], {'nb': 1, 'montant': 30000.0})
        self.assertEqual(par_mode['WAVE'], {'nb': 2, 'montant': 30000.0})

        stats = self.client.get('/api/paiements/paiements/stats/').data
        self.assertEqual({m['mode'] for m in stats['par_mode']}, {'ESPECE', 'WAVE'})
        canaux = {c['canal']: c for c in self.client.get('/api/dashboard/tresorerie-canaux/').data['canaux']}
        self.assertEqual(canaux['ESPECE']['encaissements'], 30000)
        self.assertEqual(canaux['WAVE']['encaissements'], 30000)
        # Le filtre par mode retrouve aussi le règlement mixte.
        liste = self.client.get('/api/paiements/paiements/?mode=WAVE').data
        lignes = liste['results'] if isinstance(liste, dict) else liste
        self.assertEqual({l['id'] for l in lignes}, {str(mixte.id), str(wave.id)})

    def test_ticket_thermique_a_la_hauteur_du_contenu(self):
        """Une page de 297 mm sur un rouleau réglé plus court était réduite à
        l'impression : le ticket sortait à moitié de la largeur du papier."""
        p = self._encaisser(montant_inscription=50000, montant_mensualite=1250000,
                            montant_reliquat=30000, mode_paiement='MIXTE',
                            modes_reglement=[{'mode': 'ESPECE', 'montant': 660000},
                                             {'mode': 'WAVE', 'montant': 670000}])
        for taille, largeur_mm in (('80MM', 80), ('58MM', 58)):
            pdf = self._pdf(p, taille)
            self.assertEqual(len(pdf.pages), 1, taille)
            boite = pdf.pages[0].mediabox
            self.assertAlmostEqual(float(boite.width) * 25.4 / 72, largeur_mm, places=0)
            hauteur_mm = float(boite.height) * 25.4 / 72
            self.assertLess(hauteur_mm, 200, taille)   # plus de page A4 de haut
            self.assertGreater(hauteur_mm, 60, taille)
            texte = pdf.pages[0].extract_text()
            # Rien de rogné : l'en-tête et le pied sont sur la page.
            self.assertIn('REÇU DE PAIEMENT', texte, taille)
            self.assertIn('Merci de conserver', texte, taille)
            self.assertIn('1 250 000', texte, taille)

    def test_autres_formats_papier(self):
        p = self._encaisser(montant_inscription=50000, montant_reliquat=30000,
                            observations='Versement du père')
        for taille, largeur_pt in (('A6', 297.6), ('LETTER', 612), ('LEGAL', 612)):
            pdf = self._pdf(p, taille)
            self.assertAlmostEqual(float(pdf.pages[0].mediabox.width), largeur_pt,
                                   delta=1, msg=taille)
            self.assertEqual(len(pdf.pages), 1, taille)
            self.assertIn('Impayés antérieurs', pdf.pages[0].extract_text(), taille)

    def test_ticket_logo_en_noir_pur(self):
        """Tête thermique : un logo en couleur sortait délavé, presque invisible."""
        import base64
        from PIL import Image
        from apps.tenants.logo import logo_noir_et_blanc
        from core.tenant import oublier_tenant

        image = Image.new('RGB', (120, 60), (255, 255, 255))
        image.paste((30, 110, 60), (10, 10, 110, 50))      # vert moyen
        tampon = BytesIO()
        image.save(tampon, format='PNG')
        logo = 'data:image/png;base64,' + base64.b64encode(tampon.getvalue()).decode()

        net = Image.open(BytesIO(base64.b64decode(logo_noir_et_blanc(logo).split(',', 1)[1])))
        self.assertEqual(set(net.getdata()), {0, 255})      # noir ou blanc, rien d'autre
        self.assertEqual(net.getpixel((60, 30)), 0)          # le vert est devenu noir
        self.assertEqual(net.getpixel((2, 2)), 255)

        # Logo clair sur fond brun : inversé, jamais un pavé noir.
        sombre = Image.new('RGB', (120, 60), (160, 60, 20))
        sombre.paste((255, 255, 255), (40, 20, 80, 40))
        tampon2 = BytesIO()
        sombre.save(tampon2, format='PNG')
        inverse = Image.open(BytesIO(base64.b64decode(logo_noir_et_blanc(
            'data:image/png;base64,' + base64.b64encode(tampon2.getvalue()).decode()
        ).split(',', 1)[1])))
        self.assertEqual(inverse.getpixel((2, 2)), 255)      # fond blanc
        self.assertEqual(inverse.getpixel((60, 30)), 0)      # motif noir

        self.tenant.logo = logo
        self.tenant.save()
        oublier_tenant(self.tenant.id)
        p = self._encaisser(montant_inscription=50000)
        pdf = self._pdf(p, '80MM')
        self.assertEqual(len(pdf.pages), 1)
        self.assertIn('Merci de conserver', pdf.pages[0].extract_text())
