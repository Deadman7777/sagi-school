"""Impayé antérieur saisi à la migration.

Invariants sous surveillance :
  - l'à-nouveaux est 411 D / 890 C, jamais un produit 706 (la dette est née
    avant SAGI SCHOOL, la constater ici gonflerait le résultat de l'année) ;
  - la synchronisation est auto-réparatrice : corriger le montant n fois ne
    laisse qu'UNE pièce au journal, remettre 0 n'en laisse aucune ;
  - le dû global de l'élève inclut l'ardoise, mais son total_attendu (le
    produit de l'année) reste intact.
"""
import datetime

from django.db.models import Sum
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.comptabilite.models import JournalEntry
from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice, Paiement
from apps.paiements.reliquat_migration import (SOURCE_MIGRATION,
                                               definir_impaye_anterieur,
                                               resume_impayes_anterieurs,
                                               synchroniser_ecritures)
from apps.paiements.report_reliquats import SOURCE_REPORT, reporter_reliquats
from apps.tenants.models import Tenant
from apps.users.models import User


class ImpayeAnterieurBase(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul')
        self.user = User.objects.create_user('a@a.sn', 'x', nom='A',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)

        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2025-2026', nb_mensualites=10,
            date_debut=datetime.date(2025, 10, 1), date_fin=datetime.date(2026, 7, 31))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='Externat', frais_inscription=50000,
            frais_mensualite=25000)
        # Dû de l'année = 50 000 + 10 × 25 000 = 300 000
        self.eleve = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, nom_complet='Fatou MBAYE',
            matricule='2025-ETB-000001', numero=1, section=self.section,
            date_inscription=datetime.date(2025, 10, 1))

    def _ecritures(self, eleve=None):
        return JournalEntry.objects.filter(
            tenant=self.tenant, source_id=(eleve or self.eleve).id,
            source__in=(SOURCE_MIGRATION, SOURCE_REPORT))


class EcrituresTest(ImpayeAnterieurBase):
    def test_a_nouveaux_411_890_sans_produit(self):
        definir_impaye_anterieur(self.eleve, 45000, note='2024-2025')
        lignes = {e.no_compte: (float(e.debit), float(e.credit))
                  for e in self._ecritures()}
        self.assertEqual(lignes, {'411': (45000.0, 0.0), '890': (0.0, 45000.0)})
        self.assertFalse(self._ecritures().filter(no_compte='706').exists())

    def test_ecriture_datee_a_l_ouverture_de_l_exercice(self):
        definir_impaye_anterieur(self.eleve, 45000)
        for e in self._ecritures():
            self.assertEqual(e.date_ecriture, self.ex.date_debut)

    def test_journal_equilibre(self):
        definir_impaye_anterieur(self.eleve, 45000)
        agg = JournalEntry.objects.filter(tenant=self.tenant, exercice=self.ex
                                          ).aggregate(d=Sum('debit'), c=Sum('credit'))
        self.assertEqual(float(agg['d']), float(agg['c']))

    def test_montant_nul_n_ecrit_rien(self):
        self.assertEqual(definir_impaye_anterieur(self.eleve, 0)['no_piece'], '')
        self.assertEqual(self._ecritures().count(), 0)


class AutoReparationTest(ImpayeAnterieurBase):
    def test_corrections_successives_ne_laissent_qu_une_piece(self):
        definir_impaye_anterieur(self.eleve, 45000)
        definir_impaye_anterieur(self.eleve, 60000)
        definir_impaye_anterieur(self.eleve, 30000)
        ecr = self._ecritures()
        self.assertEqual(ecr.count(), 2)                      # 411 + 890, une seule fois
        self.assertEqual({e.no_piece for e in ecr}.__len__(), 1)
        self.assertEqual(float(ecr.get(no_compte='411').debit), 30000.0)

    def test_no_piece_stable_entre_deux_corrections(self):
        p1 = definir_impaye_anterieur(self.eleve, 45000)['no_piece']
        p2 = definir_impaye_anterieur(self.eleve, 60000)['no_piece']
        self.assertEqual(p1, p2)

    def test_remise_a_zero_efface_l_ecriture(self):
        definir_impaye_anterieur(self.eleve, 45000)
        definir_impaye_anterieur(self.eleve, 0)
        self.assertEqual(self._ecritures().count(), 0)
        agg = JournalEntry.objects.filter(tenant=self.tenant, exercice=self.ex
                                          ).aggregate(d=Sum('debit'), c=Sum('credit'))
        self.assertEqual(float(agg['d'] or 0), float(agg['c'] or 0))

    def test_synchroniser_est_idempotent(self):
        definir_impaye_anterieur(self.eleve, 45000)
        synchroniser_ecritures(self.eleve)
        synchroniser_ecritures(self.eleve)
        self.assertEqual(self._ecritures().count(), 2)

    def test_correction_d_un_reliquat_reporte_ne_double_pas_la_creance(self):
        """Un reliquat venu du report automatique, corrigé à la main : une seule
        créance au journal, pas deux (le report écrit sous une autre source)."""
        ex_prec = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2024-2025', nb_mensualites=10,
            date_debut=datetime.date(2024, 10, 1), date_fin=datetime.date(2025, 7, 31))
        ancien = Eleve.objects.create(
            tenant=self.tenant, exercice=ex_prec, nom_complet='Moussa NDIAYE',
            matricule='2024-ETB-000002', numero=2, section=self.section,
            date_inscription=datetime.date(2024, 10, 1))
        reporter_reliquats(ex_prec, self.ex)
        fiche = Eleve.objects.get(exercice=self.ex, matricule=ancien.matricule)
        self.assertEqual(self._ecritures(fiche).count(), 2)

        definir_impaye_anterieur(fiche, 100000)
        ecr = self._ecritures(fiche)
        self.assertEqual(ecr.count(), 2)
        self.assertEqual(float(ecr.get(no_compte='411').debit), 100000.0)


class GardeFousTest(ImpayeAnterieurBase):
    def test_montant_negatif_refuse(self):
        with self.assertRaises(ValueError):
            definir_impaye_anterieur(self.eleve, -1)

    def test_exercice_cloture_refuse(self):
        self.ex.cloture = True
        self.ex.date_cloture = timezone.now()
        self.ex.save()
        self.eleve.refresh_from_db()
        with self.assertRaises(ValueError):
            definir_impaye_anterieur(self.eleve, 45000)

    def test_montant_sous_le_deja_encaisse_refuse(self):
        definir_impaye_anterieur(self.eleve, 45000)
        Paiement.objects.create(tenant=self.tenant, exercice=self.ex, eleve=self.eleve,
                                no_piece='REC-0001', montant_reliquat=30000)
        with self.assertRaises(ValueError):
            definir_impaye_anterieur(self.eleve, 20000)


class DuGlobalTest(ImpayeAnterieurBase):
    def test_l_ardoise_s_ajoute_au_du_sans_toucher_au_produit_de_l_annee(self):
        definir_impaye_anterieur(self.eleve, 45000)
        self.eleve.refresh_from_db()
        self.assertEqual(self.eleve.total_attendu, 300000.0)      # produit de l'année, intact
        self.assertEqual(self.eleve.reste_a_payer, 300000.0)
        self.assertEqual(self.eleve.reste_a_payer_global, 345000.0)

    def test_encaissement_du_reliquat_reduit_le_du_global(self):
        definir_impaye_anterieur(self.eleve, 45000)
        Paiement.objects.create(tenant=self.tenant, exercice=self.ex, eleve=self.eleve,
                                no_piece='REC-0001', montant_reliquat=45000)
        self.eleve.refresh_from_db()
        self.assertEqual(self.eleve.reliquat_restant, 0.0)
        self.assertEqual(self.eleve.reste_a_payer_global, 300000.0)

    def test_alerte_ignore_l_ardoise(self):
        """Arbitrage : le niveau d'alerte juge l'année en cours, pas la dette
        ancienne — sinon toute l'école bascule en CRITIQUE le jour de la migration."""
        definir_impaye_anterieur(self.eleve, 500000)
        self.eleve.refresh_from_db()
        avant = self.eleve.niveau_alerte
        definir_impaye_anterieur(self.eleve, 0)
        self.eleve.refresh_from_db()
        self.assertEqual(avant, self.eleve.niveau_alerte)

    def test_resume(self):
        definir_impaye_anterieur(self.eleve, 45000)
        r = resume_impayes_anterieurs(self.tenant, self.ex)
        self.assertEqual((r['nb_eleves'], r['montant_total']), (1, 45000.0))


class ApiTest(ImpayeAnterieurBase):
    def _url(self, suffixe=''):
        return f'/api/eleves/{suffixe}'

    def test_patch_fiche_ecrit_l_a_nouveaux(self):
        r = self.client.patch(self._url(f'{self.eleve.id}/'),
                              {'reliquat_anterieur': 45000,
                               'reliquat_note': 'ardoise cahier'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self._ecritures().count(), 2)
        self.assertEqual(r.data['reste_a_payer_global'], 345000.0)
        self.assertEqual(r.data['reliquat_origine_libelle'], 'ardoise cahier')

    def test_patch_montant_negatif_rejete(self):
        r = self.client.patch(self._url(f'{self.eleve.id}/'),
                              {'reliquat_anterieur': -5}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self._ecritures().count(), 0)

    def test_patch_sans_toucher_au_reliquat_ne_touche_pas_au_journal(self):
        definir_impaye_anterieur(self.eleve, 45000)
        piece = self._ecritures().first().no_piece
        r = self.client.patch(self._url(f'{self.eleve.id}/'),
                              {'nom_complet': 'Fatou MBAYE DIOP'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self._ecritures().count(), 2)
        self.assertEqual(self._ecritures().first().no_piece, piece)

    def test_saisie_en_lot(self):
        autre = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, nom_complet='Awa SALL',
            matricule='2025-ETB-000003', numero=3, section=self.section,
            date_inscription=datetime.date(2025, 10, 1))
        r = self.client.post(self._url('impayes-anterieurs/'), {'lignes': [
            {'eleve_id': str(self.eleve.id), 'montant': 45000, 'note': '2024-2025'},
            {'eleve_id': str(autre.id),      'montant': 20000},
        ]}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['nb_appliques'], 2)
        self.assertEqual(r.data['resume']['montant_total'], 65000.0)

    def test_saisie_en_lot_une_ligne_fautive_ne_bloque_pas_les_autres(self):
        r = self.client.post(self._url('impayes-anterieurs/'), {'lignes': [
            {'eleve_id': str(self.eleve.id), 'montant': 45000},
            {'eleve_id': str(self.eleve.id), 'montant': -1},
        ]}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual((r.data['nb_appliques'], r.data['nb_refuses']), (1, 1))
        self.assertEqual(r.data['resume']['montant_total'], 45000.0)

    def test_liste_pour_la_grille_de_saisie(self):
        definir_impaye_anterieur(self.eleve, 45000, note='2024-2025')
        r = self.client.get(self._url('impayes-anterieurs/'))
        self.assertEqual(r.status_code, 200, r.data)
        ligne = next(l for l in r.data['lignes'] if l['eleve_id'] == str(self.eleve.id))
        self.assertEqual((ligne['montant'], ligne['restant'], ligne['note']),
                         (45000.0, 45000.0, '2024-2025'))
