"""Prise en charge sur les services optionnels, mois par mois.

Les Petits Érudits (15/10/2026) : des enfants ont une prise en charge sur un
service seulement (cantine, transport…), qui change selon les mois — alors
que la PEC ne portait que sur la scolarité. C'est une REMISE : le dû de la
famille baisse, personne d'autre ne doit cette part.
"""
import datetime

from rest_framework.test import APITestCase

from apps.eleves.echeancier import construire_echeancier
from apps.eleves.models import Eleve, EleveService, Section, Service
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant
from apps.users.models import User


class PecServicesTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Les Petits Érudits', code_etablissement='LPE')
        self.client.force_authenticate(User.objects.create_user(
            'a@lpe.sn', 'x', nom='Admin', role='ADMIN_ECOLE', tenant=self.tenant))
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026-2027', cloture=False, nb_mensualites=9,
            date_debut=datetime.date(2026, 10, 1), date_fin=datetime.date(2027, 6, 30))
        section = Section.objects.create(tenant=self.tenant, nom='Crèche',
                                         frais_inscription=0, frais_mensualite=17000,
                                         frais_uniforme=0, frais_fournitures=0)
        self.eleve = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, section=section, nom_complet='Awa NDIAYE',
            date_inscription=datetime.date(2026, 10, 1))
        self.cantine = Service.objects.create(tenant=self.tenant, nom='Cantine',
                                              montant=10000, periodicite='MENSUEL')
        self.ab = EleveService.objects.create(tenant=self.tenant, eleve=self.eleve,
                                              service=self.cantine)

    def _patch(self, **data):
        r = self.client.patch(f'/api/eleves/{self.eleve.id}/',
                              {'abonnements': [str(self.cantine.id)], **data}, format='json')
        self.eleve = Eleve.objects.get(pk=self.eleve.pk)
        return r

    def test_sans_pec_rien_ne_change(self):
        self.assertEqual(self.eleve.total_attendu, (17000 + 10000) * 9)

    def test_pec_differente_selon_les_mois(self):
        r = self._patch(pec_services={str(self.cantine.id): {'10': 5000, '11': 0, '12': 10000}})
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(self.eleve.abonnements.get().pec_mois, {'10': 5000.0, '12': 10000.0})
        self.assertEqual(self.eleve.total_attendu, (17000 + 10000) * 9 - 15000)
        self.assertEqual(self.eleve.montant_pec_annuel, 15000)
        du = {l['mois']: l['du'] for l in construire_echeancier(self.eleve)['lignes']}
        self.assertEqual((du[10], du[11], du[12]), (22000, 27000, 17000))
        # La scolarité reste entière : la PEC ne touche que le service.
        self.assertEqual(self.eleve.montant_pec_mensualite_mensuel, 0)

    def test_pec_plafonnee_au_tarif_et_retirable(self):
        self._patch(pec_services={str(self.cantine.id): {'10': 99999}})
        self.assertEqual(self.eleve.total_attendu, (17000 + 10000) * 9 - 10000)
        self._patch(pec_services={str(self.cantine.id): {}})
        self.assertEqual(self.eleve.abonnements.get().pec_mois, {})
        self.assertEqual(self.eleve.total_attendu, (17000 + 10000) * 9)

    def test_mois_sans_service_n_a_rien_a_reduire(self):
        self._patch(mois_services={str(self.cantine.id): [10, 11]},
                    pec_services={str(self.cantine.id): {'10': 4000, '1': 4000}})
        self.assertEqual(self.eleve.montant_pec_services_annuel, 4000)
        self.assertEqual(self.eleve.total_attendu, 17000 * 9 + 10000 * 2 - 4000)

    def test_saisie_invalide_refusee(self):
        r = self._patch(pec_services={str(self.cantine.id): {'13': 1000}})
        self.assertEqual(r.status_code, 400)
        r = self._patch(pec_services={str(self.cantine.id): {'10': -5}})
        self.assertEqual(r.status_code, 400)

    def test_proforma_montre_la_pec_du_service(self):
        from apps.paiements.proformas import _lignes_mois
        self._patch(pec_services={str(self.cantine.id): {'10': 5000}})
        ech = construire_echeancier(self.eleve)
        lignes = _lignes_mois(self.eleve, ech['lignes'][:1])
        libelles = {l['designation']: l for l in lignes}
        self.assertIn('Prise en charge — Cantine', libelles)
        self.assertEqual(round(sum(l['montant'] for l in lignes), 2), ech['lignes'][0]['du'])
