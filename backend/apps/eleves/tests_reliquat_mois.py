"""Tests : un règlement partiel laisse un reliquat, réclamé au passage suivant.

Le cas décrit par l'école : un élève doit 185 000 à l'inscription et donne
100 000. Il reste 85 000. Cette somme doit être réclamée avec l'échéance
suivante — faire partie de ce qu'on demande ce mois-là, et se lire comme un
reliquat sur le reçu.

Le guichet ne proposait que l'échéance courante. Le reliquat existait bien dans
la fiche et dans les alertes, mais nulle part à l'endroit où l'on encaisse : le
caissier devait le retrouver ailleurs pour penser à le réclamer, et le reçu
remis à la famille portait deux fois le même intitulé « Frais d'inscription »
sans que rien ne dise que le second achevait le premier.

À ne pas confondre avec `montant_reliquat`, qui solde l'ardoise d'un EXERCICE
ANTÉRIEUR : celle-là a sa propre créance reportée en à-nouveaux et ne constate
aucun produit. Ici, tout se passe à l'intérieur de l'année en cours.
"""
import datetime

from rest_framework.test import APITestCase

from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User


class ReliquatEcheanceTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='École', code_etablissement='ECO')
        self.user = User.objects.create_user(
            'a@a.sn', 'x', nom='Admin', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        # Année civile : tous les mois sont échus au 31 décembre.
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', nb_mensualites=12,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='Internat', frais_inscription=185000,
            frais_mensualite=60000, frais_uniforme=0, frais_fournitures=0)
        self.eleve = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, section=self.section,
            nom_complet='Awa NDIAYE', date_inscription=self.ex.date_debut)

    def _saisie(self):
        r = self.client.get(f'/api/eleves/{self.eleve.id}/saisie-paiement/')
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.data

    def _encaisser(self, **montants):
        corps = {'eleve': str(self.eleve.id), 'exercice': str(self.ex.id),
                 'mode_paiement': 'ESPECE'}
        corps.update(montants)
        r = self.client.post('/api/paiements/paiements/', corps, format='json')
        self.assertEqual(r.status_code, 201, r.content[:300])
        return r.data

    def _recu(self, no_piece):
        p = Paiement.objects.get(tenant=self.tenant, no_piece=no_piece)
        r = self.client.get(f'/api/paiements/paiements/{p.id}/recu/')
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.data

    # ── Le cas décrit ─────────────────────────────────────────────────────
    def test_un_reglement_partiel_laisse_le_reste_en_arriere(self):
        """185 000 dus, 100 000 versés → 85 000 de reliquat."""
        self._encaisser(montant_inscription=100000)

        self.assertEqual(self._saisie()['arrieres']['entree']['reste'], 85000)

    def test_le_reliquat_porte_le_nom_des_frais_d_entree(self):
        self._encaisser(montant_inscription=100000)

        self.assertEqual(self._saisie()['arrieres']['entree']['libelle'], 'Inscription')

    def test_il_entre_dans_le_total_des_arrieres(self):
        self._encaisser(montant_inscription=100000)
        d = self._saisie()

        self.assertGreaterEqual(d['arrieres']['total'], 85000)

    def test_une_fois_solde_il_disparait(self):
        self._encaisser(montant_inscription=100000)
        self._encaisser(montant_inscription=85000)

        self.assertEqual(self._saisie()['arrieres']['entree']['reste'], 0)

    def test_rien_a_reclamer_quand_tout_est_regle_d_emblee(self):
        self._encaisser(montant_inscription=185000)

        self.assertEqual(self._saisie()['arrieres']['entree']['reste'], 0)

    # ── Les mois échus non soldés ─────────────────────────────────────────
    def test_un_mois_regle_a_moitie_reste_reclamable(self):
        self._encaisser(montant_mensualite=30000, mois_regles=[1])
        arr = self._saisie()['arrieres']

        janvier = next(m for m in arr['mois'] if m['num'] == 1)
        self.assertEqual(janvier['reste'], 30000)

    def test_les_mois_soldes_ne_sont_pas_reclames(self):
        self._encaisser(montant_mensualite=60000, mois_regles=[1])
        arr = self._saisie()['arrieres']

        self.assertNotIn(1, [m['num'] for m in arr['mois']])

    def test_le_total_somme_l_entree_et_les_mois(self):
        self._encaisser(montant_inscription=100000)
        self._encaisser(montant_mensualite=30000, mois_regles=[1])
        arr = self._saisie()['arrieres']

        self.assertEqual(
            arr['total'],
            round(arr['entree']['reste'] + sum(m['reste'] for m in arr['mois']), 2))

    def test_seuls_les_mois_echus_sont_reclames(self):
        """Réclamer un mois non encore exigible transformerait l'échéancier en
        avance obligatoire."""
        self.tenant.echeance_mensualite = 'FIN_MOIS'
        self.tenant.save()
        arr = self._saisie()['arrieres']

        self.assertTrue(all(m['reste'] > 0 for m in arr['mois']))
        # Décembre n'est pas exigible avant sa fin : il n'est pas réclamé.
        self.assertNotIn(12, [m['num'] for m in arr['mois']])

    # ── Le reçu ───────────────────────────────────────────────────────────
    def test_le_premier_recu_parle_de_frais_d_inscription(self):
        piece = self._encaisser(montant_inscription=100000)['no_piece']

        libelles = [l[0] for l in self._recu(piece)['lignes']]
        self.assertIn("Frais d'inscription", libelles)

    def test_le_second_recu_parle_de_RELIQUAT(self):
        """Le cas décrit : deux reçus portaient le même intitulé, sans que rien
        ne dise que le second achevait le premier."""
        self._encaisser(montant_inscription=100000)
        piece = self._encaisser(montant_inscription=85000)['no_piece']

        libelles = [l[0] for l in self._recu(piece)['lignes']]
        self.assertIn("Reliquat frais d'inscription", libelles)

    def test_le_recu_porte_le_montant_du_reliquat(self):
        self._encaisser(montant_inscription=100000)
        piece = self._encaisser(montant_inscription=85000)['no_piece']

        ligne = next(l for l in self._recu(piece)['lignes']
                     if l[0].startswith('Reliquat'))
        self.assertEqual(ligne[1], 85000)

    def test_un_reliquat_regle_avec_la_mensualite_tient_sur_un_seul_recu(self):
        """« faire partie de la somme due de ce mois » : même reçu, deux lignes
        lisibles — le reliquat et le mois courant."""
        self._encaisser(montant_inscription=100000)
        piece = self._encaisser(montant_inscription=85000,
                                montant_mensualite=60000, mois_regles=[2])['no_piece']
        recu = self._recu(piece)

        libelles = [l[0] for l in recu['lignes']]
        self.assertIn("Reliquat frais d'inscription", libelles)
        self.assertTrue(any('Février' in l for l in libelles))
        self.assertEqual(recu['total'], 145000)

    def test_le_reliquat_du_renouvellement_porte_le_mot_de_l_ecole(self):
        self.tenant.renouvellement_actif = True
        self.tenant.libelle_renouvellement = 'Réinscription'
        self.tenant.save()
        self.section.frais_renouvellement = 50000
        self.section.save()
        self.eleve.date_entree = datetime.date(2024, 1, 5)
        self.eleve.save()

        self._encaisser(montant_inscription=20000)
        piece = self._encaisser(montant_inscription=30000)['no_piece']

        libelles = [l[0] for l in self._recu(piece)['lignes']]
        self.assertIn('Reliquat réinscription', libelles)
