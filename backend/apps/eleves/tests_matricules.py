"""Matricule de promo AAAA-CODE-NNNN et rebasage de l'existant.

Ce que ces tests protègent :
  - le matricule est ancré sur l'ANNÉE D'ENTRÉE (l'exercice), pas sur l'année
    civile du jour de la saisie — sinon une même promo porte deux années ;
  - il ne bouge plus jamais : réinscription, clôture, changement de niveau ;
  - date_entree survit à la réinscription, alors que date_inscription est
    repositionnée au début du nouvel exercice pour le prorata ;
  - le rebasage renumérote par ordre chronologique réel et est rejouable.
"""
import datetime

from rest_framework.test import APITestCase

from apps.eleves.matricules import Attributeur, identite_nouvel_eleve
from apps.eleves.models import Eleve, Section
from apps.eleves.rebasage import appliquer_rebasage, calculer_rebasage
from apps.paiements.models import Exercice
from apps.paiements.report_reliquats import reporter_reliquats
from apps.tenants.models import Tenant
from apps.users.models import User


class MatriculeBase(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Complexe Shoumoul Excellence',
                                            code_etablissement='she')
        self.user = User.objects.create_user('a@a.sn', 'x', nom='A',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)

        self.ex1 = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2024-2025', nb_mensualites=10,
            date_debut=datetime.date(2024, 10, 1), date_fin=datetime.date(2025, 7, 31))
        self.ex2 = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2025-2026', nb_mensualites=10,
            date_debut=datetime.date(2025, 10, 1), date_fin=datetime.date(2026, 7, 31))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='Externat', frais_inscription=50000,
            frais_mensualite=25000)

    def _eleve(self, nom, exercice, date_inscription=None, **extra):
        """Crée une fiche comme le fait la vue : identité attribuée."""
        date_inscription = date_inscription or exercice.date_debut
        identite = identite_nouvel_eleve(self.tenant, exercice,
                                         date_entree=date_inscription)
        return Eleve.objects.create(
            tenant=self.tenant, exercice=exercice, section=self.section,
            nom_complet=nom, date_inscription=date_inscription, **identite, **extra)


class AttributionTest(MatriculeBase):
    def test_format_promo(self):
        e = self._eleve('Fatou MBAYE', self.ex2)
        self.assertEqual(e.matricule, '2025-SHE-0001')
        self.assertEqual(e.annee_entree, '2025-2026')

    def test_rang_incremente_dans_la_promo(self):
        self._eleve('A', self.ex2)
        self._eleve('B', self.ex2)
        c = self._eleve('C', self.ex2)
        self.assertEqual(c.matricule, '2025-SHE-0003')

    def test_chaque_promo_repart_a_un(self):
        a = self._eleve('Ancien', self.ex1)
        b = self._eleve('Nouveau', self.ex2)
        self.assertEqual(a.matricule, '2024-SHE-0001')
        self.assertEqual(b.matricule, '2025-SHE-0001')

    def test_annee_est_celle_de_l_exercice_pas_du_jour_de_saisie(self):
        """Un élève saisi en janvier 2026 pour l'exercice 2025-2026 reste
        de la promo 2025 — c'est tout l'intérêt du changement de format."""
        e = self._eleve('Tardif', self.ex2, datetime.date(2026, 1, 15))
        self.assertTrue(e.matricule.startswith('2025-'))
        self.assertEqual(e.date_entree, datetime.date(2026, 1, 15))

    def test_matricule_fourni_est_respecte(self):
        identite = identite_nouvel_eleve(self.tenant, self.ex2, matricule='ANCIEN-42')
        self.assertEqual(identite['matricule'], 'ANCIEN-42')

    def test_attributeur_ne_redonne_pas_un_matricule_fourni(self):
        """L'école fournit 2025-SHE-0001 sur une ligne d'import : la ligne
        suivante, générée, ne doit pas retomber dessus."""
        a = Attributeur(self.tenant, self.ex2)
        premier = a.suivant(matricule='2025-SHE-0001')['matricule']
        second  = a.suivant()['matricule']
        self.assertEqual(premier, '2025-SHE-0001')
        self.assertNotEqual(second, premier)

    def test_code_etablissement_absent(self):
        tenant = Tenant.objects.create(nom='Sans code')
        ex = Exercice.objects.create(
            tenant=tenant, annee_scolaire='2025-2026', nb_mensualites=10,
            date_debut=datetime.date(2025, 10, 1), date_fin=datetime.date(2026, 7, 31))
        self.assertEqual(identite_nouvel_eleve(tenant, ex)['matricule'],
                         '2025-ETB-0001')

    def test_matricule_tient_dans_le_champ(self):
        # Code d'école à sa taille maximale (10) : le matricule doit rester
        # sous les 20 caractères du champ, même avec un rang à 4 chiffres.
        tenant = Tenant.objects.create(nom='Longue', code_etablissement='ABCDEFGHIJ')
        ex = Exercice.objects.create(
            tenant=tenant, annee_scolaire='2025-2026', nb_mensualites=10,
            date_debut=datetime.date(2025, 10, 1), date_fin=datetime.date(2026, 7, 31))
        matricule = identite_nouvel_eleve(tenant, ex)['matricule']
        self.assertLessEqual(len(matricule),
                             Eleve._meta.get_field('matricule').max_length)

    def test_creation_par_api(self):
        r = self.client.post('/api/eleves/', {
            'nom_complet': 'Awa SALL', 'section': str(self.section.id),
            'genre': 'F', 'date_naissance': '2015-03-02', 'lieu_naissance': 'Rufisque',
            'date_inscription': '2025-11-04', 'nom_pere': 'Papa', 'telephone_pere': '770000000',
        }, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['matricule'], '2025-SHE-0001')
        self.assertEqual(r.data['annee_entree'], '2025-2026')
        self.assertEqual(r.data['date_entree'], '2025-11-04')


class ReinscriptionTest(MatriculeBase):
    def test_identite_survit_a_la_reinscription(self):
        ancien = self._eleve('Fatou MBAYE', self.ex1, datetime.date(2024, 11, 20))
        reporter_reliquats(self.ex1, self.ex2)   # dû non réglé → réinscription
        fiche = Eleve.objects.get(exercice=self.ex2, nom_complet='Fatou MBAYE')

        self.assertEqual(fiche.matricule, ancien.matricule)
        self.assertEqual(fiche.annee_entree, '2024-2025')
        self.assertEqual(fiche.date_entree, datetime.date(2024, 11, 20))
        # date_inscription, elle, est bien repositionnée pour le prorata —
        # c'est précisément pour ça que date_entree doit exister à part.
        self.assertEqual(fiche.date_inscription, self.ex2.date_debut)

    def test_nouvel_entrant_ne_prend_pas_le_rang_d_un_reinscrit(self):
        self._eleve('Ancien', self.ex1)
        reporter_reliquats(self.ex1, self.ex2)
        nouveau = self._eleve('Nouveau', self.ex2)
        self.assertEqual(nouveau.matricule, '2025-SHE-0001')


class RebasageTest(MatriculeBase):
    def _brut(self, nom, exercice, matricule, date_inscription, **extra):
        """Fiche à l'ANCIEN format, comme dans une base déjà installée."""
        return Eleve.objects.create(
            tenant=self.tenant, exercice=exercice, section=self.section,
            nom_complet=nom, matricule=matricule, date_inscription=date_inscription,
            numero=Eleve.objects.filter(tenant=self.tenant).count() + 1, **extra)

    def test_renumerote_par_ordre_chronologique(self):
        # Saisis dans le désordre : le 2e arrivé a été enregistré en premier.
        self._brut('Deuxieme', self.ex2, '2026-ETB-000001', datetime.date(2025, 12, 1))
        self._brut('Premier',  self.ex2, '2025-ETB-000002', datetime.date(2025, 10, 1))

        appliquer_rebasage(self.tenant)
        self.assertEqual(Eleve.objects.get(nom_complet='Premier').matricule,
                         '2025-SHE-0001')
        self.assertEqual(Eleve.objects.get(nom_complet='Deuxieme').matricule,
                         '2025-SHE-0002')

    def test_ancien_matricule_conserve(self):
        self._brut('Fatou', self.ex2, '2026-ETB-000007', datetime.date(2025, 10, 1))
        appliquer_rebasage(self.tenant)
        fiche = Eleve.objects.get(nom_complet='Fatou')
        self.assertEqual(fiche.matricule_ancien, '2026-ETB-000007')

    def test_promo_lue_sur_l_exercice_d_entree(self):
        self._brut('Ancien', self.ex1, '2025-ETB-000001', datetime.date(2024, 10, 1))
        self._brut('Recent', self.ex2, '2025-ETB-000002', datetime.date(2025, 10, 1))
        appliquer_rebasage(self.tenant)
        self.assertEqual(Eleve.objects.get(nom_complet='Ancien').matricule,
                         '2024-SHE-0001')
        self.assertEqual(Eleve.objects.get(nom_complet='Recent').matricule,
                         '2025-SHE-0001')

    def test_les_fiches_d_un_meme_enfant_partagent_le_matricule(self):
        ancien = self._brut('Fatou', self.ex1, '2025-ETB-000001', datetime.date(2024, 10, 1))
        suite  = self._brut('Fatou', self.ex2, '2025-ETB-000001', datetime.date(2025, 10, 1),
                            eleve_precedent=ancien)
        rapport = appliquer_rebasage(self.tenant)
        self.assertEqual(rapport['nb_eleves'], 1)      # un seul enfant, deux fiches
        ancien.refresh_from_db(); suite.refresh_from_db()
        self.assertEqual(ancien.matricule, suite.matricule)
        # La promo est celle de la PREMIÈRE année, pas de la fiche courante.
        self.assertEqual(suite.matricule, '2024-SHE-0001')
        self.assertEqual(suite.date_entree, datetime.date(2024, 10, 1))

    def test_fiches_non_chainees_mais_meme_matricule_regroupees(self):
        """Une fiche importée avant le report n'a pas de lien de chaîne : le
        matricule identique suffit à reconnaître le même enfant."""
        self._brut('Fatou', self.ex1, '2025-ETB-000001', datetime.date(2024, 10, 1))
        self._brut('Fatou', self.ex2, '2025-ETB-000001', datetime.date(2025, 10, 1))
        self.assertEqual(calculer_rebasage(self.tenant)['nb_eleves'], 1)

    def test_reattribution_croisee_ne_viole_pas_l_unicite(self):
        """Deux élèves du même exercice qui échangent leurs rangs : l'écriture
        directe ferait sauter la contrainte (tenant, exercice, matricule)."""
        self._brut('Second', self.ex2, '2025-SHE-0001', datetime.date(2025, 12, 1))
        self._brut('Premier', self.ex2, '2025-SHE-0002', datetime.date(2025, 10, 1))
        appliquer_rebasage(self.tenant)
        self.assertEqual(Eleve.objects.get(nom_complet='Premier').matricule,
                         '2025-SHE-0001')
        self.assertEqual(Eleve.objects.get(nom_complet='Second').matricule,
                         '2025-SHE-0002')

    def test_rejouable(self):
        self._brut('Fatou', self.ex2, '2026-ETB-000001', datetime.date(2025, 10, 1))
        appliquer_rebasage(self.tenant)
        premier = Eleve.objects.get(nom_complet='Fatou').matricule

        rapport = appliquer_rebasage(self.tenant)
        self.assertEqual(rapport['nb_changements'], 0)
        fiche = Eleve.objects.get(nom_complet='Fatou')
        self.assertEqual(fiche.matricule, premier)
        # Le matricule d'origine de l'école n'est pas écrasé par le nôtre.
        self.assertEqual(fiche.matricule_ancien, '2026-ETB-000001')

    def test_diagnostic_n_ecrit_rien(self):
        self._brut('Fatou', self.ex2, '2026-ETB-000001', datetime.date(2025, 10, 1))
        rapport = calculer_rebasage(self.tenant)
        self.assertEqual(rapport['nb_changements'], 1)
        self.assertEqual(Eleve.objects.get(nom_complet='Fatou').matricule,
                         '2026-ETB-000001')

    def test_remplit_la_promo_des_eleves_deja_au_bon_format(self):
        self._brut('Fatou', self.ex2, '2025-SHE-0001', datetime.date(2025, 10, 1))
        appliquer_rebasage(self.tenant)
        fiche = Eleve.objects.get(nom_complet='Fatou')
        self.assertEqual(fiche.annee_entree, '2025-2026')
        self.assertEqual(fiche.date_entree, datetime.date(2025, 10, 1))

    def test_isolation_tenant(self):
        autre = Tenant.objects.create(nom='Autre', code_etablissement='AUT')
        ex = Exercice.objects.create(
            tenant=autre, annee_scolaire='2025-2026', nb_mensualites=10,
            date_debut=datetime.date(2025, 10, 1), date_fin=datetime.date(2026, 7, 31))
        Eleve.objects.create(tenant=autre, exercice=ex, nom_complet='Voisin',
                             matricule='2025-AUT-0001', numero=1,
                             date_inscription=ex.date_debut)
        self._brut('Fatou', self.ex2, '2026-ETB-000001', datetime.date(2025, 10, 1))

        rapport = appliquer_rebasage(self.tenant)
        self.assertEqual(rapport['nb_eleves'], 1)
        self.assertEqual(Eleve.objects.get(nom_complet='Voisin').matricule,
                         '2025-AUT-0001')
