"""Classement configurable, domaines de matières, bulletins longs.

Démonstration d'octobre 2026 : certaines écoles ne classent pas leurs élèves
(ni 1er ni 2e), d'autres les valorisent par mentions et badges ; un programme
de l'élémentaire (CEB) compte vingt à trente matières, rangées par domaines.

Ce que ces tests rendent impossible :
- un rang qui sort chez une école qui ne classe pas ;
- une matière « hors moyenne » qui pèse quand même dans un des écrans ;
- un moteur, un bulletin, un historique et une analyse qui donnent quatre
  moyennes différentes pour le même élève (on teste la COHÉRENCE) ;
- un bulletin de trente-cinq matières réduit à 55 % au lieu d'être paginé.
"""
import datetime
from io import BytesIO

from pypdf import PdfReader
from rest_framework.test import APITestCase

from apps.academique.models import (Classe, DomaineMatiere, Evaluation, Matiere,
                                    NiveauScolaire, Note, PalierMention, TypeEvaluation)
from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant
from apps.users.models import User

ANNEE = '2026'


class Base(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='École Les Filaos', code_etablissement='FIL')
        self.user = User.objects.create_user('dir@filaos.sn', 'x', nom='Dir',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        niveau = NiveauScolaire.objects.create(tenant=self.tenant, nom='Élémentaire',
                                               code='ELEMENTAIRE', note_max=20)
        self.section = Section.objects.create(tenant=self.tenant, nom='Élémentaire',
                                              frais_mensualite=10000, niveau=niveau)
        self.classe = Classe.objects.create(tenant=self.tenant, section=self.section, nom='CE2')
        self.ex = Exercice.objects.create(tenant=self.tenant, annee_scolaire=ANNEE,
                                          date_debut=datetime.date(2026, 1, 1),
                                          date_fin=datetime.date(2026, 12, 31))
        self.type = TypeEvaluation.objects.create(tenant=self.tenant, nom='Composition', poids=1)
        self.evaluations = {}

    def matiere(self, nom, coef=1, domaine=None, compte=True):
        m = Matiere.objects.create(tenant=self.tenant, classe=self.classe, nom=nom,
                                   coefficient=coef, note_max=20, domaine=domaine,
                                   compte_dans_moyenne=compte)
        self.evaluations[m.id] = Evaluation.objects.create(
            tenant=self.tenant, matiere=m, type_eval=self.type, trimestre='T1',
            date_eval=datetime.date(2026, 3, 1), note_max=20)
        return m

    def eleve(self, nom, notes):
        e = Eleve.objects.create(tenant=self.tenant, exercice=self.ex, section=self.section,
                                 classe=self.classe, nom_complet=nom,
                                 date_inscription=datetime.date(2026, 1, 1))
        for matiere, valeur in notes.items():
            Note.objects.create(tenant=self.tenant, eleve=e,
                                evaluation=self.evaluations[matiere.id], valeur=valeur)
        return e

    def calculer(self):
        r = self.client.post('/api/academique/calculer/',
                             {'classe_id': str(self.classe.id), 'trimestre': 'T1'}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def bulletin(self, eleve):
        r = self.client.get(f'/api/academique/bulletin/{eleve.id}/T1/')
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def pdf(self, eleve):
        r = self.client.get(f'/api/academique/bulletin-pdf/{eleve.id}/T1/')
        self.assertEqual(r.status_code, 200, r.content)
        return PdfReader(BytesIO(r.content))

    def regler(self, **champs):
        Tenant.objects.filter(pk=self.tenant.pk).update(**champs)
        self.tenant.refresh_from_db()
        from django.core.cache import cache
        cache.clear()


class ModeClassementTest(Base):
    def setUp(self):
        super().setUp()
        self.fr = self.matiere('Français', 2)
        self.ma = self.matiere('Maths', 3)
        self.awa = self.eleve('Awa NDIAYE', {self.fr: 18, self.ma: 17})
        self.bob = self.eleve('Bamba SECK', {self.fr: 9, self.ma: 11})

    def test_classique_par_defaut(self):
        res = self.calculer()
        self.assertEqual(res['mode_classement'], 'CLASSIQUE')
        self.assertEqual([r['rang'] for r in res['resultats']], [1, 2])
        self.assertEqual(self.bulletin(self.awa)['stats']['rang'], 1)

    def test_aucun_classement_ne_sort_aucun_rang(self):
        self.regler(mode_classement='AUCUN')
        res = self.calculer()
        self.assertTrue(all(r['rang'] is None for r in res['resultats']))
        self.assertTrue(all(m['rang_matiere'] is None
                            for r in res['resultats'] for m in r['matieres']))
        # Ordre alphabétique : trié par moyenne, la liste redirait le classement.
        self.assertEqual([r['eleve_nom'] for r in res['resultats']], ['Awa NDIAYE', 'Bamba SECK'])
        b = self.bulletin(self.bob)
        self.assertIsNone(b['stats']['rang'])
        self.assertTrue(all(m['rang'] is None for m in b['matieres']))
        texte = self.pdf(self.bob).pages[0].extract_text()
        self.assertNotIn('RANG', texte)
        self.assertNotIn('2e / 2', texte)

    def test_mentions_personnalisees(self):
        self.regler(mode_classement='MENTIONS')
        PalierMention.objects.create(tenant=self.tenant, libelle="Tableau d'honneur", seuil=16,
                                     couleur='#1b5e20', badge='TH', distinction=True)
        PalierMention.objects.create(tenant=self.tenant, libelle='Encouragements', seuil=12,
                                     couleur='#1565c0')
        PalierMention.objects.create(tenant=self.tenant, libelle='Doit progresser', seuil=0,
                                     couleur='#c62828')
        res = self.calculer()
        mentions = {r['eleve_nom']: r['mention']['libelle'] for r in res['resultats']}
        self.assertEqual(mentions, {'Awa NDIAYE': "Tableau d'honneur", 'Bamba SECK': 'Doit progresser'})
        self.assertEqual(res['stats']['nb_distingues'], 1)
        # L'appréciation de chaque matière suit la même échelle.
        awa = next(r for r in res['resultats'] if r['eleve_nom'] == 'Awa NDIAYE')
        self.assertEqual({m['appreciation'] for m in awa['matieres']}, {"Tableau d'honneur"})
        b = self.bulletin(self.awa)
        self.assertEqual(b['stats']['mention']['badge'], 'TH')
        self.assertIsNone(b['stats']['rang'])
        texte = self.pdf(self.awa).pages[0].extract_text()
        self.assertIn('TH', texte)
        self.assertNotIn('1e / 2', texte)
        a = self.client.get('/api/academique/analyse/').json()
        self.assertEqual([d['nom'] for d in a['distingues']], ['Awa NDIAYE'])
        self.assertTrue(all(t['rang'] is None for t in a['top_eleves']))

    def test_paliers_initialises_reprennent_l_echelle_historique(self):
        r = self.client.get('/api/academique/paliers/').json()
        self.assertTrue(r['par_defaut'])
        self.assertEqual(r['effectifs'][0]['libelle'], 'Excellent')
        self.assertEqual(self.client.post('/api/academique/paliers/initialiser/').status_code, 201)
        self.assertEqual(PalierMention.objects.filter(tenant=self.tenant).count(), 7)
        self.assertEqual(self.client.post('/api/academique/paliers/initialiser/').status_code, 409)


class CoherenceMoyennesTest(Base):
    """Le même élève, la même moyenne, quel que soit l'écran."""

    def moyennes(self, eleve):
        res = self.calculer()
        moteur = next(r['moy_generale'] for r in res['resultats'] if r['eleve_id'] == str(eleve.id))
        bulletin = self.bulletin(eleve)['stats']['moy_generale']
        hist = next(h['moy_generale'] for h in
                    self.client.get('/api/academique/historique-bulletins/').json()['bulletins']
                    if h['eleve_id'] == str(eleve.id))
        analyse = self.client.get('/api/academique/analyse/').json()['top_eleves'][0]['moyenne']
        return moteur, bulletin, hist, analyse

    def test_matiere_hors_moyenne(self):
        fr = self.matiere('Français', 1)
        eps = self.matiere('EPS', 1, compte=False)
        awa = self.eleve('Awa NDIAYE', {fr: 12, eps: 20})
        # 12 : l'EPS à 20 ne remonte pas la moyenne.
        self.assertEqual(set(self.moyennes(awa)), {12.0})
        texte = self.pdf(awa).pages[0].extract_text()
        self.assertIn('EPS *', texte)
        self.assertIn('hors moyenne', texte)

    def test_domaines_sans_coefficient_ne_changent_rien(self):
        lc = DomaineMatiere.objects.create(tenant=self.tenant, nom='Langue et communication', ordre=1)
        ma = DomaineMatiere.objects.create(tenant=self.tenant, nom='Mathématiques', ordre=2)
        a = self.matiere('Lecture', 1, lc)
        b = self.matiere('Grammaire', 1, lc)
        c = self.matiere('Numération', 2, ma)
        awa = self.eleve('Awa NDIAYE', {a: 10, b: 14, c: 16})
        self.regler(agregation_domaines=True)
        # (10 + 14 + 32) / 4 = 14, exactement le calcul simple.
        self.assertEqual(set(self.moyennes(awa)), {14.0})

    def test_agregation_par_domaines_ponderes(self):
        lc = DomaineMatiere.objects.create(tenant=self.tenant, nom='Langue et communication',
                                           ordre=1, coefficient=1)
        ma = DomaineMatiere.objects.create(tenant=self.tenant, nom='Mathématiques',
                                           ordre=2, coefficient=1)
        a = self.matiere('Lecture', 1, lc)
        b = self.matiere('Grammaire', 1, lc)
        b2 = self.matiere('Dictée', 1, lc)
        c = self.matiere('Numération', 1, ma)
        awa = self.eleve('Awa NDIAYE', {a: 10, b: 10, b2: 10, c: 20})
        # Calcul simple : 50/4 = 12,5. Par domaines (1 pour 1) : (10 + 20)/2 = 15.
        self.assertEqual(set(self.moyennes(awa)), {12.5})
        self.regler(agregation_domaines=True)
        self.assertEqual(set(self.moyennes(awa)), {15.0})
        texte = self.pdf(awa).pages[0].extract_text()
        self.assertIn('LANGUE ET COMMUNICATION', texte)
        self.assertIn('Moyenne du domaine', texte)


class BulletinLongTest(Base):
    def _bulletin_de(self, n):
        notes = {}
        for i in range(n):
            notes[self.matiere(f'Activité numéro {i + 1}', 1)] = 10 + i % 10
        awa = self.eleve('Awa NDIAYE', notes)
        self.calculer()
        return awa

    def test_trente_cinq_matieres_passent_en_a4_paginee(self):
        awa = self._bulletin_de(35)
        pages = self.pdf(awa).pages
        # A4 debout (595 pt de large), pas une demi-feuille réduite.
        self.assertTrue(all(round(float(p.mediabox.width)) == 595 for p in pages))
        texte = ''.join(p.extract_text() for p in pages)
        for i in (1, 18, 35):
            self.assertIn(f'Activité numéro {i}', texte)
        self.assertIn('Le Directeur', texte)

    def test_format_a4_demande(self):
        self.regler(format_bulletin='A4')
        awa = self._bulletin_de(4)
        pages = self.pdf(awa).pages
        self.assertEqual(len(pages), 1)
        self.assertEqual(round(float(pages[0].mediabox.width)), 595)

    def test_dix_matieres_restent_deux_par_feuille(self):
        awa = self._bulletin_de(10)
        page = self.pdf(awa).pages[0]
        # A4 couchée : 842 pt de large.
        self.assertEqual(round(float(page.mediabox.width)), 842)


class ModeleCEBTest(Base):
    def test_applique_le_modele_sans_doublon(self):
        Matiere.objects.create(tenant=self.tenant, classe=self.classe, nom='Lecture',
                               coefficient=3, note_max=20)
        corps = {'classes': [str(self.classe.id)], 'programme': 'FR'}
        r = self.client.post('/api/academique/domaines/modele-ceb/', corps, format='json').json()
        self.assertEqual(r['domaines_crees'], 4)
        lecture = Matiere.objects.get(classe=self.classe, nom='Lecture')
        self.assertEqual(lecture.domaine.code, 'LC')
        self.assertEqual(lecture.coefficient, 3)        # la saisie de l'école est gardée
        nb = Matiere.objects.filter(classe=self.classe).count()
        r = self.client.post('/api/academique/domaines/modele-ceb/', corps, format='json').json()
        self.assertEqual((r['domaines_crees'], r['matieres_creees']), (0, 0))
        self.assertEqual(Matiere.objects.filter(classe=self.classe).count(), nb)
        self.assertEqual(nb, 21)
