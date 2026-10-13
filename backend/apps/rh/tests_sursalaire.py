"""Sursalaire et prime de transport : saisis sur la fiche du salarié, ils
entrent au brut du bulletin et au salaire convenu de la dette au personnel."""
import datetime
from decimal import Decimal

from django.test import TestCase

from apps.tenants.models import Tenant
from apps.rh.models import Employe, ParametresFiscaux
from apps.rh.services import PaieCalculateur


class SursalaireTransportTest(TestCase):
    def setUp(self):
        ParametresFiscaux.objects.create(annee=2026)
        self.tenant = Tenant.objects.create(nom='École', regime_paie='SIMPLIFIE')
        self.employe = Employe.objects.create(
            tenant=self.tenant, nom_complet='Awa NDIAYE', type_employe='ADMINISTRATION',
            poste='Secrétaire', date_embauche=datetime.date(2025, 10, 1), salaire_base=Decimal('150000'),
            sursalaire=Decimal('25000'), prime_transport=Decimal('20800'))

    def test_sursalaire_et_transport_entrent_au_brut(self):
        b = PaieCalculateur.calculer_bulletin(self.employe, 1, 2026,
                                              sursalaire=Decimal('25000'),
                                              prime_transport=Decimal('20800'))
        self.assertEqual(b['sursalaire'], Decimal('25000'))
        self.assertEqual(b['salaire_brut'], Decimal('195800'))
        self.assertEqual(b['net_a_payer'], Decimal('195800'))

    def test_le_bulletin_garde_le_sursalaire(self):
        b = PaieCalculateur.creer_bulletin(self.employe, 1, 2026, sursalaire=Decimal('25000'))
        b.refresh_from_db()
        self.assertEqual(b.sursalaire, Decimal('25000'))

    def test_salaire_convenu_de_la_dette_inclut_sursalaire_et_transport(self):
        from apps.paiements.models import Exercice
        from apps.rh.dette_personnel import situation_personnel
        ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026-2027', nb_mensualites=9,
            date_debut=datetime.date(2026, 10, 1), date_fin=datetime.date(2027, 7, 31))
        s = situation_personnel(self.employe, exercice=ex, today=datetime.date(2026, 10, 15))
        mois = [l for l in s['lignes'] if l['source'] == 'SALAIRE']
        self.assertTrue(mois)
        self.assertEqual(mois[0]['du'], 195800)


class CoutAnnuelTest(TestCase):
    def setUp(self):
        from apps.paiements.models import Exercice
        ParametresFiscaux.objects.create(annee=2026)
        ParametresFiscaux.objects.create(annee=2027)
        self.tenant = Tenant.objects.create(nom='École', regime_paie='SIMPLIFIE')
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026-2027', nb_mensualites=9,
            date_debut=datetime.date(2026, 10, 1), date_fin=datetime.date(2027, 7, 31))
        self.employe = Employe.objects.create(
            tenant=self.tenant, nom_complet='Awa NDIAYE', type_employe='ADMINISTRATION',
            poste='Secrétaire', date_embauche=datetime.date(2025, 10, 1),
            salaire_base=Decimal('150000'), sursalaire=Decimal('25000'),
            prime_transport=Decimal('20800'))

    def test_projection_sur_les_mois_de_paie(self):
        from apps.rh.cout_personnel import cout_annuel
        r = cout_annuel(self.tenant, self.ex)
        self.assertEqual(r['nb_mois'], 9)
        self.assertEqual(r['totaux']['cout_total'], 195800 * 9)
        self.assertEqual(r['totaux']['realise'], 0)

    def test_bulletin_valide_remplace_la_projection(self):
        from apps.rh.cout_personnel import cout_annuel
        b = PaieCalculateur.creer_bulletin(self.employe, 10, 2026, sursalaire=Decimal('25000'))
        b.statut = 'VALIDE'
        b.save()
        r = cout_annuel(self.tenant, self.ex)
        self.assertEqual(r['totaux']['realise'], 175000)
        self.assertEqual(r['totaux']['prevu'], 195800 * 8)
        self.assertEqual(r['lignes'][0]['nb_mois_realises'], 1)

    def test_embauche_en_cours_d_annee(self):
        from apps.rh.cout_personnel import cout_annuel
        self.employe.date_embauche = datetime.date(2027, 1, 15)
        self.employe.save()
        r = cout_annuel(self.tenant, self.ex)
        self.assertEqual(r['lignes'][0]['nb_mois'], 6)   # janvier → juin
