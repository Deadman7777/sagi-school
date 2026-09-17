"""Certificat de scolarité à partir du modèle Word de l'établissement.

Le piège principal : Word découpe le texte en morceaux à sa guise. Un code
comme {NOM_COMPLET} arrive souvent en plusieurs morceaux, et un remplacement
naïf le laisserait intact dans le certificat remis à la famille.
"""
import datetime
import io
import zipfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from apps.eleves.modele_word import (ModeleInvalide, champs_reconnus, codes_du_modele, remplir_docx,
                                    verifier_docx)
from apps.eleves.models import Eleve, ModeleCertificat, Section
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant
from apps.users.models import User

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def run(texte, gras=False):
    rpr = '<w:rPr><w:b/></w:rPr>' if gras else ''
    return f'<w:r>{rpr}<w:t xml:space="preserve">{texte}</w:t></w:r>'


def paragraphe(*runs):
    return '<w:p>' + ''.join(runs) + '</w:p>'


def docx(corps, entete=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types/>')
        z.writestr('word/document.xml',
                   f'<?xml version="1.0" encoding="UTF-8"?><w:document {W}><w:body>{corps}</w:body></w:document>')
        if entete is not None:
            z.writestr('word/header1.xml',
                       f'<?xml version="1.0" encoding="UTF-8"?><w:hdr {W}>{entete}</w:hdr>')
    return buf.getvalue()


def texte_de(contenu, partie='word/document.xml'):
    import re
    xml = zipfile.ZipFile(io.BytesIO(contenu)).read(partie).decode('utf-8')
    paras = re.findall(r'<w:p>(.*?)</w:p>', xml, re.S)
    return ['' .join(re.findall(r'<w:t[^>]*>(.*?)</w:t>', p, re.S)) for p in paras]


class RemplissageTest(SimpleTestCase):
    V = {'NOM_COMPLET': 'Awa NDIAYE', 'CLASSE': 'CM2 A', 'ECOLE': 'Shoumoul'}

    def test_code_dans_un_seul_morceau(self):
        out = remplir_docx(docx(paragraphe(run('Élève : {NOM_COMPLET}.'))), self.V)
        self.assertEqual(texte_de(out), ['Élève : Awa NDIAYE.'])

    def test_code_decoupe_par_word_en_trois_morceaux(self):
        corps = paragraphe(run('Je certifie que '), run('{NOM_', gras=True), run('COMP'), run('LET} est inscrite.'))
        out = remplir_docx(docx(corps), self.V)
        self.assertEqual(texte_de(out), ['Je certifie que Awa NDIAYE est inscrite.'])
        # la mise en forme du début du code (gras) porte la valeur
        self.assertIn('<w:b/></w:rPr><w:t xml:space="preserve">Awa NDIAYE</w:t>',
                      zipfile.ZipFile(io.BytesIO(out)).read('word/document.xml').decode())

    def test_accolade_isolee_dans_son_morceau(self):
        corps = paragraphe(run('en classe de {'), run('CLASSE'), run('}'), run(' cette année'))
        self.assertEqual(texte_de(remplir_docx(docx(corps), self.V)), ['en classe de CM2 A cette année'])

    def test_plusieurs_codes_dans_le_meme_paragraphe(self):
        corps = paragraphe(run('{NOM_COMPLET} ({CLA'), run('SSE}) — {ECOLE}'))
        self.assertEqual(texte_de(remplir_docx(docx(corps), self.V)), ['Awa NDIAYE (CM2 A) — Shoumoul'])

    def test_casse_et_espaces_toleres(self):
        corps = paragraphe(run('{ nom_complet }'))
        self.assertEqual(texte_de(remplir_docx(docx(corps), self.V)), ['Awa NDIAYE'])

    def test_un_code_ne_traverse_pas_deux_paragraphes(self):
        corps = paragraphe(run('{NOM_')) + paragraphe(run('COMPLET}'))
        self.assertEqual(texte_de(remplir_docx(docx(corps), self.V)), ['{NOM_', 'COMPLET}'])

    def test_code_inconnu_laisse_visible(self):
        corps = paragraphe(run('{NOM_COMPLET} {MOYENNE}'))
        self.assertEqual(texte_de(remplir_docx(docx(corps), self.V)), ['Awa NDIAYE {MOYENNE}'])

    def test_caracteres_speciaux_echappes(self):
        corps = paragraphe(run('{ECOLE}'))
        out = remplir_docx(docx(corps), {'ECOLE': 'Daara <Al & Nour>'})
        xml = zipfile.ZipFile(io.BytesIO(out)).read('word/document.xml').decode()
        self.assertIn('Daara &lt;Al &amp; Nour&gt;', xml)

    def test_en_tete_rempli(self):
        out = remplir_docx(docx(paragraphe(run('x')), entete=paragraphe(run('{ECOLE}'))), self.V)
        self.assertEqual(texte_de(out, 'word/header1.xml'), ['Shoumoul'])

    def test_texte_sans_code_intact(self):
        corps = paragraphe(run('Le directeur'), run(' soussigné'))
        source = docx(corps)
        out = remplir_docx(source, self.V)
        self.assertEqual(zipfile.ZipFile(io.BytesIO(out)).read('word/document.xml'),
                         zipfile.ZipFile(io.BytesIO(source)).read('word/document.xml'))

    def test_codes_du_modele(self):
        corps = paragraphe(run('{NOM_'), run('COMPLET} {classe} {NOM_COMPLET}'))
        self.assertEqual(codes_du_modele(docx(corps, entete=paragraphe(run('{ECOLE}')))),
                         ['NOM_COMPLET', 'CLASSE', 'ECOLE'])

    def test_fichier_doc_ancien_refuse_avec_conseil(self):
        with self.assertRaisesMessage(ModeleInvalide, '.docx'):
            verifier_docx(b'\xd0\xcf\x11\xe0' + b'\x00' * 100)

    def test_fichier_quelconque_refuse(self):
        with self.assertRaises(ModeleInvalide):
            verifier_docx(b'%PDF-1.4 ...')


class ModeleCertificatApiTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul', ville='Rufisque',
                                            numero_autorisation='AUT-12')
        self.admin = User.objects.create_user('a@a.sn', 'x', nom='A', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.admin)
        exercice = Exercice.objects.create(tenant=self.tenant, annee_scolaire='2025-2026',
                                           date_debut=datetime.date(2025, 10, 1),
                                           date_fin=datetime.date(2026, 7, 31))
        section = Section.objects.create(tenant=self.tenant, nom='CM2')
        self.eleve = Eleve.objects.create(
            tenant=self.tenant, exercice=exercice, section=section, nom_complet='Awa NDIAYE',
            genre='F', matricule='26-0001', date_naissance=datetime.date(2014, 5, 3),
            lieu_naissance='Rufisque')

    def _deposer(self, contenu, nom='certificat.docx'):
        return self.client.post('/api/eleves/certificat-modele/',
                                {'fichier': SimpleUploadedFile(nom, contenu)}, format='multipart')

    def test_depot_puis_certificat_word_rempli(self):
        corps = paragraphe(run('{NOM_COMPLET}, {NE_E} le {DATE_NAISSANCE} à {LIEU_NAISSANCE}, '
                               'est {INSCRIT_E} en {CLASSE} ({ANNEE_SCOLAIRE}) — {ECOLE}, {NUMERO_AUTORISATION}'))
        r = self._deposer(docx(corps))
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data['modele']['codes_inconnus'], [])

        r = self.client.get(f'/api/eleves/{self.eleve.id}/certificat/?modele=word')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn('.docx', r['Content-Disposition'])
        self.assertEqual(texte_de(r.content), [
            'Awa NDIAYE, née le 03/05/2014 à Rufisque, est inscrite en CM2 (2025-2026) — Shoumoul, AUT-12'])

    def test_codes_inconnus_signales_au_depot(self):
        r = self._deposer(docx(paragraphe(run('{NOM_COMPLET} {MOYENNE_GENERALE}'))))
        self.assertEqual(r.data['modele']['codes_inconnus'], ['MOYENNE_GENERALE'])

    def test_nouveau_depot_remplace_l_ancien(self):
        self._deposer(docx(paragraphe(run('v1'))), 'v1.docx')
        self._deposer(docx(paragraphe(run('v2'))), 'v2.docx')
        self.assertEqual(ModeleCertificat.objects.filter(tenant=self.tenant).count(), 1)
        r = self.client.get('/api/eleves/certificat-modele/?telecharger=1')
        self.assertEqual(texte_de(r.content), ['v2'])

    def test_fichier_invalide_refuse(self):
        r = self._deposer(b'pas un word', 'notes.txt')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(ModeleCertificat.objects.exists())

    def test_sans_modele_le_word_est_introuvable_et_le_pdf_marche(self):
        self.assertEqual(self.client.get(f'/api/eleves/{self.eleve.id}/certificat/?modele=word').status_code, 404)
        r = self.client.get(f'/api/eleves/{self.eleve.id}/certificat/')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.content.startswith(b'%PDF'))

    def test_retrait_du_modele(self):
        self._deposer(docx(paragraphe(run('x'))))
        r = self.client.delete('/api/eleves/certificat-modele/')
        self.assertIsNone(r.data['modele'])
        self.assertFalse(ModeleCertificat.objects.exists())

    def test_seul_l_admin_change_le_modele(self):
        secretaire = User.objects.create_user('s@a.sn', 'x', nom='S', role='ADMIN_SCOLARITE', tenant=self.tenant)
        self.client.force_authenticate(secretaire)
        self.assertEqual(self._deposer(docx(paragraphe(run('x')))).status_code, 403)

    def test_le_modele_d_une_ecole_ne_sert_pas_a_l_autre(self):
        self._deposer(docx(paragraphe(run('{ECOLE}'))))
        autre = Tenant.objects.create(nom='Autre école')
        self.client.force_authenticate(User.objects.create_user(
            'b@b.sn', 'x', nom='B', role='ADMIN_ECOLE', tenant=autre))
        self.assertIsNone(self.client.get('/api/eleves/certificat-modele/').data['modele'])


class BlancsSansCodesTest(SimpleTestCase):
    """Le modèle déposé tel quel : les blancs après les libellés se remplissent."""
    VALEURS = {'NOM_COMPLET': 'Awa NDIAYE', 'DATE_NAISSANCE': '12/03/2019', 'LIEU_NAISSANCE': 'Rufisque',
               'CLASSE': 'CI', 'ANNEE_SCOLAIRE': '2026-2027', 'NOM_PERE': 'Ousmane NDIAYE',
               'NOM_MERE': 'Fatou SOW', 'MATRICULE': '2026-EFA-0001', 'VILLE': 'Rufisque',
               'DATE_DU_JOUR': '17/09/2026', 'NOM_TUTEUR': ''}

    def _rempli(self, *paras):
        return texte_de(remplir_docx(docx(''.join(paragraphe(*p) for p in paras)), self.VALEURS))

    def test_formulations_courantes(self):
        lignes = self._rempli(
            [run('Nom et prénom(s) : ..............................')],
            [run('Né(e) le ……………… à ………………')],
            [run('Fils/Fille de ______________ et de ______________')],
            [run('est inscrit(e) en classe de ........ pour l\u2019année scolaire ........')],
            [run('Matricule : .........')],
            [run('Fait à .............., le ..............')])
        self.assertEqual(lignes, [
            'Nom et prénom(s) : Awa NDIAYE',
            'Né(e) le 12/03/2019 à Rufisque',
            'Fils/Fille de Ousmane NDIAYE et de Fatou SOW',
            'est inscrit(e) en classe de CI pour l\u2019année scolaire 2026-2027',
            'Matricule : 2026-EFA-0001',
            'Fait à Rufisque, le 17/09/2026'])

    def test_blanc_decoupe_par_word_et_mise_en_forme_conservee(self):
        xml = remplir_docx(docx(paragraphe(run('Certifie que '), run('.....', gras=True), run('.......'))),
                           self.VALEURS)
        self.assertEqual(texte_de(xml), ['Certifie que Awa NDIAYE'])
        self.assertIn('<w:b/>', zipfile.ZipFile(io.BytesIO(xml)).read('word/document.xml').decode())

    def test_blanc_non_reconnu_ou_sans_valeur_reste_a_la_main(self):
        lignes = self._rempli([run('Je soussigné ................, Directeur')],
                              [run('Tuteur : ..........')])
        self.assertEqual(lignes, ['Je soussigné ................, Directeur', 'Tuteur : ..........'])

    def test_codes_et_blancs_ensemble(self):
        lignes = self._rempli([run('{NOM_COMPLET}, classe : .......')])
        self.assertEqual(lignes, ['Awa NDIAYE, classe : CI'])

    def test_une_ponctuation_ordinaire_n_est_pas_un_blanc(self):
        self.assertEqual(self._rempli([run('Nom... voir plus bas.')]), ['Nom... voir plus bas.'])

    def test_champs_reconnus(self):
        contenu = docx(paragraphe(run('Nom et prénom : ......')) + paragraphe(run('Né le ...... à ......')))
        self.assertEqual([c['code'] for c in champs_reconnus(contenu)],
                         ['NOM_COMPLET', 'DATE_NAISSANCE', 'LIEU_NAISSANCE'])


class GabaritsSobresTest(SimpleTestCase):
    """Ticket 80 mm et certificat standard : lisibles, sans traits qui chevauchent le texte."""

    def test_ticket_montants_lisibles_sans_bordure_de_ligne(self):
        from django.template.loader import render_to_string
        html = render_to_string('pdf/recu_ticket.html', {
            'lignes': [("Frais d'inscription", 16000.0), ('Taekwondo — Kimono', 10000.0)],
            'total': 26000.0, 'total_attendu': 300000.0, 'deja_paye_avant': 0, 'total_paye_apres': 26000.0,
            'reste_apres': 274000.0, 'tenant_nom': 'École', 'no_piece': 'REC-1', 'eleve': 'Awa'})
        # Espace insécable : un montant ne se coupe pas en bout de ligne.
        self.assertIn('16\u202f000', html)
        self.assertIn('274\u202f000 F', html)
        self.assertNotIn('border-bottom', html)
        self.assertNotIn('{#', html)

    def test_certificat_standard_accorde_au_genre_et_sans_cadre(self):
        import datetime
        from django.template.loader import render_to_string
        from django.utils import timezone
        from apps.tenants.models import Tenant
        eleve = Eleve(nom_complet='Awa NDIAYE', genre='F', date_naissance=datetime.date(2019, 3, 12))
        html = render_to_string('pdf/certificat_scolarite.html', {
            'tenant': Tenant(nom='École Test'), 'eleve': eleve, 'classe_nom': 'CI', 'ne': 'née',
            'inscrit': 'inscrite', 'annee_scolaire': '2026-2027', 'date_edition': timezone.now(),
            'tenant_ville': 'Rufisque'})
        self.assertIn('Née le', html)
        self.assertIn('régulièrement inscrite', html)
        self.assertNotIn('border', html)
