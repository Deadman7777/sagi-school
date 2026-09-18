"""Produits : le 706 est réservé au service éducatif, les services extra vont au 758.

Décision CEO du 17/09/2026 : garderie, garde du soir, cantine et activités sont
des produits accessoires. Les compter en 706 gonflait le chiffre d'affaires de
la scolarité et faussait la lecture du compte de résultat.
"""
import datetime

from rest_framework.test import APITestCase

from apps.comptabilite.models import JournalEntry
from apps.eleves.models import Eleve, EleveService, Section, Service
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User

J = datetime.date


class ProduitsAccessoiresTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Crèche Les Poussins', code_etablissement='POU')
        self.user = User.objects.create_user('dir@poussins.sn', 'x', nom='Directrice',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        today = datetime.date.today()
        self.ex = Exercice.objects.create(tenant=self.tenant, annee_scolaire='2026-2027', nb_mensualites=10,
                                          date_debut=J(today.year, today.month, 1),
                                          date_fin=J(today.year + 1, today.month, 1) - datetime.timedelta(days=1))
        self.mois = self.ex.date_debut.month
        self.section = Section.objects.create(tenant=self.tenant, nom='CI', frais_inscription=25000,
                                              frais_mensualite=30000)
        self.eleve = Eleve.objects.create(tenant=self.tenant, exercice=self.ex, section=self.section,
                                          nom_complet='Awa NDIAYE', date_inscription=self.ex.date_debut)

    def _payer(self, **data):
        r = self.client.post('/api/paiements/paiements/', {
            'eleve': str(self.eleve.id), 'mode_paiement': 'ESPECE', **data}, format='json')
        self.assertEqual(r.status_code, 201, r.content[:300])
        return r.data

    def _produits(self, paiement_id):
        return {e.no_compte: float(e.credit) for e in JournalEntry.objects.filter(
            source_id=paiement_id, credit__gt=0, no_compte__startswith='7')}

    def test_la_scolarite_reste_en_706(self):
        p = self._payer(montant_inscription=25000, montant_mensualite=30000, mois_regles=[self.mois])
        self.assertEqual(self._produits(p['id']), {'706': 55000})

    def test_la_garderie_encaissee_sur_place_va_en_758(self):
        p = self._payer(montant_mensualite=2000, mois_regles=[self.mois], part_accessoire=2000)
        self.assertEqual(self._produits(p['id']), {'758': 2000})

    def test_un_reglement_mixte_se_partage(self):
        p = self._payer(montant_mensualite=32000, mois_regles=[self.mois], part_accessoire=2000)
        self.assertEqual(self._produits(p['id']), {'706': 30000, '758': 2000})

    def test_les_services_itemises_sont_accessoires_par_defaut(self):
        service = Service.objects.create(tenant=self.tenant, nom='Cantine', montant=8000,
                                         periodicite='MENSUEL')
        EleveService.objects.create(tenant=self.tenant, eleve=self.eleve, service=service)
        p = self._payer(montant_mensualite=30000, montant_divers=8000, mois_regles=[self.mois],
                        services_regles=[{'nom': 'Cantine', 'montant': 8000, 'nature': 'MENSUEL'}])
        self.assertEqual(self._produits(p['id']), {'706': 30000, '758': 8000})
        self.assertEqual(float(Paiement.objects.get(pk=p['id']).part_accessoire), 8000)

    def test_la_part_accessoire_ne_gonfle_pas_le_total_encaisse(self):
        p = self._payer(montant_mensualite=2000, mois_regles=[self.mois], part_accessoire=2000)
        paiement = Paiement.objects.get(pk=p['id'])
        self.assertEqual(float(paiement.total), 2000)
        tresorerie = {e.no_compte: float(e.debit) for e in JournalEntry.objects.filter(
            source_id=p['id'], debit__gt=0)}
        self.assertEqual(tresorerie.get('571'), 2000)       # une seule entrée de trésorerie
        self.assertEqual(tresorerie.get('411'), 2000)

    def test_un_reliquat_anterieur_ne_constate_aucun_produit(self):
        self.eleve.reliquat_anterieur = 10000
        self.eleve.save()
        p = self._payer(montant_reliquat=10000, part_accessoire=10000)
        self.assertEqual(self._produits(p['id']), {})

    def test_le_compte_de_resultat_range_les_deux_au_bon_endroit(self):
        self._payer(montant_mensualite=30000, mois_regles=[self.mois])
        self._payer(montant_mensualite=2000, mois_regles=[self.mois], part_accessoire=2000)
        r = self.client.get('/api/comptabilite/compte-resultat/')
        self.assertEqual(r.status_code, 200, r.content[:200])
        # Deux postes distincts, compte par compte, et un total qui les porte.
        postes = {p['compte']: p['montant'] for p in r.data['detail_produits']}
        self.assertEqual((postes.get('706'), postes.get('758')), (30000, 2000))
        self.assertEqual(r.data['total_produits'], 32000)
