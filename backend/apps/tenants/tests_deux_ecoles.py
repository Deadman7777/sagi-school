"""Le même geste, sur deux écoles d'histoires différentes.

Trois incidents de production en une journée partageaient le même motif : ça
marche pour une école, pas pour l'autre. Même base, même code, même exercice —
seule leur HISTOIRE différait.

  · numéro de reçu calculé par tri alphabétique : l'école ayant fait une reprise
    de migration (pièces REP-) ne pouvait plus émettre un seul reçu ;
  · liste paginée prise pour un tableau : l'école ayant des organismes payeurs
    voyait son sélecteur vide ;
  · réclamation du reliquat : dépendante des montants saisis à la main.

Ces bugs sont invisibles sur une école neuve, qui est exactement ce que
construisent les tests d'une fonctionnalité. D'où ce module : il rejoue les
mêmes gestes sur DEUX écoles — une neuve, une migrée — et exige le même
résultat. Toute nouveauté qui lit l'historique d'un établissement doit passer
ici.

L'école « migrée » porte ce qui distingue une vraie école d'une école de test :
pièces à préfixes multiples, ardoise d'un exercice antérieur, mois facturés
saisis à la main, renouvellement activé, organismes payeurs, budget.
"""
import datetime

from rest_framework.test import APITestCase

from apps.comptabilite.models import BudgetLigne, JournalEntry
from apps.eleves.models import Eleve, Organisme, Section
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User


class DeuxEcolesTest(APITestCase):
    """Chaque test s'exécute sur les deux écoles et compare."""

    def setUp(self):
        self.neuve  = self._ecole('Daara Neuf', 'NEU')
        self.migree = self._ecole('Daara Migré', 'MIG')
        self._donner_une_histoire(self.migree)

    # ── Construction ──────────────────────────────────────────────────────
    def _ecole(self, nom, code):
        tenant = Tenant.objects.create(nom=nom, code_etablissement=code)
        ex = Exercice.objects.create(
            tenant=tenant, annee_scolaire='2026', nb_mensualites=12,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))
        section = Section.objects.create(
            tenant=tenant, nom='Tahfiiz', frais_inscription=185000,
            frais_renouvellement=50000, frais_mensualite=60000,
            frais_uniforme=0, frais_fournitures=0)
        eleve = Eleve.objects.create(
            tenant=tenant, exercice=ex, section=section,
            nom_complet=f'Élève {code}', date_inscription=ex.date_debut)
        user = User.objects.create_user(
            f'{code.lower()}@a.sn', 'x', nom='Admin', role='ADMIN_ECOLE', tenant=tenant)
        return {'tenant': tenant, 'exercice': ex, 'section': section,
                'eleve': eleve, 'user': user}

    def _donner_une_histoire(self, ecole):
        """Tout ce qu'une école réelle accumule et qu'une école de test n'a pas."""
        t, ex, eleve = ecole['tenant'], ecole['exercice'], ecole['eleve']

        # Reprise de migration : pièce REP-, numéro BAS — celle qui cassait la
        # séquence des reçus par tri alphabétique.
        Paiement.objects.create(
            tenant=t, exercice=ex, eleve=eleve, no_piece='REP-0003',
            mode_paiement='ESPECE', montant_mensualite=60000,
            mois_regles=[1], statut='ACTIF')
        # Reçus antérieurs, au-delà du numéro de la reprise.
        for i in range(1, 8):
            Paiement.objects.create(
                tenant=t, exercice=ex, eleve=eleve, no_piece=f'REC-{i:04d}',
                mode_paiement='ESPECE', montant_mensualite=1000, statut='ACTIF')
        # À-nouveaux d'ardoise (RAN-) et pièce migrée sans chiffre.
        JournalEntry.objects.create(
            tenant=t, exercice=ex, no_piece='RAN-0001',
            date_ecriture=ex.date_debut, source='REPORT', no_compte='411',
            debit=40000, credit=0, libelle='Reliquat 2025', ordre=1)
        Paiement.objects.create(
            tenant=t, exercice=ex, eleve=eleve, no_piece='OUVERTURE',
            mode_paiement='ESPECE', montant_divers=500, statut='ACTIF')

        # Ardoise d'un exercice antérieur, mois facturés saisis à la main,
        # renouvellement activé, entrée ancienne.
        eleve.reliquat_anterieur = 40000
        eleve.montants_mois = {'3': 20000}
        eleve.date_entree = datetime.date(2023, 1, 10)
        eleve.save()
        t.renouvellement_actif = True
        t.libelle_renouvellement = 'Réinscription'
        t.mois_renouvellement = 1
        t.save()

        # Organismes payeurs et budget : deux modules qu'une école neuve n'a pas.
        Organisme.objects.create(tenant=t, nom='État du Sénégal', actif=True)
        BudgetLigne.objects.create(
            tenant=t, exercice=ex, no_compte='622', libelle='Loyer', m01=100000)
        BudgetLigne.objects.create(
            tenant=t, exercice=ex, no_compte='622', libelle='Loyer internat',
            m01=80000, mode_realise='IMPUTATION')

    def _connecter(self, ecole):
        self.client.force_authenticate(ecole['user'])
        return ecole

    def _les_deux(self):
        return [('neuve', self.neuve), ('migrée', self.migree)]

    # ── Les écrans répondent sur les deux ─────────────────────────────────
    ROUTES = [
        '/api/paiements/paiements/',
        '/api/paiements/paiements/stats/',
        '/api/eleves/suivi-mensuel/',
        '/api/comptabilite/budget/',
        '/api/comptabilite/charges/',
        '/api/eleves/organismes/',
    ]

    def test_chaque_ecran_repond_pour_les_deux_ecoles(self):
        """Le filet le plus large : un 500 sur une seule école se voit ici."""
        for nom, ecole in self._les_deux():
            self._connecter(ecole)
            for route in self.ROUTES:
                with self.subTest(ecole=nom, route=route):
                    self.assertEqual(self.client.get(route).status_code, 200)

    def test_la_saisie_de_paiement_repond_pour_les_deux(self):
        for nom, ecole in self._les_deux():
            self._connecter(ecole)
            with self.subTest(ecole=nom):
                r = self.client.get(
                    f"/api/eleves/{ecole['eleve'].id}/saisie-paiement/")
                self.assertEqual(r.status_code, 200, r.content[:300])

    def test_l_echeancier_repond_pour_les_deux(self):
        for nom, ecole in self._les_deux():
            self._connecter(ecole)
            with self.subTest(ecole=nom):
                r = self.client.get(f"/api/eleves/{ecole['eleve'].id}/echeancier/")
                self.assertEqual(r.status_code, 200, r.content[:300])

    # ── Encaisser marche sur les deux ─────────────────────────────────────
    def _encaisser(self, ecole, **montants):
        corps = {'eleve': str(ecole['eleve'].id),
                 'exercice': str(ecole['exercice'].id), 'mode_paiement': 'ESPECE'}
        corps.update(montants or {'montant_mensualite': 60000})
        return self.client.post('/api/paiements/paiements/', corps, format='json')

    def test_encaisser_marche_pour_les_deux_ecoles(self):
        """L'incident du 31 juillet : l'école migrée renvoyait 500."""
        for nom, ecole in self._les_deux():
            self._connecter(ecole)
            with self.subTest(ecole=nom):
                r = self._encaisser(ecole)
                self.assertEqual(r.status_code, 201, r.content[:300])

    def test_encaisser_deux_fois_de_suite_marche_pour_les_deux(self):
        for nom, ecole in self._les_deux():
            self._connecter(ecole)
            with self.subTest(ecole=nom):
                self.assertEqual(self._encaisser(ecole).status_code, 201)
                self.assertEqual(self._encaisser(ecole).status_code, 201)

    def test_les_numeros_de_piece_restent_uniques_par_ecole(self):
        for nom, ecole in self._les_deux():
            self._connecter(ecole)
            for _ in range(3):
                self._encaisser(ecole)
            with self.subTest(ecole=nom):
                pieces = list(Paiement.objects
                              .filter(tenant=ecole['tenant'])
                              .values_list('no_piece', flat=True))
                self.assertEqual(len(pieces), len(set(pieces)))

    def test_chaque_ecole_a_sa_propre_sequence(self):
        """Deux écoles doivent pouvoir porter chacune son REC-0001."""
        self._connecter(self.neuve)
        premier = self._encaisser(self.neuve).data['no_piece']

        self.assertEqual(premier, 'REC-0001')
        self.assertTrue(Paiement.objects.filter(
            tenant=self.migree['tenant'], no_piece='REC-0001').exists())

    # ── Une écriture d'une école n'entre jamais chez la voisine ───────────
    def test_les_paiements_ne_fuient_pas_d_une_ecole_a_l_autre(self):
        self._connecter(self.neuve)
        self._encaisser(self.neuve)

        r = self.client.get('/api/paiements/paiements/')
        data = r.data.get('results', r.data) if isinstance(r.data, dict) else r.data
        self.assertEqual(len(data), 1)

    def test_le_budget_ne_fuit_pas_d_une_ecole_a_l_autre(self):
        self._connecter(self.neuve)

        self.assertEqual(self.client.get('/api/comptabilite/budget/').data['lignes'], [])

    # ── Le reliquat se calcule sur les deux ───────────────────────────────
    def _arrieres(self, ecole):
        r = self.client.get(f"/api/eleves/{ecole['eleve'].id}/saisie-paiement/")
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.data['arrieres']

    def test_le_reliquat_d_entree_se_reclame_dans_les_deux_ecoles(self):
        """La RÈGLE, pas un montant : ce qu'on verse sur les frais d'entrée
        diminue le reliquat d'autant. Une valeur en dur ne vaudrait que pour
        l'école qui a servi à l'écrire — c'est précisément le piège qu'on
        cherche à éviter ici."""
        for nom, ecole in self._les_deux():
            self._connecter(ecole)
            avant = self._arrieres(ecole)['entree']['reste']
            self._encaisser(ecole, montant_inscription=10000)
            apres = self._arrieres(ecole)['entree']['reste']

            with self.subTest(ecole=nom):
                self.assertGreater(avant, 0)
                self.assertEqual(round(avant - apres, 2), 10000)

    def test_le_mot_des_frais_d_entree_suit_le_reglage_de_chaque_ecole(self):
        self._connecter(self.neuve)
        r_neuve = self.client.get(
            f"/api/eleves/{self.neuve['eleve'].id}/saisie-paiement/")
        self._connecter(self.migree)
        r_migree = self.client.get(
            f"/api/eleves/{self.migree['eleve'].id}/saisie-paiement/")

        self.assertEqual(r_neuve.data['libelle_entree'], 'Inscription')
        self.assertEqual(r_migree.data['libelle_entree'], 'Réinscription')

    # ── Les listes rendent toujours une forme exploitable ─────────────────
    def test_les_listes_rendent_une_forme_stable_pour_les_deux(self):
        """Une réponse paginée prise pour un tableau a laissé le sélecteur
        « Payé par » vide en production. La forme ne doit pas dépendre du
        nombre de lignes qu'une école possède."""
        for nom, ecole in self._les_deux():
            self._connecter(ecole)
            for route in ('/api/eleves/organismes/', '/api/paiements/paiements/'):
                with self.subTest(ecole=nom, route=route):
                    data = self.client.get(route).data
                    lignes = (data.get('results', data)
                              if isinstance(data, dict) else data)
                    self.assertIsInstance(lignes, list)
