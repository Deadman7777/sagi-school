"""Tests : l'écran de saisie d'un paiement dit la même chose que la fiche.

Le reçu remis à une famille et la situation financière de l'élève doivent
porter le même solde. Ils étaient calculés à deux endroits différents : la
fiche par `frais_mensualite_effectif`, la saisie en recalculant la prise en
charge depuis les anciens taux (`type_pec`, `taux_pec_*`).

La migration 0024 ayant remis ces taux à zéro pour que les montants soient
seuls maîtres, la saisie rendait depuis le tarif BRUT : elle réclamait la
mensualité entière à un élève pris en charge.
"""
import datetime

from rest_framework.test import APITestCase

from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User


class CoherenceFicheSaisieTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='École', code_etablissement='ECO')
        self.user = User.objects.create_user(
            'a@a.sn', 'x', nom='Admin', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', nb_mensualites=10,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='CM2', frais_inscription=100000,
            frais_mensualite=50000, frais_uniforme=0, frais_fournitures=0)
        self.eleve = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, section=self.section,
            nom_complet='Awa NDIAYE', date_inscription=self.ex.date_debut)

    def _saisie(self):
        r = self.client.get(f'/api/eleves/{self.eleve.id}/saisie-paiement/')
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.data

    def _relire(self):
        return Eleve.objects.get(pk=self.eleve.pk)

    # ── Le cas signalé ────────────────────────────────────────────────────
    def test_la_mensualite_proposee_est_nette_de_prise_en_charge(self):
        self.eleve.pec_mensualite = 20000
        self.eleve.save()

        self.assertEqual(self._saisie()['fees_nets']['mensualite'], 30000)

    def test_elle_egale_exactement_celle_de_la_fiche(self):
        """L'invariant : une seule vérité pour les deux écrans."""
        self.eleve.pec_mensualite = 20000
        self.eleve.save()

        self.assertEqual(self._saisie()['fees_nets']['mensualite'],
                         self._relire().frais_mensualite_effectif)

    def test_l_inscription_aussi_est_nette(self):
        self.eleve.pec_inscription = 60000
        self.eleve.save()

        self.assertEqual(self._saisie()['fees_nets']['inscription'], 40000)

    def test_une_prise_en_charge_totale_ne_reclame_rien(self):
        self.eleve.pec_mensualite = 50000        # 100 % de la mensualité
        self.eleve.save()

        self.assertEqual(self._saisie()['fees_nets']['mensualite'], 0)

    def test_les_anciens_taux_ne_reprennent_pas_la_main(self):
        """La régression venait de là : les taux, neutralisés par 0024,
        rendaient le tarif brut."""
        self.eleve.type_pec = 'MENSUALITES'
        self.eleve.taux_pec_mensualite = 50      # résidu historique
        self.eleve.pec_mensualite = 20000        # la vérité
        self.eleve.save()

        self.assertEqual(self._saisie()['fees_nets']['mensualite'], 30000)

    # ── Cohérence des soldes ──────────────────────────────────────────────
    def test_le_total_annuel_egale_celui_de_la_fiche(self):
        self.eleve.pec_mensualite = 20000
        self.eleve.save()

        self.assertEqual(self._saisie()['total_annuel_net'],
                         round(float(self._relire().total_attendu), 2))

    def test_le_reste_suit_les_encaissements(self):
        self.eleve.pec_mensualite = 20000        # net : 30 000 / mois
        self.eleve.save()
        Paiement.objects.create(
            tenant=self.tenant, exercice=self.ex, eleve=self.eleve,
            no_piece='REC-1', mode_paiement='ESPECE',
            montant_mensualite=30000, statut='ACTIF')

        self.assertEqual(self._saisie()['reste']['mensualite'], 0)

    def test_sans_prise_en_charge_rien_ne_change(self):
        d = self._saisie()
        self.assertEqual(d['fees_nets']['mensualite'], 50000)
        self.assertEqual(d['fees_nets']['inscription'], 100000)
