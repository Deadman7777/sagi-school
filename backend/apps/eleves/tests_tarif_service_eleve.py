"""Tarif d'un service propre à chaque élève.

Constat à une installation (octobre 2026) : pour le transport, dans une même
zone, le prix varie d'un élève à l'autre (distance, accord avec la famille).
Un seul tarif par service obligeait à créer un « service » par prix.

Ce que ces tests rendent impossible :
- un tarif particulier qui change le total sans changer l'échéancier (ou
  l'inverse) — on teste la cohérence, pas une valeur isolée ;
- un tarif particulier qui déteint sur les autres élèves du même service ;
- un élève sans tarif particulier qui ne suit plus le tarif du service.
"""
import datetime

from rest_framework.test import APITestCase

from apps.eleves.echeancier import construire_echeancier
from apps.eleves.models import Eleve, EleveService, Section, Service
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant
from apps.users.models import User

ENTREE = datetime.date(2026, 10, 1)


class TarifServiceEleveTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='École Les Niayes', code_etablissement='NIA')
        user = User.objects.create_user('d@niayes.sn', 'x', nom='Directeur', role='ADMIN_ECOLE',
                                        tenant=self.tenant)
        self.client.force_authenticate(user)
        self.ex = Exercice.objects.create(tenant=self.tenant, annee_scolaire='2026-2027', nb_mensualites=9,
                                          date_debut=ENTREE, date_fin=datetime.date(2027, 9, 30))
        self.section = Section.objects.create(tenant=self.tenant, nom='CE1', frais_inscription=20000,
                                              frais_mensualite=15000)
        self.transport = Service.objects.create(tenant=self.tenant, nom='Transport zone Keur Massar',
                                                montant=12000, periodicite='MENSUEL')
        self.awa = self._eleve('Awa NDIAYE')
        self.bamba = self._eleve('Bamba SECK')

    def _eleve(self, nom):
        e = Eleve.objects.create(tenant=self.tenant, exercice=self.ex, section=self.section,
                                 nom_complet=nom, date_inscription=ENTREE)
        EleveService.objects.create(tenant=self.tenant, eleve=e, service=self.transport)
        return e

    def _recharger(self, e):
        return Eleve.objects.prefetch_related('abonnements__service').get(pk=e.pk)

    def _patch(self, e, tarifs):
        r = self.client.patch(f'/api/eleves/{e.id}/', {'tarifs_services': tarifs}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def test_tarif_particulier_coherent_partout(self):
        nb = self._recharger(self.awa).nb_mensualites_dues
        avant = self._recharger(self.awa).total_attendu
        d = self._patch(self.awa, {str(self.transport.id): 8000})
        ab = d['abonnements_detail'][0]
        self.assertEqual((ab['montant'], ab['tarif_service'], ab['prix']), (8000, 12000, 8000))

        awa = self._recharger(self.awa)
        self.assertEqual(awa.total_attendu, avant - 4000 * nb)
        self.assertEqual(awa.du_mensuel_standard, 15000 + 8000)
        ech = construire_echeancier(awa, today=ENTREE)
        self.assertEqual(sum(l['du'] for l in ech['lignes'] if l['mois']), awa.total_attendu
                         - awa.du_hors_mensualite)
        # L'autre élève du même service garde le tarif du service.
        self.assertEqual(self._recharger(self.bamba).du_mensuel_standard, 15000 + 12000)
        # Situation au guichet : le montant proposé est celui de l'élève.
        sit = self.client.get(f'/api/eleves/{self.awa.id}/saisie-paiement/').json()
        svc = next(s for s in sit['services'] if s['id'] == str(self.transport.id))
        self.assertEqual((svc['montant'], svc['tarif_service']), (8000, 12000))

    def test_tarif_vide_revient_au_tarif_du_service(self):
        self._patch(self.awa, {str(self.transport.id): 8000})
        self._patch(self.awa, {str(self.transport.id): None})
        self.assertIsNone(EleveService.objects.get(eleve=self.awa).montant)
        self.transport.montant = 13000
        self.transport.save()
        self.assertEqual(self._recharger(self.awa).du_mensuel_standard, 15000 + 13000)

    def test_tarif_negatif_refuse_et_zero_accepte(self):
        r = self.client.patch(f'/api/eleves/{self.awa.id}/',
                              {'tarifs_services': {str(self.transport.id): -5}}, format='json')
        self.assertEqual(r.status_code, 400)
        self._patch(self.awa, {str(self.transport.id): 0})      # transport offert
        self.assertEqual(self._recharger(self.awa).du_mensuel_standard, 15000)

    def test_tarif_a_la_creation(self):
        r = self.client.post('/api/eleves/', {
            'nom_complet': 'Coumba DIOP', 'section': str(self.section.id), 'exercice': str(self.ex.id),
            'date_inscription': str(ENTREE), 'abonnements': [str(self.transport.id)],
            'tarifs_services': {str(self.transport.id): 10000}}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        e = self._recharger(Eleve.objects.get(nom_complet='Coumba DIOP'))
        self.assertEqual(e.du_mensuel_standard, 15000 + 10000)
