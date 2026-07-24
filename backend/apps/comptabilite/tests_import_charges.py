"""Test de l'import Excel des charges."""
import datetime
from io import BytesIO

import openpyxl
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import Sum
from rest_framework.test import APITestCase

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.paiements.models import Exercice
from apps.comptabilite.models import JournalEntry


def _xlsx(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Charges'
    ws.append(['Date', 'Libellé', 'Compte (optionnel)', 'Montant', 'Réglé via (571 défaut)'])
    for r in rows:
        ws.append(r)
    buf = BytesIO()
    wb.save(buf)
    return SimpleUploadedFile(
        'charges.xlsx', buf.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


class ImportChargesTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul')
        self.user = User.objects.create_user(
            'a@a.sn', 'x', nom='Admin', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', cloture=False,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))

    def test_apercu_suggere_le_compte_par_nature(self):
        f = _xlsx([
            ['15/01/2026', 'Loyer janvier', '', 150000, '571'],
            ['20/01/2026', 'Facture SENELEC', '', 45000, '571'],
            ['', 'Ligne sans montant', '', '', '571'],  # ERREUR
        ])
        r = self.client.post('/api/comptabilite/import-charges/', {'fichier': f}, format='multipart')
        self.assertEqual(r.status_code, 200, r.content)
        lignes = r.data['lignes']
        self.assertEqual(r.data['resume']['ok'], 2)
        self.assertEqual(r.data['resume']['erreurs'], 1)
        # Loyer → 622, SENELEC → 6052 (suggérés)
        by_lib = {l['libelle']: l for l in lignes}
        self.assertEqual(by_lib['Loyer janvier']['no_compte'], '622')
        self.assertEqual(by_lib['Facture SENELEC']['no_compte'], '6052')

    def test_confirmation_cree_les_ecritures(self):
        f = _xlsx([
            ['15/01/2026', 'Loyer janvier', '', 150000, '571'],
            ['20/01/2026', 'Achat riz cantine', '', 60000, '571'],
        ])
        r = self.client.post('/api/comptabilite/import-charges/',
                             {'fichier': f, 'confirmer': '1'}, format='multipart')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data['crees'], 2)

        # Écritures : 622 D 150000, 604 D 60000, 571 C 210000
        deb = lambda c: JournalEntry.objects.filter(
            tenant=self.tenant, no_compte=c).aggregate(s=Sum('debit'))['s'] or 0
        self.assertEqual(deb('622'), 150000)
        self.assertEqual(deb('604'), 60000)
        cred_571 = JournalEntry.objects.filter(
            tenant=self.tenant, no_compte='571').aggregate(s=Sum('credit'))['s'] or 0
        self.assertEqual(cred_571, 210000)
        # Équilibre
        agg = JournalEntry.objects.filter(tenant=self.tenant, source='CHARGE')\
            .aggregate(d=Sum('debit'), c=Sum('credit'))
        self.assertEqual(agg['d'], agg['c'])

    def test_template_telechargeable(self):
        r = self.client.get('/api/comptabilite/import-charges/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('spreadsheetml', r['Content-Type'])
