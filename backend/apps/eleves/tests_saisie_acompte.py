"""Tests : la saisie d'un paiement sait encaisser un acompte, et dit pourquoi.

Deux manques que le guichet ne savait pas traiter.

1. La prise en charge n'était qu'un net. Un élève à 60 000 de mensualité, plus
   8 000 et 5 000 de services, avec 8 000 de prise en charge, se voyait
   réclamer 65 000 sans que rien à l'écran n'explique le passage de 73 000 à
   65 000. Impossible de répondre au parent qui pose la question.

2. Un mois n'était que « payé » ou « non payé » — vrai dès qu'un paiement le
   DÉSIGNAIT, même sans le couvrir. Une famille qui versait 35 000 sur les
   65 000 du mois soldait ce mois aux yeux de l'écran : il proposait le suivant
   et laissait 30 000 derrière lui, que la fiche continuait pourtant à
   réclamer. Les deux écrans se contredisaient sur le même élève.

Le dû mois par mois vient désormais de l'échéancier, seule source du reste à
payer sur la fiche, les alertes et les relances.
"""
import datetime

from rest_framework.test import APITestCase

from apps.eleves.echeancier import construire_echeancier
from apps.eleves.models import Eleve, EleveService, Section, Service
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User


class SaisieAcompteTest(APITestCase):
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
            frais_mensualite=60000, frais_uniforme=0, frais_fournitures=0)
        self.eleve = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, section=self.section,
            nom_complet='Awa NDIAYE', date_inscription=self.ex.date_debut)
        # Le cas rapporté : 60 000 + 8 000 + 5 000 = 73 000, dont 8 000 pris en
        # charge → 65 000 réellement dus par la famille.
        for nom, montant in (('Cantine', 8000), ('Transport', 5000)):
            svc = Service.objects.create(tenant=self.tenant, nom=nom,
                                         montant=montant, periodicite='MENSUEL')
            EleveService.objects.create(tenant=self.tenant, eleve=self.eleve, service=svc)
        self.eleve.pec_mensualite = 8000
        self.eleve.prise_en_charge = 'Fondation'
        self.eleve.save()

    def _saisie(self):
        r = self.client.get(f'/api/eleves/{self.eleve.id}/saisie-paiement/')
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.data

    def _mois(self, num):
        return next(m for m in self._saisie()['mois_ecole'] if m['num'] == num)

    def _payer(self, montant, mois, piece='REC-1'):
        return Paiement.objects.create(
            tenant=self.tenant, exercice=self.ex, eleve=self.eleve,
            no_piece=piece, mode_paiement='ESPECE',
            montant_mensualite=montant, mois_regles=mois, statut='ACTIF')

    # ── 1. La prise en charge, décomposée ─────────────────────────────────
    def test_le_mois_ordinaire_est_decompose_brut_pec_net(self):
        """Exactement le cas rapporté : 73 000 − 8 000 = 65 000."""
        pec = self._saisie()['pec']['mensuel']

        self.assertEqual((pec['brut'], pec['pec'], pec['net']), (73000, 8000, 65000))

    def test_le_brut_moins_la_pec_egale_toujours_le_net(self):
        for cle in ('inscription', 'mensuel', 'annuel'):
            with self.subTest(cle):
                b = self._saisie()['pec'][cle]
                self.assertEqual(round(b['brut'] - b['pec'], 2), b['net'])

    def test_le_net_mensuel_est_celui_de_la_fiche(self):
        """Un seul calcul : la saisie ne refait pas le sien."""
        self.assertEqual(self._saisie()['pec']['mensuel']['net'],
                         Eleve.objects.get(pk=self.eleve.pk).du_mensuel_standard)

    def test_l_organisme_payeur_est_nomme_quand_il_y_en_a_un(self):
        self.assertEqual(self._saisie()['pec']['libelle'], 'Fondation')

    def test_sans_prise_en_charge_la_part_est_nulle(self):
        self.eleve.pec_mensualite = 0
        self.eleve.save()

        pec = self._saisie()['pec']['mensuel']
        self.assertEqual((pec['brut'], pec['pec'], pec['net']), (73000, 0, 73000))

    # ── 2. Le mois porte son reste, pas un booléen ────────────────────────
    def test_un_mois_intact_doit_le_net_de_prise_en_charge(self):
        m = self._mois(1)

        self.assertEqual((m['du_brut'], m['pec'], m['montant']), (73000, 8000, 65000))
        self.assertEqual((m['verse'], m['reste'], m['statut']), (0, 65000, 'IMPAYE'))

    def test_un_acompte_laisse_le_mois_partiel_avec_son_reste(self):
        """Le cas rapporté : la famille donne 35 000 sur 65 000."""
        self._payer(35000, [1])
        m = self._mois(1)

        self.assertEqual(m['verse'], 35000)
        self.assertEqual(m['reste'], 30000)
        self.assertEqual(m['statut'], 'PARTIEL')

    def test_un_mois_entame_n_est_pas_declare_paye(self):
        """La régression : « payé » était vrai dès qu'un paiement désignait le
        mois. L'écran sautait donc le mois et perdait l'acompte de vue."""
        self._payer(35000, [1])

        self.assertFalse(self._mois(1)['paye'])

    def test_un_mois_soldé_l_est(self):
        self._payer(65000, [1])
        m = self._mois(1)

        self.assertTrue(m['paye'])
        self.assertEqual((m['reste'], m['statut']), (0, 'SOLDE'))

    def test_le_reste_de_chaque_mois_egale_celui_de_l_echeancier(self):
        """L'invariant : la saisie et la fiche lisent le même échéancier."""
        self._payer(35000, [1])
        self._payer(65000, [2], piece='REC-2')

        lignes = {l['mois']: l for l in
                  construire_echeancier(Eleve.objects.get(pk=self.eleve.pk))['lignes']}
        for m in self._saisie()['mois_ecole']:
            if m['du']:
                with self.subTest(mois=m['num']):
                    self.assertEqual(m['reste'],  lignes[m['num']]['reste'])
                    self.assertEqual(m['verse'],  lignes[m['num']]['paye'])
                    self.assertEqual(m['statut'], lignes[m['num']]['statut'])

    def test_la_somme_des_restes_mensuels_ne_depasse_pas_le_total(self):
        self._payer(35000, [1])
        d = self._saisie()
        restes = sum(m['reste'] for m in d['mois_ecole'] if m['du'])

        self.assertLessEqual(restes, d['total_restant'])

    # ── Les mois non facturés restent hors jeu ────────────────────────────
    def test_un_mois_anterieur_a_l_entree_n_est_pas_du(self):
        self.eleve.date_inscription = datetime.date(2026, 4, 1)
        self.eleve.save()
        d = self._saisie()

        janvier = next(m for m in d['mois_ecole'] if m['num'] == 1)
        self.assertFalse(janvier['du'])
        self.assertEqual((janvier['montant'], janvier['reste']), (0, 0))

    def test_les_mois_facturés_sont_ceux_de_l_echeancier(self):
        """Le prorata était recalculé ici, et ignorait les mois saisis par
        l'école — l'écran réclamait des mois que la fiche ne facturait pas."""
        self.eleve.mois_dus = [2, 3]
        self.eleve.save()
        d = self._saisie()

        self.assertEqual(sorted(m['num'] for m in d['mois_ecole'] if m['du']), [2, 3])

    def test_un_montant_saisi_pour_un_mois_n_est_pas_re_reduit(self):
        """Le montant décidé par l'école EST le dû : la prise en charge ne
        s'applique pas une seconde fois par-dessus."""
        self.eleve.montants_mois = {'1': 20000}
        self.eleve.save()
        m = self._mois(1)

        self.assertEqual((m['montant'], m['pec'], m['du_brut']), (20000, 0, 20000))
        self.assertTrue(m['montant_saisi'])
