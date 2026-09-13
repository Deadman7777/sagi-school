"""Un élève sorti ne doit que ce qui était dû le jour de son départ.

Décision de la direction (septembre 2026). Avant : un abandon de janvier
restait débiteur de février à juillet — sur sa fiche, dans « Anciens élèves »,
et dans le reliquat reporté sur l'année suivante (à-nouveaux 411/890 gonflés).

Règles, pas montants : chaque écran lit le même calendrier, et le recalage
ne descend jamais sous ce qui a déjà été encaissé.
"""
import datetime

from rest_framework.test import APITestCase

from apps.comptabilite.models import JournalEntry
from apps.eleves.echeancier import construire_echeancier, mois_factures
from apps.eleves.models import Eleve, Section
from apps.eleves.parcours import anciens_eleves
from apps.paiements.models import Exercice, Paiement
from apps.paiements.recalage_sortants import recaler_reliquats_sortants
from apps.paiements.reliquat_migration import synchroniser_ecritures
from apps.paiements.report_reliquats import calculer_reliquats, reporter_reliquats
from apps.tenants.models import Tenant


class DuAuDepartBase(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul')
        self.ex1 = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2024-2025', nb_mensualites=10,
            date_debut=datetime.date(2024, 10, 1), date_fin=datetime.date(2025, 7, 31))
        self.ex2 = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2025-2026', nb_mensualites=10,
            date_debut=datetime.date(2025, 10, 1), date_fin=datetime.date(2026, 7, 31))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='Externat', frais_inscription=50000, frais_mensualite=25000)
        self.eleve = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex1, nom_complet='Fatou MBAYE',
            matricule='2024-ETB-000001', section=self.section,
            date_inscription=datetime.date(2024, 10, 1))
        # Inscription + octobre → décembre réglés.
        self._payer(self.eleve, self.ex1, montant_inscription=50000,
                    montant_mensualite=75000, mois_regles=[10, 11, 12])

    def _payer(self, eleve, exercice, **kw):
        return Paiement.objects.create(
            tenant=self.tenant, exercice=exercice, eleve=eleve,
            no_piece=f'REC-{Paiement.objects.count() + 1:04d}', mode_paiement='ESPECE',
            statut='ACTIF', **kw)

    def _abandon(self, jour=datetime.date(2025, 1, 15)):
        self.eleve.statut = 'ABANDONNE'
        self.eleve.date_sortie = jour
        self.eleve.save()


class CalendrierDuSortantTest(DuAuDepartBase):
    def test_seuls_les_mois_exigibles_au_depart_sont_factures(self):
        self._abandon()
        self.assertEqual(mois_factures(self.eleve), [10, 11, 12, 1])
        self.assertEqual(len(mois_factures(self.eleve, jusqu_a_la_sortie=False)), 10)

    def test_fiche_echeancier_anciens_et_report_disent_la_meme_chose(self):
        self._abandon()
        eleve = Eleve.objects.get(pk=self.eleve.pk)
        ech = construire_echeancier(eleve, today=datetime.date(2025, 9, 1))
        du_fiche = eleve.reste_a_payer
        self.assertEqual(ech['totaux']['reste'], du_fiche)
        self.assertEqual(ech['synthese']['mois_a_venir'], 0)
        ancien = anciens_eleves(self.tenant)['lignes'][0]
        self.assertEqual(ancien['solde_du'], du_fiche)
        [(_, reliquat)] = calculer_reliquats(self.ex1)
        self.assertEqual(reliquat, du_fiche)
        self.assertEqual(du_fiche, 25000)          # janvier seulement

    def test_regle_d_exigibilite_de_l_ecole_respectee(self):
        """École à paiement anticipé : février est exigible dès janvier."""
        self.tenant.echeance_mensualite = 'ANTICIPE'
        self.tenant.jour_echeance = 5
        self.tenant.save()
        self._abandon(datetime.date(2025, 1, 15))
        eleve = Eleve.objects.get(pk=self.eleve.pk)
        self.assertEqual(mois_factures(eleve), [10, 11, 12, 1, 2])

    def test_sans_date_de_sortie_rien_n_est_retire(self):
        self.eleve.statut = 'ABANDONNE'
        self.eleve.date_sortie = None
        Eleve.objects.filter(pk=self.eleve.pk).update(statut='ABANDONNE', date_sortie=None)
        self.assertEqual(len(mois_factures(Eleve.objects.get(pk=self.eleve.pk))), 10)

    def test_eleve_present_inchange(self):
        self.assertEqual(len(mois_factures(self.eleve)), 10)

    def test_report_ecrit_l_a_nouveaux_du_du_au_depart(self):
        self._abandon()
        reporter_reliquats(self.ex1, self.ex2)
        fiche = Eleve.objects.get(exercice=self.ex2)
        self.assertEqual(float(fiche.reliquat_anterieur), 25000)
        self.assertTrue(JournalEntry.objects.filter(
            source_id=fiche.id, no_compte='411', debit=25000).exists())


class RecalageTest(DuAuDepartBase):
    """Reliquats reportés AVANT la règle : 175 000 au lieu de 25 000."""

    def setUp(self):
        super().setUp()
        self._abandon()
        self.fiche = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex2, nom_complet='Fatou MBAYE',
            matricule='2024-ETB-000001', section=self.section, statut='ABANDONNE',
            fiche_creance=True, eleve_precedent=self.eleve,
            date_inscription=self.ex2.date_debut,
            reliquat_anterieur=175000, reliquat_exercice_origine=self.ex1)
        synchroniser_ecritures(self.fiche)

    def _411(self):
        return sum(float(e.debit) for e in JournalEntry.objects.filter(
            source_id=self.fiche.id, no_compte='411'))

    def test_simulation_n_ecrit_rien(self):
        r = recaler_reliquats_sortants(self.tenant)
        self.assertEqual(r['nb'], 1)
        self.assertEqual((r['lignes'][0]['avant'], r['lignes'][0]['apres']), (175000, 25000))
        self.fiche.refresh_from_db()
        self.assertEqual(float(self.fiche.reliquat_anterieur), 175000)
        self.assertEqual(self._411(), 175000)

    def test_application_recale_fiche_et_a_nouveaux(self):
        recaler_reliquats_sortants(self.tenant, appliquer=True)
        self.fiche.refresh_from_db()
        self.assertEqual(float(self.fiche.reliquat_anterieur), 25000)
        self.assertEqual(self._411(), 25000)
        # Rejouable : plus rien à recaler.
        self.assertEqual(recaler_reliquats_sortants(self.tenant, appliquer=True)['nb'], 0)

    def test_jamais_sous_l_encaisse(self):
        self._payer(self.fiche, self.ex2, montant_reliquat=60000)
        r = recaler_reliquats_sortants(self.tenant, appliquer=True)
        self.assertTrue(r['lignes'][0]['plafonne_a_l_encaisse'])
        self.fiche.refresh_from_db()
        self.assertEqual(float(self.fiche.reliquat_anterieur), 60000)

    def test_exercice_cloture_non_touche(self):
        self.ex2.cloture = True
        self.ex2.save()
        self.assertEqual(recaler_reliquats_sortants(self.tenant, appliquer=True)['nb'], 0)


class CommandeRecalageTest(DuAuDepartBase):
    def test_ecole_ambigue_liste_les_candidates(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        autre = Tenant.objects.create(nom='Shoumoul TEST')
        with self.assertRaises(CommandError) as ctx:
            call_command('recaler_reliquats_sortants', ecole='Shoumoul')
        self.assertIn(str(autre.id), str(ctx.exception))
        self.assertIn(str(self.tenant.id), str(ctx.exception))
