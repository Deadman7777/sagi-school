"""Tests : rattraper la date d'entrée des fiches migrées, et le seuil d'ancienneté.

Le renouvellement décide « nouveau ou ancien » à partir de `date_entree`. Les
fiches créées avant l'existence de ce champ ne la portent pas, et la règle est
prudente : sans information, l'élève est un nouvel entrant. Une école migrée
pouvait donc activer le renouvellement et n'en voir AUCUN effet — la
fonctionnalité livrée mais inerte.

`date_inscription` — que le formulaire de création intitule « Date d'entrée » —
porte la vraie date d'arrivée. La commande la recopie.

Le seuil d'ancienneté, lui, appartient au chef d'établissement : Shoumoul
considère ancien tout élève ayant 9 mois de présence, une école raisonnant en
années pleines en retiendra 12.
"""
import datetime
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant


class MarquerAnciensTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            nom='Shoumoul', code_etablissement='SHO',
            renouvellement_actif=True, anciennete_renouvellement_mois=9)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026-2027', nb_mensualites=12,
            date_debut=datetime.date(2026, 7, 1), date_fin=datetime.date(2027, 6, 30))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='Internat', frais_inscription=185000,
            frais_renouvellement=50000, frais_mensualite=60000)

    def _eleve(self, nom, date_inscription, date_entree=None):
        e = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, section=self.section,
            nom_complet=nom, date_inscription=date_inscription)
        if date_entree:
            Eleve.objects.filter(pk=e.pk).update(date_entree=date_entree)
        return e

    def _relire(self, e):
        return Eleve.objects.select_related('tenant', 'section', 'exercice').get(pk=e.pk)

    def _lancer(self, *args):
        sortie = StringIO()
        call_command('marquer_anciens', *args, stdout=sortie, stderr=StringIO())
        return sortie.getvalue()

    # ── La commande ───────────────────────────────────────────────────────
    def test_elle_recopie_la_date_d_inscription(self):
        e = self._eleve('Ancien NDIAYE', datetime.date(2024, 10, 5))

        self._lancer()

        self.assertEqual(self._relire(e).date_entree, datetime.date(2024, 10, 5))

    def test_elle_renseigne_aussi_la_promo(self):
        e = self._eleve('Ancien NDIAYE', datetime.date(2024, 10, 5))

        self._lancer()

        self.assertTrue(self._relire(e).annee_entree)

    def test_elle_ne_reecrit_pas_une_date_deja_posee(self):
        """Une date d'entrée renseignée est une donnée établie."""
        e = self._eleve('Déjà daté', datetime.date(2026, 7, 1),
                        date_entree=datetime.date(2020, 1, 1))

        self._lancer()

        self.assertEqual(self._relire(e).date_entree, datetime.date(2020, 1, 1))

    def test_la_simulation_n_ecrit_rien(self):
        e = self._eleve('Ancien NDIAYE', datetime.date(2024, 10, 5))

        sortie = self._lancer('--simuler')

        self.assertIsNone(self._relire(e).date_entree)
        self.assertIn('SIMULATION', sortie)

    def test_elle_annonce_le_partage_anciens_nouveaux(self):
        self._eleve('Ancien', datetime.date(2024, 10, 5))
        self._eleve('Nouveau', datetime.date(2026, 7, 6))

        sortie = self._lancer('--simuler')

        self.assertIn('1 ancien(s)', sortie)
        self.assertIn('1 nouvel(le)s', sortie)

    def test_elle_peut_ne_viser_qu_une_ecole(self):
        autre = Tenant.objects.create(nom='Autre', code_etablissement='AUT')
        ex2 = Exercice.objects.create(
            tenant=autre, annee_scolaire='2026', nb_mensualites=12,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))
        section2 = Section.objects.create(tenant=autre, nom='CM2')
        voisin = Eleve.objects.create(
            tenant=autre, exercice=ex2, section=section2, nom_complet='Voisin',
            date_inscription=datetime.date(2024, 1, 1))
        mien = self._eleve('Mien', datetime.date(2024, 10, 5))

        self._lancer('--ecole', 'SHO')

        self.assertIsNotNone(self._relire(mien).date_entree)
        self.assertIsNone(Eleve.objects.get(pk=voisin.pk).date_entree)

    # ── Le seuil d'ancienneté appartient à l'école ────────────────────────
    def test_neuf_mois_suffisent_quand_l_ecole_le_decide(self):
        """Entré le 1er octobre 2025, exercice ouvert le 1er juillet 2026 :
        9 mois de présence, donc ancien pour Shoumoul."""
        e = self._eleve('Neuf mois', datetime.date(2025, 10, 1))
        self._lancer()

        self.assertTrue(self._relire(e).renouvellement_du)

    def test_le_meme_eleve_reste_nouveau_au_seuil_de_douze_mois(self):
        """La même fiche, une école qui raisonne en années pleines."""
        self.tenant.anciennete_renouvellement_mois = 12
        self.tenant.save()
        e = self._eleve('Neuf mois', datetime.date(2025, 10, 1))
        self._lancer()

        self.assertFalse(self._relire(e).renouvellement_du)

    def test_le_cas_donne_par_l_ecole(self):
        """« Un élève inscrit le 20 octobre 2025 ne doit pas de renouvellement
        en 2026 » : 8 mois et 11 jours au 1er juillet, sous les 9 mois."""
        e = self._eleve('Vingt octobre', datetime.date(2025, 10, 20))
        self._lancer()

        self.assertFalse(self._relire(e).renouvellement_du)

    def test_un_eleve_entre_pendant_l_exercice_reste_nouveau(self):
        e = self._eleve('Mamy DAYA', datetime.date(2026, 7, 6))
        self._lancer()

        eleve = self._relire(e)
        self.assertFalse(eleve.renouvellement_du)
        self.assertEqual(eleve.frais_entree, 185000)

    def test_par_defaut_le_seuil_est_d_un_an(self):
        """Une école qui ne touche à rien garde le comportement d'origine."""
        neuve = Tenant.objects.create(nom='Neuve', code_etablissement='NEU')

        self.assertEqual(neuve.anciennete_renouvellement_mois, 12)

    # ── Ce que la commande apporte vraiment ───────────────────────────────
    def test_le_renouvellement_marche_deja_par_le_repli_sur_l_inscription(self):
        """À vérifier avant de croire la commande indispensable : quand
        `date_inscription` porte la vraie date d'arrivée, le repli suffit déjà —
        l'élève est reconnu ancien sans qu'on ait rien lancé."""
        e = self._eleve('Ancien', datetime.date(2024, 10, 5))

        self.assertEqual(self._relire(e).frais_entree, 50000)

    def test_la_commande_fige_la_date_pour_qu_elle_survive(self):
        """Son apport est la DURABILITÉ. `date_inscription` est repositionnée
        au début de chaque exercice pour le prorata des mensualités : le jour où
        elle l'est, le repli dirait « nouveau » et l'ancienneté serait perdue.
        `date_entree`, elle, ne bouge jamais et se recopie à la réinscription."""
        e = self._eleve('Ancien', datetime.date(2024, 10, 5))
        self._lancer()

        # L'exercice avance et le prorata recale la date d'inscription.
        Eleve.objects.filter(pk=e.pk).update(date_inscription=self.ex.date_debut)

        eleve = self._relire(e)
        self.assertEqual(eleve.date_entree, datetime.date(2024, 10, 5))
        self.assertTrue(eleve.renouvellement_du)

    def test_sans_la_commande_le_recalage_ferait_perdre_l_anciennete(self):
        """La démonstration inverse : même fiche, commande non lancée."""
        e = self._eleve('Ancien', datetime.date(2024, 10, 5))

        Eleve.objects.filter(pk=e.pk).update(date_inscription=self.ex.date_debut)

        self.assertFalse(self._relire(e).renouvellement_du)

    # ── Le compte-rendu, quand il n'y a rien à rattraper ──────────────────
    def test_elle_annonce_l_etat_meme_sans_rien_a_ecrire(self):
        """Le cas de Shoumoul : 68 fiches, toutes datées. « Rien à faire » ne
        répond pas à la question qu'on se pose en lançant la commande."""
        self._eleve('Ancien', datetime.date(2024, 10, 5),
                    date_entree=datetime.date(2024, 10, 5))
        self._eleve('Nouveau', datetime.date(2026, 7, 6),
                    date_entree=datetime.date(2026, 7, 6))

        sortie = self._lancer()

        self.assertIn('Rien à rattraper', sortie)
        self.assertIn('1 ancien(s)', sortie)
        self.assertIn('1 nouvel(le)s', sortie)

    def test_elle_previent_quand_le_renouvellement_n_est_pas_active(self):
        self.tenant.renouvellement_actif = False
        self.tenant.save()
        self._eleve('Ancien', datetime.date(2024, 10, 5),
                    date_entree=datetime.date(2024, 10, 5))

        self.assertIn("n'est PAS activé", self._lancer())

    def test_elle_signale_un_niveau_sans_montant_de_renouvellement(self):
        """Un niveau à 0 est un renouvellement gratuit — rarement voulu quand on
        vient d'activer le réglage."""
        self.section.frais_renouvellement = 0
        self.section.save()
        self._eleve('Ancien', datetime.date(2024, 10, 5),
                    date_entree=datetime.date(2024, 10, 5))

        sortie = self._lancer()

        self.assertIn('sans montant de renouvellement', sortie)
        self.assertIn('Internat', sortie)

    def test_un_niveau_tarife_ne_declenche_aucun_avertissement(self):
        self._eleve('Ancien', datetime.date(2024, 10, 5),
                    date_entree=datetime.date(2024, 10, 5))

        self.assertNotIn('sans montant de renouvellement', self._lancer())
