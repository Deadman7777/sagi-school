"""Test de la reconstruction du reste dû par élève (modèle Shoumoul)."""
import datetime
import tempfile
from io import StringIO

import openpyxl
from django.core.management import call_command
from django.db.models import Sum
from rest_framework.test import APITestCase

from apps.tenants.models import Tenant
from apps.paiements.models import Exercice
from apps.eleves.models import Eleve, Section
from apps.comptabilite.models import JournalEntry


def _fichier(lignes):
    """lignes = [(nom, a_jour 'O'/'N', dette)]. Génère un xlsx au format attendu."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Élèves'
    hdr = [''] * 23
    hdr[0] = 'Nom complet *'; hdr[17] = 'À jour'; hdr[18] = 'Dette actuelle'
    ws.append(hdr)
    for nom, aj, dette in lignes:
        r = [''] * 23
        r[0] = nom; r[17] = aj; r[18] = dette
        ws.append(r)
    f = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
    wb.save(f.name)
    return f.name


class ResteDuShoumoulTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Complexe Shoumoul Excellence')
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', cloture=False, nb_mensualites=12,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='Internat Tahfiiz',
            frais_inscription=185000, frais_mensualite=60000)

    def _eleve(self, nom):
        return Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, nom_complet=nom, section=self.section,
            date_inscription=datetime.date(2026, 1, 1))

    def test_a_jour_et_non_a_jour(self):
        e_ajour = self._eleve('Keba FALL')       # renouvellement 55 000, à jour
        e_ajour2 = self._eleve('Ndeye INCONNUE')  # pas dans la liste → doit 55 000, à jour
        e_dette = self._eleve('Mamadou DIALLO')   # non à jour, dette 400 000

        fichier = _fichier([
            ('Keba FALL', 'O', ''),
            ('Ndeye INCONNUE', 'O', ''),
            ('Mamadou DIALLO', 'N', 400000),
        ])

        call_command('recaler_reste_du_shoumoul', fichier=fichier,
                     tenant_id=str(self.tenant.id), exercice='2026',
                     appliquer=True, stdout=StringIO())

        for e in (e_ajour, e_ajour2, e_dette):
            e.refresh_from_db()
        # À jour, renouvellement versé : reste = 5 × 60 000 + 0 = 300 000
        self.assertEqual(e_ajour.reste_a_payer, 300000)
        # À jour, renouvellement dû : reste = 300 000 + 55 000 = 355 000
        self.assertEqual(e_ajour2.reste_a_payer, 355000)
        # Non à jour : reste = sa dette = 400 000
        self.assertEqual(e_dette.reste_a_payer, 400000)

        # 706 non doublé : crédit reprise = débit neutralisation
        ids = [p.id for e in (e_ajour, e_ajour2, e_dette)
               for p in e.paiements.filter(mode_paiement='REPRISE')]
        rep = JournalEntry.objects.filter(source='PAIEMENT', source_id__in=ids, no_compte='706')\
            .aggregate(c=Sum('credit'))['c'] or 0
        neu = JournalEntry.objects.filter(no_piece='RECAL-REP', no_compte='706')\
            .aggregate(d=Sum('debit'))['d'] or 0
        self.assertEqual(float(rep), float(neu))

        agg = JournalEntry.objects.filter(tenant=self.tenant).aggregate(d=Sum('debit'), c=Sum('credit'))
        self.assertEqual(agg['d'], agg['c'])

    def test_dry_run_ne_cree_rien(self):
        self._eleve('Keba FALL')
        fichier = _fichier([('Keba FALL', 'O', '')])
        call_command('recaler_reste_du_shoumoul', fichier=fichier,
                     tenant_id=str(self.tenant.id), exercice='2026', stdout=StringIO())
        self.assertFalse(JournalEntry.objects.filter(tenant=self.tenant).exists())
