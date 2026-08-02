"""Test : appliquer un barème mensuel à toute une section.

Le montant propre à chaque mois se posait fiche par fiche. Cela convient à une
exception ; pas à un barème d'établissement. Une école dont la mensualité change
en cours d'année devait ouvrir chaque fiche pour une règle valable pour tous.
"""
import datetime

from rest_framework.test import APITestCase

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.paiements.models import Exercice, Paiement
from apps.eleves.models import Eleve, Section


class BaremeMensuelTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='CEDT LE G15')
        self.user = User.objects.create_user('dir@g15.sn', 'x', nom='Directeur',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026-2027', cloture=False,
            nb_mensualites=9,
            date_debut=datetime.date(2026, 10, 1), date_fin=datetime.date(2027, 6, 30))
        self.sn = Section.objects.create(tenant=self.tenant, nom='1re année — Sénégalais',
                                         frais_inscription=61000, frais_mensualite=60000)
        self.etr = Section.objects.create(tenant=self.tenant, nom='1re année — Étranger',
                                          frais_inscription=201000, frais_mensualite=100000)

    def _auditeur(self, nom, section=None):
        return Eleve.objects.create(tenant=self.tenant, exercice=self.ex,
                                    section=section or self.sn, nom_complet=nom,
                                    date_inscription=self.ex.date_debut)

    # Barème du G15 : 60 000 d'octobre à décembre, 70 000 de janvier à juin.
    BAREME = {'10': 60000, '11': 60000, '12': 60000,
              '1': 70000, '2': 70000, '3': 70000,
              '4': 70000, '5': 70000, '6': 70000}

    _DEFAUT = object()

    def _appliquer(self, section=None, bareme=_DEFAUT):
        # `bareme={}` doit rester un barème vide, pas retomber sur le défaut.
        montants = self.BAREME if bareme is self._DEFAUT else bareme
        return self.client.post('/api/eleves/liste/bareme-mensuel/',
                                {'section': str((section or self.sn).id),
                                 'montants': montants}, format='json')

    def test_le_bareme_se_pose_sur_toute_la_section(self):
        a, b = self._auditeur('Abdou SARR'), self._auditeur('Fatou BA')
        r = self._appliquer()
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data['appliques'], 2)

        for e in (a, b):
            e.refresh_from_db()
            self.assertEqual(e.montants_mois['10'], 60000)
            self.assertEqual(e.montants_mois['1'], 70000)
            # 61 000 d'inscription + 3 mois à 60 000 + 6 mois à 70 000
            self.assertEqual(float(e.total_attendu), 661000)

    def test_les_autres_sections_ne_bougent_pas(self):
        etranger = self._auditeur('Kofi MENSAH', section=self.etr)
        self._appliquer()
        etranger.refresh_from_db()
        self.assertEqual(etranger.montants_mois, {})

    def test_un_eleve_deja_trop_encaisse_est_signale_sans_bloquer_le_lot(self):
        ok = self._auditeur('Abdou SARR')
        trop = self._auditeur('Moussa DIOP')
        Paiement.objects.create(tenant=self.tenant, exercice=self.ex, eleve=trop,
                                no_piece='REC-0001', montant_mensualite=90000,
                                mois_regles=[10])

        r = self._appliquer()
        self.assertEqual(r.data['appliques'], 1)
        self.assertEqual(len(r.data['ignores']), 1)
        self.assertIn('Moussa DIOP', r.data['ignores'][0]['eleve'])

        ok.refresh_from_db(); trop.refresh_from_db()
        self.assertEqual(ok.montants_mois['10'], 60000)
        self.assertEqual(trop.montants_mois, {}, "la fiche en litige reste intacte")

    def test_une_exception_posee_sur_un_autre_mois_est_preservee(self):
        e = self._auditeur('Abdou SARR')
        e.montants_mois = {'7': 0}      # juillet offert, décision de l'école
        e.save(update_fields=['montants_mois'])

        self._appliquer()
        e.refresh_from_db()
        self.assertEqual(e.montants_mois['7'], 0)
        self.assertEqual(e.montants_mois['10'], 60000)

    def test_un_bareme_vide_est_refuse(self):
        self._auditeur('Abdou SARR')
        r = self._appliquer(bareme={})
        self.assertEqual(r.status_code, 400)

    def test_un_montant_negatif_est_refuse(self):
        self._auditeur('Abdou SARR')
        r = self._appliquer(bareme={'10': -5000})
        self.assertEqual(r.status_code, 400)
