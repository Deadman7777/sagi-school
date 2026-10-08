"""Tests : corriger le montant d'un reçu.

Signalé le 08/10/2026. Un reçu de 32 500 (espèces) saisi par erreur — la
famille n'avait remis que 25 000. À la correction, le serveur refusait :
« La ventilation des modes de paiement (32,500) ne correspond pas au total à
régler (25,000 FCFA) » — le formulaire ne renvoie pas la ventilation, et le
serveur reprenait celle du reçu d'origine.
"""
import datetime

from rest_framework.test import APITestCase

from apps.comptabilite.models import JournalEntry
from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User


class ModifierPaiementTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='LPE', code_etablissement='LPE')
        self.user = User.objects.create_user(
            'a@a.sn', 'x', nom='Admin', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.exercice = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026-2027', nb_mensualites=10,
            date_debut=datetime.date(2026, 9, 1), date_fin=datetime.date(2027, 7, 31))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='CI', frais_inscription=12000,
            frais_mensualite=12000, frais_uniforme=0, frais_fournitures=0)
        self.eleve = Eleve.objects.create(
            tenant=self.tenant, exercice=self.exercice, section=self.section,
            nom_complet='Mouhamadou MBENGUE', date_inscription=self.exercice.date_debut)

    def _encaisser(self, **corps):
        corps.setdefault('mode_paiement', 'ESPECE')
        corps['eleve'] = str(self.eleve.id)
        r = self.client.post('/api/paiements/paiements/', corps, format='json')
        self.assertEqual(r.status_code, 201, r.content[:300])
        return Paiement.objects.get(id=r.data['id'])

    def _modifier(self, p, **corps):
        return self.client.post(f'/api/paiements/paiements/{p.id}/modifier/',
                                corps, format='json')

    def test_baisse_du_montant_sans_ventilation(self):
        p = self._encaisser(montant_inscription=12000, montant_mensualite=12000,
                            montant_divers=8500)
        r = self._modifier(p, montant_inscription=12000, montant_mensualite=12000,
                           montant_divers=1000, mode_paiement='ESPECE')
        self.assertEqual(r.status_code, 200, r.content[:300])
        nouveau = Paiement.objects.get(no_piece=r.data['nouveau_no_piece'])
        self.assertEqual(float(nouveau.total), 25000)
        self.assertEqual(nouveau.mode_paiement, 'ESPECE')
        self.assertEqual(nouveau.modes_reglement, [{'mode': 'ESPECE', 'montant': 25000.0}])
        ecr = JournalEntry.objects.filter(tenant=self.tenant, source='PAIEMENT',
                                          source_id=nouveau.id)
        self.assertEqual(sum(float(e.debit) for e in ecr),
                         sum(float(e.credit) for e in ecr))
        self.assertEqual(sum(float(e.debit) for e in ecr if e.no_compte.startswith('57')),
                         25000)

    def test_changement_de_mode_simple(self):
        p = self._encaisser(montant_mensualite=12000)
        r = self._modifier(p, montant_mensualite=10000, mode_paiement='WAVE')
        self.assertEqual(r.status_code, 200, r.content[:300])
        nouveau = Paiement.objects.get(no_piece=r.data['nouveau_no_piece'])
        self.assertEqual(nouveau.modes_reglement, [{'mode': 'WAVE', 'montant': 10000.0}])

    def test_multi_mode_total_inchange_reprend_la_ventilation(self):
        p = self._encaisser(montant_inscription=12000, montant_mensualite=12000,
                            modes_reglement=[{'mode': 'ESPECE', 'montant': 20000},
                                             {'mode': 'WAVE', 'montant': 4000}])
        r = self._modifier(p, montant_inscription=14000, montant_mensualite=10000,
                           mode_paiement='MIXTE')
        self.assertEqual(r.status_code, 200, r.content[:300])
        nouveau = Paiement.objects.get(no_piece=r.data['nouveau_no_piece'])
        self.assertEqual(nouveau.mode_paiement, 'MIXTE')
        self.assertEqual(len(nouveau.modes_reglement), 2)

    def test_multi_mode_total_change_demande_la_repartition(self):
        p = self._encaisser(montant_inscription=12000, montant_mensualite=12000,
                            modes_reglement=[{'mode': 'ESPECE', 'montant': 20000},
                                             {'mode': 'WAVE', 'montant': 4000}])
        r = self._modifier(p, montant_inscription=12000, montant_mensualite=8000,
                           mode_paiement='MIXTE')
        self.assertEqual(r.status_code, 400)
        self.assertIn('plusieurs modes', r.data['error'])
        p.refresh_from_db()
        self.assertEqual(p.statut, 'ACTIF')


class ModifierVentilationTest(ModifierPaiementTest):
    """08/10/2026 : 26 000 saisis en espèces, la famille avait remis 24 000 en
    espèces et 2 000 par Wave."""

    def _tresorerie(self, p):
        """Débits de trésorerie par compte : 57x espèces, 552x mobile money."""
        ecr = JournalEntry.objects.filter(tenant=self.tenant, source='PAIEMENT', source_id=p.id)
        par = {}
        for e in ecr:
            if e.no_compte[:2] in ('57', '55') and float(e.debit):
                par[e.no_compte] = par.get(e.no_compte, 0) + float(e.debit)
        return par

    def test_mode_unique_reventile_en_deux_modes(self):
        p = self._encaisser(montant_inscription=12000, montant_mensualite=12000, montant_divers=2000)
        r = self._modifier(p, montant_inscription=12000, montant_mensualite=12000, montant_divers=2000,
                           mode_paiement='MIXTE',
                           modes_reglement=[{'mode': 'ESPECE', 'montant': 24000},
                                            {'mode': 'WAVE', 'montant': 2000}])
        self.assertEqual(r.status_code, 200, r.content[:300])
        nouveau = Paiement.objects.get(no_piece=r.data['nouveau_no_piece'])
        self.assertEqual(nouveau.mode_paiement, 'MIXTE')
        self.assertEqual(nouveau.modes_reglement, [{'mode': 'ESPECE', 'montant': 24000.0},
                                                   {'mode': 'WAVE', 'montant': 2000.0}])
        tres = self._tresorerie(nouveau)
        self.assertEqual(tres.get('5521'), 2000.0)
        self.assertEqual(sum(tres.values()), 26000.0)

    def test_ventilation_fausse_refusee(self):
        p = self._encaisser(montant_mensualite=12000)
        r = self._modifier(p, montant_mensualite=12000, mode_paiement='MIXTE',
                           modes_reglement=[{'mode': 'ESPECE', 'montant': 10000},
                                            {'mode': 'WAVE', 'montant': 1000}])
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Paiement.objects.get(id=p.id).statut, 'ACTIF')

    def test_changer_de_mode_a_montant_egal(self):
        """L'ancienne ventilation (espèces) couvrait le total : elle était
        reprise et le changement de mode ignoré."""
        p = self._encaisser(montant_mensualite=12000)
        r = self._modifier(p, montant_mensualite=12000, mode_paiement='WAVE')
        self.assertEqual(r.status_code, 200, r.content[:300])
        nouveau = Paiement.objects.get(no_piece=r.data['nouveau_no_piece'])
        self.assertEqual(nouveau.modes_reglement, [{'mode': 'WAVE', 'montant': 12000.0}])

    def test_repasser_un_multi_mode_en_mode_unique(self):
        p = self._encaisser(montant_mensualite=12000,
                            modes_reglement=[{'mode': 'ESPECE', 'montant': 10000},
                                             {'mode': 'WAVE', 'montant': 2000}])
        r = self._modifier(p, montant_mensualite=12000, mode_paiement='ESPECE',
                           modes_reglement=[{'mode': 'ESPECE', 'montant': 12000}])
        self.assertEqual(r.status_code, 200, r.content[:300])
        nouveau = Paiement.objects.get(no_piece=r.data['nouveau_no_piece'])
        self.assertEqual(nouveau.mode_paiement, 'ESPECE')
