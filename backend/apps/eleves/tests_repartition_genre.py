"""Filles et garçons à côté du total, sur l'écran et les listes PDF (08/10/2026).

Les trois comptes viennent du même champ `genre` : on vérifie qu'ils se
recoupent (G + F + non renseigné = total) partout.
"""
from io import BytesIO

from pypdf import PdfReader

from rest_framework.test import APITestCase

from apps.eleves.tests_base_active import BaseActiveTest


class RepartitionGenreTest(APITestCase):
    # On reprend la préparation de BaseActiveTest, pas ses tests.
    _eleve = BaseActiveTest._eleve

    def setUp(self):
        BaseActiveTest.setUp(self)
        self._eleve('Awa NDIAYE', genre='F')
        self._eleve('Fatou SOW', genre='F')
        self._eleve('Cheikh FALL', genre='G')
        self._eleve('Inconnu BA')                       # genre non renseigné
        self._eleve('Moussa DIOP', genre='G', statut='DIPLOME')   # sorti : hors effectif

    def _texte(self, r):
        self.assertEqual(r.status_code, 200, r.content[:200])
        return ' '.join(p.extract_text() for p in PdfReader(BytesIO(r.content)).pages)

    def test_effectifs_par_classe(self):
        d = self.client.get('/api/eleves/effectifs-classes/').data
        self.assertEqual((d['total'], d['nb_garcons'], d['nb_filles']), (4, 1, 2))
        ligne = next(c for c in d['classes'] if c['classe'] == 'CI A')
        self.assertEqual((ligne['nb'], ligne['nb_garcons'], ligne['nb_filles']), (4, 1, 2))

    def test_liste_de_classe_pdf(self):
        texte = self._texte(self.client.get('/api/eleves/liste-classe-pdf/',
                                            {'classe': str(self.classe.id)}))
        self.assertIn('Garçons', texte)
        self.assertIn('Filles', texte)

    def test_liste_financiere_pdf(self):
        texte = self._texte(self.client.get('/api/eleves/export-pdf/'))
        self.assertIn('Garçons 1 · Filles 2 · non renseigné 1', texte)
