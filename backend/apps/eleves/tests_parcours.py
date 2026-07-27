"""Parcours d'un élève, base des anciens élèves, et sort des sortants endettés.

Ce que ces tests protègent :
  - un enfant qui reste plusieurs années se lit d'un seul tenant, de son
    entrée à sa sortie ;
  - la dette affichée n'est PAS la somme des restes annuels — un impayé
    reconduit d'année en année serait compté autant de fois qu'il a traversé
    d'exercices ;
  - un diplômé qui part en devant garde sa créance au bilan (à-nouveaux
    411/890) SANS revenir dans la liste des élèves ni dans les effectifs.
"""
import datetime

from rest_framework.test import APITestCase

from apps.comptabilite.models import JournalEntry
from apps.eleves.matricules import identite_nouvel_eleve
from apps.eleves.models import Eleve, Section
from apps.eleves.parcours import anciens_eleves, construire_parcours
from apps.paiements.models import Exercice, Paiement
from apps.paiements.report_reliquats import SOURCE_REPORT, reporter_reliquats
from apps.tenants.models import Tenant
from apps.users.models import User


class ParcoursBase(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul', code_etablissement='SHE')
        self.user = User.objects.create_user('a@a.sn', 'x', nom='A',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)

        self.ex1 = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2023-2024', nb_mensualites=10,
            date_debut=datetime.date(2023, 10, 1), date_fin=datetime.date(2024, 7, 31))
        self.ex2 = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2024-2025', nb_mensualites=10,
            date_debut=datetime.date(2024, 10, 1), date_fin=datetime.date(2025, 7, 31))
        self.ex3 = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2025-2026', nb_mensualites=10,
            date_debut=datetime.date(2025, 10, 1), date_fin=datetime.date(2026, 7, 31))
        # Dû annuel = 50 000 + 10 × 25 000 = 300 000
        self.section = Section.objects.create(
            tenant=self.tenant, nom='Externat', frais_inscription=50000,
            frais_mensualite=25000)

    def _eleve(self, nom, exercice, **extra):
        identite = identite_nouvel_eleve(self.tenant, exercice)
        return Eleve.objects.create(
            tenant=self.tenant, exercice=exercice, section=self.section,
            nom_complet=nom, date_inscription=exercice.date_debut,
            **identite, **extra)

    def _payer(self, eleve, montant):
        return Paiement.objects.create(
            tenant=self.tenant, exercice=eleve.exercice, eleve=eleve,
            no_piece=f"REC-{Paiement.objects.count() + 1:04d}",
            montant_mensualite=montant)


class ParcoursTest(ParcoursBase):
    def test_une_seule_annee(self):
        eleve = self._eleve('Fatou MBAYE', self.ex3)
        p = construire_parcours(eleve)
        self.assertEqual(p['nb_annees'], 1)
        self.assertEqual(p['annee_entree'], '2025-2026')
        self.assertFalse(p['est_sorti'])

    def test_trois_annees_chainees(self):
        eleve = self._eleve('Fatou MBAYE', self.ex1)
        self._payer(eleve, 100000)          # reste 200 000
        reporter_reliquats(self.ex1, self.ex2)
        fiche2 = Eleve.objects.get(exercice=self.ex2, nom_complet='Fatou MBAYE')
        self._payer(fiche2, 50000)
        reporter_reliquats(self.ex2, self.ex3)
        fiche3 = Eleve.objects.get(exercice=self.ex3, nom_complet='Fatou MBAYE')

        p = construire_parcours(fiche3)
        self.assertEqual(p['nb_annees'], 3)
        self.assertEqual([a['annee'] for a in p['annees']],
                         ['2023-2024', '2024-2025', '2025-2026'])
        self.assertEqual(p['annee_entree'], '2023-2024')
        self.assertEqual(p['total_paye'], 150000.0)

    def test_le_parcours_se_lit_depuis_n_importe_quelle_fiche(self):
        eleve = self._eleve('Fatou MBAYE', self.ex1)
        reporter_reliquats(self.ex1, self.ex2)
        depuis_la_premiere = construire_parcours(eleve)
        self.assertEqual(depuis_la_premiere['nb_annees'], 2)

    def test_la_dette_n_est_pas_la_somme_des_restes_annuels(self):
        """L'impayé de la 1re année est reconduit en reliquat les années
        suivantes : le sommer donnerait trois fois la même ardoise."""
        eleve = self._eleve('Fatou MBAYE', self.ex1)
        self._payer(eleve, 300000)          # année 1 soldée
        reporter_reliquats(self.ex1, self.ex2)
        self.assertFalse(Eleve.objects.filter(exercice=self.ex2).exists())

        # Deuxième enfant, lui, laisse une ardoise
        autre = self._eleve('Moussa NDIAYE', self.ex1)
        self._payer(autre, 250000)          # reste 50 000
        reporter_reliquats(self.ex1, self.ex2)
        fiche2 = Eleve.objects.get(exercice=self.ex2, nom_complet='Moussa NDIAYE')
        reporter_reliquats(self.ex2, self.ex3)
        fiche3 = Eleve.objects.get(exercice=self.ex3, nom_complet='Moussa NDIAYE')

        p = construire_parcours(fiche3)
        somme_naive = sum(a['du_global'] for a in p['annees'])
        self.assertGreater(somme_naive, p['du_actuel'])       # le piège existe
        self.assertEqual(p['du_actuel'], fiche3.reste_a_payer_global)

    def test_api(self):
        eleve = self._eleve('Fatou MBAYE', self.ex1)
        reporter_reliquats(self.ex1, self.ex2)
        r = self.client.get(f'/api/eleves/{eleve.id}/parcours/')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['nb_annees'], 2)
        self.assertEqual(r.data['matricule'], eleve.matricule)

    def test_api_eleve_inconnu(self):
        autre = Tenant.objects.create(nom='Voisine', code_etablissement='VOI')
        ex = Exercice.objects.create(
            tenant=autre, annee_scolaire='2025-2026', nb_mensualites=10,
            date_debut=datetime.date(2025, 10, 1), date_fin=datetime.date(2026, 7, 31))
        etranger = Eleve.objects.create(tenant=autre, exercice=ex, numero=1,
                                        nom_complet='Voisin',
                                        date_inscription=ex.date_debut)
        r = self.client.get(f'/api/eleves/{etranger.id}/parcours/')
        self.assertEqual(r.status_code, 404)


class SortantEndetteTest(ParcoursBase):
    def _diplome_endette(self):
        eleve = self._eleve('Fatou MBAYE', self.ex2, statut='DIPLOME')
        self._payer(eleve, 250000)          # reste 50 000
        reporter_reliquats(self.ex2, self.ex3)
        return eleve, Eleve.objects.get(exercice=self.ex3, nom_complet='Fatou MBAYE')

    def test_la_creance_reste_au_bilan(self):
        _, fiche = self._diplome_endette()
        self.assertTrue(fiche.fiche_creance)
        self.assertEqual(float(fiche.reliquat_anterieur), 50000.0)
        ecritures = JournalEntry.objects.filter(
            tenant=self.tenant, exercice=self.ex3,
            source=SOURCE_REPORT, source_id=fiche.id)
        self.assertEqual(
            {e.no_compte: float(e.debit or 0) + float(e.credit or 0) for e in ecritures},
            {'411': 50000.0, '890': 50000.0})

    def test_absent_de_la_liste_des_eleves(self):
        _, fiche = self._diplome_endette()
        r = self.client.get('/api/eleves/liste/', {'exercice': str(self.ex3.id)})
        self.assertEqual(r.status_code, 200)
        ids = [e['id'] for e in r.data['results']]
        self.assertNotIn(str(fiche.id), ids)

    def test_visible_sur_demande_explicite(self):
        _, fiche = self._diplome_endette()
        r = self.client.get('/api/eleves/liste/',
                            {'exercice': str(self.ex3.id), 'creances': '1'})
        self.assertIn(str(fiche.id), [e['id'] for e in r.data['results']])

    def test_un_eleve_inscrit_est_bien_reinscrit_normalement(self):
        eleve = self._eleve('Moussa NDIAYE', self.ex2)   # statut INSCRIT
        self._payer(eleve, 250000)
        reporter_reliquats(self.ex2, self.ex3)
        fiche = Eleve.objects.get(exercice=self.ex3, nom_complet='Moussa NDIAYE')
        self.assertFalse(fiche.fiche_creance)
        r = self.client.get('/api/eleves/liste/', {'exercice': str(self.ex3.id)})
        self.assertIn(str(fiche.id), [e['id'] for e in r.data['results']])


class AnciensElevesTest(ParcoursBase):
    def test_un_diplome_apparait_avec_son_historique(self):
        eleve = self._eleve('Fatou MBAYE', self.ex1)
        self._payer(eleve, 300000)
        reporter_reliquats(self.ex1, self.ex2)          # soldé : pas de report
        suite = self._eleve('Fatou MBAYE', self.ex2, statut='DIPLOME')
        suite.matricule = eleve.matricule
        suite.save(update_fields=['matricule'])
        self._payer(suite, 300000)

        r = anciens_eleves(self.tenant)
        self.assertEqual(r['nb'], 1)
        ligne = r['lignes'][0]
        self.assertEqual(ligne['statut'], 'DIPLOME')
        self.assertEqual(ligne['nb_annees'], 2)
        self.assertEqual(ligne['total_paye'], 600000.0)
        self.assertEqual(ligne['annee_sortie'], '2024-2025')

    def test_un_eleve_inscrit_n_y_est_pas(self):
        self._eleve('Fatou MBAYE', self.ex3)
        self.assertEqual(anciens_eleves(self.tenant)['nb'], 0)

    def test_le_statut_retenu_est_celui_de_la_derniere_annee(self):
        """Un enfant qui abandonne puis revient n'est plus un ancien."""
        abandon = self._eleve('Moussa NDIAYE', self.ex1, statut='ABANDONNE')
        retour = self._eleve('Moussa NDIAYE', self.ex2, eleve_precedent=abandon)
        retour.matricule = abandon.matricule
        retour.save(update_fields=['matricule'])
        self.assertEqual(anciens_eleves(self.tenant)['nb'], 0)

    def test_solde_du_d_un_sortant_endette(self):
        eleve = self._eleve('Fatou MBAYE', self.ex2, statut='DIPLOME')
        self._payer(eleve, 250000)
        reporter_reliquats(self.ex2, self.ex3)

        r = anciens_eleves(self.tenant)
        self.assertEqual(r['nb'], 1)
        self.assertEqual(r['lignes'][0]['solde_du'], 50000.0)
        self.assertEqual(r['total_du'], 50000.0)

    def test_recherche_par_matricule_et_par_nom(self):
        eleve = self._eleve('Fatou MBAYE', self.ex2, statut='DIPLOME')
        self.assertEqual(anciens_eleves(self.tenant, recherche='fatou')['nb'], 1)
        self.assertEqual(anciens_eleves(self.tenant, recherche=eleve.matricule)['nb'], 1)
        self.assertEqual(anciens_eleves(self.tenant, recherche='zzz')['nb'], 0)

    def test_filtre_par_statut(self):
        self._eleve('Diplomee', self.ex2, statut='DIPLOME')
        self._eleve('Transfere', self.ex2, statut='TRANSFERE')
        self.assertEqual(anciens_eleves(self.tenant, statut='DIPLOME')['nb'], 1)
        self.assertEqual(anciens_eleves(self.tenant)['nb_diplomes'], 1)

    def test_isolation_tenant(self):
        autre = Tenant.objects.create(nom='Voisine', code_etablissement='VOI')
        ex = Exercice.objects.create(
            tenant=autre, annee_scolaire='2024-2025', nb_mensualites=10,
            date_debut=datetime.date(2024, 10, 1), date_fin=datetime.date(2025, 7, 31))
        Eleve.objects.create(tenant=autre, exercice=ex, numero=1, statut='DIPLOME',
                             nom_complet='Voisin', date_inscription=ex.date_debut)
        self._eleve('Fatou MBAYE', self.ex2, statut='DIPLOME')
        self.assertEqual([l['nom_complet'] for l in anciens_eleves(self.tenant)['lignes']],
                         ['Fatou MBAYE'])

    def test_api(self):
        self._eleve('Fatou MBAYE', self.ex2, statut='DIPLOME')
        r = self.client.get('/api/eleves/anciens/')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['nb'], 1)


class ParcoursPDFTest(ParcoursBase):
    def test_pdf_genere(self):
        eleve = self._eleve('Fatou MBAYE', self.ex1)
        self._payer(eleve, 100000)
        reporter_reliquats(self.ex1, self.ex2)
        r = self.client.get(f'/api/eleves/{eleve.id}/parcours-pdf/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')
        self.assertTrue(r.content.startswith(b'%PDF'))

    def test_pdf_eleve_inconnu(self):
        import uuid
        r = self.client.get(f'/api/eleves/{uuid.uuid4()}/parcours-pdf/')
        self.assertEqual(r.status_code, 404)
