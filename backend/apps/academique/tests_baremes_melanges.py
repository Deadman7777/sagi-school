"""Test : une note sur /10 vaut le double d'une note sur /20.

Depuis que le barème est libre (5, 10, 15, 30, 60…), rien n'empêche une
école de noter une interrogation sur /10 et la composition sur /20 dans la
même matière, ni d'avoir une matière sur /10 à côté d'une matière sur /20.

Le moteur additionne `note.valeur` telle quelle : 8/10, qui est un très bon
résultat, pèse autant que 8/20, qui est un échec.
"""
import datetime

from rest_framework.test import APITestCase

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.paiements.models import Exercice
from apps.eleves.models import Eleve, Section
from apps.academique.models import (Classe, Evaluation, Matiere, NiveauScolaire,
                                    Note, TypeEvaluation)


class BaremesMelangesTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Daara Tahfiiz')
        self.user = User.objects.create_user(
            'dir@daara.sn', 'x', nom='Directeur', role='ADMIN_ECOLE',
            tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2025-2026', cloture=False,
            date_debut=datetime.date(2025, 10, 1), date_fin=datetime.date(2026, 7, 31))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='Élémentaire', frais_mensualite=22000)
        self.niveau = NiveauScolaire.objects.create(
            tenant=self.tenant, nom='Élémentaire', code='ELEMENTAIRE', note_max=20)
        self.classe = Classe.objects.create(
            tenant=self.tenant, nom='CM2', code='CM2', niveau=self.niveau)
        self.type_eval = TypeEvaluation.objects.create(
            tenant=self.tenant, nom='Composition', poids=1)

    def _matiere(self, nom, note_max, coef=1):
        return Matiere.objects.create(tenant=self.tenant, classe=self.classe,
                                      nom=nom, coefficient=coef, note_max=note_max)

    def _eval(self, matiere, note_max):
        return Evaluation.objects.create(
            tenant=self.tenant, matiere=matiere, type_eval=self.type_eval,
            trimestre='T1', date_eval=datetime.date(2025, 12, 12), note_max=note_max)

    def _e(self):
        self.eleve = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, section=self.section,
            classe=self.classe, nom_complet='Awa SECK')
        return self.eleve

    def _calculer(self):
        return self.client.post('/api/academique/calculer/',
                                {'classe_id': str(self.classe.id), 'trimestre': 'T1'},
                                format='json')

    def test_deux_baremes_dans_une_meme_matiere(self):
        """Matière /20 : une compo 15/20 et une interro 8/10 (= 16/20).

        L'élève a deux bons résultats. Sa moyenne doit être proche de 15,5/20,
        et en aucun cas tomber sous la moyenne.
        """
        m = self._matiere('Mathématiques', note_max=20)
        compo  = self._eval(m, note_max=20)
        interro = self._eval(m, note_max=10)
        e = Eleve.objects.create(tenant=self.tenant, exercice=self.ex,
                                 section=self.section, classe=self.classe,
                                 nom_complet='Awa SECK')
        Note.objects.create(tenant=self.tenant, eleve=e, evaluation=compo, valeur=15)
        Note.objects.create(tenant=self.tenant, eleve=e, evaluation=interro, valeur=8)

        r = self._calculer()
        self.assertEqual(r.status_code, 200, r.content)
        moyenne = r.data['resultats'][0]['matieres'][0]['moyenne']
        self.assertAlmostEqual(moyenne, 15.5, places=1,
            msg=f"15/20 et 8/10 donnent {moyenne} au lieu de 15.5/20")

    def test_deux_matieres_de_baremes_differents(self):
        """Récitation notée /10, Mathématiques /20, même coefficient.

        8/10 et 12/20 : l'élève est au-dessus de la moyenne dans les deux.
        Sa moyenne générale doit l'être aussi.
        """
        recitation = self._matiere('Récitation', note_max=10)
        maths      = self._matiere('Mathématiques', note_max=20)
        ev_r = self._eval(recitation, note_max=10)
        ev_m = self._eval(maths, note_max=20)
        e = Eleve.objects.create(tenant=self.tenant, exercice=self.ex,
                                 section=self.section, classe=self.classe,
                                 nom_complet='Modou FALL')
        Note.objects.create(tenant=self.tenant, eleve=e, evaluation=ev_r, valeur=8)
        Note.objects.create(tenant=self.tenant, eleve=e, evaluation=ev_m, valeur=12)

        r = self._calculer()
        self.assertEqual(r.status_code, 200, r.content)
        moy_gen = r.data['resultats'][0]['moy_generale']
        # 8/10 = 16/20 ; avec 12/20 et le meme coefficient, la moyenne est 14/20.
        self.assertAlmostEqual(moy_gen, 14.0, places=1,
            msg=f"8/10 et 12/20 donnent une moyenne generale de {moy_gen} au lieu de 14/20")

    def test_la_matiere_garde_son_bareme_le_general_est_ramene(self):
        """L'arbitrage retenu : affichage par matière, agrégation au niveau.

        Récitation /10 coef 1, Maths /20 coef 1. L'élève a 8 et 12.
        Le bulletin doit montrer « 8/10 » sur la ligne Récitation — pas 16 —
        et une moyenne générale de 14/20.
        """
        recitation = self._matiere('Récitation', note_max=10)
        maths      = self._matiere('Mathématiques', note_max=20)
        Note.objects.create(tenant=self.tenant, eleve=self._e(),
                            evaluation=self._eval(recitation, 10), valeur=8)
        Note.objects.create(tenant=self.tenant, eleve=self.eleve,
                            evaluation=self._eval(maths, 20), valeur=12)
        self._calculer()

        r = self.client.get(f'/api/academique/bulletin/{self.eleve.id}/T1/')
        self.assertEqual(r.status_code, 200, r.content)
        par_nom = {m['nom']: m for m in r.data['matieres']}
        self.assertEqual(par_nom['Récitation']['moyenne'], 8.0,
                         "la recitation doit rester sur SON bareme")
        self.assertEqual(par_nom['Récitation']['note_max'], 10.0)
        self.assertEqual(par_nom['Mathématiques']['moyenne'], 12.0)
        self.assertAlmostEqual(r.data['stats']['moy_generale'], 14.0, places=1)

    def test_le_bulletin_et_le_calcul_donnent_le_meme_chiffre(self):
        """Cohérence entre deux écrans, pas une valeur en dur.

        Le moteur (écran Résultats) et le bulletin lisent la même grandeur :
        ils ne doivent jamais l'annoncer différemment.
        """
        recitation = self._matiere('Récitation', note_max=10, coef=3)
        maths      = self._matiere('Mathématiques', note_max=20, coef=2)
        Note.objects.create(tenant=self.tenant, eleve=self._e(),
                            evaluation=self._eval(recitation, 5), valeur=4)
        Note.objects.create(tenant=self.tenant, eleve=self.eleve,
                            evaluation=self._eval(maths, 20), valeur=11)

        calcul = self._calculer()
        moy_moteur = calcul.data['resultats'][0]['moy_generale']

        r = self.client.get(f'/api/academique/bulletin/{self.eleve.id}/T1/')
        moy_bulletin = r.data['stats']['moy_generale']

        self.assertEqual(moy_moteur, moy_bulletin,
            f"moteur {moy_moteur} vs bulletin {moy_bulletin}")

    def test_la_somme_des_points_redonne_la_moyenne_generale(self):
        """Ce que le parent vérifie sur le papier : Σ points / Σ coef."""
        recitation = self._matiere('Récitation', note_max=10, coef=3)
        maths      = self._matiere('Mathématiques', note_max=20, coef=2)
        Note.objects.create(tenant=self.tenant, eleve=self._e(),
                            evaluation=self._eval(recitation, 10), valeur=9)
        Note.objects.create(tenant=self.tenant, eleve=self.eleve,
                            evaluation=self._eval(maths, 20), valeur=13)
        self._calculer()

        r = self.client.get(f'/api/academique/bulletin/{self.eleve.id}/T1/')
        total_points = sum(m['points'] for m in r.data['matieres'])
        total_coef   = sum(m['coefficient'] for m in r.data['matieres'])
        self.assertAlmostEqual(total_points / total_coef,
                               r.data['stats']['moy_generale'], places=1)

    def test_une_ecole_entierement_sur_20_ne_bouge_pas(self):
        """Le cas de toutes les écoles actuelles : rien ne doit changer."""
        maths = self._matiere('Mathématiques', note_max=20, coef=4)
        hist  = self._matiere('Histoire', note_max=20, coef=2)
        Note.objects.create(tenant=self.tenant, eleve=self._e(),
                            evaluation=self._eval(maths, 20), valeur=14)
        Note.objects.create(tenant=self.tenant, eleve=self.eleve,
                            evaluation=self._eval(hist, 20), valeur=11)
        r = self._calculer()
        # (14x4 + 11x2) / 6 = 13
        self.assertAlmostEqual(r.data['resultats'][0]['moy_generale'], 13.0, places=1)


class NoteHorsBaremeTest(BaremesMelangesTest):
    """Une note ne peut pas dépasser le barème de son évaluation."""

    def test_l_api_refuse_une_note_hors_bareme(self):
        m  = self._matiere('Récitation', note_max=10)
        ev = self._eval(m, note_max=10)
        e  = self._e()
        r = self.client.post('/api/academique/notes/',
                             {'eleve': str(e.id), 'evaluation': str(ev.id), 'valeur': '18'},
                             format='json')
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn('barème', str(r.data).lower().replace('bareme', 'barème'))

    def test_l_api_accepte_la_note_au_bareme_exact(self):
        m  = self._matiere('Récitation', note_max=10)
        ev = self._eval(m, note_max=10)
        e  = self._e()
        r = self.client.post('/api/academique/notes/',
                             {'eleve': str(e.id), 'evaluation': str(ev.id), 'valeur': '10'},
                             format='json')
        self.assertEqual(r.status_code, 201, r.content)

    def test_la_grille_de_saisie_refuse_aussi_et_le_dit(self):
        """bulk_save écrit sans passer par le serializer : même règle."""
        m  = self._matiere('Récitation', note_max=10)
        ev = self._eval(m, note_max=10)
        bon, mauvais = self._e(), self._e()
        r = self.client.post('/api/academique/notes/bulk_save/', {'notes': [
            {'eleve': str(bon.id),     'evaluation': str(ev.id), 'valeur': 9},
            {'eleve': str(mauvais.id), 'evaluation': str(ev.id), 'valeur': 18},
        ]}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data['created'], 1)
        self.assertEqual(r.data['errors'], 1)
        self.assertEqual(len(r.data['refusees']), 1)
        self.assertEqual(r.data['refusees'][0]['eleve'], str(mauvais.id))
        self.assertFalse(Note.objects.filter(eleve=mauvais).exists(),
                         "la note hors bareme ne doit pas entrer en base")

    def test_un_absent_n_est_pas_juge_sur_sa_note(self):
        m  = self._matiere('Récitation', note_max=10)
        ev = self._eval(m, note_max=10)
        e  = self._e()
        r = self.client.post('/api/academique/notes/bulk_save/', {'notes': [
            {'eleve': str(e.id), 'evaluation': str(ev.id), 'valeur': 0, 'absent': True},
        ]}, format='json')
        self.assertEqual(r.data['created'], 1, r.data)
        self.assertEqual(r.data['errors'], 0)
