"""Tests : la promo du matricule suit la DATE D'ENTRÉE, pas l'exercice.

Cas Shoumoul : la migration a versé les 59 élèves dans le seul exercice 2026.
Un enfant réellement entré en 2021 ressortait avec un matricule 2026-CSE-…,
donc l'année de SAISIE et non sa promo — précisément ce que le format promo
devait supprimer.
"""
import datetime

from django.test import TestCase

from apps.eleves.matricules import (Attributeur, annee_promo, libelle_promo)
from apps.eleves.models import Eleve, Section
from apps.eleves.rebasage import calculer_rebasage
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant


class PromoDateEntreeTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul', code_etablissement='CSE')
        # Shoumoul compte en année civile : exercice « 2026 », janvier→décembre.
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', nb_mensualites=12,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='S', frais_inscription=0, frais_mensualite=0)

    # ── L'année de la promo ───────────────────────────────────────────────
    def test_sans_date_l_exercice_fait_foi(self):
        self.assertEqual(annee_promo(self.ex), 2026)

    def test_une_entree_ancienne_donne_sa_propre_promo(self):
        self.assertEqual(annee_promo(self.ex, datetime.date(2021, 3, 15)), 2021)

    def test_annee_scolaire_a_cheval_bascule_sur_le_mois_de_debut(self):
        """École d'octobre à juin : janvier 2022 appartient à la promo 2021."""
        ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2025-2026',
            date_debut=datetime.date(2025, 10, 1), date_fin=datetime.date(2026, 6, 30))
        self.assertEqual(annee_promo(ex, datetime.date(2022, 1, 20)), 2021)
        self.assertEqual(annee_promo(ex, datetime.date(2021, 11, 5)), 2021)
        self.assertEqual(annee_promo(ex, datetime.date(2022, 10, 2)), 2022)

    def test_libelle_garde_le_format_de_l_ecole(self):
        # Année civile → « 2021 », pas « 2021-2022 » qui n'existe pas ici.
        self.assertEqual(libelle_promo(self.ex, datetime.date(2021, 3, 1)), '2021')

    # ── Attribution ───────────────────────────────────────────────────────
    def test_matricule_porte_l_annee_d_entree_reelle(self):
        a = Attributeur(self.tenant, self.ex)
        vieux = a.suivant(date_entree=datetime.date(2021, 9, 1))
        neuf  = a.suivant(date_entree=datetime.date(2026, 6, 25))

        self.assertTrue(vieux['matricule'].startswith('2021-CSE-'), vieux['matricule'])
        self.assertTrue(neuf['matricule'].startswith('2026-CSE-'), neuf['matricule'])
        self.assertEqual(vieux['annee_entree'], '2021')

    def test_les_rangs_sont_comptes_par_promo(self):
        a = Attributeur(self.tenant, self.ex)
        p1 = a.suivant(date_entree=datetime.date(2021, 9, 1))
        p2 = a.suivant(date_entree=datetime.date(2021, 10, 1))
        n1 = a.suivant(date_entree=datetime.date(2026, 2, 1))

        self.assertEqual(p1['matricule'], '2021-CSE-0001')
        self.assertEqual(p2['matricule'], '2021-CSE-0002')
        self.assertEqual(n1['matricule'], '2026-CSE-0001')

    def test_sans_date_le_comportement_ne_change_pas(self):
        a = Attributeur(self.tenant, self.ex)
        self.assertEqual(a.suivant()['matricule'], '2026-CSE-0001')

    # ── Rebasage de l'existant ────────────────────────────────────────────
    def test_le_rebasage_replace_les_migres_dans_leur_promo(self):
        for nom, entree in (('Ancien 2021', datetime.date(2021, 4, 10)),
                            ('Ancien 2023', datetime.date(2023, 5, 2)),
                            ('Nouveau 2026', datetime.date(2026, 6, 25))):
            Eleve.objects.create(
                tenant=self.tenant, exercice=self.ex, section=self.section,
                nom_complet=nom, date_inscription=entree, matricule=None)

        lignes = {l['nom_complet']: l for l in calculer_rebasage(self.tenant)['lignes']}

        self.assertEqual(lignes['Ancien 2021']['nouveau'],  '2021-CSE-0001')
        self.assertEqual(lignes['Ancien 2023']['nouveau'],  '2023-CSE-0001')
        self.assertEqual(lignes['Nouveau 2026']['nouveau'], '2026-CSE-0001')
        self.assertEqual(lignes['Ancien 2021']['promo'], '2021')
