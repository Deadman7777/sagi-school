"""Test : importer une école transporte son passé, pas l'heure du serveur.

Le bug de la bascule du Complexe Shoumoul Excellence (19/08/2026) tenait à une
propriété peu connue de `bulk_create` : il appelle `pre_save()` sur chaque
colonne avant l'INSERT, donc `auto_now_add` et `auto_now` s'appliquent aussi
aux lignes copiées d'une autre base. Toute l'école s'est retrouvée créée —
et réglée — le jour de l'import.

Ce test n'a pas besoin de deux bases : il vérifie la règle au bon endroit,
`horloge_neutralisee()`, en tentant d'insérer une ligne datée du passé.
"""
import datetime

from django.test import TestCase
from django.utils import timezone

from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice, Paiement
from apps.sauvegarde.management.commands.importer_ecole import horloge_neutralisee
from apps.tenants.models import Tenant


class HorlogeImportTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul', code_etablissement='SHO')
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', nb_mensualites=12,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='CM2', frais_inscription=100000,
            frais_mensualite=50000, frais_uniforme=0, frais_fournitures=0)
        self.eleve = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, section=self.section,
            nom_complet='Awa NDIAYE', date_inscription=self.ex.date_debut)

    def _ligne_du_passe(self, no_piece):
        """Un règlement tel qu'il sort du dump : daté, horodaté, du passé."""
        return Paiement(
            tenant=self.tenant, exercice=self.ex, eleve=self.eleve,
            no_piece=no_piece, mode_paiement='ESPECE',
            montant_mensualite=50000, statut='ACTIF',
            date_paiement=datetime.date(2026, 3, 14),
            created_at=timezone.make_aware(datetime.datetime(2026, 3, 14, 9, 30)),
            updated_at=timezone.make_aware(datetime.datetime(2026, 3, 14, 9, 30)))

    def test_l_import_conserve_les_dates_d_origine(self):
        with horloge_neutralisee():
            Paiement.objects.bulk_create([self._ligne_du_passe('REC-0001')])

        p = Paiement.objects.get(no_piece='REC-0001')
        self.assertEqual(p.date_paiement, datetime.date(2026, 3, 14))
        self.assertEqual(p.created_at.date(), datetime.date(2026, 3, 14))
        self.assertEqual(p.updated_at.date(), datetime.date(2026, 3, 14))

    def test_hors_import_l_horloge_reprend_la_main(self):
        """La neutralisation ne doit pas fuir hors du bloc : une saisie
        ordinaire qui ne précise rien reste horodatée maintenant."""
        with horloge_neutralisee():
            pass

        p = Paiement.objects.create(
            tenant=self.tenant, exercice=self.ex, eleve=self.eleve,
            no_piece='REC-0002', mode_paiement='ESPECE',
            montant_mensualite=50000, statut='ACTIF')

        self.assertEqual(p.created_at.date(), timezone.localdate())

    def test_l_horloge_est_rendue_meme_si_l_import_echoue(self):
        """Un import interrompu ne doit pas laisser l'application sans
        horodatage pour le reste de la session."""
        class Interruption(Exception):
            pass

        with self.assertRaises(Interruption):
            with horloge_neutralisee():
                raise Interruption()

        champ = Paiement._meta.get_field('created_at')
        self.assertTrue(champ.auto_now_add)
