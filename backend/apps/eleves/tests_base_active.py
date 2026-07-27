"""Tests : base réelle des élèves actifs, anciens élèves, effectifs par classe.

Trois besoins liés : un élève qui sort ne doit plus compter parmi les actifs,
son alerte doit cesser de grossir, et l'école doit pouvoir enregistrer un
diplômé d'avant la migration dont aucune fiche n'existe.
"""
import datetime

from rest_framework.test import APITestCase

from apps.academique.models import Classe
from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant
from apps.users.models import User


class BaseActiveTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul', code_etablissement='CSE')
        self.user = User.objects.create_user(
            'a@a.sn', 'x', nom='Admin', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', nb_mensualites=12,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='Externat', frais_inscription=50000,
            frais_mensualite=25000)
        self.classe = Classe.objects.create(tenant=self.tenant, nom='CI A')

    def _eleve(self, nom, **extra):
        from apps.eleves.matricules import identite_nouvel_eleve
        extra.setdefault('section', self.section)
        extra.setdefault('classe', self.classe)
        return Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, nom_complet=nom,
            date_inscription=self.ex.date_debut,
            **identite_nouvel_eleve(self.tenant, self.ex), **extra)

    def _ids_liste(self, **params):
        r = self.client.get('/api/eleves/liste/', params)
        self.assertEqual(r.status_code, 200, r.content[:200])
        return [e['id'] for e in r.data['results']]

    # ── La liste ne contient que des élèves présents ──────────────────────
    def test_un_sortant_quitte_la_liste_active(self):
        present = self._eleve('Awa NDIAYE')
        parti = self._eleve('Bina FALL', statut='DIPLOME')

        ids = self._ids_liste()

        self.assertIn(str(present.id), ids)
        self.assertNotIn(str(parti.id), ids)

    def test_les_sortants_restent_consultables_sur_demande(self):
        parti = self._eleve('Bina FALL', statut='ABANDONNE')
        self.assertIn(str(parti.id), self._ids_liste(sortants='1'))

    def test_un_filtre_statut_explicite_reste_honore(self):
        parti = self._eleve('Bina FALL', statut='DIPLOME')
        self.assertIn(str(parti.id), self._ids_liste(statut='DIPLOME'))

    def test_un_sortant_apparait_dans_anciens_eleves(self):
        parti = self._eleve('Bina FALL', statut='DIPLOME')
        r = self.client.get('/api/eleves/anciens/')
        self.assertIn(str(parti.id), [l['eleve_id'] for l in r.data['lignes']])

    # ── La date de sortie arrête l'horloge des arriérés ───────────────────
    def test_le_passage_en_sortie_date_la_sortie(self):
        eleve = self._eleve('Bina FALL')
        r = self.client.patch(f'/api/eleves/{eleve.id}/',
                              {'statut': 'ABANDONNE'}, format='json')
        self.assertEqual(r.status_code, 200, r.content[:200])
        eleve.refresh_from_db()
        self.assertIsNotNone(eleve.date_sortie)

    def test_reinscrire_efface_la_date_de_sortie(self):
        eleve = self._eleve('Bina FALL', statut='ABANDONNE',
                            date_sortie=datetime.date(2026, 3, 31))
        r = self.client.patch(f'/api/eleves/{eleve.id}/',
                              {'statut': 'INSCRIT'}, format='json')
        self.assertEqual(r.status_code, 200, r.content[:200])
        eleve.refresh_from_db()
        self.assertIsNone(eleve.date_sortie)

    def test_les_arrieres_cessent_de_grossir_apres_le_depart(self):
        """Un abandon de mars ne doit pas accumuler jusqu'en décembre."""
        eleve = self._eleve('Bina FALL', statut='ABANDONNE',
                            date_sortie=datetime.date(2026, 3, 31))
        decembre = datetime.date(2026, 12, 15)

        self.assertEqual(eleve.mois_echus(decembre), 3)      # jan, fév, mars

    def test_la_fiche_d_un_sortant_reste_ouvrable(self):
        """get_object() passe par le queryset : exclure les sortants de la
        liste ne doit pas rendre leur fiche inaccessible."""
        parti = self._eleve('Bina FALL', statut='DIPLOME')
        r = self.client.get(f'/api/eleves/{parti.id}/')
        self.assertEqual(r.status_code, 200, r.content[:200])

    def test_sans_date_de_sortie_le_calcul_ne_change_pas(self):
        eleve = self._eleve('Awa NDIAYE')
        self.assertEqual(eleve.mois_echus(datetime.date(2026, 12, 15)), 12)

    # ── Enregistrer un ancien élève inconnu du système ────────────────────
    def test_creer_un_ancien_eleve(self):
        r = self.client.post('/api/eleves/ancien/', {
            'nom_complet': 'Ousmane DIOP',
            'genre': 'M',
            'date_naissance': '2005-04-12',
            'date_entree': '2019-10-01',
            'date_sortie': '2023-06-30',
            'statut': 'DIPLOME',
        }, format='json')

        self.assertEqual(r.status_code, 201, r.content[:300])
        eleve = Eleve.objects.get(nom_complet='Ousmane DIOP')
        self.assertEqual(eleve.statut, 'DIPLOME')
        self.assertEqual(eleve.date_sortie, datetime.date(2023, 6, 30))
        # Matricule sur la promo d'ENTRÉE, pas sur l'année de saisie.
        self.assertTrue(eleve.matricule.startswith('2019-CSE-'), eleve.matricule)

    def test_un_ancien_cree_n_entre_pas_dans_la_liste_active(self):
        self.client.post('/api/eleves/ancien/', {
            'nom_complet': 'Ousmane DIOP', 'date_entree': '2019-10-01',
            'statut': 'DIPLOME'}, format='json')
        eleve = Eleve.objects.get(nom_complet='Ousmane DIOP')

        self.assertNotIn(str(eleve.id), self._ids_liste())
        r = self.client.get('/api/eleves/anciens/')
        self.assertIn(str(eleve.id), [l['eleve_id'] for l in r.data['lignes']])

    def test_refus_sans_date_d_entree(self):
        r = self.client.post('/api/eleves/ancien/',
                             {'nom_complet': 'X', 'statut': 'DIPLOME'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_refus_si_la_sortie_precede_l_entree(self):
        r = self.client.post('/api/eleves/ancien/', {
            'nom_complet': 'X', 'date_entree': '2020-01-01',
            'date_sortie': '2019-01-01', 'statut': 'DIPLOME'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_refus_d_un_statut_qui_n_est_pas_une_sortie(self):
        r = self.client.post('/api/eleves/ancien/', {
            'nom_complet': 'X', 'date_entree': '2020-01-01',
            'statut': 'INSCRIT'}, format='json')
        self.assertEqual(r.status_code, 400)

    # ── Effectifs par classe ──────────────────────────────────────────────
    def test_effectifs_par_classe_ignorent_les_sortants(self):
        self._eleve('Awa NDIAYE')
        self._eleve('Cheikh SOW')
        self._eleve('Bina FALL', statut='DIPLOME')

        r = self.client.get('/api/eleves/effectifs-classes/')

        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertEqual(r.data['total'], 2)
        ligne = next(c for c in r.data['classes'] if c['classe'] == 'CI A')
        self.assertEqual(ligne['nb'], 2)

    def test_liste_de_classe_pdf_sans_donnees_financieres(self):
        self._eleve('Awa NDIAYE')
        r = self.client.get('/api/eleves/liste-classe-pdf/',
                            {'classe': str(self.classe.id)})
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertEqual(r['Content-Type'], 'application/pdf')
