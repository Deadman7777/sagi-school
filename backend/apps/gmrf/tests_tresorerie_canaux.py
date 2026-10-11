"""Les prêts et financements entrent dans la « Trésorerie par canal ».

Signalé le 11/10/2026 : deux prêts (410 000 et 300 000) versés en caisse (571)
n'apparaissaient pas dans les encaissements de la caisse au tableau de bord.
Le solde les contenait (il se lit au journal) mais la colonne Encaissements
ne comptait que les reçus élèves : solde ≠ initial + encaissements −
décaissements, et l'argent du prêt n'était « ventilé » nulle part.
"""
import datetime

from rest_framework.test import APITestCase

from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant
from apps.users.models import User


class TresorerieCanauxGmrfTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='École Test', code_etablissement='ETS')
        self.user = User.objects.create_user('a@a.sn', 'x', nom='A',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        today = datetime.date.today()
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='courant', nb_mensualites=10,
            date_debut=today.replace(month=1, day=1), date_fin=today.replace(month=12, day=31),
            solde_initial_caisse=20000)
        section = Section.objects.create(tenant=self.tenant, nom='CM2', frais_inscription=50000,
                                         frais_mensualite=10000)
        self.eleve = Eleve.objects.create(tenant=self.tenant, exercice=self.ex, section=section,
                                          nom_complet='Awa NDIAYE', date_inscription=self.ex.date_debut)

    def _pret(self, montant):
        r = self.client.post('/api/gmrf/prets/', {
            'organisme_preteur': 'Banque', 'montant': montant, 'taux_interet': 0,
            'duree_mois': 10, 'date_deblocage': str(datetime.date.today()),
            'compte_tresorerie': '571'}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        return r.data

    def _caisse(self):
        d = self.client.get('/api/dashboard/tresorerie-canaux/').data
        return next(c for c in d['canaux'] if c['canal'] == 'ESPECE'), d['totaux']

    def test_les_deux_prets_entrent_en_caisse(self):
        self._pret(410000)
        self._pret(300000)
        r = self.client.post('/api/paiements/paiements/', {
            'eleve': str(self.eleve.id), 'mode_paiement': 'ESPECE',
            'montant_inscription': 50000}, format='json')
        self.assertEqual(r.status_code, 201, r.content[:300])

        caisse, totaux = self._caisse()

        self.assertEqual(caisse['encaissements_eleves'], 50000)
        self.assertEqual(caisse['autres_entrees'], 710000)
        self.assertEqual(caisse['encaissements'], 760000)
        self.assertEqual(caisse['solde'], 20000 + 760000)
        self.assertEqual(totaux['autres_entrees'], 710000)

    def test_le_solde_se_reconstitue_avec_les_colonnes(self):
        """initial + encaissements − décaissements = solde, prêt remboursé compris."""
        pret = self._pret(410000)
        self.client.patch(f"/api/gmrf/echeances/{pret['echeances'][0]['id']}/",
                          {'action': 'payer', 'mode_paiement': 'ESPECE'}, format='json')

        caisse, _ = self._caisse()

        self.assertEqual(caisse['decaissements'], 41000)
        self.assertEqual(caisse['solde_initial'] + caisse['encaissements'] - caisse['decaissements'],
                         caisse['solde'])

    def test_un_recu_eleve_annule_ne_devient_pas_une_autre_entree(self):
        r = self.client.post('/api/paiements/paiements/', {
            'eleve': str(self.eleve.id), 'mode_paiement': 'ESPECE',
            'montant_inscription': 50000}, format='json')
        self.client.post(f"/api/paiements/paiements/{r.data['id']}/annuler/")

        caisse, _ = self._caisse()

        self.assertEqual((caisse['encaissements'], caisse['autres_entrees'], caisse['decaissements']),
                         (0, 0, 0))
