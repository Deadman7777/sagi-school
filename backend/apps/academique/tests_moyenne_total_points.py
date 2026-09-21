"""Moyenne générale « total des points / total des barèmes » (Shoumoul).

L'élève de référence, donné par la directrice : quatorze notes, tous les
coefficients à 1,

    10/10 10/10 10/10 4/5 5/5 10/10 9/10 10/10 10/10 10/10 10/10 20/20 20/20 7/10

Elle additionne les points : 145 sur 150, soit 9,67/10 (elle écrit 9,66). Le
calcul par matières, lui, fait la moyenne de quatorze notes ramenées sur 20 :
une récitation sur /5 y pèse autant qu'une composition sur /20.

Règles vérifiées :
  - en mode POINTS, 145/150 → 9,67/10 ou 19,33/20, que les notes soient dans
    quatorze matières ou toutes dans la même ;
  - le bulletin retombe sur le calcul : total 145, total des poids 15 (/10),
    moyenne 9,67 — et l'analyse comme l'historique lisent la même moyenne ;
  - le mode MATIERES ne change pas (défaut : aucune école ne bouge) ;
  - changer de règle efface les moyennes de l'année, qui seraient fausses.
"""
import datetime

from rest_framework.test import APITestCase

from apps.academique.models import (BulletinCache, Classe, Evaluation, Matiere,
                                    NiveauScolaire, Note, TypeEvaluation)
from apps.academique.resultats import situation_periode
from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant
from apps.users.models import User

# (note, barème) — l'élève de la directrice
NOTES = [(10, 10), (10, 10), (10, 10), (4, 5), (5, 5), (10, 10), (9, 10),
         (10, 10), (10, 10), (10, 10), (10, 10), (20, 20), (20, 20), (7, 10)]


class MoyenneTotalPointsBase(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul')
        self.user = User.objects.create_user('dir@shoumoul.sn', 'x', nom='Directrice',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2025-2026', cloture=False,
            date_debut=datetime.date(2025, 10, 1), date_fin=datetime.date(2026, 7, 31))
        self.section = Section.objects.create(tenant=self.tenant, nom='Hifz')
        # Niveau créé depuis la section : /20 par défaut, comme chez Shoumoul.
        self.niveau = NiveauScolaire.objects.create(tenant=self.tenant, nom='Hifz',
                                                    code='HIFZ', note_max=20)
        self.classe = Classe.objects.create(tenant=self.tenant, nom='Hifz 1', code='H1',
                                            niveau=self.niveau)
        self.type_eval = TypeEvaluation.objects.create(tenant=self.tenant, nom='Évaluation', poids=1)
        self.eleve = Eleve.objects.create(tenant=self.tenant, exercice=self.ex,
                                          section=self.section, classe=self.classe,
                                          nom_complet='Abdou DIOP')

    def _regler(self, mode, bareme=None):
        self.tenant.calcul_moyenne = mode
        self.tenant.bareme_moyenne = bareme
        self.tenant.save()

    def _eval(self, matiere, bareme):
        return Evaluation.objects.create(tenant=self.tenant, matiere=matiere,
                                         type_eval=self.type_eval, trimestre='T1',
                                         date_eval=datetime.date(2025, 12, 12), note_max=bareme)

    def _une_matiere_par_note(self):
        for i, (note, bareme) in enumerate(NOTES):
            m = Matiere.objects.create(tenant=self.tenant, classe=self.classe, nom=f'Matière {i + 1}',
                                       coefficient=1, note_max=bareme, ordre=i)
            Note.objects.create(tenant=self.tenant, eleve=self.eleve,
                                evaluation=self._eval(m, bareme), valeur=note)

    def _toutes_dans_une_matiere(self):
        m = Matiere.objects.create(tenant=self.tenant, classe=self.classe, nom='Coran',
                                   coefficient=1, note_max=10)
        for note, bareme in NOTES:
            Note.objects.create(tenant=self.tenant, eleve=self.eleve,
                                evaluation=self._eval(m, bareme), valeur=note)

    def _calculer(self):
        r = self.client.post('/api/academique/calculer/',
                             {'classe_id': str(self.classe.id), 'trimestre': 'T1'}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        return r.data['resultats'][0]


class ModePointsTest(MoyenneTotalPointsBase):
    def test_la_moyenne_de_la_directrice_sur_10(self):
        self._regler('POINTS', 10)
        self._une_matiere_par_note()
        r = self._calculer()
        self.assertEqual(r['moy_generale'], 9.67)
        self.assertEqual(r['total_points'], 145)
        self.assertEqual(r['total_coef'], 15)

    def test_sur_20(self):
        self._regler('POINTS', 20)
        self._une_matiere_par_note()
        self.assertEqual(self._calculer()['moy_generale'], 19.33)

    def test_meme_resultat_si_toutes_les_notes_sont_dans_une_matiere(self):
        self._regler('POINTS', 10)
        self._toutes_dans_une_matiere()
        r = self._calculer()
        self.assertEqual(r['moy_generale'], 9.67)
        # La matière s'affiche sur son barème : 145/150 d'une matière sur /10.
        self.assertEqual(r['matieres'][0]['moyenne'], 9.67)

    def test_une_matiere_sur_20_pese_deux_fois_une_matiere_sur_10(self):
        self._regler('POINTS', 10)
        self._une_matiere_par_note()
        poids = {m['note_max']: m['coefficient'] for m in self._calculer()['matieres']}
        self.assertEqual(poids, {10.0: 1.0, 5.0: 0.5, 20.0: 2.0})

    def test_le_coefficient_de_la_matiere_compte_toujours(self):
        """Coefficient 2 sur une matière : ses points et ses barèmes doublent."""
        self._regler('POINTS', 10)
        m1 = Matiere.objects.create(tenant=self.tenant, classe=self.classe, nom='Coran',
                                    coefficient=2, note_max=10)
        m2 = Matiere.objects.create(tenant=self.tenant, classe=self.classe, nom='Tajwid',
                                    coefficient=1, note_max=20)
        Note.objects.create(tenant=self.tenant, eleve=self.eleve, evaluation=self._eval(m1, 10), valeur=8)
        Note.objects.create(tenant=self.tenant, eleve=self.eleve, evaluation=self._eval(m2, 20), valeur=10)
        # (8×2 + 10) / (10×2 + 20) × 10 = 26/40 × 10 = 6,5
        self.assertEqual(self._calculer()['moy_generale'], 6.5)

    def test_le_bulletin_retombe_sur_le_calcul(self):
        self._regler('POINTS', 10)
        self._une_matiere_par_note()
        r = self._calculer()
        s = situation_periode(self.tenant, self.eleve, 'T1', '2025-2026')
        self.assertEqual(s['moy_generale'], r['moy_generale'])
        self.assertEqual(s['total_points'], 145)
        self.assertEqual(s['total_coef'], 15)
        bulletin = self.client.get(f'/api/academique/bulletin/{self.eleve.id}/T1/')
        self.assertEqual(bulletin.status_code, 200, bulletin.content)
        self.assertEqual(bulletin.data['stats']['moy_generale'], 9.67)
        pdf = self.client.get(f'/api/academique/bulletin-pdf/{self.eleve.id}/T1/')
        self.assertEqual(pdf.status_code, 200)

    def test_analyse_et_historique_lisent_la_meme_moyenne(self):
        self._regler('POINTS', 10)
        self._une_matiere_par_note()
        self._calculer()
        historique = self.client.get('/api/academique/historique-bulletins/')
        self.assertEqual(historique.status_code, 200, historique.content)
        lignes = historique.data['bulletins']
        self.assertEqual(lignes[0]['moy_generale'], 9.67)
        analyse = self.client.get('/api/academique/analyse/')
        self.assertEqual(analyse.status_code, 200, analyse.content)
        self.assertIn('9.67', str(analyse.data))


class ModeMatieresInchangeTest(MoyenneTotalPointsBase):
    def test_par_defaut_la_moyenne_des_matieres(self):
        self.assertEqual(self.tenant.calcul_moyenne, 'MATIERES')
        self._une_matiere_par_note()
        r = self._calculer()
        # Quatorze notes ramenées sur 20 : 268 / 14.
        self.assertEqual(r['moy_generale'], 19.14)
        self.assertFalse(BulletinCache.objects.exclude(poids=None).exists())

    def test_bareme_de_l_ecole_sur_10_en_mode_matieres(self):
        self._regler('MATIERES', 10)
        self._une_matiere_par_note()
        self.assertEqual(self._calculer()['moy_generale'], 9.57)


class ChangementDeRegleTest(MoyenneTotalPointsBase):
    def test_changer_de_regle_efface_les_moyennes_de_l_annee(self):
        self._une_matiere_par_note()
        self._calculer()
        self.assertEqual(BulletinCache.objects.count(), 14)
        r = self.client.patch('/api/tenants/mon_ecole/',
                              {'calcul_moyenne': 'POINTS', 'bareme_moyenne': 10}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data['moyennes_a_recalculer'], 14)
        self.assertEqual(BulletinCache.objects.count(), 0)
        self.assertEqual(self._calculer()['moy_generale'], 9.67)

    def test_enregistrer_sans_rien_changer_ne_touche_a_rien(self):
        self._une_matiere_par_note()
        self._calculer()
        r = self.client.patch('/api/tenants/mon_ecole/', {'nb_periodes': 3}, format='json')
        self.assertNotIn('moyennes_a_recalculer', r.data)
        self.assertEqual(BulletinCache.objects.count(), 14)

    def test_bareme_negatif_refuse(self):
        r = self.client.patch('/api/tenants/mon_ecole/', {'bareme_moyenne': -10}, format='json')
        self.assertEqual(r.status_code, 400)
