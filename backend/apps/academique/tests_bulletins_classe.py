"""Bulletins d'une classe : un seul document, deux par feuille A4.

Une classe de 40 élèves consommait 40 feuilles, éditées une par une.
Demande du CEO (19/09/2026) : éditer par classe, deux bulletins par page
séparés par un trait de découpe, pour diviser la charge de papier par deux.
Le 23/09, Shoumoul a imprimé des bulletins de treize matières réduits de
moitié pour tenir dans leur demi-feuille : illisibles. Le gabarit est
désormais dessiné pour sa demi-feuille ; depuis le 24/09, deux bulletins
debout côte à côte sur une A4 couchée.

Ce que ces tests rendent impossible :
- un document qui repasse à une feuille par élève ;
- un bulletin coupé en deux par le trait de découpe ;
- un bulletin de treize matières réduit pour tenir dans sa moitié ;
- une feuille blanche au nom d'un élève qui n'a aucune note.

Le nombre de pages est vérifié à chaque fois : c'est la seule chose qui
distingue « le PDF sort » de « le PDF économise du papier ».
"""
import datetime
from io import BytesIO

from pypdf import PdfReader
from rest_framework.test import APITestCase

from apps.academique.models import (Classe, Evaluation, Matiere, NiveauScolaire,
                                    Note, TypeEvaluation)
from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant
from apps.users.models import User


# Les quatorze matières de la 1ère Étape CI de Shoumoul, telles que saisies.
MATIERES_SHOUMOUL = (
    'Activités de mesure', 'Activités géométriques', 'Activités numériques', 'Art',
    'Compréhension', 'Copie', 'Découverte du monde', 'Développement Durable',
    'Dictée de mots', 'Ecriture', 'Identification de mots', "Production D'écrits",
    'Résolution de Problème', 'Vocabulaire')


class BulletinsClasseTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='École du Cap', code_etablissement='CAP')
        self.user = User.objects.create_user('dir@cap.sn', 'x', nom='Dir',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        niveau = NiveauScolaire.objects.create(tenant=self.tenant, nom='Élémentaire',
                                               code='ELEMENTAIRE', note_max=20)
        self.section = Section.objects.create(tenant=self.tenant, nom='Élémentaire',
                                              frais_mensualite=10000, niveau=niveau)
        self.classe = Classe.objects.create(tenant=self.tenant, section=self.section, nom='CM2')
        self.ex = Exercice.objects.create(tenant=self.tenant, annee_scolaire='2026',
                                          date_debut=datetime.date(2026, 1, 1),
                                          date_fin=datetime.date(2026, 12, 31))
        self.matiere = Matiere.objects.create(tenant=self.tenant, classe=self.classe,
                                              nom='Français', coefficient=2, note_max=20)
        type_eval = TypeEvaluation.objects.create(tenant=self.tenant, nom='Composition', poids=2)
        self.evaluation = Evaluation.objects.create(
            tenant=self.tenant, matiere=self.matiere, type_eval=type_eval, trimestre='T1',
            date_eval=datetime.date(2026, 3, 1), note_max=20)

    def _eleve(self, nom, note=None):
        eleve = Eleve.objects.create(tenant=self.tenant, exercice=self.ex, section=self.section,
                                     classe=self.classe, nom_complet=nom,
                                     date_inscription=datetime.date(2026, 1, 1))
        if note is not None:
            Note.objects.create(tenant=self.tenant, eleve=eleve,
                                evaluation=self.evaluation, valeur=note)
        return eleve

    def _matieres_en_plus(self, combien, noms=None, types=('Devoir 1', 'Devoir 2')):
        """Une vraie classe a dix matières, pas une : c'est ce volume qui
        décide si deux bulletins tiennent encore sur une feuille."""
        types = [TypeEvaluation.objects.create(tenant=self.tenant, nom=nom, poids=1)
                 for nom in types]
        noms = noms or [f'Matière {i + 1}' for i in range(combien)]
        evaluations = []
        for nom in noms:
            matiere = Matiere.objects.create(tenant=self.tenant, classe=self.classe,
                                             nom=nom, coefficient=2, note_max=20)
            evaluations += [Evaluation.objects.create(
                tenant=self.tenant, matiere=matiere, type_eval=type_eval, trimestre='T1',
                date_eval=datetime.date(2026, 3, 1), note_max=20) for type_eval in types]
        return evaluations

    def _noter(self, eleve, evaluations):
        Note.objects.bulk_create([Note(tenant=self.tenant, eleve=eleve, evaluation=ev,
                                       valeur=12) for ev in evaluations])

    def _calculer(self):
        # Les moyennes sont mises en cache par cet appel : le bulletin les lit,
        # il ne les recalcule pas.
        self.client.post('/api/academique/calculer/',
                         {'classe_id': str(self.classe.id), 'trimestre': 'T1'}, format='json')

    def _pdf(self):
        self._calculer()
        return self.client.get(f'/api/academique/bulletins-classe/{self.classe.id}/T1/')

    def _pages(self, reponse):
        return PdfReader(BytesIO(reponse.content)).pages

    def test_le_document_contient_toute_la_classe(self):
        for nom, note in (('Awa NDIAYE', 14), ('Moussa FALL', 11), ('Fatou SOW', 17)):
            self._eleve(nom, note)
        r = self._pdf()
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(r['Content-Type'], 'application/pdf')
        pages = self._pages(r)
        # 3 élèves → 2 feuilles (2 + 1), pas 3.
        self.assertEqual(len(pages), 2)
        texte = '\n'.join(p.extract_text() for p in pages)
        for nom in ('AWA NDIAYE', 'MOUSSA FALL', 'FATOU SOW'):
            self.assertIn(nom, texte)

    def test_une_classe_entiere_tient_sur_la_moitie_des_feuilles(self):
        evaluations = self._matieres_en_plus(10)
        for i in range(8):
            self._noter(self._eleve(f'Élève NUMERO{i:02d}'), evaluations)
        r = self._pdf()
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(len(self._pages(r)), 4)       # 8 élèves, 4 feuilles

    def _deux_bulletins_longs(self, nb_matieres):
        """Deux bulletins ENTIERS par A4, séparés au milieu, jusqu'à leurs
        signatures — même quand il faut les réduire pour y arriver."""
        evaluations = self._matieres_en_plus(nb_matieres)
        for i in range(2):
            self._noter(self._eleve(f'Élève NUMERO{i:02d}'), evaluations)
        r = self._pdf()
        self.assertEqual(r.status_code, 200, r.content[:300])
        pages = self._pages(r)
        self.assertEqual(len(pages), 1)                 # une feuille pour deux
        texte = pages[0].extract_text().upper()
        self.assertIn('DÉCOUPER', texte)
        self.assertIn('NUMERO00', texte)
        self.assertIn('NUMERO01', texte)
        self.assertEqual(texte.count('LE DIRECTEUR'), 2)

    def test_treize_matieres_deux_bulletins_entiers_par_feuille(self):
        # Les bulletins de Shoumoul imprimés le 23/09.
        self._deux_bulletins_longs(13)

    def test_vingt_cinq_matieres_deux_bulletins_entiers_par_feuille(self):
        self._deux_bulletins_longs(25)

    def test_le_trait_de_decoupe_est_imprime_entre_deux_bulletins(self):
        # Sans repère visible, l'école coupe de travers.
        for nom in ('Awa NDIAYE', 'Moussa FALL'):
            self._eleve(nom, 14)
        r = self._pdf()
        self.assertIn('DÉCOUPER ICI', self._pages(r)[0].extract_text().upper())

    def test_treize_matieres_ne_sont_pas_reduites(self):
        # Réduits pour tenir dans leur demi-feuille, les bulletins étaient
        # illisibles : treize matières doivent y tenir à taille réelle.
        from apps.academique.views import HAUTEURS_BULLETIN, _bulletin_sur_une_page
        from django.template.loader import render_to_string
        from apps.academique.views import contexte_bulletin
        evaluations = self._matieres_en_plus(13)
        eleve = self._eleve('Awa NDIAYE')
        self._noter(eleve, evaluations)
        self._calculer()
        contexte = contexte_bulletin(self.tenant, eleve, 'T1', '2026', None)
        contexte.pop('_lignes')
        _, hauteur = _bulletin_sur_une_page(
            render_to_string('pdf/_bulletin_corps.html', contexte), self.tenant)
        self.assertEqual(HAUTEURS_BULLETIN[hauteur], '210')

    def test_les_matieres_de_shoumoul_tiennent_sans_reduction(self):
        # Le 24/09, les bulletins de la 1ère Étape CI sortaient réduits à
        # 72 % : « Matière 1 » tenait sur une ligne, « Activités
        # géométriques » sur deux, et les quatorze matières réelles ne
        # tenaient plus dans la demi-feuille. Imprimés, trop petits.
        from apps.academique.views import HAUTEURS_BULLETIN, _bulletin_sur_une_page
        from django.template.loader import render_to_string
        from apps.academique.views import contexte_bulletin
        # L'en-tête complet de l'école : tutelle, autorisation et logo.
        import base64
        from io import BytesIO as Tampon
        from PIL import Image
        image = Tampon()
        Image.new('RGB', (120, 120), (26, 60, 94)).save(image, 'PNG')
        Tenant.objects.filter(pk=self.tenant.pk).update(
            nom='Complexe Shoumoul Excellence', inspection_academie='Rufisque',
            inspection_ief='Sangalkam', numero_autorisation='00250',
            logo='data:image/png;base64,' + base64.b64encode(image.getvalue()).decode())
        self.tenant.refresh_from_db()
        evaluations = self._matieres_en_plus(0, noms=MATIERES_SHOUMOUL, types=('Évaluation',))
        eleve = self._eleve('Mouhamed Salih BADIANE')
        self._noter(eleve, evaluations)
        # « Très Insuffisant », l'appréciation la plus longue.
        Note.objects.filter(eleve=eleve, evaluation=evaluations[0]).update(valeur=0)
        self._calculer()
        contexte = contexte_bulletin(self.tenant, eleve, 'T1', '2026', None)
        contexte.pop('_lignes')
        _, hauteur = _bulletin_sur_une_page(
            render_to_string('pdf/_bulletin_corps.html', contexte), self.tenant)
        # 215 mm au plus : réduit à 97 %, rien qui se voie à l'impression
        # (la place de signer, sous les signatures, fait déborder 210).
        self.assertLessEqual(int(HAUTEURS_BULLETIN[hauteur]), 215)

    def test_analyse_et_suivi_lisent_l_annee_du_calcul(self):
        # Le 24/09/2026, l'écran envoyait l'année du calendrier (« 2026-2027 »)
        # au calcul, l'analyse et le suivi lisaient l'exercice : les deux
        # écrans restaient vides. Une seule année, celle de l'exercice.
        eleve = self._eleve('Awa NDIAYE', 14)
        calcul = self.client.post('/api/academique/calculer/',
                                  {'classe_id': str(self.classe.id), 'trimestre': 'T1'},
                                  format='json').json()
        self.assertEqual(calcul['annee_scolaire'], self.ex.annee_scolaire)
        analyse = self.client.get('/api/academique/analyse/').json()
        self.assertEqual(analyse['annee_scolaire'], calcul['annee_scolaire'])
        self.assertEqual(len(analyse['top_eleves']), 1)
        fiche = self.client.get(f'/api/academique/fiche-pedagogique/{eleve.id}/').json()
        self.assertEqual([p['code'] for p in fiche['periodes']], ['T1'])

    def test_realigner_les_moyennes_rangees_sous_l_annee_du_calendrier(self):
        # Shoumoul : exercice « 2026 », moyennes calculées sous « 2026-2027 ».
        from django.core.management import call_command
        from apps.academique.models import BulletinCache
        eleve = self._eleve('Awa NDIAYE', 14)
        self.client.post('/api/academique/calculer/',
                         {'classe_id': str(self.classe.id), 'trimestre': 'T1',
                          'annee_scolaire': '2026-2027'}, format='json')
        self.assertEqual(len(self.client.get('/api/academique/analyse/').json()['top_eleves']), 0)

        call_command('realigner_annee_bulletins', ecole='Cap')           # simulation
        self.assertTrue(BulletinCache.objects.filter(annee_scolaire='2026-2027').exists())

        call_command('realigner_annee_bulletins', ecole='Cap', appliquer=True)
        self.assertFalse(BulletinCache.objects.filter(annee_scolaire='2026-2027').exists())
        ligne = BulletinCache.objects.get(eleve=eleve, annee_scolaire='2026')
        self.assertEqual(float(ligne.moyenne), 14)
        self.assertEqual(ligne.rang_matiere, 1)
        self.assertEqual(len(self.client.get('/api/academique/analyse/').json()['top_eleves']), 1)

    def test_effectif_garcons_filles_en_tete(self):
        for nom, genre in (('Awa NDIAYE', 'F'), ('Fatou SOW', 'F'), ('Moussa FALL', 'G')):
            eleve = self._eleve(nom, 12)
            Eleve.objects.filter(pk=eleve.pk).update(genre=genre)
        texte = self._pages(self._pdf())[0].extract_text()
        self.assertIn('Effectif : 3 élèves', texte)
        self.assertRegex(texte, r'Garçons\s*:\s*1\s+Filles\s*:\s*2')

    def test_un_eleve_sans_note_n_a_pas_de_feuille_blanche(self):
        self._eleve('Awa NDIAYE', 14)
        self._eleve('Sans Note')           # inscrit, jamais évalué
        r = self._pdf()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['X-Sans-Notes'], '1')
        self.assertEqual(len(self._pages(r)), 1)
        self.assertNotIn('SANS NOTE', self._pages(r)[0].extract_text().upper())

    def test_classe_sans_aucune_note_refuse_au_lieu_d_editer_du_vide(self):
        self._eleve('Personne')
        r = self._pdf()
        self.assertEqual(r.status_code, 404)
        self.assertIn('aucun', r.content.decode().lower())

    def test_meme_contenu_qu_un_bulletin_edite_a_l_unite(self):
        # Le corps est un gabarit partagé : si l'un change, l'autre suit.
        eleve = self._eleve('Awa NDIAYE', 14)
        self._calculer()
        unite = self.client.get(f'/api/academique/bulletin-pdf/{eleve.id}/T1/')
        self.assertEqual(unite.status_code, 200)
        classe = self._pages(self._pdf())[0].extract_text().upper()
        for attendu in ('AWA NDIAYE', 'BULLETIN DE NOTES', 'FRANÇAIS'.upper(), '14'):
            self.assertIn(attendu, classe)
