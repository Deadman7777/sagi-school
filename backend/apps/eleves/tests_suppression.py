"""Suppression d'un élève saisi par erreur (08/10/2026) — voir suppression.py."""
import datetime

from rest_framework.test import APITestCase

from apps.dashboard.models import AuditLog
from apps.eleves.matricules import identite_nouvel_eleve
from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User


class SuppressionEleveTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='LPE', code_etablissement='LPE')
        self.user = User.objects.create_user('d@lpe.sn', 'x', nom='Dir', role='ADMIN_ECOLE',
                                             tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex1 = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2025-2026', nb_mensualites=10, cloture=False,
            date_debut=datetime.date(2025, 10, 1), date_fin=datetime.date(2026, 7, 31))
        self.ex2 = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026-2027', nb_mensualites=10,
            date_debut=datetime.date(2026, 10, 1), date_fin=datetime.date(2027, 7, 31))
        self.section = Section.objects.create(tenant=self.tenant, nom='CP', frais_inscription=20000,
                                              frais_mensualite=10000)

    def _eleve(self, nom='Awa Diop', exercice=None, **extra):
        exercice = exercice or self.ex2
        return Eleve.objects.create(tenant=self.tenant, exercice=exercice, section=self.section,
                                    nom_complet=nom, date_inscription=exercice.date_debut,
                                    **identite_nouvel_eleve(self.tenant, exercice), **extra)

    def _recu(self, e, statut='ACTIF', no='REC-0001'):
        return Paiement.objects.create(tenant=self.tenant, exercice=e.exercice, eleve=e,
                                       no_piece=no, montant_inscription=20000, statut=statut)

    def test_fiche_vierge_supprimee_et_tracee(self):
        e = self._eleve()
        r = self.client.delete(f'/api/eleves/{e.id}/')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(Eleve.objects.filter(id=e.id).exists())
        log = AuditLog.objects.get(action='DELETE', objet_id=str(e.id))
        self.assertIn('Awa Diop', log.description)

    def test_recu_actif_refuse(self):
        e = self._eleve()
        self._recu(e)
        r = self.client.delete(f'/api/eleves/{e.id}/')
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data['code'], 'SUPPRESSION_REFUSEE')
        self.assertIn('REC-0001', r.data['error'])
        self.assertTrue(Eleve.objects.filter(id=e.id).exists())
        self.assertTrue(Paiement.objects.filter(no_piece='REC-0001').exists())

    def test_recu_annule_part_avec_la_fiche_numero_trace(self):
        e = self._eleve()
        self._recu(e, statut='ANNULE', no='REC-0009')
        r = self.client.delete(f'/api/eleves/{e.id}/')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn('REC-0009', AuditLog.objects.get(action='DELETE').description)

    def test_reliquat_et_exercice_cloture_refuses(self):
        e = self._eleve(reliquat_anterieur=15000)
        self.assertEqual(self.client.delete(f'/api/eleves/{e.id}/').status_code, 409)
        self.ex1.cloture = True
        self.ex1.save()
        vieux = self._eleve('Moussa Fall', self.ex1)
        r = self.client.delete(f'/api/eleves/{vieux.id}/')
        self.assertEqual(r.status_code, 409)
        self.assertIn('clôturé', r.data['error'])

    def test_fiche_reinscrite_refusee_mais_parcours_entier_permis(self):
        avant = self._eleve('Fatou Sarr', self.ex1)
        apres = Eleve.objects.create(tenant=self.tenant, exercice=self.ex2, section=self.section,
                                     nom_complet='Fatou Sarr', date_inscription=self.ex2.date_debut,
                                     matricule=avant.matricule, eleve_precedent=avant)
        self.assertEqual(self.client.delete(f'/api/eleves/{avant.id}/').status_code, 409)
        r = self.client.delete(f'/api/eleves/{apres.id}/?parcours=1')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data['nb_fiches'], 2)
        self.assertFalse(Eleve.objects.filter(id__in=[avant.id, apres.id]).exists())

    def test_parcours_refuse_si_une_annee_a_un_recu(self):
        avant = self._eleve('Fatou Sarr', self.ex1)
        self._recu(avant)
        apres = Eleve.objects.create(tenant=self.tenant, exercice=self.ex2, section=self.section,
                                     nom_complet='Fatou Sarr', date_inscription=self.ex2.date_debut,
                                     matricule=avant.matricule, eleve_precedent=avant)
        self.assertEqual(self.client.delete(f'/api/eleves/{apres.id}/?parcours=1').status_code, 409)
        self.assertEqual(Eleve.objects.filter(id__in=[avant.id, apres.id]).count(), 2)

    def test_role_lecteur_ou_comptable_refuse(self):
        e = self._eleve()
        for role in ('LECTEUR', 'ADMIN_COMPTABLE'):
            self.user.role = role
            self.user.save()
            self.assertEqual(self.client.delete(f'/api/eleves/{e.id}/').status_code, 403)
        self.assertTrue(Eleve.objects.filter(id=e.id).exists())

    def test_autre_ecole_introuvable(self):
        autre = Tenant.objects.create(nom='X', code_etablissement='X')
        ex = Exercice.objects.create(tenant=autre, annee_scolaire='2026-2027', nb_mensualites=10,
                                     date_debut=self.ex2.date_debut, date_fin=self.ex2.date_fin)
        e = Eleve.objects.create(tenant=autre, exercice=ex, nom_complet='Z',
                                 date_inscription=ex.date_debut)
        self.assertEqual(self.client.delete(f'/api/eleves/{e.id}/').status_code, 404)
        self.assertTrue(Eleve.objects.filter(id=e.id).exists())
