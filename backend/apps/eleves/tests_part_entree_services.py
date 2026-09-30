"""Tests : ce qui se paie à l'inscription — la scolarité, pas la cantine.

Cas de l'école (30/09) : terme échu, dernière mensualité encaissée à
l'inscription, et une Cantine mensuelle avec frais d'adhésion, SANS la case
« 1er mois payé à l'inscription ». À l'inscription, la famille paie
l'inscription, l'adhésion et la mensualité de juin — pas la cantine de juin,
qui se paie à son terme comme les autres mois.

Avant : tout le mois de juin basculait à l'entrée. Le guichet proposait la
cantine et, décochée, elle passait aussitôt en retard.
"""
import datetime

from rest_framework.test import APITestCase

from apps.eleves.echeancier import alerte_depuis_echeancier, construire_echeancier
from apps.eleves.models import Eleve, EleveService, Section, Service
from apps.paiements.models import Exercice, Paiement
from apps.paiements.proformas import chiffrer_nouvel_eleve
from apps.tenants.models import Tenant
from apps.users.models import User

ENTREE = datetime.date(2026, 10, 1)


class PartEntreeTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Collège Test', code_etablissement='CLT',
                                            echeance_mensualite='FIN_MOIS',
                                            dernier_mois_a_inscription=True)
        user = User.objects.create_user('d@c.sn', 'x', nom='Directeur',
                                        role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026-2027', nb_mensualites=9,
            date_debut=ENTREE, date_fin=datetime.date(2027, 9, 30))
        self.section = Section.objects.create(tenant=self.tenant, nom='CM2',
                                              frais_inscription=20000, frais_mensualite=15000)
        self.cantine = Service.objects.create(tenant=self.tenant, nom='Cantine', montant=10000,
                                              periodicite='MENSUEL')
        self.eleve = Eleve.objects.create(tenant=self.tenant, exercice=self.ex, section=self.section,
                                          nom_complet='Awa NDIAYE', date_inscription=ENTREE)
        EleveService.objects.create(tenant=self.tenant, eleve=self.eleve, service=self.cantine)

    def _juin(self, today):
        ech = construire_echeancier(self.eleve, today=today)
        return ech, next(l for l in ech['lignes'] if l['mois'] == 6)

    def _payer_inscription(self):
        # Inscription + mensualité de juin, sans la cantine (décochée au guichet).
        Paiement.objects.create(tenant=self.tenant, exercice=self.ex, eleve=self.eleve,
                                no_piece='REC-0001', mode_paiement='ESPECE',
                                montant_inscription=20000, montant_mensualite=15000,
                                mois_regles=[6], statut='ACTIF')

    def test_seule_la_scolarite_de_juin_est_due_a_l_entree(self):
        _, juin = self._juin(datetime.date(2026, 10, 2))
        self.assertEqual(juin['du'], 25000)
        self.assertEqual(juin['entree_scolarite'], 15000)
        self.assertEqual(juin['entree_services'], 0)
        self.assertEqual(juin['reste_echu'], 15000)      # la cantine n'est pas échue

    def test_cantine_decochee_n_est_pas_en_retard(self):
        self._payer_inscription()
        ech, juin = self._juin(datetime.date(2026, 10, 2))
        self.assertEqual(juin['reste'], 10000)           # la cantine reste due…
        self.assertEqual(juin['reste_echu'], 0)          # …mais pas encore échue
        self.assertFalse(juin['echu'])
        self.assertEqual(ech['synthese']['retards'], 0)
        self.assertIn(alerte_depuis_echeancier(ech)['niveau'], ('OK', 'A_JOUR'))

    def test_la_cantine_de_juin_tombe_a_son_terme(self):
        self._payer_inscription()
        _, juin = self._juin(datetime.date(2027, 7, 2))  # terme échu : juin se paie en juillet
        self.assertEqual(juin['reste_echu'], 10000)
        self.assertTrue(juin['echu'])

    def test_le_guichet_ne_reclame_que_la_part_d_entree(self):
        d = self.client.get(f'/api/eleves/{self.eleve.id}/saisie-paiement/').data
        juin = next(m for m in d['mois_ecole'] if m['num'] == 6)
        self.assertEqual(juin['entree']['scolarite'], 15000)
        self.assertEqual(juin['entree']['services'], 0)
        self.assertEqual(juin['entree']['reste'], 15000)

    def test_service_avec_la_case_1er_mois(self):
        # Case cochée sur le service : SA part du premier mois est due à
        # l'entrée — et elle seule, la scolarité d'octobre suit son terme.
        self.cantine.premier_mois_a_inscription = True
        self.cantine.save()
        ech, _ = self._juin(datetime.date(2026, 10, 2))
        octobre = next(l for l in ech['lignes'] if l['mois'] == 10)
        self.assertEqual(octobre['entree_services'], 10000)
        self.assertEqual(octobre['entree_scolarite'], 0)
        self.assertEqual(octobre['reste_echu'], 10000)

    def test_la_proforma_suit_la_meme_regle(self):
        calc = chiffrer_nouvel_eleve(self.tenant, self.ex, self.section, services=[self.cantine],
                                     date_entree=ENTREE)
        a_l_entree = calc['echeances'][0]
        self.assertEqual(a_l_entree['montant'], 20000 + 15000)   # inscription + mensualité de juin
        juin = next(e for e in calc['echeances'] if e['libelle'].startswith('Juin'))
        self.assertEqual(juin['montant'], 10000)                  # la cantine de juin, à son terme
