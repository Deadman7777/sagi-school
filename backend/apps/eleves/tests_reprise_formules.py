"""Reprise d'une crèche partie avec « une section par formule » et une garderie en frais divers.

Ce que ces tests rendent impossible :
- **changer le dû d'un élève** en regroupant ses sections — c'est vérifié élève
  par élève, et bloquant ;
- **une simulation qui écrit** en base ;
- **toucher à une année clôturée** ;
- **reclasser plus que les frais divers** d'un reçu, ou le reçu d'un enfant au mois.
"""
import datetime

from rest_framework.test import APITestCase

from apps.eleves.echeancier import construire_echeancier
from apps.eleves.models import Eleve, FormuleEleve, FormuleSection, PresenceGarderie, Section
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User

J = datetime.date


class RepriseTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Crèche Les Poussins', code_etablissement='POU')
        self.user = User.objects.create_user('dir@poussins.sn', 'x', nom='Directrice',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        today = datetime.date.today()
        self.ex = Exercice.objects.create(tenant=self.tenant, annee_scolaire='2025-2026', nb_mensualites=10,
                                          date_debut=J(today.year - 1, today.month, 1),
                                          date_fin=J(today.year + 1, today.month, 1) - datetime.timedelta(days=1))
        self.s13 = Section.objects.create(tenant=self.tenant, nom='Crèche 08H-13H', frais_inscription=25000,
                                          frais_mensualite=30000)
        self.s17 = Section.objects.create(tenant=self.tenant, nom='Crèche 08H-17H', frais_inscription=25000,
                                          frais_mensualite=40000)
        self.s19 = Section.objects.create(tenant=self.tenant, nom='Crèche 08H-19H', frais_inscription=25000,
                                          frais_mensualite=55000)
        debut = self.ex.date_debut
        self.awa = Eleve.objects.create(tenant=self.tenant, exercice=self.ex, section=self.s13,
                                        nom_complet='Awa NDIAYE', date_inscription=debut)
        self.modou = Eleve.objects.create(tenant=self.tenant, exercice=self.ex, section=self.s17,
                                          nom_complet='Modou FALL', date_inscription=debut)
        self.ndeye = Eleve.objects.create(tenant=self.tenant, exercice=self.ex, section=self.s19,
                                          nom_complet='Ndèye DIOP', date_inscription=debut)
        Paiement.objects.create(tenant=self.tenant, exercice=self.ex, eleve=self.modou, no_piece='R1',
                                mode_paiement='ESPECE', statut='ACTIF', montant_inscription=25000,
                                montant_mensualite=40000, mois_regles=[debut.month])

    def _corps(self, **extra):
        corps = {'cible': str(self.s13.id), 'formules': [
            {'section': str(self.s13.id), 'nom': '08H-13H'},
            {'section': str(self.s17.id), 'nom': '08H-17H'},
            {'section': str(self.s19.id), 'nom': '08H-19H'}]}
        corps.update(extra)
        return corps

    def _regrouper(self, **extra):
        return self.client.post('/api/eleves/sections/regrouper-formules/', self._corps(**extra), format='json')

    def test_simulation_n_ecrit_rien(self):
        avant = {e.id: e.total_attendu for e in Eleve.objects.all()}
        r = self._regrouper()
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual((r.data['nb_eleves'], r.data['differences'], r.data['applique']), (3, [], False))
        self.assertEqual([f['nb_eleves'] for f in r.data['formules']], [1, 1, 1])
        self.assertFalse(FormuleSection.objects.exists())
        self.assertEqual(Eleve.objects.get(pk=self.modou.pk).section_id, self.s17.id)
        self.assertEqual({e.id: e.total_attendu for e in Eleve.objects.all()}, avant)

    def test_application_garde_le_du_et_les_paiements(self):
        avant = {e.id: e.total_attendu for e in Eleve.objects.all()}
        r = self._regrouper(appliquer=True)
        self.assertTrue(r.data['applique'], r.data)
        self.assertEqual(sorted(r.data['sections_videes']), ['Crèche 08H-17H', 'Crèche 08H-19H'])
        for e in Eleve.objects.all():
            self.assertEqual(e.section_id, self.s13.id)
            self.assertEqual(e.total_attendu, avant[e.id])
        modou = Eleve.objects.get(pk=self.modou.pk)
        self.assertEqual(modou.formule_actuelle.nom, '08H-17H')
        premier = construire_echeancier(modou)['lignes'][0]
        self.assertEqual((premier['du'], premier['statut']), (40000, 'SOLDE'))

    def test_frais_d_entree_differents_bloquent_sauf_accord(self):
        self.s19.frais_inscription = 30000
        self.s19.save()
        r = self._regrouper(appliquer=True)
        self.assertTrue(r.data['bloque'])
        self.assertFalse(r.data['applique'])
        self.assertIn('Ndèye DIOP', [d['nom_complet'] for d in r.data['differences']])
        self.assertTrue(r.data['ecarts_frais'])
        self.assertFalse(FormuleEleve.objects.exists())
        r = self._regrouper(appliquer=True, forcer=True)
        self.assertTrue(r.data['applique'])

    def test_annee_cloturee_intacte(self):
        ancien = Exercice.objects.create(tenant=self.tenant, annee_scolaire='2024-2025', cloture=True,
                                         date_debut=J(2024, 10, 1), date_fin=J(2025, 7, 31))
        vieux = Eleve.objects.create(tenant=self.tenant, exercice=ancien, section=self.s17,
                                     nom_complet='Ancien ÉLÈVE', date_inscription=J(2024, 10, 1))
        self._regrouper(appliquer=True)
        self.assertEqual(Eleve.objects.get(pk=vieux.pk).section_id, self.s17.id)

    def test_refus_section_a_la_journee_et_doublon(self):
        self.s19.mode_tarif = 'JOURNEE'
        self.s19.tarif_journee = 5000
        self.s19.save()
        self.assertEqual(self._regrouper().status_code, 400)
        r = self.client.post('/api/eleves/sections/regrouper-formules/', {'cible': str(self.s13.id), 'formules': [
            {'section': str(self.s13.id), 'nom': 'A'}, {'section': str(self.s13.id), 'nom': 'B'}]}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_reserve_a_la_direction(self):
        caissier = User.objects.create_user('caisse@poussins.sn', 'x', nom='Caisse', role='ADMIN_SCOLARITE',
                                            tenant=self.tenant)
        self.client.force_authenticate(caissier)
        self.assertEqual(self._regrouper().status_code, 403)


class RepriseGarderieTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Crèche Les Poussins', code_etablissement='POU')
        self.user = User.objects.create_user('dir@poussins.sn', 'x', nom='Directrice',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        today = datetime.date.today()
        self.ex = Exercice.objects.create(tenant=self.tenant, annee_scolaire='2025-2026', nb_mensualites=10,
                                          date_debut=J(today.year - 1, today.month, 1),
                                          date_fin=J(today.year + 1, today.month, 1) - datetime.timedelta(days=1))
        self.garderie = Section.objects.create(tenant=self.tenant, nom='Garderie', frais_inscription=10000,
                                               mode_tarif='JOURNEE', tarif_journee=5000, tarif_demi_journee=3000)
        self.au_mois = Section.objects.create(tenant=self.tenant, nom='Crèche', frais_mensualite=30000)
        self.awa = Eleve.objects.create(tenant=self.tenant, exercice=self.ex, section=self.garderie,
                                        nom_complet='Awa NDIAYE', date_inscription=self.ex.date_debut)
        precedent = today.replace(day=1) - datetime.timedelta(days=1)
        self.mois = precedent.month
        for jour in (2, 3):
            PresenceGarderie.objects.create(tenant=self.tenant, eleve=self.awa, date=precedent.replace(day=jour),
                                            formule='JOURNEE', montant=5000)
        self.p = Paiement.objects.create(tenant=self.tenant, exercice=self.ex, eleve=self.awa, no_piece='G1',
                                         mode_paiement='ESPECE', statut='ACTIF', montant_divers=10000,
                                         observations='Garderie journée × 2', date_paiement=precedent)

    def _ligne(self):
        e = Eleve.objects.get(pk=self.awa.pk)
        return next(l for l in construire_echeancier(e)['lignes'] if l['mois'] == self.mois)

    def test_reclasser_solde_les_jours_sans_changer_le_total(self):
        self.assertEqual(self._ligne()['statut'], 'IMPAYE')
        liste = self.client.get('/api/eleves/garderie/reprise/').data
        self.assertEqual([(l['no_piece'], l['divers'], l['mois_propose']) for l in liste],
                         [('G1', 10000, self.mois)])
        r = self.client.post('/api/eleves/garderie/reprise/', {'paiement': str(self.p.id), 'mois': self.mois},
                             format='json')
        self.assertEqual(r.status_code, 200, r.content[:300])
        p = Paiement.objects.get(pk=self.p.pk)
        self.assertEqual((float(p.montant_divers), float(p.montant_mensualite), p.mois_regles),
                         (0.0, 10000.0, [self.mois]))
        self.assertEqual(float(p.total_exercice), 10000)
        self.assertIn('Reclassé en garderie', p.observations)
        self.assertEqual(self._ligne()['statut'], 'SOLDE')
        self.assertEqual(self.client.get('/api/eleves/garderie/reprise/').data, [])

    def test_montant_superieur_aux_divers_refuse(self):
        r = self.client.post('/api/eleves/garderie/reprise/',
                             {'paiement': str(self.p.id), 'mois': self.mois, 'montant': 15000}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_enfant_au_mois_refuse(self):
        self.awa.section = self.au_mois
        self.awa.save()
        r = self.client.post('/api/eleves/garderie/reprise/', {'paiement': str(self.p.id), 'mois': self.mois},
                             format='json')
        self.assertEqual(r.status_code, 400)
