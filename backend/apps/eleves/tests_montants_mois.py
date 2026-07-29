"""Tests : montant dû saisissable pour un mois particulier.

Cas Shoumoul. Les élèves règlent le premier mois avec les frais
d'inscription. Un élève entré le 16 juillet ne vivra ce mois qu'à moitié, et
l'école lui accorde une réduction — sur un mois déjà compris dans son
inscription. Le système lui réclamait pourtant juillet entier.

Deux besoins que le même champ couvre : réduire un mois entamé, et mettre à
zéro un mois déjà réglé ailleurs.
"""
import datetime

from rest_framework.test import APITestCase

from apps.eleves.models import Eleve, EleveService, Section, Service
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User


class MontantsMoisTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul', code_etablissement='CSE')
        self.user = User.objects.create_user(
            'a@a.sn', 'x', nom='Admin', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', nb_mensualites=12,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='INTERNAT', frais_inscription=185000,
            frais_mensualite=60000, frais_uniforme=0, frais_fournitures=0)
        # Entré le 16 juillet : juillet, août, septembre facturés.
        self.eleve = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, section=self.section,
            nom_complet='Awa NDIAYE',
            date_inscription=datetime.date(2026, 7, 16),
            date_entree=datetime.date(2026, 7, 16),
            mois_dus=[7, 8, 9])

    def _relire(self):
        return Eleve.objects.get(pk=self.eleve.pk)

    def _post(self, montants):
        return self.client.post(f'/api/eleves/{self.eleve.id}/montants-mois/',
                                {'montants': montants}, format='json')

    def _lignes(self):
        from apps.eleves.echeancier import construire_echeancier
        ech = construire_echeancier(self._relire())
        return {l['mois']: l for l in ech['lignes']}

    # ── Le cas signalé ────────────────────────────────────────────────────
    def test_au_depart_les_trois_mois_sont_pleins(self):
        self.assertEqual(self._relire().total_attendu, 185000 + 60000 * 3)

    def test_un_mois_inclus_dans_l_inscription_se_met_a_zero(self):
        r = self._post({'7': 0})

        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(self._lignes()[7]['du'], 0)
        self.assertEqual(self._relire().total_attendu, 185000 + 60000 * 2)

    def test_une_reduction_sur_un_mois_entame(self):
        """Entré le 16 : l'école ne facture que la moitié de juillet."""
        self._post({'7': 30000})

        self.assertEqual(self._lignes()[7]['du'], 30000)
        self.assertEqual(self._relire().total_attendu, 185000 + 30000 + 60000 * 2)

    def test_les_autres_mois_gardent_le_tarif(self):
        self._post({'7': 30000})
        lignes = self._lignes()
        self.assertEqual((lignes[8]['du'], lignes[9]['du']), (60000, 60000))

    # ── L'invariant qui compte ────────────────────────────────────────────
    def test_le_total_de_la_fiche_egale_celui_de_l_echeancier(self):
        """C'est la garantie : un montant saisi doit se retrouver dans le
        total, sinon la fiche contredit son propre détail."""
        from apps.eleves.echeancier import construire_echeancier
        self._post({'7': 30000, '9': 0})

        ech = construire_echeancier(self._relire())

        self.assertEqual(ech['totaux']['du'], self._relire().total_attendu)

    def test_zero_est_une_valeur_saisie_pas_une_absence(self):
        self._post({'7': 0})
        self.assertTrue(self._lignes()[7]['montant_saisi'])
        self.assertFalse(self._lignes()[8]['montant_saisi'])

    def test_un_dict_vide_remet_tous_les_tarifs(self):
        self._post({'7': 0, '8': 10000})
        self._post({})

        lignes = self._lignes()
        self.assertEqual((lignes[7]['du'], lignes[8]['du']), (60000, 60000))

    # ── Avec des services mensuels ────────────────────────────────────────
    def test_le_montant_saisi_remplace_aussi_les_services(self):
        service = Service.objects.create(
            tenant=self.tenant, nom='Internat', montant=13000, periodicite='MENSUEL')
        EleveService.objects.create(
            tenant=self.tenant, eleve=self.eleve, service=service)

        self.assertEqual(self._lignes()[8]['du'], 73000)   # tarif + service
        self._post({'7': 30000})
        self.assertEqual(self._lignes()[7]['du'], 30000)   # le saisi fait foi

    # ── Garde-fous ────────────────────────────────────────────────────────
    def test_refuse_de_descendre_sous_ce_qui_est_encaisse(self):
        Paiement.objects.create(
            tenant=self.tenant, exercice=self.ex, eleve=self.eleve,
            no_piece='REC-1', mode_paiement='ESPECE',
            montant_mensualite=60000, mois_regles=[7], statut='ACTIF')

        r = self._post({'7': 20000})

        self.assertEqual(r.status_code, 400)
        self.assertIn('juillet', str(r.data).lower())

    def test_refuse_un_mois_non_facture(self):
        self.assertEqual(self._post({'3': 10000}).status_code, 400)

    def test_refuse_un_montant_negatif(self):
        self.assertEqual(self._post({'7': -1000}).status_code, 400)

    def test_refuse_sur_un_exercice_cloture(self):
        self.ex.cloture = True
        self.ex.save()
        self.assertEqual(self._post({'7': 0}).status_code, 400)

    # ── Non-régression ────────────────────────────────────────────────────
    def test_sans_montant_saisi_le_calcul_ne_change_pas(self):
        eleve = self._relire()
        self.assertEqual(eleve.total_attendu, 185000 + 60000 * 3)
        self.assertEqual(eleve.du_mensuel_standard, 60000)
