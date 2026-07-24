"""Lot A — Paiement multi-mode : helper de ventilation + intégration
recette élève et charge (règlement réparti sur plusieurs modes)."""
import datetime
from decimal import Decimal

from django.test import SimpleTestCase
from django.db.models import Sum
from rest_framework.test import APITestCase

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.paiements.models import Exercice, Paiement
from apps.eleves.models import Eleve
from apps.comptabilite.models import JournalEntry
from apps.comptabilite.tresorerie import (
    normaliser_ventilation, lignes_tresorerie, compte_du_mode)


class VentilationHelperTest(SimpleTestCase):
    """Tests unitaires du helper de trésorerie (sans base)."""

    def test_reglement_simple_sans_ventilation(self):
        v = normaliser_ventilation([], 60000, mode_simple='WAVE')
        self.assertEqual(len(v), 1)
        self.assertEqual(v[0]['mode'], 'WAVE')
        self.assertEqual(v[0]['montant'], Decimal('60000.00'))

    def test_multimode_somme_exacte(self):
        v = normaliser_ventilation([
            {'mode': 'ESPECE', 'montant': 30000},
            {'mode': 'WAVE', 'montant': 20000},
            {'mode': 'ORANGE_MONEY', 'montant': 10000},
        ], 60000)
        self.assertEqual(len(v), 3)
        self.assertEqual(sum(x['montant'] for x in v), Decimal('60000.00'))

    def test_multimode_somme_incoherente_rejetee(self):
        with self.assertRaises(ValueError):
            normaliser_ventilation([
                {'mode': 'ESPECE', 'montant': 30000},
                {'mode': 'WAVE', 'montant': 20000},
            ], 60000)

    def test_montant_negatif_rejete(self):
        with self.assertRaises(ValueError):
            normaliser_ventilation([{'mode': 'ESPECE', 'montant': -5}], -5)

    def test_mode_manquant_rejete(self):
        with self.assertRaises(ValueError):
            normaliser_ventilation([{'montant': 60000}], 60000)

    def test_mapping_mode_compte(self):
        self.assertEqual(compte_du_mode('ESPECE')[0], '571')
        self.assertEqual(compte_du_mode('WAVE')[0], '5521')
        self.assertEqual(compte_du_mode('ORANGE_MONEY')[0], '5522')
        self.assertEqual(compte_du_mode('VIREMENT')[0], '521')
        self.assertEqual(compte_du_mode('INCONNU')[0], '571')  # repli caisse

    def test_lignes_tresorerie_debit_ordres_et_comptes(self):
        v = normaliser_ventilation([
            {'mode': 'ESPECE', 'montant': 30000},
            {'mode': 'WAVE', 'montant': 20000},
            {'mode': 'ORANGE_MONEY', 'montant': 10000},
        ], 60000)
        lignes = lignes_tresorerie(v, 'debit', 'Test', ordre_debut=3)
        comptes = {l['no_compte']: l['debit'] for l in lignes}
        self.assertEqual(comptes['571'], 30000)
        self.assertEqual(comptes['5521'], 20000)
        self.assertEqual(comptes['5522'], 10000)
        self.assertTrue(all(l['credit'] == 0 for l in lignes))
        self.assertEqual([l['ordre'] for l in lignes], [3, 4, 5])


class _BaseAPITest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='École A')
        self.user = User.objects.create_user(
            'admin@a.sn', 'x', nom='Admin A', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.exercice = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2025-2026',
            date_debut=datetime.date(2025, 10, 1), date_fin=datetime.date(2026, 9, 30))

    def _entries(self, **f):
        return JournalEntry.objects.filter(tenant=self.tenant, **f)


class PaiementMultiModeTest(_BaseAPITest):
    def setUp(self):
        super().setUp()
        self.eleve = Eleve.objects.create(
            tenant=self.tenant, exercice=self.exercice, nom_complet='Awa Diallo')

    def test_paiement_multimode_cree_un_debit_par_mode(self):
        r = self.client.post('/api/paiements/paiements/', {
            'eleve': self.eleve.id,
            'montant_mensualite': 60000,
            'mode_paiement': 'ESPECE',
            'modes_reglement': [
                {'mode': 'ESPECE', 'montant': 30000},
                {'mode': 'WAVE', 'montant': 20000},
                {'mode': 'ORANGE_MONEY', 'montant': 10000},
            ],
        }, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        p = Paiement.objects.get(id=r.data['id'])
        self.assertEqual(p.mode_paiement, 'MIXTE')

        def debit(compte):
            return self._entries(source='PAIEMENT', source_id=p.id, no_compte=compte)\
                .aggregate(s=Sum('debit'))['s'] or 0
        self.assertEqual(debit('571'), 30000)
        self.assertEqual(debit('5521'), 20000)
        self.assertEqual(debit('5522'), 10000)

        # L'écriture reste équilibrée.
        agg = self._entries(source='PAIEMENT', source_id=p.id)\
            .aggregate(d=Sum('debit'), c=Sum('credit'))
        self.assertEqual(agg['d'], agg['c'])

    def test_paiement_multimode_somme_fausse_rejete_et_ne_persiste_pas(self):
        r = self.client.post('/api/paiements/paiements/', {
            'eleve': self.eleve.id,
            'montant_mensualite': 60000,
            'modes_reglement': [
                {'mode': 'ESPECE', 'montant': 30000},
                {'mode': 'WAVE', 'montant': 20000},
            ],
        }, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Paiement.objects.filter(tenant=self.tenant).exists())
        self.assertFalse(self._entries(source='PAIEMENT').exists())

    def test_paiement_simple_reste_fonctionnel(self):
        r = self.client.post('/api/paiements/paiements/', {
            'eleve': self.eleve.id,
            'montant_mensualite': 50000,
            'mode_paiement': 'WAVE',
        }, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        p = Paiement.objects.get(id=r.data['id'])
        self.assertEqual(p.mode_paiement, 'WAVE')
        self.assertEqual(
            self._entries(source='PAIEMENT', source_id=p.id,
                          no_compte='5521', debit=50000).count(), 1)


class ChargeMultiModeTest(_BaseAPITest):
    def test_charge_multimode_credit_tresorerie_ventile(self):
        r = self.client.post('/api/comptabilite/charges/', {
            'no_compte': '6011',
            'montant': 60000,
            'libelle': 'Fournitures',
            'modes_reglement': [
                {'mode': 'ESPECE', 'montant': 40000},
                {'mode': 'WAVE', 'montant': 20000},
            ],
        }, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        np = r.data['no_piece']

        def credit(compte):
            return self._entries(no_piece=np, no_compte=compte)\
                .aggregate(s=Sum('credit'))['s'] or 0
        self.assertEqual(credit('571'), 40000)
        self.assertEqual(credit('5521'), 20000)

        agg = self._entries(no_piece=np).aggregate(d=Sum('debit'), c=Sum('credit'))
        self.assertEqual(agg['d'], agg['c'])

    def test_charge_simple_reste_fonctionnelle(self):
        r = self.client.post('/api/comptabilite/charges/', {
            'no_compte': '6011', 'montant': 25000, 'libelle': 'Eau',
            'compte_credit': '521',
        }, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        np = r.data['no_piece']
        self.assertEqual(
            self._entries(no_piece=np, no_compte='521', credit=25000).count(), 1)


class GedBudgetTest(_BaseAPITest):
    """Lot D — rattachement d'une pièce justificative à une ligne de budget."""
    DATA_URI = 'data:application/pdf;base64,JVBERi0xLjQK'

    def test_piece_attachable_a_une_ligne_budget(self):
        from apps.comptabilite.models import BudgetLigne
        bl = BudgetLigne.objects.create(
            tenant=self.tenant, exercice=self.exercice, no_compte='6011', libelle='Fournitures')
        r = self.client.post('/api/gouvernance/pieces/', {
            'objet_type': 'BUDGET', 'objet_id': str(bl.id),
            'type_piece': 'FACTURE', 'nom': 'devis.pdf', 'contenu': self.DATA_URI,
        }, format='json')
        self.assertEqual(r.status_code, 201, r.content)

        r2 = self.client.get(
            f'/api/gouvernance/pieces/?objet_type=BUDGET&objet_id={bl.id}')
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(len(r2.data), 1)
        self.assertEqual(r2.data[0]['nom'], 'devis.pdf')


class BudgetProjetTest(_BaseAPITest):
    """Lot B — budget analytique par projet."""

    def _projet(self, libelle):
        r = self.client.post('/api/gouvernance/projets/', {'libelle': libelle}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        return r.data['id']

    def test_meme_compte_ventilable_par_projet(self):
        pa, pb = self._projet('Projet A'), self._projet('Projet B')
        from apps.comptabilite.models import BudgetLigne
        for pid in (pa, pb, None):
            payload = {'no_compte': '6011', 'libelle': 'Fournitures', 'm01': 100000}
            if pid:
                payload['projet_id'] = pid
            r = self.client.post('/api/comptabilite/budget/', payload, format='json')
            self.assertIn(r.status_code, (200, 201), r.content)
        # 3 lignes : projet A, projet B, générale (projet vide).
        self.assertEqual(
            BudgetLigne.objects.filter(tenant=self.tenant, no_compte='6011').count(), 3)

    def test_realise_filtre_par_projet(self):
        pa = self._projet('Projet A')
        self.client.post('/api/comptabilite/budget/',
                         {'no_compte': '6011', 'm01': 100000, 'projet_id': pa}, format='json')
        # Une charge taggée projet A + une charge non taggée, même compte.
        self.client.post('/api/comptabilite/charges/',
                         {'no_compte': '6011', 'montant': 40000, 'libelle': 'F', 'projet_id': pa}, format='json')
        self.client.post('/api/comptabilite/charges/',
                         {'no_compte': '6011', 'montant': 10000, 'libelle': 'G'}, format='json')

        r = self.client.get('/api/comptabilite/budget/')
        ligne_pa = next(l for l in r.data['lignes'] if l['projet'] == pa)
        # Le réalisé de la ligne projet A ne compte QUE la charge taggée A.
        self.assertEqual(ligne_pa['total_realise'], 40000)


class RhMultiModeTest(_BaseAPITest):
    """Lot C — RH : avance multi-mode ventilée + rattachée à une ressource."""

    def _employe(self):
        from apps.rh.models import Employe
        return Employe.objects.create(
            tenant=self.tenant, nom_complet='Awa Sow', type_employe='ENSEIGNANT',
            poste='Professeure', date_embauche=datetime.date(2024, 1, 1),
            salaire_base=200000)

    def test_avance_multimode_ventilee_et_taggee(self):
        from apps.gouvernance.models import Ressource
        res = Ressource.objects.create(
            tenant=self.tenant, reference='R1', libelle='Don', montant=1000000)
        emp = self._employe()

        r = self.client.post(f'/api/rh/employes/{emp.id}/avance/', {
            'montant': 60000, 'mode_paiement': 'CAISSE',
            'ressource_id': str(res.id),
            'modes_reglement': [
                {'mode': 'CAISSE', 'montant': 40000},
                {'mode': 'WAVE', 'montant': 20000},
            ],
        }, format='json')
        self.assertEqual(r.status_code, 201, r.content)

        av = JournalEntry.objects.filter(tenant=self.tenant, source='AVANCE')
        self.assertEqual(av.filter(no_compte='421').aggregate(s=Sum('debit'))['s'], 60000)
        self.assertEqual(av.filter(no_compte='571').aggregate(s=Sum('credit'))['s'], 40000)
        self.assertEqual(av.filter(no_compte='5521').aggregate(s=Sum('credit'))['s'], 20000)
        self.assertTrue(av.filter(no_compte='421', ressource=res).exists())
        agg = av.aggregate(d=Sum('debit'), c=Sum('credit'))
        self.assertEqual(agg['d'], agg['c'])
