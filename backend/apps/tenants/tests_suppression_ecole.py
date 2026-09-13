"""« Supprimer » une école l'efface définitivement (décision du 13/09/2026).

Avant : seule la licence partait, l'école restait active en base et le site
vitrine affichait 13 « écoles équipées » pour 3 réelles.
"""
import datetime

from django.core.management import call_command
from rest_framework.test import APITestCase

from apps.comptabilite.models import JournalEntry
from apps.eleves.models import Eleve, Organisme, Section
from apps.gmrf.models import Financement, TypeFinancement
from apps.licences.models import Licence
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User


def ecole_complete(nom):
    t = Tenant.objects.create(nom=nom)
    lic = Licence.objects.create(tenant=t, cle_licence=Licence.generer_cle(nom[:6]), type='PRO',
                                 statut='ACTIVE', date_debut=datetime.date(2026, 1, 1),
                                 date_fin=datetime.date(2027, 1, 1))
    User.objects.create_user(f'dir@{nom.lower()}.sn', 'x', nom='Dir', role='ADMIN_ECOLE', tenant=t)
    ex = Exercice.objects.create(tenant=t, annee_scolaire='2026', date_debut=datetime.date(2026, 1, 1),
                                 date_fin=datetime.date(2026, 12, 31))
    section = Section.objects.create(tenant=t, nom='CM2', frais_mensualite=10000)
    eleve = Eleve.objects.create(tenant=t, exercice=ex, section=section, nom_complet='Awa',
                                 date_inscription=datetime.date(2026, 1, 1))
    etat = Organisme.objects.create(tenant=t, nom='État', type='ETAT')
    Paiement.objects.create(tenant=t, exercice=ex, eleve=eleve, no_piece='REC-1', mode_paiement='ESPECE',
                            montant_mensualite=10000, organisme=etat, statut='ACTIF')
    tf = TypeFinancement.objects.create(tenant=t, code='DON', libelle='Don')
    Financement.objects.create(tenant=t, reference='F-1', type_financement=tf, libelle='Don', montant=1000)
    JournalEntry.objects.create(tenant=t, exercice=ex, no_piece='X', date_ecriture=datetime.date(2026, 1, 2),
                                no_compte='571', debit=10000, credit=0, libelle='x', source='PAIEMENT')
    return t, lic


class SuppressionEcoleTest(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user('hg@hg.sn', 'x', nom='HG', role='SUPER_ADMIN')
        self.client.force_authenticate(self.admin)
        self.test, self.lic_test = ecole_complete('Essai')
        self.vraie, _ = ecole_complete('Vraie')

    def test_supprimer_efface_l_ecole_et_toutes_ses_donnees(self):
        r = self.client.delete(f'/api/licences/{self.lic_test.id}/', {'confirmation': 'Essai'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertFalse(Tenant.objects.filter(id=self.test.id).exists())
        for modele in (Eleve, Paiement, JournalEntry, Financement, Organisme, User):
            self.assertFalse(modele.objects.filter(tenant_id=self.test.id).exists(), modele.__name__)
        # L'autre école n'est pas touchée.
        self.assertEqual(Eleve.objects.filter(tenant=self.vraie).count(), 1)
        self.assertEqual(Paiement.objects.filter(tenant=self.vraie).count(), 1)

    def test_confirmation_du_nom_obligatoire(self):
        r = self.client.delete(f'/api/licences/{self.lic_test.id}/', {'confirmation': 'essai'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertTrue(Tenant.objects.filter(id=self.test.id).exists())

    def test_admin_ecole_ne_peut_pas_supprimer(self):
        dir_ = User.objects.get(tenant=self.test)
        self.client.force_authenticate(dir_)
        r = self.client.delete(f'/api/licences/{self.lic_test.id}/', {'confirmation': 'Essai'}, format='json')
        self.assertEqual(r.status_code, 403)

    def test_vitrine_ne_compte_que_les_ecoles_avec_licence(self):
        from django.core.cache import cache
        cache.delete('site_public_stats')
        Licence.objects.filter(tenant=self.test).delete()       # ancien « Supprimer »
        self.assertEqual(self.client.get('/api/public/stats/').data['ecoles'], 1)

    def test_commande_nettoie_les_ecoles_sans_licence(self):
        Licence.objects.filter(tenant=self.test).delete()
        call_command('supprimer_ecoles_sans_licence')                 # simulation
        self.assertTrue(Tenant.objects.filter(id=self.test.id).exists())
        call_command('supprimer_ecoles_sans_licence', appliquer=True)
        self.assertFalse(Tenant.objects.filter(id=self.test.id).exists())
        self.assertTrue(Tenant.objects.filter(id=self.vraie.id).exists())
