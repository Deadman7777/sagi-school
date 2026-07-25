"""Report des reliquats d'un exercice sur le suivant + encaissement.

Deux invariants comptables sous surveillance :
  - le report est un à-nouveaux (411/890) passé dans le NOUVEL exercice,
    jamais dans l'exercice clôturé ;
  - encaisser un reliquat ne crée aucun produit 706 (il a été constaté
    l'année d'origine) — sinon le résultat est gonflé du même montant deux
    années de suite.
"""
import datetime

from django.db.models import Sum
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.comptabilite.models import JournalEntry
from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice, Paiement
from apps.paiements.report_reliquats import (calculer_reliquats,
                                             reporter_reliquats)
from apps.tenants.models import Tenant
from apps.users.models import User


class ReportReliquatsBase(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul')
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
        # Dû 2024-2025 = 50 000 + 10 × 25 000 = 300 000
        self.eleve = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex1, nom_complet='Fatou MBAYE',
            matricule='2024-ETB-000001', numero=1, section=self.section,
            date_inscription=datetime.date(2024, 10, 1))

    def _payer(self, eleve, exercice, **montants):
        return Paiement.objects.create(
            tenant=self.tenant, exercice=exercice, eleve=eleve,
            no_piece=f"REC-{Paiement.objects.count() + 1:04d}", **montants)

    def _cloturer(self, exercice):
        exercice.cloture = True
        exercice.date_cloture = timezone.now()
        exercice.save()


class CalculReliquatTest(ReportReliquatsBase):
    def test_reste_du_de_fin_d_annee(self):
        self._payer(self.eleve, self.ex1, montant_inscription=50000,
                    montant_mensualite=100000)   # payé 150 000 / 300 000
        lignes = calculer_reliquats(self.ex1)
        self.assertEqual(len(lignes), 1)
        self.assertEqual(lignes[0][1], 150000)

    def test_eleve_solde_n_est_pas_reporte(self):
        self._payer(self.eleve, self.ex1, montant_inscription=50000,
                    montant_mensualite=250000)
        self.assertEqual(calculer_reliquats(self.ex1), [])

    def test_paiement_annule_ne_solde_rien(self):
        self._payer(self.eleve, self.ex1, montant_mensualite=300000,
                    statut='ANNULE')
        lignes = calculer_reliquats(self.ex1)
        self.assertEqual(lignes[0][1], 300000)


class ReportTest(ReportReliquatsBase):
    def setUp(self):
        super().setUp()
        self._payer(self.eleve, self.ex1, montant_inscription=50000,
                    montant_mensualite=100000)   # reste 150 000
        self._cloturer(self.ex1)

    def test_reinscrit_l_eleve_avec_son_identite(self):
        reporter_reliquats(self.ex1, self.ex2)
        fiche = Eleve.objects.get(exercice=self.ex2)
        self.assertEqual(fiche.nom_complet, 'Fatou MBAYE')
        # Même enfant : matricule et numéro conservés d'une année sur l'autre
        self.assertEqual(fiche.matricule, '2024-ETB-000001')
        self.assertEqual(fiche.numero, 1)
        self.assertEqual(fiche.eleve_precedent_id, self.eleve.id)
        self.assertEqual(float(fiche.reliquat_anterieur), 150000)
        self.assertEqual(fiche.reliquat_exercice_origine_id, self.ex1.id)
        # Le dû de l'année reste celui de 2025-2026, reliquat non compris
        self.assertEqual(fiche.total_attendu, 300000)
        self.assertEqual(fiche.reste_a_payer_global, 450000)

    def test_a_nouveaux_dans_le_nouvel_exercice_uniquement(self):
        reporter_reliquats(self.ex1, self.ex2)
        ecr = JournalEntry.objects.filter(source='REPORT_RELIQUAT')
        self.assertEqual(ecr.count(), 2)
        # Rien n'a été écrit dans l'exercice clôturé
        self.assertEqual(ecr.filter(exercice=self.ex1).count(), 0)
        self.assertEqual(ecr.filter(exercice=self.ex2).count(), 2)
        self.assertEqual(float(ecr.get(no_compte='411').debit), 150000)
        self.assertEqual(float(ecr.get(no_compte='890').credit), 150000)
        # Aucun produit constaté à nouveau
        self.assertFalse(ecr.filter(no_compte='706').exists())
        agg = ecr.aggregate(d=Sum('debit'), c=Sum('credit'))
        self.assertEqual(agg['d'], agg['c'])

    def test_report_idempotent(self):
        reporter_reliquats(self.ex1, self.ex2)
        rapport = reporter_reliquats(self.ex1, self.ex2)
        self.assertEqual(rapport['nb_reportes'], 0)
        self.assertEqual(rapport['nb_ignores'], 1)
        self.assertEqual(rapport['ignores'][0]['motif'], 'deja_reporte')
        self.assertEqual(Eleve.objects.filter(exercice=self.ex2).count(), 1)
        self.assertEqual(JournalEntry.objects.filter(source='REPORT_RELIQUAT').count(), 2)

    def test_dry_run_n_ecrit_rien(self):
        rapport = reporter_reliquats(self.ex1, self.ex2, dry_run=True)
        self.assertEqual(rapport['nb_reportes'], 1)
        self.assertEqual(rapport['montant_total'], 150000)
        self.assertEqual(Eleve.objects.filter(exercice=self.ex2).count(), 0)
        self.assertFalse(JournalEntry.objects.filter(source='REPORT_RELIQUAT').exists())

    def test_accroche_le_reliquat_a_une_fiche_deja_reinscrite(self):
        deja = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex2, nom_complet='Fatou MBAYE',
            matricule='2024-ETB-000001', numero=1, section=self.section,
            date_inscription=self.ex2.date_debut)
        reporter_reliquats(self.ex1, self.ex2)
        self.assertEqual(Eleve.objects.filter(exercice=self.ex2).count(), 1)
        deja.refresh_from_db()
        self.assertEqual(float(deja.reliquat_anterieur), 150000)
        self.assertEqual(deja.eleve_precedent_id, self.eleve.id)

    def test_sans_creation_ignore_les_non_reinscrits(self):
        rapport = reporter_reliquats(self.ex1, self.ex2, creer_fiches=False)
        self.assertEqual(rapport['nb_reportes'], 0)
        self.assertEqual(rapport['ignores'][0]['motif'], 'non_reinscrit')
        self.assertEqual(Eleve.objects.filter(exercice=self.ex2).count(), 0)

    def test_refuse_un_exercice_cible_cloture(self):
        self._cloturer(self.ex2)
        with self.assertRaises(ValueError):
            reporter_reliquats(self.ex1, self.ex2)

    def test_dette_traverse_deux_exercices(self):
        """Un reliquat non réglé sur l'année N+1 se reporte encore sur N+2."""
        reporter_reliquats(self.ex1, self.ex2)
        fiche2 = Eleve.objects.get(exercice=self.ex2)
        # Elle solde l'année en cours mais pas le reliquat
        self._payer(fiche2, self.ex2, montant_inscription=50000,
                    montant_mensualite=250000)
        self._cloturer(self.ex2)
        ex3 = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026-2027', nb_mensualites=10,
            date_debut=datetime.date(2026, 10, 1), date_fin=datetime.date(2027, 7, 31))

        reporter_reliquats(self.ex2, ex3)
        fiche3 = Eleve.objects.get(exercice=ex3)
        self.assertEqual(float(fiche3.reliquat_anterieur), 150000)

    def test_ndongo_passager_signale_au_lieu_d_etre_reinscrit(self):
        # 10 mois convenus → même dû que le régime exercice, donc même
        # reliquat de 150 000 : seul le traitement du régime change.
        self.eleve.regime = 'PASSAGER'
        self.eleve.nb_mois_passager = 10
        self.eleve.save()
        rapport = reporter_reliquats(self.ex1, self.ex2)
        self.assertEqual(rapport['nb_reportes'], 0)
        self.assertEqual(rapport['nb_a_verifier'], 1)
        self.assertEqual(rapport['a_verifier'][0]['motif'], 'passager_a_reinscrire')
        self.assertEqual(Eleve.objects.filter(exercice=self.ex2).count(), 0)


class EncaissementReliquatTest(ReportReliquatsBase):
    def setUp(self):
        super().setUp()
        self._payer(self.eleve, self.ex1, montant_inscription=50000,
                    montant_mensualite=100000)
        self._cloturer(self.ex1)
        reporter_reliquats(self.ex1, self.ex2)
        self.fiche = Eleve.objects.get(exercice=self.ex2)

    def _produits_706(self):
        return float(JournalEntry.objects.filter(
            tenant=self.tenant, exercice=self.ex2, no_compte='706'
        ).aggregate(c=Sum('credit'))['c'] or 0)

    def test_encaisser_un_reliquat_ne_cree_aucun_produit(self):
        r = self.client.post('/api/paiements/paiements/', {
            'eleve': str(self.fiche.id), 'montant_reliquat': 50000,
            'mode_paiement': 'ESPECE',
        }, format='json')
        self.assertEqual(r.status_code, 201, r.content)

        self.assertEqual(self._produits_706(), 0)
        p = Paiement.objects.get(id=r.data['id'])
        ecr = JournalEntry.objects.filter(source='PAIEMENT', source_id=p.id)
        # Trésorerie débitée, créance 411 soldée, rien d'autre
        self.assertEqual(float(ecr.get(no_compte='571').debit), 50000)
        self.assertEqual(float(ecr.get(no_compte='411').credit), 50000)
        agg = ecr.aggregate(d=Sum('debit'), c=Sum('credit'))
        self.assertEqual(agg['d'], agg['c'])

    def test_paiement_mixte_annee_et_reliquat(self):
        r = self.client.post('/api/paiements/paiements/', {
            'eleve': str(self.fiche.id), 'montant_inscription': 50000,
            'montant_reliquat': 30000, 'mode_paiement': 'ESPECE',
        }, format='json')
        self.assertEqual(r.status_code, 201, r.content)

        # Seule la part « année en cours » devient un produit
        self.assertEqual(self._produits_706(), 50000)
        p = Paiement.objects.get(id=r.data['id'])
        self.assertEqual(float(p.total), 80000)
        self.assertEqual(float(p.total_exercice), 50000)
        ecr = JournalEntry.objects.filter(source='PAIEMENT', source_id=p.id)
        self.assertEqual(float(ecr.get(no_compte='571').debit), 80000)
        agg = ecr.aggregate(d=Sum('debit'), c=Sum('credit'))
        self.assertEqual(agg['d'], agg['c'])

    def test_suivi_temps_reel_du_reliquat(self):
        self.client.post('/api/paiements/paiements/', {
            'eleve': str(self.fiche.id), 'montant_reliquat': 50000,
            'mode_paiement': 'ESPECE'}, format='json')

        r = self.client.get(f'/api/eleves/{self.fiche.id}/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['reliquat_anterieur'], '150000.00')
        self.assertEqual(r.data['reliquat_paye'], 50000)
        self.assertEqual(r.data['reliquat_restant'], 100000)
        self.assertEqual(r.data['reliquat_origine_libelle'], '2024-2025')
        # Le dû de l'année n'a pas bougé : le reliquat vit à côté
        self.assertEqual(r.data['reste_a_payer'], 300000)
        self.assertEqual(r.data['reste_a_payer_global'], 400000)

    def test_refuse_plus_que_le_reliquat_du(self):
        r = self.client.post('/api/paiements/paiements/', {
            'eleve': str(self.fiche.id), 'montant_reliquat': 200000,
            'mode_paiement': 'ESPECE'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Paiement.objects.filter(eleve=self.fiche).exists())

    def test_refuse_un_reliquat_sur_un_eleve_sans_dette(self):
        neuf = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex2, nom_complet='Nouveau',
            section=self.section, date_inscription=self.ex2.date_debut)
        r = self.client.post('/api/paiements/paiements/', {
            'eleve': str(neuf.id), 'montant_reliquat': 10000,
            'mode_paiement': 'ESPECE'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_le_niveau_d_alerte_ignore_le_reliquat(self):
        """Canal séparé : l'alerte reste celle de l'année en cours."""
        r = self.client.get(f'/api/eleves/{self.fiche.id}/')
        alerte_avec_reliquat = r.data['niveau_alerte']

        sans = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex2, nom_complet='Témoin',
            section=self.section, date_inscription=self.ex2.date_debut)
        r2 = self.client.get(f'/api/eleves/{sans.id}/')
        self.assertEqual(alerte_avec_reliquat, r2.data['niveau_alerte'])

    def test_annulation_extourne_sans_produit_fantome(self):
        r = self.client.post('/api/paiements/paiements/', {
            'eleve': str(self.fiche.id), 'montant_reliquat': 50000,
            'mode_paiement': 'ESPECE'}, format='json')
        self.client.post(f"/api/paiements/paiements/{r.data['id']}/annuler/", {}, format='json')

        self.assertEqual(self._produits_706(), 0)
        agg = JournalEntry.objects.filter(tenant=self.tenant).aggregate(
            d=Sum('debit'), c=Sum('credit'))
        self.assertEqual(agg['d'], agg['c'])
        # Le reliquat redevient dû en entier
        self.fiche.refresh_from_db()
        self.assertEqual(self.fiche.reliquat_restant, 150000)

    def test_recu_separe_annee_et_reliquat(self):
        """Le suivi du reçu porte sur l'année : le reliquat encaissé ne doit
        pas venir en déduction du dû de l'année en cours."""
        r = self.client.post('/api/paiements/paiements/', {
            'eleve': str(self.fiche.id), 'montant_inscription': 50000,
            'montant_reliquat': 30000, 'mode_paiement': 'ESPECE'}, format='json')
        recu = self.client.get(f"/api/paiements/paiements/{r.data['id']}/recu/")
        self.assertEqual(recu.status_code, 200, recu.content)
        d = recu.data

        self.assertEqual(d['total'], 80000)             # encaissé
        self.assertEqual(d['total_attendu'], 300000)    # dû de l'année
        self.assertEqual(d['total_paye_apres'], 50000)  # part année seulement
        self.assertEqual(d['reste_apres'], 250000)
        self.assertEqual(d['reliquat'], 30000)
        self.assertEqual(d['reliquat_annee'], '2024-2025')
        self.assertEqual(d['reliquat_restant_apres'], 120000)
        self.assertEqual(d['reste_global_apres'], 370000)
        self.assertIn(('Reliquat 2024-2025', 30000), d['lignes'])

    def test_pdf_recu_avec_reliquat(self):
        r = self.client.post('/api/paiements/paiements/', {
            'eleve': str(self.fiche.id), 'montant_reliquat': 30000,
            'mode_paiement': 'ESPECE'}, format='json')
        # 'taille' et non 'format' — ce dernier est réservé par DRF.
        for taille in ('A4', 'A5', '80MM'):
            pdf = self.client.get(
                f"/api/paiements/paiements/{r.data['id']}/recu-pdf/?taille={taille}")
            self.assertEqual(pdf.status_code, 200, f"taille {taille}")
            self.assertEqual(pdf['Content-Type'], 'application/pdf')

    def test_filtre_avec_reliquat(self):
        Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex2, nom_complet='Sans dette',
            section=self.section, date_inscription=self.ex2.date_debut)
        r = self.client.get('/api/eleves/?avec_reliquat=1')
        noms = [e['nom_complet'] for e in (r.data.get('results') or r.data)]
        self.assertEqual(noms, ['Fatou MBAYE'])


class ReportEndpointTest(ReportReliquatsBase):
    def setUp(self):
        super().setUp()
        self._payer(self.eleve, self.ex1, montant_mensualite=100000)  # reste 200 000
        self._cloturer(self.ex1)

    def test_get_previsualise_sans_ecrire(self):
        r = self.client.get('/api/paiements/reporter-reliquats/')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.data['dry_run'])
        self.assertEqual(r.data['exercice_source'], '2024-2025')
        self.assertEqual(r.data['exercice_cible'], '2025-2026')
        self.assertEqual(r.data['montant_total'], 200000)
        self.assertEqual(Eleve.objects.filter(exercice=self.ex2).count(), 0)

    def test_post_exige_une_confirmation(self):
        r = self.client.post('/api/paiements/reporter-reliquats/', {}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Eleve.objects.filter(exercice=self.ex2).count(), 0)

    def test_post_effectue_le_report(self):
        r = self.client.post('/api/paiements/reporter-reliquats/', {'confirme': True},
                             format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data['nb_reportes'], 1)
        fiche = Eleve.objects.get(exercice=self.ex2)
        self.assertEqual(float(fiche.reliquat_anterieur), 200000)


class ClotureReportTest(ReportReliquatsBase):
    def test_la_cloture_reconduit_les_impayes(self):
        self._payer(self.eleve, self.ex1, montant_mensualite=100000)
        self.ex2.delete()   # la clôture crée elle-même l'exercice suivant

        r = self.client.post('/api/paiements/cloturer-exercice/', {'confirme': True},
                             format='json')
        self.assertEqual(r.status_code, 200, r.content)
        rapport = r.data['report_reliquats']
        self.assertEqual(rapport['nb_reportes'], 1)
        self.assertEqual(rapport['montant_total'], 200000)

        suivant = Exercice.objects.get(cloture=False)
        fiche = Eleve.objects.get(exercice=suivant)
        self.assertEqual(float(fiche.reliquat_anterieur), 200000)
        self.assertEqual(JournalEntry.objects.filter(
            source='REPORT_RELIQUAT', exercice=suivant).count(), 2)

    def test_cloture_sans_report_si_desactive(self):
        self._payer(self.eleve, self.ex1, montant_mensualite=100000)
        self.ex2.delete()
        r = self.client.post('/api/paiements/cloturer-exercice/',
                             {'confirme': True, 'reporter_impayes': False},
                             format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNone(r.data['report_reliquats'])
        self.assertFalse(JournalEntry.objects.filter(source='REPORT_RELIQUAT').exists())
