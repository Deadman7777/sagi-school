"""Tests : un règlement annulé n'a plus AUCUN effet.

Signalé le 01/10/2026. Une caissière saisit l'inscription (50 000) mêlée à la
mensualité, puis annule deux reçus de 50 000. Après coup :

  · la fiche de l'élève affichait 150 000 payés au lieu de 50 000 — la liste
    des élèves additionnait tous les reçus, annulés compris ;
  · le 411 restait « gonflé » : le reçu annulé et son extourne demeuraient
    dans les cumuls du grand livre et de la balance (100 000 de plus au débit
    ET au crédit par reçu annulé).

Et quand l'école a deux exercices ouverts, l'extourne partait sur l'autre :
le reçu annulé restait entier dans le 411 de son exercice.
"""
import datetime

from rest_framework.test import APITestCase

from apps.comptabilite.models import JournalEntry
from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User


class PaiementAnnuleTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='LPE', code_etablissement='LPE')
        self.user = User.objects.create_user(
            'a@a.sn', 'x', nom='Admin', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.exercice = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026-2027', nb_mensualites=10,
            date_debut=datetime.date(2026, 9, 1), date_fin=datetime.date(2027, 7, 31))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='Grande Section', frais_inscription=50000,
            frais_mensualite=17000, frais_uniforme=0, frais_fournitures=0)
        self.eleve = self._eleve(self.exercice)

    def _eleve(self, exercice):
        return Eleve.objects.create(
            tenant=self.tenant, exercice=exercice, section=self.section,
            nom_complet='Rouguiyatou DIOUF', date_inscription=exercice.date_debut)

    def _encaisser(self, eleve, **montants):
        corps = {'eleve': str(eleve.id), 'mode_paiement': 'ESPECE'}
        corps.update(montants)
        r = self.client.post('/api/paiements/paiements/', corps, format='json')
        self.assertEqual(r.status_code, 201, r.content[:300])
        return Paiement.objects.get(id=r.data['id'])

    def _annuler(self, paiement):
        r = self.client.post(f'/api/paiements/paiements/{paiement.id}/annuler/')
        self.assertEqual(r.status_code, 200, r.content[:300])

    def _le_cas_du_client(self):
        """Un reçu actif de 50 000, deux reçus de 50 000 annulés."""
        self._encaisser(self.eleve, montant_inscription=33000, montant_mensualite=17000)
        for _ in range(2):
            self._annuler(self._encaisser(self.eleve, montant_inscription=50000))

    def _compte(self, lignes, no):
        return next(l for l in lignes if l['no_compte'] == no)

    # ── La fiche élève ─────────────────────────────────────────────────────
    def test_la_liste_des_eleves_ne_compte_pas_les_annules(self):
        """Le symptôme rapporté : 150 000 payés au lieu de 50 000."""
        self._le_cas_du_client()

        r = self.client.get('/api/eleves/')
        lignes = r.data['results'] if isinstance(r.data, dict) else r.data
        fiche = next(e for e in lignes if e['id'] == str(self.eleve.id))

        self.assertEqual(fiche['total_paye'], 50000)

    def test_la_propriete_total_paye_ne_compte_pas_les_annules(self):
        self._le_cas_du_client()

        self.assertEqual(float(Eleve.objects.get(id=self.eleve.id).total_paye), 50000)

    # ── La comptabilité ────────────────────────────────────────────────────
    def test_le_411_n_est_plus_gonfle_au_grand_livre(self):
        self._le_cas_du_client()

        gl = self.client.get('/api/comptabilite/grand-livre/').data
        c411 = self._compte(gl, '411')

        self.assertEqual((c411['total_debit'], c411['total_credit']), (50000, 50000))
        self.assertEqual(self._compte(gl, '706')['total_credit'], 50000)
        self.assertEqual(self._compte(gl, '571')['total_debit'], 50000)

    def test_la_balance_ne_garde_que_le_recu_actif(self):
        self._le_cas_du_client()

        lignes = self.client.get('/api/comptabilite/balance/').data['lignes']

        self.assertEqual(self._compte(lignes, '411')['mvt_debit'], 50000)
        self.assertEqual(self._compte(lignes, '706')['sf_crediteur'], 50000)

    def test_le_journal_garde_la_trace_de_l_erreur(self):
        """Écarté des cumuls, pas effacé : l'erreur et sa correction restent."""
        self._le_cas_du_client()

        self.assertEqual(JournalEntry.objects.filter(
            tenant=self.tenant, source='ANNUL_PAIEMENT').values('no_piece').distinct().count(), 2)

    def test_une_extourne_partielle_reste_visible(self):
        """On n'écarte qu'une paire qui se compense exactement : sinon le
        grand livre cacherait un écart réel."""
        p = self._encaisser(self.eleve, montant_inscription=50000)
        self._annuler(p)
        JournalEntry.objects.filter(source='ANNUL_PAIEMENT', no_compte='411').first().delete()

        gl = self.client.get('/api/comptabilite/grand-livre/').data

        self.assertGreater(self._compte(gl, '706')['total_credit'], 0)

    # ── L'exercice de l'extourne ───────────────────────────────────────────
    def test_l_extourne_va_sur_l_exercice_du_paiement(self):
        """Deux exercices ouverts : l'annulation suit le reçu, pas le dernier ouvert."""
        Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2027-2028', nb_mensualites=10,
            date_debut=datetime.date(2027, 9, 1), date_fin=datetime.date(2028, 7, 31))
        p = self._encaisser(self.eleve, montant_inscription=50000)

        self._annuler(p)

        self.assertEqual(set(JournalEntry.objects.filter(
            source='ANNUL_PAIEMENT', source_id=p.id).values_list('exercice_id', flat=True)),
            {self.exercice.id})
