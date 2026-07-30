"""Tests : ce que l'école devrait encaisser chaque mois, et retrouver un règlement.

Le suivi mensuel ne montrait que l'ENCAISSÉ. Utile pour constater, inutile pour
décider : un directeur qui prépare son mois veut savoir ce qu'il doit rentrer en
janvier, puis en février, d'après la situation réelle de chaque élève.

La prévision vient de l'échéancier — la source qui fait déjà foi sur la fiche,
les alertes et les relances. Elle ne peut donc pas contredire ce que l'école
réclame effectivement aux familles.

Et la recherche : retrouver un reçu supposait de faire défiler toute l'année.
"""
import datetime

from rest_framework.test import APITestCase

from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User


class SuiviPrevisionnelTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='École', code_etablissement='ECO')
        self.user = User.objects.create_user(
            'a@a.sn', 'x', nom='Admin', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', nb_mensualites=12,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='CM2', frais_inscription=100000,
            frais_mensualite=50000, frais_uniforme=0, frais_fournitures=0)

    def _eleve(self, nom, **kw):
        champs = dict(tenant=self.tenant, exercice=self.ex, section=self.section,
                      nom_complet=nom, date_inscription=self.ex.date_debut,
                      statut='INSCRIT')
        champs.update(kw)
        return Eleve.objects.create(**champs)

    def _suivi(self):
        r = self.client.get('/api/eleves/suivi-mensuel/')
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.data

    def _mois(self, num):
        return next(m for m in self._suivi()['global'] if m['mois_num'] == num)

    # ── La prévision mensuelle ────────────────────────────────────────────
    def test_chaque_mois_annonce_la_scolarite_attendue(self):
        """Trois élèves à 50 000 → 150 000 attendus en janvier."""
        for n in ('Awa', 'Modou', 'Fatou'):
            self._eleve(n)

        self.assertEqual(self._mois(1)['scolarite_prevue'], 150000)

    def test_elle_compte_les_eleves_reellement_dus_ce_mois_la(self):
        self._eleve('Awa')
        self._eleve('Modou')

        self.assertEqual(self._mois(1)['nb_eleves_dus'], 2)

    def test_un_eleve_entre_en_cours_d_annee_ne_pese_pas_sur_les_mois_d_avant(self):
        """« selon les données disponibles pour chaque élève » : le prorata
        d'entrée s'applique, comme partout ailleurs."""
        self._eleve('Awa')
        self._eleve('Tardif', date_inscription=datetime.date(2026, 6, 1))

        self.assertEqual(self._mois(1)['scolarite_prevue'], 50000)
        self.assertEqual(self._mois(6)['scolarite_prevue'], 100000)

    def test_un_montant_saisi_pour_un_mois_est_respecte(self):
        e = self._eleve('Awa')
        e.montants_mois = {'2': 20000}
        e.save()

        self.assertEqual(self._mois(1)['scolarite_prevue'], 50000)
        self.assertEqual(self._mois(2)['scolarite_prevue'], 20000)

    def test_une_prise_en_charge_reduit_l_attendu(self):
        e = self._eleve('Awa')
        e.pec_mensualite = 20000
        e.save()

        self.assertEqual(self._mois(1)['scolarite_prevue'], 30000)

    def test_le_reste_suit_les_encaissements(self):
        e = self._eleve('Awa')
        Paiement.objects.create(
            tenant=self.tenant, exercice=self.ex, eleve=e, no_piece='REC-1',
            mode_paiement='ESPECE', montant_mensualite=30000, mois_regles=[1],
            statut='ACTIF', date_paiement=datetime.date(2026, 1, 10))
        m = self._mois(1)

        self.assertEqual(m['scolarite_prevue'], 50000)
        self.assertEqual(m['scolarite_encaissee'], 30000)
        self.assertEqual(m['scolarite_reste'], 20000)

    def test_le_mois_solde_n_attend_plus_rien(self):
        e = self._eleve('Awa')
        Paiement.objects.create(
            tenant=self.tenant, exercice=self.ex, eleve=e, no_piece='REC-1',
            mode_paiement='ESPECE', montant_mensualite=50000, mois_regles=[1],
            statut='ACTIF', date_paiement=datetime.date(2026, 1, 10))

        self.assertEqual(self._mois(1)['scolarite_reste'], 0)

    def test_la_somme_des_mois_egale_le_du_mensuel_de_l_ecole(self):
        """L'invariant : la prévision ne peut pas dire autre chose que la somme
        des échéanciers dont elle est tirée."""
        self._eleve('Awa')
        self._eleve('Modou', date_inscription=datetime.date(2026, 4, 1))
        suivi = self._suivi()

        total_prevu = sum(m['scolarite_prevue'] for m in suivi['global'])
        attendu_mensuel = sum(
            float(e.total_attendu) - e.du_hors_mensualite
            for e in Eleve.objects.filter(tenant=self.tenant, statut='INSCRIT'))

        self.assertAlmostEqual(total_prevu, attendu_mensuel, places=2)

    def test_les_mois_sans_eleve_du_restent_a_zero(self):
        self._eleve('Tardif', date_inscription=datetime.date(2026, 6, 1))

        self.assertEqual(self._mois(1)['scolarite_prevue'], 0)
        self.assertEqual(self._mois(1)['nb_eleves_dus'], 0)

    def test_un_eleve_sorti_ne_compte_plus(self):
        self._eleve('Awa')
        self._eleve('Parti', statut='ABANDONNE')

        self.assertEqual(self._mois(1)['scolarite_prevue'], 50000)

    # ── Recherche d'un règlement ──────────────────────────────────────────
    def _payer(self, eleve, piece, montant=50000, obs=''):
        return Paiement.objects.create(
            tenant=self.tenant, exercice=self.ex, eleve=eleve, no_piece=piece,
            mode_paiement='ESPECE', montant_mensualite=montant, statut='ACTIF',
            observations=obs, date_paiement=datetime.date(2026, 1, 10))

    def _chercher(self, q):
        r = self.client.get(f'/api/paiements/paiements/?q={q}')
        self.assertEqual(r.status_code, 200, r.content[:300])
        data = r.data
        return data.get('results', data) if isinstance(data, dict) else data

    def test_on_retrouve_un_paiement_par_le_nom_de_l_eleve(self):
        self._payer(self._eleve('Awa NDIAYE'), 'REC-1')
        self._payer(self._eleve('Modou FALL'), 'REC-2')

        trouves = self._chercher('ndiaye')
        self.assertEqual([p['no_piece'] for p in trouves], ['REC-1'])

    def test_on_retrouve_un_paiement_par_son_numero_de_recu(self):
        self._payer(self._eleve('Awa NDIAYE'), 'REC-1')
        self._payer(self._eleve('Modou FALL'), 'REC-2')

        self.assertEqual([p['no_piece'] for p in self._chercher('REC-2')], ['REC-2'])

    def test_on_retrouve_un_paiement_par_son_matricule(self):
        e = self._eleve('Awa NDIAYE', matricule='2026-ECO-0042')
        self._payer(e, 'REC-1')
        self._payer(self._eleve('Modou FALL'), 'REC-2')

        self.assertEqual([p['no_piece'] for p in self._chercher('0042')], ['REC-1'])

    def test_on_retrouve_un_paiement_par_ses_observations(self):
        self._payer(self._eleve('Awa NDIAYE'), 'REC-1', obs='Versé par le grand-père')
        self._payer(self._eleve('Modou FALL'), 'REC-2')

        self.assertEqual([p['no_piece'] for p in self._chercher('grand-père')], ['REC-1'])

    def test_une_recherche_vide_ne_filtre_rien(self):
        self._payer(self._eleve('Awa NDIAYE'), 'REC-1')
        self._payer(self._eleve('Modou FALL'), 'REC-2')

        self.assertEqual(len(self._chercher('')), 2)
