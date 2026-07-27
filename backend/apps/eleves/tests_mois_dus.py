"""Tests : situation de l'élève modifiable — mois dus et prise en charge.

Le cas qui a motivé le lot : Fatimatou Binetou NDIAYE, entrée le 25 juin,
185 000 d'inscription dont 135 000 pris en charge, 60 000 de mensualité et
13 000 de service par mois. L'école facture août→décembre, soit 5 mois :

    (185 000 + 60 000 × 5) − 135 000  +  13 000 × 5  =  415 000

Le système affichait 141 000 : une PEC mensuelle à 60 000 (100 % de la
mensualité) et 7 mois de prorata au lieu de 5.
"""
import datetime

from rest_framework.test import APITestCase

from apps.eleves.models import Eleve, EleveService, Section, Service
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User


class MoisDusTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul', code_etablissement='SHE')
        self.user = User.objects.create_user(
            'a@a.sn', 'x', nom='Admin', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', cloture=False, nb_mensualites=12,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='INTERNAT TAHFIIZ',
            frais_inscription=185000, frais_mensualite=60000,
            frais_uniforme=0, frais_fournitures=0)
        self.eleve = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, section=self.section,
            nom_complet='Fatimatou Binetou NDIAYE',
            date_inscription=datetime.date(2026, 6, 25),
            pec_inscription=135000, pec_mensualite=60000)
        service = Service.objects.create(
            tenant=self.tenant, nom='Internat', montant=13000, periodicite='MENSUEL')
        EleveService.objects.create(tenant=self.tenant, eleve=self.eleve, service=service)

    def _patch(self, **data):
        return self.client.patch(f'/api/eleves/{self.eleve.id}/', data, format='json')

    def _relire(self):
        self.eleve.refresh_from_db()
        return self.eleve

    # ── Le cas Fatimatou, de bout en bout ─────────────────────────────────
    def test_etat_initial_reproduit_le_bug_constate(self):
        self.assertEqual(self.eleve.nb_mensualites_dues, 7)   # juin → décembre
        self.assertEqual(self.eleve.total_attendu, 141000)

    def test_corriger_pec_et_mois_donne_le_montant_attendu(self):
        r = self._patch(pec_mensualite=0, mois_dus=[8, 9, 10, 11, 12])
        self.assertEqual(r.status_code, 200, r.content[:300])

        el = self._relire()
        self.assertEqual(el.nb_mensualites_dues, 5)
        self.assertEqual(el.montant_pec_mensualite_mensuel, 0)
        self.assertEqual(el.total_attendu, 415000)

    # ── Le piège qui rendait la correction impossible ─────────────────────
    def test_pec_a_zero_ne_revient_pas_par_l_ancien_taux(self):
        """Avant, montant_pec_* repliait sur type_pec/taux quand le montant
        valait 0 : remettre la PEC à zéro la faisait revenir intacte."""
        self.eleve.type_pec = 'TOTALE'
        self.eleve.taux_pec_mensualite = 100
        self.eleve.save()

        self._patch(pec_mensualite=0)

        self.assertEqual(self._relire().montant_pec_mensualite_mensuel, 0)

    # ── Garde-fous ────────────────────────────────────────────────────────
    def test_refuse_de_retirer_un_mois_deja_regle(self):
        Paiement.objects.create(
            tenant=self.tenant, exercice=self.ex, eleve=self.eleve,
            no_piece='REC-1', mode_paiement='ESPECE',
            montant_mensualite=60000, mois_regles=[9], statut='ACTIF')

        r = self._patch(mois_dus=[10, 11, 12])

        self.assertEqual(r.status_code, 400)
        self.assertIn('septembre', str(r.data).lower())

    def test_un_paiement_annule_ne_bloque_pas(self):
        Paiement.objects.create(
            tenant=self.tenant, exercice=self.ex, eleve=self.eleve,
            no_piece='REC-2', mode_paiement='ESPECE',
            montant_mensualite=60000, mois_regles=[9], statut='ANNULE')

        self.assertEqual(self._patch(mois_dus=[10, 11, 12]).status_code, 200)

    def test_mois_hors_bornes_refuses(self):
        self.assertEqual(self._patch(mois_dus=[0, 5]).status_code, 400)
        self.assertEqual(self._patch(mois_dus=[5, 13]).status_code, 400)

    def test_doublons_et_desordre_normalises(self):
        self._patch(mois_dus=[12, 8, 8, 9])
        self.assertEqual(self._relire().mois_dus, [8, 9, 12])

    # ── Non-régression : une école qui ne touche à rien ───────────────────
    def test_mois_dus_vide_laisse_le_prorata_faire_foi(self):
        self._patch(mois_dus=[])
        el = self._relire()
        self.assertEqual(el.mois_dus, [])
        self.assertEqual(el.nb_mensualites_dues, 7)

    def test_origine_indiquee_a_l_ecran(self):
        r = self.client.get(f'/api/eleves/{self.eleve.id}/')
        self.assertEqual(r.data['mois_dus_origine'], 'PRORATA')
        self.assertEqual(r.data['mois_dus_effectifs'], [6, 7, 8, 9, 10, 11, 12])

        self._patch(mois_dus=[8, 9, 10, 11, 12])

        r = self.client.get(f'/api/eleves/{self.eleve.id}/')
        self.assertEqual(r.data['mois_dus_origine'], 'SAISI')
        self.assertEqual(r.data['mois_dus_effectifs'], [8, 9, 10, 11, 12])
