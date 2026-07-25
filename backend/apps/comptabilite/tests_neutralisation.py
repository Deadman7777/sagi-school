"""Neutralisation des reprises — réparation des produits faussés.

Reproduit l'état d'une base où des corrections de reprises successives ont
empilé des débits 706 orphelins jusqu'à faire tomber le total des recettes
à 0, et vérifie que la réparation rend son montant juste au produit migré.
"""
import datetime
from io import StringIO

from django.core.management import call_command
from django.db.models import Sum
from django.test import TestCase

from apps.comptabilite.models import JournalEntry
from apps.comptabilite.neutralisation import neutraliser_reprises
from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice
from apps.paiements.reprise import creer_paiement_reprise
from apps.tenants.models import Tenant

AGREGAT = 13337500          # total des entrées du journal de caisse Excel


class NeutralisationBase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul')
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', nb_mensualites=12,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='S', frais_inscription=55000, frais_mensualite=60000)
        # Agrégats du journal de caisse migré : les produits sont déjà là.
        for compte, debit, credit, ordre in (('571', AGREGAT, 0, 1),
                                             ('706', 0, AGREGAT, 2)):
            JournalEntry.objects.create(
                tenant=self.tenant, exercice=self.ex, no_piece='MIG',
                date_ecriture=self.ex.date_debut, no_compte=compte,
                debit=debit, credit=credit, source='MIGRATION', ordre=ordre)

    def _eleve(self, nom):
        return Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, nom_complet=nom,
            section=self.section, date_inscription=self.ex.date_debut)

    def _net_70(self):
        agg = JournalEntry.objects.filter(
            tenant=self.tenant, exercice=self.ex, no_compte__startswith='70'
        ).aggregate(c=Sum('credit'), d=Sum('debit'))
        return float(agg['c'] or 0) - float(agg['d'] or 0)

    def _orphelin(self, montant):
        """Débit 706 laissé par une correction antérieure (bug historique)."""
        JournalEntry.objects.create(
            tenant=self.tenant, exercice=self.ex, no_piece='RECAL-REP',
            date_ecriture=self.ex.date_debut, source='RECAL_MIGRATION',
            no_compte='706', debit=montant, credit=0, ordre=1,
            libelle='Neutralisation reprise corrigée — ancienne')
        JournalEntry.objects.create(
            tenant=self.tenant, exercice=self.ex, no_piece='RECAL-REP',
            date_ecriture=self.ex.date_debut, source='RECAL_MIGRATION',
            no_compte='890', debit=0, credit=montant, ordre=2,
            libelle='Contrepartie reprise corrigée — ancienne')


class NeutralisationTest(NeutralisationBase):
    def test_recalcule_au_lieu_d_empiler(self):
        e = self._eleve('Awa')
        creer_paiement_reprise(self.tenant, self.ex, e,
                               montants={'montant_inscription': 0,
                                         'montant_mensualite': 300000,
                                         'montant_uniforme': 0,
                                         'montant_fournitures': 0})
        for _ in range(3):
            neutraliser_reprises(self.tenant, self.ex)
        self.assertEqual(JournalEntry.objects.filter(
            tenant=self.tenant, source='RECAL_MIGRATION').count(), 2)
        self.assertEqual(self._net_70(), AGREGAT)

    def test_nettoie_les_orphelins_accumules(self):
        e = self._eleve('Awa')
        creer_paiement_reprise(self.tenant, self.ex, e,
                               montants={'montant_inscription': 0,
                                         'montant_mensualite': 300000,
                                         'montant_uniforme': 0,
                                         'montant_fournitures': 0})
        self._orphelin(420000)
        self._orphelin(500000)
        neutraliser_reprises(self.tenant, self.ex)
        self.assertEqual(self._net_70(), AGREGAT)

    def test_epargne_le_recalage_de_tresorerie(self):
        """RECAL-TRESO partage la source RECAL_MIGRATION : il ne doit pas
        être emporté par la remise à plat des reprises."""
        JournalEntry.objects.create(
            tenant=self.tenant, exercice=self.ex, no_piece='RECAL-TRESO',
            date_ecriture=self.ex.date_debut, source='RECAL_MIGRATION',
            no_compte='571', debit=250000, credit=0, ordre=1,
            libelle='Recalage trésorerie')
        neutraliser_reprises(self.tenant, self.ex)
        self.assertTrue(JournalEntry.objects.filter(no_piece='RECAL-TRESO').exists())

    def test_sans_agregats_migres_aucune_neutralisation(self):
        JournalEntry.objects.filter(source='MIGRATION').delete()
        e = self._eleve('Awa')
        creer_paiement_reprise(self.tenant, self.ex, e,
                               montants={'montant_inscription': 0,
                                         'montant_mensualite': 300000,
                                         'montant_uniforme': 0,
                                         'montant_fournitures': 0})
        self.assertEqual(neutraliser_reprises(self.tenant, self.ex), 0.0)
        # Le produit de la reprise reste acquis : rien à annuler ici
        self.assertEqual(self._net_70(), 300000)


class ReparationCommandeTest(NeutralisationBase):
    def setUp(self):
        super().setUp()
        e = self._eleve('Awa')
        creer_paiement_reprise(self.tenant, self.ex, e,
                               montants={'montant_inscription': 0,
                                         'montant_mensualite': 300000,
                                         'montant_uniforme': 0,
                                         'montant_fournitures': 0})
        # État observé chez Shoumoul : tant de débits orphelins que le net
        # produits passe sous zéro (le tableau de bord affichait 0).
        self._orphelin(300000)
        for montant in (4000000, 5000000, 4500000):
            self._orphelin(montant)

    def _appeler(self, *args):
        out = StringIO()
        call_command('reparer_neutralisation_reprises', '--tenant', 'Shoumoul',
                     *args, stdout=out)
        return out.getvalue()

    def test_diagnostic_n_ecrit_rien(self):
        avant = self._net_70()
        self.assertLess(avant, 0)     # d'où le 0 affiché au tableau de bord
        sortie = self._appeler()
        self.assertIn('Diagnostic seul', sortie)
        self.assertEqual(self._net_70(), avant)

    def test_reparation_retablit_le_produit_migre(self):
        self._appeler('--appliquer')
        self.assertEqual(self._net_70(), AGREGAT)
        self.assertEqual(JournalEntry.objects.filter(
            tenant=self.tenant, source='RECAL_MIGRATION',
            no_piece='RECAL-REP').count(), 2)
        agg = JournalEntry.objects.filter(tenant=self.tenant).aggregate(
            d=Sum('debit'), c=Sum('credit'))
        self.assertEqual(agg['d'], agg['c'])

    def test_reparation_idempotente(self):
        self._appeler('--appliquer')
        sortie = self._appeler()
        self.assertIn('déjà cohérente', sortie)
        self.assertEqual(self._net_70(), AGREGAT)
