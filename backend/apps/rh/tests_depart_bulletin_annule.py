"""Suivi Shoumoul (septembre 2026) — trois défauts du module RH.

1. Un bulletin généré pour le mauvais mois puis ANNULÉ bloquait la période :
   impossible de refaire le bulletin d'août, « déjà généré ».
2. Aucun moyen de faire sortir un employé parti de l'établissement.
3. (écran) pas de recherche — côté front, non testé ici.
"""
import datetime
from decimal import Decimal

from rest_framework.test import APITestCase

from apps.comptabilite.models import JournalEntry
from apps.paiements.models import Exercice
from apps.rh.models import AvanceSalaire, BulletinPaie, Employe, ParametresFiscaux
from apps.tenants.models import Tenant
from apps.users.models import User


class RHBase(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='École')
        self.user = User.objects.create_user('a@a.sn', 'x', nom='A',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        ParametresFiscaux.objects.create(annee=2026, tranches_ir=[])
        Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2025-2026', nb_mensualites=10,
            date_debut=datetime.date(2025, 10, 1), date_fin=datetime.date(2026, 9, 30))
        self.employe = Employe.objects.create(
            tenant=self.tenant, nom_complet='Awa NDIAYE', matricule='EMP-0001',
            type_employe='ENSEIGNANT', poste='Professeure',
            salaire_base=Decimal('150000'), date_embauche=datetime.date(2024, 9, 1))

    def _generer(self, mois, annee=2026):
        return self.client.post('/api/rh/bulletins/', {
            'employe_id': str(self.employe.id), 'mois': mois, 'annee': annee,
        }, format='json')

    def _valider(self, bulletin_id):
        return self.client.post(f'/api/rh/bulletins/{bulletin_id}/valider/')


class BulletinAnnuleLibereLaPeriodeTest(RHBase):
    def test_regenerer_un_mois_annule(self):
        r = self._generer(8)
        self.assertEqual(r.status_code, 201, r.data)
        self._valider(r.data['id'])
        r_ann = self.client.post(f"/api/rh/bulletins/{r.data['id']}/annuler/")
        self.assertEqual(r_ann.status_code, 200, r_ann.data)

        r2 = self._generer(8)
        self.assertEqual(r2.status_code, 201, r2.data)
        # L'annulé reste en base : ses écritures et leur extourne le désignent.
        self.assertEqual(BulletinPaie.objects.filter(employe=self.employe, mois=8).count(), 2)

    def test_un_bulletin_vivant_bloque_toujours_la_periode(self):
        self._generer(7)
        r = self._generer(7)
        self.assertEqual(r.status_code, 400)
        self.assertIn('brouillon', r.data['error'])

    def test_brouillon_supprimable_valide_non(self):
        b1 = self._generer(5).data['id']
        self.assertEqual(self.client.delete(f'/api/rh/bulletins/{b1}/').status_code, 204)
        b2 = self._generer(6).data['id']
        self._valider(b2)
        self.assertEqual(self.client.delete(f'/api/rh/bulletins/{b2}/').status_code, 400)
        self.assertTrue(JournalEntry.objects.filter(source='PAIE', source_id=b2).exists())


class DepartEmployeTest(RHBase):
    def test_employe_sans_histoire_se_supprime(self):
        r = self.client.delete(f'/api/rh/employes/{self.employe.id}/')
        self.assertEqual(r.status_code, 204)
        self.assertFalse(Employe.objects.filter(id=self.employe.id).exists())

    def test_employe_paye_ne_se_supprime_pas(self):
        self._valider(self._generer(3).data['id'])
        r = self.client.delete(f'/api/rh/employes/{self.employe.id}/')
        self.assertEqual(r.status_code, 409)
        self.assertFalse(r.data['bilan']['peut_supprimer'])
        self.assertTrue(Employe.objects.filter(id=self.employe.id).exists())

    def test_depart_ferme_la_paie_apres_le_mois_de_depart(self):
        self._valider(self._generer(3).data['id'])
        r = self.client.post(f'/api/rh/employes/{self.employe.id}/depart/', {
            'date_depart': '2026-04-15', 'motif_depart': 'Démission'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.employe.refresh_from_db()
        self.assertEqual(self.employe.statut, 'QUITTE')
        # Le mois du départ reste payable (dernier salaire)…
        self.assertEqual(self._generer(4).status_code, 201)
        # … le suivant non.
        r5 = self._generer(5)
        self.assertEqual(r5.status_code, 400)
        self.assertIn('quitté', r5.data['error'])

    def test_depart_refuse_si_bulletin_posterieur(self):
        self._generer(6)
        r = self.client.post(f'/api/rh/employes/{self.employe.id}/depart/', {
            'date_depart': '2026-04-15', 'motif_depart': 'Fin de contrat'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_depart_exige_un_motif(self):
        r = self.client.post(f'/api/rh/employes/{self.employe.id}/depart/', {
            'date_depart': '2026-04-15', 'motif_depart': ''}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_bilan_signale_l_avance_non_soldee(self):
        AvanceSalaire.objects.create(tenant=self.tenant, employe=self.employe,
                                     montant=Decimal('40000'), date_avance=datetime.date(2026, 3, 1))
        bilan = self.client.get(f'/api/rh/employes/{self.employe.id}/bilan-depart/').data
        self.assertEqual(bilan['avances_restantes'], 40000.0)
        self.assertFalse(bilan['peut_supprimer'])

    def test_matricule_non_reattribue_apres_suppression(self):
        payload = {'nom_complet': 'B', 'type_employe': 'APPUI', 'poste': 'Gardien',
                   'type_contrat': 'CDI', 'date_embauche': '2026-01-01'}
        e2 = self.client.post('/api/rh/employes/', payload, format='json').data
        e3 = self.client.post('/api/rh/employes/', payload, format='json').data
        self.client.delete(f"/api/rh/employes/{e2['id']}/")
        e4 = self.client.post('/api/rh/employes/', payload, format='json').data
        self.assertNotEqual(e4['matricule'], e3['matricule'])

    def test_reintegration_annule_le_depart(self):
        self.client.post(f'/api/rh/employes/{self.employe.id}/depart/', {
            'date_depart': '2026-04-15', 'motif_depart': 'Erreur'}, format='json')
        r = self.client.post(f'/api/rh/employes/{self.employe.id}/reintegrer/')
        self.assertEqual(r.data['statut'], 'ACTIF')
        self.assertEqual(self._generer(6).status_code, 201)
