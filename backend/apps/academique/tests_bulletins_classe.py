"""Bulletins d'une classe : un seul document, deux par feuille A4.

Une classe de 40 élèves consommait 40 feuilles, éditées une par une.
Demande du CEO (19/09/2026) : éditer par classe, deux bulletins par page
séparés par un trait de découpe, pour diviser la charge de papier par deux.

Ce que ces tests rendent impossible :
- un document qui repasse à une feuille par élève (le premier gabarit, qui
  empilait deux bulletins dans une page A4, en produisait vingt-huit pour
  sept élèves : xhtml2pdf n'honore pas « page-break-inside: avoid ») ;
- un bulletin coupé en deux par le trait de découpe ;
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

    def _matieres_en_plus(self, combien):
        """Une vraie classe a dix matières, pas une : c'est ce volume qui
        décide si deux bulletins tiennent encore sur une feuille."""
        types = [TypeEvaluation.objects.create(tenant=self.tenant, nom=nom, poids=poids)
                 for nom, poids in (('Devoir 1', 1), ('Devoir 2', 1))]
        evaluations = []
        for i in range(combien):
            matiere = Matiere.objects.create(tenant=self.tenant, classe=self.classe,
                                             nom=f'Matière {i + 1}', coefficient=2, note_max=20)
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
        # Le cas réel : dix matières, deux devoirs chacune. C'est ici que le
        # premier gabarit repassait à une feuille par élève.
        evaluations = self._matieres_en_plus(10)
        for i in range(8):
            self._noter(self._eleve(f'Élève NUMERO{i:02d}'), evaluations)
        r = self._pdf()
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(len(self._pages(r)), 4)       # 8 élèves, 4 feuilles

    def _deux_bulletins_longs(self, nb_matieres):
        """Un bulletin qui déborde de sa demi-feuille était coupé entre deux
        matières, les deux morceaux sur une même feuille, sans trait. Il est
        désormais réduit pour tenir dans sa moitié : deux bulletins ENTIERS
        par A4, séparés au milieu."""
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
        # Chaque bulletin arrive jusqu'à ses signatures : rien n'est perdu.
        self.assertEqual(texte.count('LE DIRECTEUR'), 2)

    def test_seize_matieres_deux_bulletins_entiers_par_feuille(self):
        # La 2e Étape CE1 de Shoumoul.
        self._deux_bulletins_longs(16)

    def test_vingt_cinq_matieres_deux_bulletins_entiers_par_feuille(self):
        self._deux_bulletins_longs(25)

    def test_le_trait_de_decoupe_est_imprime_entre_deux_bulletins(self):
        # Sans repère visible, l'école coupe de travers.
        for nom in ('Awa NDIAYE', 'Moussa FALL'):
            self._eleve(nom, 14)
        r = self._pdf()
        self.assertIn('DÉCOUPER ICI', self._pages(r)[0].extract_text().upper())

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
