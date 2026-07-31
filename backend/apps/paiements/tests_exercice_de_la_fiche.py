"""Tests : un règlement appartient à l'exercice de la FICHE, pas au dernier ouvert.

Signalé sur Shoumoul, école aux données migrées, et invisible partout ailleurs.

Les deux notions coïncident tant qu'une école n'a qu'un exercice — le cas de
toute école créée dans l'application. Une école MIGRÉE en a plusieurs, et ses
fiches non réinscrites pointent encore l'exercice d'origine. Le règlement partait
alors sur « le dernier exercice ouvert » pendant que la fiche, son échéancier et
ses alertes lisaient l'autre :

  · le paiement n'apparaissait nulle part sur l'élève — « les paiements ne sont
    pas liés avec les fiches » ;
  · le mois réglé restait dû, sans explication.

Une seule règle désormais : tout ce qui concerne un élève se lit et s'écrit sur
SON exercice.
"""
import datetime

from rest_framework.test import APITestCase

from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User


class ExerciceDeLaFicheTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul', code_etablissement='SHO')
        self.user = User.objects.create_user(
            'a@a.sn', 'x', nom='Admin', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        # Deux exercices ouverts : la situation d'une école migrée.
        self.ancien = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2025-2026', nb_mensualites=12,
            date_debut=datetime.date(2025, 7, 1), date_fin=datetime.date(2026, 6, 30))
        self.courant = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026-2027', nb_mensualites=12,
            date_debut=datetime.date(2026, 7, 1), date_fin=datetime.date(2027, 6, 30))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='Internat', frais_inscription=185000,
            frais_mensualite=60000, frais_uniforme=0, frais_fournitures=0)

    def _eleve(self, exercice, nom='Mamy DAYA'):
        return Eleve.objects.create(
            tenant=self.tenant, exercice=exercice, section=self.section,
            nom_complet=nom, date_inscription=exercice.date_debut)

    def _encaisser(self, eleve, **montants):
        corps = {'eleve': str(eleve.id), 'mode_paiement': 'ESPECE'}
        corps.update(montants or {'montant_mensualite': 60000})
        return self.client.post('/api/paiements/paiements/', corps, format='json')

    def _saisie(self, eleve):
        r = self.client.get(f'/api/eleves/{eleve.id}/saisie-paiement/')
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.data

    # ── Le règlement suit la fiche ────────────────────────────────────────
    def test_le_paiement_va_sur_l_exercice_de_la_fiche(self):
        """La fiche est restée sur l'ancien exercice : son règlement aussi."""
        eleve = self._eleve(self.ancien)

        r = self._encaisser(eleve)

        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(Paiement.objects.get(id=r.data['id']).exercice_id,
                         self.ancien.id)

    def test_une_fiche_de_l_exercice_courant_n_est_pas_affectee(self):
        """Le cas de toutes les écoles sans données migrées."""
        eleve = self._eleve(self.courant)

        r = self._encaisser(eleve)

        self.assertEqual(Paiement.objects.get(id=r.data['id']).exercice_id,
                         self.courant.id)

    def test_le_paiement_est_visible_sur_la_fiche(self):
        """Le symptôme rapporté : le règlement n'apparaissait pas sur l'élève."""
        eleve = self._eleve(self.ancien)

        self._encaisser(eleve, montant_mensualite=60000, mois_regles=[7])

        self.assertEqual(self._saisie(eleve)['nb_paiements'], 1)

    def test_le_mois_regle_ne_reste_pas_du(self):
        """« je vois toujours 73 000 comme dû pour le mois d'août »."""
        eleve = self._eleve(self.ancien)

        self._encaisser(eleve, montant_mensualite=60000, mois_regles=[8])

        aout = next(m for m in self._saisie(eleve)['mois_ecole'] if m['num'] == 8)
        self.assertEqual(aout['verse'], 60000)
        self.assertEqual(aout['reste'], 0)

    def test_un_acompte_sur_le_mois_laisse_le_bon_reste(self):
        eleve = self._eleve(self.ancien)

        self._encaisser(eleve, montant_mensualite=23000, mois_regles=[8])

        aout = next(m for m in self._saisie(eleve)['mois_ecole'] if m['num'] == 8)
        self.assertEqual(aout['reste'], 37000)

    def test_le_deja_paye_de_l_ecran_suit_le_meme_exercice(self):
        """L'écran additionnait le déjà payé d'un exercice avec l'échéancier
        d'un autre."""
        eleve = self._eleve(self.ancien)

        self._encaisser(eleve, montant_inscription=100000)

        self.assertEqual(self._saisie(eleve)['deja_paye']['inscription'], 100000)

    # ── Un exercice clôturé se signale au lieu de mentir ──────────────────
    def test_encaisser_sur_une_fiche_cloturee_est_refuse_avec_le_motif(self):
        self.ancien.cloture = True
        self.ancien.save()
        eleve = self._eleve(self.ancien)

        r = self._encaisser(eleve)

        self.assertEqual(r.status_code, 400)
        self.assertIn('clôturé', str(r.data).lower().replace('cloture', 'clôturé'))

    # ── Chaque fiche garde ses règlements ─────────────────────────────────
    def test_deux_fiches_d_exercices_differents_ne_se_melangent_pas(self):
        vieille = self._eleve(self.ancien, 'Ancienne fiche')
        neuve   = self._eleve(self.courant, 'Nouvelle fiche')

        self._encaisser(vieille, montant_mensualite=60000)
        self._encaisser(neuve,   montant_mensualite=60000)

        self.assertEqual(self._saisie(vieille)['nb_paiements'], 1)
        self.assertEqual(self._saisie(neuve)['nb_paiements'], 1)
