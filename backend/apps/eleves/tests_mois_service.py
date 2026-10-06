"""Service pris une partie de l'année seulement (transport).

Constat à une installation (octobre 2026) : un enfant prend le transport en
cours d'année, l'arrête un mois, le reprend. Dès qu'on cochait le service, il
était dû pour toute l'année.

Ce que ces tests rendent impossible :
- un mois coché qui change le total sans changer l'échéancier, le guichet ou
  la proforma (ou l'inverse) — on teste la cohérence entre écrans ;
- un service arrêté qui efface ce qui était dû les mois passés ;
- un abonnement sans aucun mois, dû nulle part mais affiché comme suivi.
"""
import datetime

from rest_framework.test import APITestCase

from apps.eleves.echeancier import construire_echeancier
from apps.eleves.models import Eleve, EleveService, Section, Service
from apps.paiements.models import Exercice
from apps.paiements.proformas import chiffrer_eleve
from apps.tenants.models import Tenant
from apps.users.models import User

ENTREE = datetime.date(2026, 10, 1)
CALENDRIER = [10, 11, 12, 1, 2, 3, 4, 5, 6]          # 9 mensualités, octobre → juin


class MoisServiceTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='École Les Niayes', code_etablissement='NIA')
        user = User.objects.create_user('d@niayes.sn', 'x', nom='Directeur', role='ADMIN_ECOLE',
                                        tenant=self.tenant)
        self.client.force_authenticate(user)
        self.ex = Exercice.objects.create(tenant=self.tenant, annee_scolaire='2026-2027', nb_mensualites=9,
                                          date_debut=ENTREE, date_fin=datetime.date(2027, 9, 30))
        self.section = Section.objects.create(tenant=self.tenant, nom='CE1', frais_inscription=20000,
                                              frais_mensualite=15000)
        self.transport = Service.objects.create(tenant=self.tenant, nom='Transport',
                                                montant=12000, periodicite='MENSUEL')
        self.awa = Eleve.objects.create(tenant=self.tenant, exercice=self.ex, section=self.section,
                                        nom_complet='Awa NDIAYE', date_inscription=ENTREE)
        EleveService.objects.create(tenant=self.tenant, eleve=self.awa, service=self.transport)

    def _recharger(self):
        return Eleve.objects.prefetch_related('abonnements__service').get(pk=self.awa.pk)

    def _mois(self, mois, attendu=200):
        r = self.client.patch(f'/api/eleves/{self.awa.id}/',
                              {'mois_services': {str(self.transport.id): mois}}, format='json')
        self.assertEqual(r.status_code, attendu, r.content)
        return r.json()

    def test_par_defaut_toute_l_annee(self):
        awa = self._recharger()
        self.assertEqual(awa.montant_services_annuel, 12000 * 9)
        self.assertEqual([m['num'] for m in self.client.get(f'/api/eleves/{self.awa.id}/').json()
                          ['mois_calendrier']], CALENDRIER)

    def test_pris_puis_arrete_puis_repris_coherent_partout(self):
        # Janvier à mars, arrêt en avril, reprise en mai.
        d = self._mois([1, 2, 3, 5])
        self.assertEqual(d['abonnements_detail'][0]['mois'], [1, 2, 3, 5])
        awa = self._recharger()
        self.assertEqual(awa.montant_services_annuel, 12000 * 4)
        self.assertEqual(awa.total_attendu, 20000 + 15000 * 9 + 12000 * 4)

        ech = construire_echeancier(awa, today=ENTREE)
        du = {l['mois']: l['du'] for l in ech['lignes']}
        self.assertEqual(du[12], 15000)
        self.assertEqual(du[1], 15000 + 12000)
        self.assertEqual(du[4], 15000)
        self.assertEqual(du[5], 15000 + 12000)
        self.assertEqual(sum(du.values()), awa.total_attendu - awa.du_hors_mensualite)

        # Guichet : le service n'est proposé que sur ses mois.
        sit = self.client.get(f'/api/eleves/{self.awa.id}/saisie-paiement/').json()
        par_mois = {m['num']: m for m in sit['mois_ecole']}
        sid = str(self.transport.id)
        self.assertEqual(par_mois[1]['services'], {sid: 12000})
        self.assertEqual(par_mois[4]['services'], {})
        self.assertEqual(sum(m['montant'] for m in sit['mois_ecole']), sum(du.values()))

        # Proforma : la décomposition retombe sur le dû de l'échéancier.
        pro = chiffrer_eleve(self._recharger(), inclure_anterieur=False, today=ENTREE)
        self.assertAlmostEqual(sum(l['montant'] for l in pro['lignes']), awa.total_attendu)
        transport = [l for l in pro['lignes'] if l['designation'] == 'Transport']
        self.assertEqual(sum(l['montant'] for l in transport), 12000 * 4)

    def test_tout_coche_revient_a_toute_l_annee(self):
        self._mois(CALENDRIER)
        self.assertEqual(EleveService.objects.get(eleve=self.awa).mois, [])

    def test_aucun_mois_refuse(self):
        self._mois([], attendu=400)
        self._mois([13], attendu=400)
        self.assertEqual(EleveService.objects.get(eleve=self.awa).mois, [])

    def test_arret_garde_les_mois_passes(self):
        """Arrêter en mars : octobre à février restent dus (et payés)."""
        self._mois([10, 11, 12, 1, 2])
        awa = self._recharger()
        ech = construire_echeancier(awa, today=ENTREE)
        du = {l['mois']: l['du'] for l in ech['lignes']}
        self.assertEqual(du[2], 15000 + 12000)
        self.assertEqual(du[3], 15000)


class LibelleExerciceTest(APITestCase):
    """Le libellé de l'exercice doit commencer par l'année de début : c'est
    la date qui fixe l'année des matricules, pas le libellé."""

    def setUp(self):
        self.tenant = Tenant.objects.create(nom='École Les Niayes', code_etablissement='NIA')
        user = User.objects.create_user('d@niayes.sn', 'x', nom='Directeur', role='ADMIN_ECOLE',
                                        tenant=self.tenant)
        self.client.force_authenticate(user)
        self.ex = Exercice.objects.create(tenant=self.tenant, annee_scolaire='2025-2026',
                                          date_debut=datetime.date(2025, 10, 1),
                                          date_fin=datetime.date(2026, 9, 30))

    def _patch(self, data):
        return self.client.patch(f'/api/paiements/exercices/{self.ex.id}/', data, format='json')

    def test_libelle_seul_change_refuse(self):
        r = self._patch({'annee_scolaire': '2026-2027'})
        self.assertEqual(r.status_code, 400)
        self.assertIn('date de début', str(r.json()['annee_scolaire']))

    def test_libelle_et_dates_ensemble_acceptes(self):
        r = self._patch({'annee_scolaire': '2026-2027', 'date_debut': '2026-10-01',
                         'date_fin': '2027-09-30'})
        self.assertEqual(r.status_code, 200, r.content)

    def test_annee_civile_acceptee(self):
        r = self._patch({'annee_scolaire': '2025'})
        self.assertEqual(r.status_code, 200, r.content)
