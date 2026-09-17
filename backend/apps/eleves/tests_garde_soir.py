"""Garde du soir : l'enfant récupéré après l'heure limite est facturé par tranche.

Règle de l'école (sept. 2026) : limite 17h30, tolérance jusqu'à 17h45, puis
1 000 F la tranche — jusqu'à 18h00, puis par heure pleine d'horloge.
Ce que ces tests rendent impossible :
- facturer un départ toléré, ou compter les tranches autrement que l'école ;
- un montant qui change quand l'école révise son tarif après coup ;
- un dû de garde que la fiche, le guichet et le reçu ne voient pas.
"""
import datetime

from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from apps.eleves.echeancier import construire_echeancier, precharger
from apps.eleves.garde_soir import tranches_dues
from apps.eleves.models import Eleve, GardeSoir, Section
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User

T = datetime.time


class TranchesTest(SimpleTestCase):
    def test_bareme_de_l_ecole(self):
        attendus = {T(17, 30): 0, T(17, 35): 0, T(17, 44): 0, T(17, 45): 1, T(18, 0): 1,
                    T(18, 1): 2, T(18, 15): 2, T(19, 0): 2, T(19, 1): 3, T(20, 0): 3, T(20, 30): 4}
        for depart, n in attendus.items():
            self.assertEqual(tranches_dues(depart, T(17, 30), T(17, 45)), n, depart)

    def test_limite_a_l_heure_pleine(self):
        # Limite 18h00 sans tolérance : 18h00 toléré, 18h01–19h00 = 1 tranche.
        self.assertEqual(tranches_dues(T(18, 0), T(18, 0), T(18, 0)), 0)
        self.assertEqual(tranches_dues(T(18, 1), T(18, 0), T(18, 0)), 1)
        self.assertEqual(tranches_dues(T(19, 1), T(18, 0), T(18, 0)), 2)


class GardeSoirApiTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Complexe Les Étoiles', code_etablissement='ETO',
                                            garde_soir_actif=True)
        self.user = User.objects.create_user('dir@etoiles.sn', 'x', nom='Directeur',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        today = datetime.date.today()
        self.ex = Exercice.objects.create(tenant=self.tenant, annee_scolaire='2025-2026', nb_mensualites=10,
                                          date_debut=datetime.date(today.year - 1, today.month, 1),
                                          date_fin=datetime.date(today.year + 1, today.month, 1)
                                          - datetime.timedelta(days=1))
        self.section = Section.objects.create(tenant=self.tenant, nom='CE1', frais_mensualite=20000)
        self.eleve = Eleve.objects.create(tenant=self.tenant, exercice=self.ex, section=self.section,
                                          nom_complet='Awa NDIAYE', date_inscription=self.ex.date_debut)
        self.jour = today.replace(day=1) - datetime.timedelta(days=1)   # dernier jour du mois précédent
        self.mois = self.jour.month

    def _saisir(self, heure, jour=None):
        return self.client.post('/api/eleves/garde-soir/', {
            'eleve': str(self.eleve.id), 'date': (jour or self.jour).isoformat(), 'heure_depart': heure},
            format='json')

    def _ligne(self):
        e = Eleve.objects.get(pk=self.eleve.pk)
        return next((l for l in construire_echeancier(e)['lignes'] if l['mois'] == self.mois),
                    {'du': 0.0, 'statut': None})

    def test_depart_tardif_ajoute_au_du_du_mois(self):
        # Le mois dernier peut être hors du calendrier des mensualités : le soir
        # de garde ajoute alors son mois.
        du_avant = self._ligne()['du']
        r = self._saisir('18:15')
        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual((r.data['tranches'], r.data['montant']), (2, 2000))
        self.assertEqual(self._ligne()['du'], du_avant + 2000)
        precharge = precharger(Eleve.objects.filter(pk=self.eleve.pk)).get()
        self.assertEqual(precharge.total_attendu, Eleve.objects.get(pk=self.eleve.pk).total_attendu)

    def test_depart_tolere_rien_a_facturer_et_correction(self):
        self._saisir('19:10')
        r = self._saisir('17:40')      # correction : finalement parti dans la tolérance
        self.assertEqual(r.status_code, 400)
        self.assertIn('tolérance', r.data['error'])
        self.assertFalse(GardeSoir.objects.exists())

    def test_tarif_revise_ne_change_pas_les_soirs_passes(self):
        self._saisir('18:00')
        self.tenant.garde_soir_tarif = 1500
        self.tenant.save()
        self.assertEqual(float(GardeSoir.objects.get().montant), 1000)

    def test_refus_si_inactif_ou_soir_a_venir(self):
        demain = datetime.date.today() + datetime.timedelta(days=1)
        self.assertEqual(self._saisir('18:30', jour=demain).status_code, 400)
        self.tenant.garde_soir_actif = False
        self.tenant.save()
        # L'école est gardée 5 min en cache (core/tenant.py) : on la relit.
        from django.core.cache import cache
        cache.clear()
        self.assertEqual(self._saisir('18:30').status_code, 400)

    def test_liste_du_jour_recap_et_suppression(self):
        self._saisir('19:05')
        jour = self.client.get('/api/eleves/garde-soir/', {'date': self.jour.isoformat()}).data
        self.assertEqual([(s['nom_complet'], s['heure_depart'], s['montant']) for s in jour['soirs']],
                         [('Awa NDIAYE', '19:05', 3000)])
        self.assertEqual((jour['limite'], jour['facturation_a'], jour['tarif']), ('17:30', '17:45', 1000))
        recap = self.client.get('/api/eleves/garde-soir/', {'mois': self.mois}).data
        self.assertEqual(recap['total'], 3000)
        r = self.client.delete(f"/api/eleves/garde-soir/?id={jour['soirs'][0]['id']}")
        self.assertEqual(r.status_code, 204)

    def test_recu_mentionne_la_garde_du_soir(self):
        self._saisir('18:15')
        p = Paiement.objects.create(tenant=self.tenant, exercice=self.ex, eleve=self.eleve, no_piece='R1',
                                    mode_paiement='ESPECE', statut='ACTIF', montant_mensualite=22000,
                                    mois_regles=[self.mois])
        r = self.client.get(f'/api/paiements/paiements/{p.id}/recu/')
        self.assertIn('dont garde du soir 2', ' '.join(str(l) for l in r.data['lignes']))
        self.assertEqual(self._ligne()['statut'], 'SOLDE')
