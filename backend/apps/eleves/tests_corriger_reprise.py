"""Test : correction du déjà payé (reprise) par élève."""
import datetime
from django.db.models import Sum
from rest_framework.test import APITestCase

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.paiements.models import Exercice, Paiement
from apps.eleves.models import Eleve, Section
from apps.comptabilite.models import JournalEntry


class CorrigerRepriseTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='T')
        self.user = User.objects.create_user('a@a.sn', 'x', nom='A', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', cloture=False, nb_mensualites=12,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='S', frais_inscription=55000, frais_mensualite=60000)
        self.eleve = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, nom_complet='Awa', section=self.section,
            date_inscription=datetime.date(2026, 1, 1))

    def test_corrige_le_deja_paye_normal(self):
        # total attendu = 55000 + 12×60000 = 775000
        r = self.client.post(f'/api/eleves/{self.eleve.id}/corriger-reprise/',
                             {'montant_inscription': 55000, 'montant_mensualite': 420000},
                             format='json')
        self.assertEqual(r.status_code, 200, r.content)
        # reste = 775000 − 475000 = 300000
        self.assertEqual(r.data['reste_a_payer'], 300000)
        # une reprise créée, 706 crédité (pas de migration → pas de neutralisation)
        self.assertTrue(Paiement.objects.filter(eleve=self.eleve, mode_paiement='REPRISE').exists())
        self.assertFalse(JournalEntry.objects.filter(no_piece='RECAL-REP').exists())

    def test_706_neutralise_si_agregats_migration(self):
        # agrégats migrés présents (571 D / 706 C, équilibré) → reprise neutralisée
        JournalEntry.objects.create(tenant=self.tenant, exercice=self.ex, no_piece='M',
                                    date_ecriture=self.ex.date_debut, no_compte='571',
                                    debit=13337500, credit=0, source='MIGRATION', ordre=1)
        JournalEntry.objects.create(tenant=self.tenant, exercice=self.ex, no_piece='M',
                                    date_ecriture=self.ex.date_debut, no_compte='706',
                                    debit=0, credit=13337500, source='MIGRATION', ordre=2)
        r = self.client.post(f'/api/eleves/{self.eleve.id}/corriger-reprise/',
                             {'montant_inscription': 55000, 'montant_mensualite': 420000},
                             format='json')
        self.assertEqual(r.status_code, 200, r.content)
        # crédit reprise 706 = débit neutralisation → net reprise nul
        p = Paiement.objects.get(eleve=self.eleve, mode_paiement='REPRISE')
        rep = JournalEntry.objects.filter(source='PAIEMENT', source_id=p.id, no_compte='706')\
            .aggregate(c=Sum('credit'))['c'] or 0
        neu = JournalEntry.objects.filter(no_piece='RECAL-REP', no_compte='706')\
            .aggregate(d=Sum('debit'))['d'] or 0
        self.assertEqual(float(rep), float(neu))
        # ensemble équilibré
        agg = JournalEntry.objects.filter(tenant=self.tenant).aggregate(d=Sum('debit'), c=Sum('credit'))
        self.assertEqual(agg['d'], agg['c'])

    def test_reste_a_payer_direct(self):
        # total attendu = 775000. On fixe directement le reste réel = 100000
        # (cas social) → déjà payé = 675000, sans mode ni trésorerie.
        r = self.client.post(f'/api/eleves/{self.eleve.id}/corriger-reprise/',
                             {'reste_a_payer': 100000}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data['reste_a_payer'], 100000)
        # Aucune écriture de trésorerie (571/5521/521) créée par la reprise
        self.assertFalse(JournalEntry.objects.filter(
            source='PAIEMENT', no_compte__in=('571', '521', '5521', '5522')).exists())

    def test_get_lit_la_reprise(self):
        self.client.post(f'/api/eleves/{self.eleve.id}/corriger-reprise/',
                         {'montant_mensualite': 120000}, format='json')
        r = self.client.get(f'/api/eleves/{self.eleve.id}/corriger-reprise/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['montant_mensualite'], 120000)
