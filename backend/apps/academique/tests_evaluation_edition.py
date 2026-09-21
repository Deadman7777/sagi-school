"""Test : corriger ou supprimer une évaluation créée par erreur.

Le cas du terrain : l'évaluation a été créée sur /20 alors qu'elle était sur
/10, et la saisie des notes a commencé. Il faut pouvoir la corriger, ou la
jeter — sans laisser derrière des notes hors barème ni des moyennes périmées
qui continueraient de s'imprimer comme si de rien n'était.
"""
import datetime

from rest_framework.test import APITestCase

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.paiements.models import Exercice
from apps.eleves.models import Eleve, Section
from apps.academique.models import (BulletinCache, Classe, Evaluation, Matiere,
                                    NiveauScolaire, Note, TypeEvaluation)


class EvaluationEditionTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Daara Tahfiiz')
        self.user = User.objects.create_user(
            'dir@daara.sn', 'x', nom='Directeur', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2025-2026', cloture=False,
            date_debut=datetime.date(2025, 10, 1), date_fin=datetime.date(2026, 7, 31))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='Élémentaire', frais_mensualite=20000)
        self.niveau = NiveauScolaire.objects.create(
            tenant=self.tenant, nom='Élémentaire', code='ELEMENTAIRE', note_max=20)
        self.classe = Classe.objects.create(
            tenant=self.tenant, nom='CM2', code='CM2', niveau=self.niveau)
        self.matiere = Matiere.objects.create(
            tenant=self.tenant, classe=self.classe, nom='Récitation',
            coefficient=2, note_max=10)
        self.type_eval = TypeEvaluation.objects.create(
            tenant=self.tenant, nom='Composition', poids=1)
        # Créée par erreur sur /20
        self.evaluation = Evaluation.objects.create(
            tenant=self.tenant, matiere=self.matiere, type_eval=self.type_eval,
            trimestre='T1', date_eval=datetime.date(2025, 12, 12), note_max=20)

    def _eleve(self, nom):
        return Eleve.objects.create(tenant=self.tenant, exercice=self.ex,
                                    section=self.section, classe=self.classe,
                                    nom_complet=nom)

    def _note(self, eleve, valeur):
        return Note.objects.create(tenant=self.tenant, eleve=eleve,
                                   evaluation=self.evaluation, valeur=valeur)

    def _lignes(self, reponse):
        """La liste est paginée selon le réglage DRF : accepter les deux formes."""
        data = reponse.data
        return data['results'] if isinstance(data, dict) and 'results' in data else data

    def _url(self):
        return f'/api/academique/evaluations/{self.evaluation.id}/'

    def _calculer(self):
        return self.client.post('/api/academique/calculer/',
                                {'classe_id': str(self.classe.id), 'trimestre': 'T1'},
                                format='json')

    # ── Modification ──────────────────────────────────────────────────────
    def test_corriger_le_bareme_garde_les_notes_telles_quelles(self):
        """Le professeur notait sur 10 : ses notes ne doivent pas bouger."""
        e = self._eleve('Awa SECK')
        self._note(e, 8)
        r = self.client.patch(self._url(), {'note_max': 10}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.evaluation.refresh_from_db()
        self.assertEqual(float(self.evaluation.note_max), 10.0)
        self.assertEqual(float(Note.objects.get(eleve=e).valeur), 8.0,
                         "la note ne doit pas etre convertie")

    def test_baisser_le_bareme_sous_une_note_saisie_est_refuse(self):
        bon, trop = self._eleve('Awa SECK'), self._eleve('Modou FALL')
        self._note(bon, 8)
        self._note(trop, 15)
        r = self.client.patch(self._url(), {'note_max': 10}, format='json')
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn('Modou FALL', str(r.data))
        self.evaluation.refresh_from_db()
        self.assertEqual(float(self.evaluation.note_max), 20.0,
                         "le bareme ne doit pas avoir change")

    def test_un_absent_ne_bloque_pas_la_correction(self):
        e = self._eleve('Awa SECK')
        Note.objects.create(tenant=self.tenant, eleve=e, evaluation=self.evaluation,
                            valeur=18, absent=True)
        r = self.client.patch(self._url(), {'note_max': 10}, format='json')
        self.assertEqual(r.status_code, 200, r.content)

    def test_monter_le_bareme_passe_toujours(self):
        self._note(self._eleve('Awa SECK'), 8)
        r = self.client.patch(self._url(), {'note_max': 30}, format='json')
        self.assertEqual(r.status_code, 200, r.content)

    def test_modifier_perime_les_moyennes_calculees(self):
        self._note(self._eleve('Awa SECK'), 8)
        self._calculer()
        self.assertTrue(BulletinCache.objects.filter(tenant=self.tenant).exists())
        self.client.patch(self._url(), {'note_max': 10}, format='json')
        self.assertFalse(BulletinCache.objects.filter(tenant=self.tenant).exists(),
                         "une moyenne calculee sur l'ancien bareme ne doit pas survivre")

    # ── Suppression ───────────────────────────────────────────────────────
    def test_supprimer_emporte_les_notes_et_le_dit(self):
        for nom in ('Awa SECK', 'Modou FALL', 'Fatou NDIAYE'):
            self._note(self._eleve(nom), 7)
        r = self.client.delete(self._url())
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data['notes_supprimees'], 3)
        self.assertTrue(r.data['recalcul_necessaire'])
        self.assertFalse(Evaluation.objects.filter(id=self.evaluation.id).exists())
        self.assertEqual(Note.objects.count(), 0)

    def test_supprimer_perime_les_moyennes(self):
        self._note(self._eleve('Awa SECK'), 8)
        self._calculer()
        self.assertTrue(BulletinCache.objects.filter(tenant=self.tenant).exists())
        self.client.delete(self._url())
        self.assertFalse(BulletinCache.objects.filter(tenant=self.tenant).exists())

    def test_la_liste_annonce_le_nombre_de_notes(self):
        for nom in ('Awa SECK', 'Modou FALL'):
            self._note(self._eleve(nom), 7)
        r = self.client.get('/api/academique/evaluations/',
                            {'matiere': str(self.matiere.id), 'trimestre': 'T1'})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self._lignes(r)[0]['nb_notes'], 2)

    def test_une_evaluation_sans_note_s_annonce_a_zero(self):
        r = self.client.get('/api/academique/evaluations/',
                            {'matiere': str(self.matiere.id), 'trimestre': 'T1'})
        self.assertEqual(self._lignes(r)[0]['nb_notes'], 0)

    # ── Isolation ─────────────────────────────────────────────────────────
    def test_on_ne_supprime_pas_l_evaluation_d_une_autre_ecole(self):
        autre = Tenant.objects.create(nom='Autre école')
        eval_autre = Evaluation.objects.create(
            tenant=autre, matiere=self.matiere, type_eval=self.type_eval,
            trimestre='T1', date_eval=datetime.date(2025, 12, 12), note_max=20)
        r = self.client.delete(f'/api/academique/evaluations/{eval_autre.id}/')
        self.assertEqual(r.status_code, 404)
        self.assertTrue(Evaluation.objects.filter(id=eval_autre.id).exists())
