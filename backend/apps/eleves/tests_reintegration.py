"""Réintégration d'un élève abandonné — les règles de apps/eleves/reintegration.py.

Cas réel (Shoumoul, septembre 2026) : un enfant abandonne, revient quelques
mois plus tard, et le système ne savait pas le reprendre.
"""
import datetime

from rest_framework.test import APITestCase

from apps.comptabilite.models import JournalEntry
from apps.eleves.echeancier import mois_factures
from apps.eleves.models import Eleve, MouvementEleve, Section
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User


class ReintegrationBase(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul', code_etablissement='CSE')
        self.user = User.objects.create_user(
            'a@a.sn', 'x', nom='Admin', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.section = Section.objects.create(
            tenant=self.tenant, nom='CM2', frais_inscription=0,
            frais_mensualite=30000, frais_uniforme=0, frais_fournitures=0)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', nb_mensualites=12,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))
        self.eleve = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, section=self.section,
            nom_complet='Awa NDIAYE', matricule='CSE-26-0001', statut='INSCRIT',
            date_inscription=datetime.date(2026, 1, 1))

    def _payer(self, eleve, montant, mois, exercice=None):
        return Paiement.objects.create(
            tenant=self.tenant, exercice=exercice or self.ex, eleve=eleve,
            no_piece=f'REC-{Paiement.objects.count() + 1:04d}', mode_paiement='ESPECE',
            montant_mensualite=montant, mois_regles=mois, statut='ACTIF')

    def _abandon(self, eleve, jour):
        r = self.client.patch(f'/api/eleves/{eleve.id}/', {
            'statut': 'ABANDONNE', 'date_sortie': jour, 'motif_sortie': 'Déménagement'},
            format='json')
        self.assertEqual(r.status_code, 200, r.data)

    def _reintegrer(self, eleve, **data):
        base = {'date_retour': '2026-06-15', 'motif': 'Retour de la famille'}
        base.update(data)
        return self.client.post(f'/api/eleves/{eleve.id}/reintegrer/', base, format='json')


class MemeExerciceTest(ReintegrationBase):
    def setUp(self):
        super().setUp()
        self._payer(self.eleve, 60000, [1, 2])
        self._abandon(self.eleve, '2026-03-10')       # mars exigible et impayé

    def test_la_sortie_est_tracee(self):
        m = MouvementEleve.objects.get(eleve=self.eleve)
        self.assertEqual((m.type_mouvement, m.statut_avant, m.motif),
                         ('SORTIE', 'INSCRIT', 'Déménagement'))

    def test_dette_a_reconnaitre(self):
        r = self._reintegrer(self.eleve)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data['code'], 'DETTE_A_RECONNAITRE')
        self.assertEqual(r.data['dette'], 30000)
        self.eleve.refresh_from_db()
        self.assertEqual(self.eleve.statut, 'ABANDONNE')

    def test_reintegration_retire_les_mois_d_absence(self):
        apercu = self.client.get(
            f'/api/eleves/{self.eleve.id}/reintegration/?date_retour=2026-06-15').data
        self.assertTrue(apercu['possible'])
        self.assertEqual(apercu['cas'], 'MEME_EXERCICE')
        self.assertEqual(apercu['mois_retires'], [4, 5])

        r = self._reintegrer(self.eleve, dette_reconnue=True)
        self.assertEqual(r.status_code, 200, r.data)
        self.eleve.refresh_from_db()
        self.assertEqual(self.eleve.statut, 'INSCRIT')
        self.assertIsNone(self.eleve.date_sortie)
        mois = mois_factures(self.eleve)
        self.assertNotIn(4, mois)
        self.assertNotIn(5, mois)
        self.assertIn(3, mois)      # la dette du départ reste due
        self.assertIn(6, mois)      # le mois du retour est dû

        hist = self.client.get(f'/api/eleves/{self.eleve.id}/mouvements/').data
        self.assertEqual([h['type'] for h in hist], ['REINTEGRATION', 'SORTIE'])

    def test_l_eleve_revient_dans_la_liste_et_quitte_les_anciens(self):
        self._reintegrer(self.eleve, dette_reconnue=True)
        liste = self.client.get('/api/eleves/').data
        ids = [e['id'] for e in (liste['results'] if isinstance(liste, dict) else liste)]
        self.assertIn(str(self.eleve.id), ids)
        from apps.eleves.parcours import anciens_eleves
        self.assertEqual(anciens_eleves(self.tenant)['nb'], 0)

    def test_un_mois_d_absence_deja_paye_n_est_pas_retire(self):
        self._payer(self.eleve, 30000, [4])
        self._reintegrer(self.eleve, dette_reconnue=True)
        self.eleve.refresh_from_db()
        self.assertIn(4, mois_factures(self.eleve))
        self.assertNotIn(5, mois_factures(self.eleve))

    def test_regles_de_refus(self):
        cas = [
            ({'date_retour': ''}, 'DATE'),
            ({'date_retour': '2099-01-01'}, 'DATE'),
            ({'date_retour': '2026-03-01'}, 'DATE'),     # avant la sortie
            ({'motif': '  '}, 'MOTIF'),
        ]
        for data, code in cas:
            r = self._reintegrer(self.eleve, dette_reconnue=True, **data)
            self.assertEqual((r.status_code, r.data['code']), (400, code), data)

    def test_deja_present_refuse(self):
        self._reintegrer(self.eleve, dette_reconnue=True)
        r = self._reintegrer(self.eleve, dette_reconnue=True)
        self.assertEqual(r.data['code'], 'DEJA_PRESENT')

    def test_diplome_refuse(self):
        self.eleve.statut = 'DIPLOME'
        self.eleve.save()
        self.assertEqual(self._reintegrer(self.eleve).data['code'], 'DIPLOME')


class NouvelExerciceTest(ReintegrationBase):
    """Abandon en 2025, retour en 2026."""

    def setUp(self):
        super().setUp()
        self.ancien_ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2025', nb_mensualites=12, cloture=True,
            date_debut=datetime.date(2025, 1, 1), date_fin=datetime.date(2025, 12, 31))
        self.eleve.delete()
        self.source = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ancien_ex, section=self.section,
            nom_complet='Moussa DIOP', matricule='CSE-25-0007', statut='ABANDONNE',
            date_inscription=datetime.date(2025, 1, 1),
            date_sortie=datetime.date(2025, 3, 10))
        self._payer(self.source, 60000, [1, 2], exercice=self.ancien_ex)   # mars impayé

    def test_nouvelle_fiche_avec_la_dette_en_reliquat(self):
        r = self._reintegrer(self.source, date_retour='2026-02-01', dette_reconnue=True)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['cas'], 'NOUVEL_EXERCICE')
        fiche = Eleve.objects.get(id=r.data['eleve_id'])
        self.assertEqual(fiche.exercice, self.ex)
        self.assertEqual(fiche.matricule, 'CSE-25-0007')
        self.assertFalse(fiche.fiche_creance)
        self.assertEqual(fiche.statut, 'INSCRIT')
        self.assertEqual(fiche.eleve_precedent, self.source)
        self.assertEqual(float(fiche.reliquat_anterieur), 30000)
        self.assertEqual(fiche.nb_mensualites_dues, 11)      # facturé depuis février
        self.assertTrue(JournalEntry.objects.filter(
            source='REPORT_RELIQUAT', source_id=fiche.id, no_compte='411', debit=30000).exists())
        # L'ancienne fiche garde son histoire.
        self.source.refresh_from_db()
        self.assertEqual(self.source.statut, 'ABANDONNE')

    def test_reprend_la_fiche_de_creance_du_report_sans_doublon(self):
        from apps.paiements.report_reliquats import reporter_reliquats
        reporter_reliquats(self.ancien_ex, self.ex)
        creance = Eleve.objects.get(exercice=self.ex, matricule='CSE-25-0007')
        self.assertTrue(creance.fiche_creance)
        nb_ecritures = JournalEntry.objects.filter(source='REPORT_RELIQUAT').count()

        # Depuis « Anciens élèves », c'est la fiche de créance qui est désignée.
        r = self._reintegrer(creance, date_retour='2026-02-01', dette_reconnue=True)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['eleve_id'], str(creance.id))
        self.assertEqual(Eleve.objects.filter(exercice=self.ex).count(), 1)
        self.assertEqual(JournalEntry.objects.filter(source='REPORT_RELIQUAT').count(), nb_ecritures)
        creance.refresh_from_db()
        self.assertFalse(creance.fiche_creance)
        self.assertEqual(creance.statut, 'INSCRIT')

    def test_retour_hors_exercice_ouvert_refuse(self):
        r = self._reintegrer(self.source, date_retour='2025-06-01', dette_reconnue=True)
        self.assertEqual(r.data['code'], 'EXERCICE')
