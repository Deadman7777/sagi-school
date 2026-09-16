"""Établissement hybride : programme français et programme arabe dans la même classe.

Chaque programme a son bulletin, sa moyenne générale et son rang. Mélanger les
deux produirait une moyenne qui ne correspond à aucun bulletin remis aux
familles. La fiche pédagogique, elle, doit dire la même chose que le bulletin :
on teste la cohérence entre les écrans, pas seulement des valeurs.
"""
import datetime
import io
import re

from rest_framework.test import APITestCase

from apps.academique.models import Classe, Evaluation, Matiere, NiveauScolaire, Note, TypeEvaluation
from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant
from apps.users.models import User

ANNEE = '2025-2026'


class ProgrammesBase(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Institut Al Falah', ville='Rufisque',
                                            programmes_hybrides=True,
                                            periode_scolaire='TRIMESTRE', nb_periodes=3)
        self.user = User.objects.create_user('dir@falah.sn', 'x', nom='Directeur',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(tenant=self.tenant, annee_scolaire=ANNEE,
                                          date_debut=datetime.date(2025, 10, 1),
                                          date_fin=datetime.date(2026, 7, 31))
        niveau = NiveauScolaire.objects.create(tenant=self.tenant, nom='Élémentaire', code='ELEMENTAIRE')
        self.classe = Classe.objects.create(tenant=self.tenant, niveau=niveau, nom='CM1')
        section = Section.objects.create(tenant=self.tenant, nom='Élémentaire')
        self.compo = TypeEvaluation.objects.create(tenant=self.tenant, nom='Composition', poids=1)

        def matiere(nom, programme, coef):
            return Matiere.objects.create(tenant=self.tenant, classe=self.classe, nom=nom,
                                          programme=programme, coefficient=coef, note_max=20)
        self.maths = matiere('Mathématiques', 'FR', 2)
        self.francais = matiere('Français', 'FR', 1)
        self.coran = matiere('القرآن الكريم', 'AR', 2)
        self.arabe = matiere('اللغة العربية', 'AR', 1)

        def eleve(nom):
            return Eleve.objects.create(tenant=self.tenant, exercice=self.ex, section=section,
                                        classe=self.classe, nom_complet=nom)
        self.awa = eleve('Awa NDIAYE')
        self.omar = eleve('Omar FALL')

        # Awa : forte en français, faible en arabe. Omar : l'inverse.
        self._notes('T1', {self.awa: {self.maths: 16, self.francais: 15, self.coran: 9, self.arabe: 11},
                           self.omar: {self.maths: 8, self.francais: 10, self.coran: 18, self.arabe: 16}})
        self._notes('T2', {self.awa: {self.maths: 17, self.francais: 12, self.coran: 8, self.arabe: 13},
                           self.omar: {self.maths: 9, self.francais: 11, self.coran: 17, self.arabe: 15}})

    def _notes(self, periode, table):
        evals = {}
        for eleve, notes in table.items():
            for m, valeur in notes.items():
                if m not in evals:
                    evals[m] = Evaluation.objects.create(
                        tenant=self.tenant, matiere=m, type_eval=self.compo, trimestre=periode,
                        date_eval=datetime.date(2026, 1, 15), note_max=20)
                Note.objects.create(tenant=self.tenant, eleve=eleve, evaluation=evals[m], valeur=valeur)

    def _calculer(self, periode, programme=None):
        payload = {'classe_id': str(self.classe.id), 'trimestre': periode, 'annee_scolaire': ANNEE}
        if programme:
            payload['programme'] = programme
        r = self.client.post('/api/academique/calculer/', payload, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        return r.data

    def _tout_calculer(self):
        for p in ('T1', 'T2'):
            for prog in ('FR', 'AR'):
                self._calculer(p, prog)

    def _bulletin(self, eleve, periode, programme):
        r = self.client.get(f'/api/academique/bulletin/{eleve.id}/{periode}/',
                            {'annee': ANNEE, 'programme': programme})
        self.assertEqual(r.status_code, 200, r.content)
        return r.data


class CalculParProgrammeTest(ProgrammesBase):
    def test_le_calcul_ne_prend_que_les_matieres_du_programme(self):
        data = self._calculer('T1', 'AR')
        awa = next(r for r in data['resultats'] if r['eleve_id'] == str(self.awa.id))
        self.assertEqual({m['matiere'] for m in awa['matieres']}, {'القرآن الكريم', 'اللغة العربية'})
        # (9×2 + 11×1) / 3
        self.assertEqual(awa['moy_generale'], round(29 / 3, 2))

    def test_chaque_programme_a_son_rang(self):
        self._tout_calculer()
        self.assertEqual(self._bulletin(self.awa, 'T1', 'FR')['stats']['rang'], 1)
        self.assertEqual(self._bulletin(self.awa, 'T1', 'AR')['stats']['rang'], 2)
        self.assertEqual(self._bulletin(self.omar, 'T1', 'AR')['stats']['rang'], 1)

    def test_le_bulletin_ne_melange_pas_les_programmes(self):
        self._tout_calculer()
        fr = self._bulletin(self.awa, 'T1', 'FR')
        self.assertEqual([m['nom'] for m in fr['matieres']], ['Français', 'Mathématiques'])
        self.assertEqual(fr['stats']['moy_generale'], round((16 * 2 + 15) / 3, 2))

    def test_moyenne_de_classe_identique_ecran_et_pdf(self):
        """Le bulletin JSON calculait la moyenne des notes de matière, le PDF
        la moyenne des moyennes générales : deux chiffres sous le même nom."""
        self._tout_calculer()
        attendu = round(((16 * 2 + 15) / 3 + (8 * 2 + 10) / 3) / 2, 2)
        self.assertEqual(self._bulletin(self.awa, 'T1', 'FR')['stats']['moy_classe'], attendu)

    def test_ecole_non_hybride_inchangee(self):
        """Sans programme demandé, toutes les matières comptent — comme avant."""
        data = self._calculer('T1')
        awa = next(r for r in data['resultats'] if r['eleve_id'] == str(self.awa.id))
        self.assertEqual(len(awa['matieres']), 4)
        r = self.client.get(f'/api/academique/bulletin/{self.awa.id}/T1/', {'annee': ANNEE})
        self.assertEqual(len(r.data['matieres']), 4)

    def test_historique_un_bulletin_par_programme(self):
        self._tout_calculer()
        r = self.client.get('/api/academique/historique-bulletins/', {'annee': ANNEE, 'trimestre': 'T1'})
        awa = [b for b in r.data['bulletins'] if b['eleve_id'] == str(self.awa.id)]
        self.assertEqual(sorted(b['programme'] for b in awa), ['AR', 'FR'])
        fr = next(b for b in awa if b['programme'] == 'FR')
        self.assertEqual(fr['moy_generale'], self._bulletin(self.awa, 'T1', 'FR')['stats']['moy_generale'])

    def test_filtre_des_matieres_par_programme(self):
        r = self.client.get('/api/academique/matieres/', {'classe': str(self.classe.id), 'programme': 'AR'})
        self.assertEqual({m['nom'] for m in r.data['results']}, {'القرآن الكريم', 'اللغة العربية'})

    def test_la_copie_des_matieres_garde_le_programme(self):
        cm2 = Classe.objects.create(tenant=self.tenant, niveau=self.classe.niveau, nom='CM2')
        r = self.client.post(f'/api/academique/classes/{self.classe.id}/copier-matieres/',
                             {'cibles': [str(cm2.id)]}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(Matiere.objects.get(classe=cm2, nom='القرآن الكريم').programme, 'AR')


class BulletinsPdfTest(ProgrammesBase):
    def test_bulletin_arabe(self):
        self._tout_calculer()
        r = self.client.get(f'/api/academique/bulletin-pdf/{self.awa.id}/T2/',
                            {'annee': ANNEE, 'programme': 'AR'})
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertTrue(r.content.startswith(b'%PDF'))
        self.assertIn('bulletin_ar_', r['Content-Disposition'])

    def test_gabarit_arabe_sans_balise_residuelle(self):
        from django.template.loader import render_to_string
        from apps.academique.libelles import contexte_bulletin_ar
        from core.arabe import shape_ar
        self._tout_calculer()
        # Contexte minimal mais complet, comme le construit la vue
        ctx = {
            'tenant': self.tenant, 'annee': ANNEE, 'trimestre': 'T2', 'note_max': 20,
            'eval_columns': [{'key': ('Composition', 1), 'label': 'Composition', 'width': 34}],
            'eleve': {'nom_complet': 'Awa NDIAYE', 'matricule': '—', 'date_naissance': '—',
                      'classe': 'CM1', 'rang': 2},
            'matieres': [{'nom': 'القرآن الكريم', 'coefficient': 2.0, 'note_max': 20, 'moyenne': '8',
                          'points': '16', 'rang': 2, 'appreciation': 'Insuffisant', 'notes_cells': ['8']}],
            'total_coef': 2.0, 'total_points': 16.0,
            'stats': {'moy_generale': 8.0, 'moy_classe': 12.5, 'moy_max': 17.0, 'moy_min': 8.0, 'nb_eleves': 2},
            'appreciation_generale': 'Insuffisant', 'decision': 'Avertissement de travail',
            'is_final': False, 'decision_positive': False,
        }
        html = render_to_string('pdf/bulletin_ar.html', contexte_bulletin_ar(ctx, self.tenant, []))
        self.assertNotIn('{%', html)
        self.assertNotIn('{#', html)
        self.assertIn(shape_ar('امتحان'), html)          # « Composition »
        self.assertIn(shape_ar('غير كاف'), html)         # « Insuffisant »
        self.assertIn(shape_ar('الثلاثي الثاني'), html)  # « Trimestre 2 »
        self.assertIn(shape_ar('إنذار في العمل'), html)
        # Largeurs de colonnes : 100 %
        largeurs = [int(x) for x in re.findall(r'<col style="width:(\d+)%">',
                                               html.split('tbl-notes mb4')[1].split('</colgroup>')[0])]
        self.assertEqual(sum(largeurs), 100)

    def test_bulletin_francais_toujours_disponible(self):
        self._tout_calculer()
        r = self.client.get(f'/api/academique/bulletin-pdf/{self.awa.id}/T2/',
                            {'annee': ANNEE, 'programme': 'FR'})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.content.startswith(b'%PDF'))


class FichePedagogiqueTest(ProgrammesBase):
    def _fiche(self, eleve, programme):
        r = self.client.get(f'/api/academique/fiche-pedagogique/{eleve.id}/',
                            {'annee': ANNEE, 'programme': programme})
        self.assertEqual(r.status_code, 200, r.content)
        return r.data

    def test_points_forts_faibles_et_a_ameliorer(self):
        self._tout_calculer()
        fiche = self._fiche(self.awa, 'FR')
        self.assertEqual(fiche['points_forts'], ['Mathématiques'])      # 17
        self.assertEqual(fiche['points_faibles'], [])
        # Français : 15 → 12, une baisse de 3 points
        self.assertEqual(fiche['a_ameliorer'], [{'nom': 'Français', 'raisons': ['BAISSE']}])

        ar = self._fiche(self.awa, 'AR')
        self.assertEqual(ar['points_faibles'], ['القرآن الكريم'])        # 8
        self.assertIn('اللغة العربية', ar['en_progres'])                 # 11 → 13

    def test_la_fiche_dit_la_meme_chose_que_le_bulletin(self):
        self._tout_calculer()
        for programme in ('FR', 'AR'):
            fiche = self._fiche(self.omar, programme)
            for p in fiche['periodes']:
                bulletin = self._bulletin(self.omar, p['code'], programme)
                self.assertEqual(p['moyenne'], bulletin['stats']['moy_generale'])
                self.assertEqual(p['rang'], bulletin['stats']['rang'])
                self.assertEqual(p['moy_classe'], bulletin['stats']['moy_classe'])

    def test_evolution_generale(self):
        self._tout_calculer()
        fiche = self._fiche(self.awa, 'FR')
        t1, t2 = fiche['periodes']
        self.assertEqual(fiche['evolution_generale'], round(t2['moyenne'] - t1['moyenne'], 2))

    def test_sans_note_la_fiche_est_vide_mais_valide(self):
        fiche = self._fiche(self.awa, 'FR')
        self.assertEqual(fiche['periodes'], [])
        r = self.client.get(f'/api/academique/fiche-pedagogique-pdf/{self.awa.id}/',
                            {'annee': ANNEE, 'programme': 'FR'})
        self.assertEqual(r.status_code, 200)

    def test_pdf_francais_et_arabe(self):
        self._tout_calculer()
        for programme, suffixe in (('FR', '_fr.pdf'), ('AR', '_ar.pdf')):
            r = self.client.get(f'/api/academique/fiche-pedagogique-pdf/{self.awa.id}/',
                                {'annee': ANNEE, 'programme': programme})
            self.assertEqual(r.status_code, 200, r.content[:300])
            self.assertTrue(r.content.startswith(b'%PDF'))
            self.assertIn(suffixe, r['Content-Disposition'])

    def test_gabarit_fiche_sans_balise_residuelle(self):
        from django.template.loader import render_to_string
        from django.utils import timezone
        from apps.academique.libelles import contexte_fiche
        from apps.academique.resultats import fiche_pedagogique
        self._tout_calculer()
        for langue, programme in (('fr', 'FR'), ('ar', 'AR')):
            fiche = fiche_pedagogique(self.tenant, self.awa, ANNEE, programme)
            ctx = contexte_fiche(fiche, self.tenant, self.awa, 'CM1', langue)
            ctx['date_edition'] = timezone.localdate()
            html = render_to_string('pdf/fiche_pedagogique.html', ctx)
            self.assertNotIn('{%', html)
            self.assertNotIn('{#', html)
        self.assertIn('Un soutien est recommandé', ''.join(
            contexte_fiche(fiche_pedagogique(self.tenant, self.omar, ANNEE, 'FR'),
                           self.tenant, self.omar, 'CM1', 'fr')['recommandations']))

    def test_eleve_d_une_autre_ecole_introuvable(self):
        autre = Tenant.objects.create(nom='Autre')
        self.client.force_authenticate(User.objects.create_user(
            'b@b.sn', 'x', nom='B', role='ADMIN_ECOLE', tenant=autre))
        r = self.client.get(f'/api/academique/fiche-pedagogique/{self.awa.id}/', {'annee': ANNEE})
        self.assertEqual(r.status_code, 404)
