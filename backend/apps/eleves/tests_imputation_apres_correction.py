"""Tests : un règlement encaissé APRÈS une correction manuelle compte quand même.

Signalé sur Shoumoul, invisible ailleurs — seule une école ayant corrigé ses
données migrées possède une imputation manuelle.

L'école peut redresser à la main la répartition mensuelle de ce qu'elle a déjà
encaissé (écran « payé mois par mois »). L'API verrouille alors le total saisi
sur les encaissements du jour : la correction décrit donc exactement l'argent
connu à cet instant, et rien d'autre.

Mais l'échéancier l'appliquait comme une vérité définitive : il ÉCRASAIT toute
la répartition et jetait le reste. Conséquence, un règlement encaissé après la
correction disparaissait de la vue mensuelle. Le reçu était juste, la caisse
était juste, et la fiche affichait le mois toujours en retard — un écart qui
grandissait à chaque encaissement.

La correction fait foi sur le montant qu'elle TOTALISE. Ce qui la dépasse, ce
sont les règlements postérieurs : ils s'imputent normalement, sur les mois
qu'ils désignent.
"""
import datetime

from rest_framework.test import APITestCase

from apps.eleves.echeancier import construire_echeancier
from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User


class ImputationApresCorrectionTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul', code_etablissement='SHO')
        self.user = User.objects.create_user(
            'a@a.sn', 'x', nom='Admin', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', nb_mensualites=12,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='Internat', frais_inscription=185000,
            frais_mensualite=60000, frais_uniforme=0, frais_fournitures=0)
        self.eleve = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, section=self.section,
            nom_complet='Mamy DAYA', date_inscription=self.ex.date_debut)

    def _payer(self, montant, mois, piece, jour=15, mois_num=1):
        """`date_paiement` et `created_at` sont auto_now_add : on les repositionne
        par `update()`, seule voie qui contourne l'automatisme."""
        p = Paiement.objects.create(
            tenant=self.tenant, exercice=self.ex, eleve=self.eleve,
            no_piece=piece, mode_paiement='ESPECE', montant_mensualite=montant,
            mois_regles=mois, statut='ACTIF')
        quand = datetime.datetime(2026, mois_num, jour, 10, 0,
                                  tzinfo=datetime.timezone.utc)
        Paiement.objects.filter(pk=p.pk).update(
            date_paiement=quand.date(), created_at=quand)
        return p

    def _corriger(self, repartition):
        """L'école redresse à la main le payé mois par mois."""
        self.eleve.imputation_mois = {str(k): v for k, v in repartition.items()}
        self.eleve.save(update_fields=['imputation_mois'])
        return Eleve.objects.select_related('tenant', 'section', 'exercice').get(
            pk=self.eleve.pk)

    def _ligne(self, eleve, mois):
        return next(l for l in construire_echeancier(eleve)['lignes']
                    if l['mois'] == mois)

    # ── Le cas rapporté ───────────────────────────────────────────────────
    def test_un_paiement_posterieur_a_la_correction_solde_bien_son_mois(self):
        """« Je viens d'enregistrer un paiement pour août, reçu normal — et la
        fiche montre toujours août en retard. »"""
        self._payer(60000, [1], 'REC-0001')
        eleve = self._corriger({1: 60000})

        self._payer(60000, [8], 'REC-0002', mois_num=8)
        eleve = Eleve.objects.select_related('tenant', 'section', 'exercice').get(
            pk=self.eleve.pk)

        aout = self._ligne(eleve, 8)
        self.assertEqual(aout['paye'], 60000)
        self.assertEqual(aout['reste'], 0)
        self.assertEqual(aout['statut'], 'SOLDE')

    def test_la_correction_garde_la_main_sur_ce_qu_elle_couvre(self):
        """Elle ne doit pas être balayée par le nouveau règlement : c'est bien
        une correction, et elle reste vraie pour l'argent qu'elle décrit."""
        self._payer(60000, [1], 'REC-0001')
        self._corriger({3: 60000})          # l'école dit : c'était mars

        self._payer(60000, [8], 'REC-0002', mois_num=8)
        eleve = Eleve.objects.select_related('tenant', 'section', 'exercice').get(
            pk=self.eleve.pk)

        self.assertEqual(self._ligne(eleve, 3)['paye'], 60000)
        self.assertEqual(self._ligne(eleve, 1)['paye'], 0)
        self.assertEqual(self._ligne(eleve, 8)['paye'], 60000)

    def test_un_acompte_posterieur_compte_pour_sa_part(self):
        self._payer(60000, [1], 'REC-0001')
        self._corriger({1: 60000})

        self._payer(23000, [8], 'REC-0002', mois_num=8)
        eleve = Eleve.objects.select_related('tenant', 'section', 'exercice').get(
            pk=self.eleve.pk)

        aout = self._ligne(eleve, 8)
        self.assertEqual(aout['paye'], 23000)
        self.assertEqual(aout['reste'], 37000)
        self.assertEqual(aout['statut'], 'PARTIEL')

    def test_plusieurs_reglements_posterieurs_comptent_tous(self):
        self._payer(60000, [1], 'REC-0001')
        self._corriger({1: 60000})

        self._payer(60000, [8], 'REC-0002', mois_num=8)
        self._payer(60000, [9], 'REC-0003', mois_num=9)
        eleve = Eleve.objects.select_related('tenant', 'section', 'exercice').get(
            pk=self.eleve.pk)

        self.assertEqual(self._ligne(eleve, 8)['reste'], 0)
        self.assertEqual(self._ligne(eleve, 9)['reste'], 0)

    # ── L'invariant : le détail ne contredit jamais son total ─────────────
    def test_la_somme_des_lignes_egale_le_total_encaisse(self):
        self._payer(60000, [1], 'REC-0001')
        self._corriger({1: 60000})
        self._payer(60000, [8], 'REC-0002', mois_num=8)
        eleve = Eleve.objects.select_related('tenant', 'section', 'exercice').get(
            pk=self.eleve.pk)

        ech = construire_echeancier(eleve)
        self.assertEqual(round(sum(l['paye'] for l in ech['lignes']), 2), 120000)

    def test_un_reglement_sans_mois_designe_solde_le_plus_ancien_ouvert(self):
        self._payer(60000, [1], 'REC-0001')
        self._corriger({1: 60000})

        self._payer(60000, [], 'REC-0002', mois_num=8)
        eleve = Eleve.objects.select_related('tenant', 'section', 'exercice').get(
            pk=self.eleve.pk)

        self.assertEqual(self._ligne(eleve, 2)['paye'], 60000)

    # ── Sans correction, rien ne change ───────────────────────────────────
    def test_sans_correction_manuelle_le_comportement_est_inchange(self):
        """Le cas de toutes les écoles non migrées."""
        self._payer(60000, [1], 'REC-0001')
        self._payer(60000, [8], 'REC-0002', mois_num=8)
        eleve = Eleve.objects.select_related('tenant', 'section', 'exercice').get(
            pk=self.eleve.pk)

        self.assertEqual(self._ligne(eleve, 1)['paye'], 60000)
        self.assertEqual(self._ligne(eleve, 8)['paye'], 60000)

    def test_une_correction_seule_reste_appliquee_telle_quelle(self):
        """Tant qu'aucun règlement ne la suit, elle fait foi intégralement."""
        self._payer(60000, [1], 'REC-0001')
        eleve = self._corriger({5: 60000})

        self.assertEqual(self._ligne(eleve, 5)['paye'], 60000)
        self.assertEqual(self._ligne(eleve, 1)['paye'], 0)

    # ── L'alerte suit ─────────────────────────────────────────────────────
    def test_le_mois_regle_ne_declenche_plus_de_relance(self):
        """C'est ce que l'école voyait : « retard d'août » sur une fiche dont
        août venait d'être encaissé."""
        from apps.eleves.echeancier import alerte_depuis_echeancier

        self._payer(60000, [1], 'REC-0001')
        self._corriger({1: 60000})
        for mois in range(2, 9):
            self._payer(60000, [mois], f'REC-{mois:04d}', mois_num=mois)
        eleve = Eleve.objects.select_related('tenant', 'section', 'exercice').get(
            pk=self.eleve.pk)

        ech = construire_echeancier(eleve, today=datetime.date(2026, 8, 20))
        alerte = alerte_depuis_echeancier(ech)

        self.assertNotIn(8, alerte['mois'])
