"""« J'entre 10, le tableau affiche 5 » — pour tous les élèves d'une matière.

Deux causes donnaient exactement la moitié :
  1. une évaluation sans aucune note (créée deux fois, pas encore passée)
     comptait zéro pour tout le monde : (10 + 0) / 2 = 5 ;
  2. une matière passée de /20 (le défaut) à /10 gardait ses évaluations sur
     /20 : 10 saisi valait 10/20, soit 5/10.
"""
import datetime
from io import StringIO

from django.core.management import call_command
from rest_framework.test import APITestCase

from apps.academique.models import (Classe, Evaluation, Matiere, NiveauScolaire, Note,
                                    TypeEvaluation)
from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant
from apps.users.models import User


class NotesDiviseesBase(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Complexe Shoumoul Excellence')
        self.client.force_authenticate(User.objects.create_user(
            'dir@shoumoul.sn', 'x', nom='Directrice', role='ADMIN_ECOLE', tenant=self.tenant))
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026-2027', cloture=False,
            date_debut=datetime.date(2026, 10, 1), date_fin=datetime.date(2027, 7, 31))
        section = Section.objects.create(tenant=self.tenant, nom='1ère Etape')
        niveau = NiveauScolaire.objects.create(tenant=self.tenant, nom='1ère Etape',
                                               code='E1', note_max=20)
        self.classe = Classe.objects.create(tenant=self.tenant, nom='1ère Etape CP', code='CP',
                                            niveau=niveau)
        self.type_eval = TypeEvaluation.objects.create(tenant=self.tenant, nom='Devoir', poids=1)
        self.eleves = [Eleve.objects.create(tenant=self.tenant, exercice=self.ex, section=section,
                                            classe=self.classe, nom_complet=nom)
                       for nom in ('Adama NIANG', 'Adama THIAW')]

    def _matiere(self, note_max):
        return Matiere.objects.create(tenant=self.tenant, classe=self.classe,
                                      nom='Identification de mots', coefficient=1,
                                      note_max=note_max)

    def _eval(self, matiere, note_max):
        return Evaluation.objects.create(tenant=self.tenant, matiere=matiere,
                                         type_eval=self.type_eval, trimestre='S2',
                                         date_eval=datetime.date(2027, 3, 1), note_max=note_max)

    def _noter(self, ev, *notes):
        for e, n in zip(self.eleves, notes):
            Note.objects.create(tenant=self.tenant, eleve=e, evaluation=ev, valeur=n)

    def _moyennes(self):
        r = self.client.post('/api/academique/calculer/',
                             {'classe_id': str(self.classe.id), 'trimestre': 'S2'}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        return {x['eleve_nom']: x['matieres'][0]['moyenne'] for x in r.data['resultats']}


class EvaluationVideTest(NotesDiviseesBase):
    def test_une_evaluation_sans_aucune_note_ne_divise_plus_par_deux(self):
        m = self._matiere(10)
        self._noter(self._eval(m, 10), 10, 8)
        self._eval(m, 10)                       # doublon vide
        self.assertEqual(self._moyennes(), {'Adama NIANG': 10, 'Adama THIAW': 8})

    def test_l_eleve_absent_quand_les_autres_ont_compose_compte_toujours_zero(self):
        m = self._matiere(10)
        self._noter(self._eval(m, 10), 10, 8)
        rattrapage = self._eval(m, 10)
        Note.objects.create(tenant=self.tenant, eleve=self.eleves[0], evaluation=rattrapage, valeur=10)
        self.assertEqual(self._moyennes(), {'Adama NIANG': 10, 'Adama THIAW': 4})


class BaremeDeLaMatiereTest(NotesDiviseesBase):
    def test_passer_la_matiere_a_10_emporte_ses_evaluations(self):
        m = self._matiere(20)                   # créée avec le barème par défaut
        ev = self._eval(m, 20)
        self._noter(ev, 10, 7)                  # saisies en pensant « sur 10 »
        r = self.client.patch(f'/api/academique/matieres/{m.id}/', {'note_max': 10}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        ev.refresh_from_db()
        self.assertEqual(ev.note_max, 10)
        self.assertEqual(self._moyennes(), {'Adama NIANG': 10, 'Adama THIAW': 7})
        # Les notes ne sont jamais converties.
        self.assertEqual(sorted(float(n.valeur) for n in Note.objects.all()), [7.0, 10.0])

    def test_une_note_trop_haute_bloque_l_alignement(self):
        m = self._matiere(20)
        ev = self._eval(m, 20)
        self._noter(ev, 15, 7)                  # 15 n'existe pas sur /10
        self.client.patch(f'/api/academique/matieres/{m.id}/', {'note_max': 10}, format='json')
        ev.refresh_from_db()
        self.assertEqual(ev.note_max, 20)


class CommandeVerifierBaremesTest(NotesDiviseesBase):
    def test_diagnostic_puis_correction(self):
        m = self._matiere(10)
        ev = self._eval(m, 20)                  # l'état constaté chez Shoumoul
        self._noter(ev, 10, 9)
        self._eval(m, 10)                       # et un doublon vide
        self.assertEqual(self._moyennes(), {'Adama NIANG': 5, 'Adama THIAW': 4.5})

        sortie = StringIO()
        call_command('verifier_baremes', ecole='Shoumoul', stdout=sortie)
        texte = sortie.getvalue()
        self.assertIn('Identification de mots', texte)
        self.assertIn('évaluation /20, matière /10', texte)
        self.assertIn('sans aucune note (ignorées par le calcul) : 1', texte)
        ev.refresh_from_db()
        self.assertEqual(ev.note_max, 20)       # diagnostic seul : rien ne bouge

        call_command('verifier_baremes', ecole='Shoumoul', aligner=True, stdout=StringIO())
        ev.refresh_from_db()
        self.assertEqual(ev.note_max, 10)
        self.assertEqual(self._moyennes(), {'Adama NIANG': 10, 'Adama THIAW': 9})


class CommandeVerifierClasseTest(NotesDiviseesBase):
    def test_chaque_anomalie_est_signalee_et_le_releve_imprime(self):
        m = self._matiere(10)
        ev1 = self._eval(m, 10)
        self._noter(ev1, 10, 8)
        ev2 = self._eval(m, 10)                 # 2e évaluation : moyennée, THIAW sans note
        Note.objects.create(tenant=self.tenant, eleve=self.eleves[0], evaluation=ev2, valeur=12)
        m2 = Matiere.objects.create(tenant=self.tenant, classe=self.classe, nom='Copie',
                                    coefficient=1, note_max=5)
        self._eval(m2, 5)                       # jamais notée
        self._moyennes()

        sortie = StringIO()
        call_command('verifier_classe', ecole='Shoumoul', classe='CP', periode='S2', stdout=sortie)
        texte = sortie.getvalue()
        self.assertIn('2 évaluations notées sur S2', texte)
        self.assertIn("Adama THIAW n'a PAS de note — compte 0", texte)
        self.assertIn('Adama NIANG a 12 sur /10', texte)
        self.assertIn('Copie · Devoir : aucune note', texte)
        self.assertIn('RELEVÉ 1ère Etape CP — S2', texte)
        self.assertIn('Identification de mots: 10+12', texte)
        self.assertIn('MOYENNE', texte)
