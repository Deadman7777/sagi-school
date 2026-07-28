"""Tests : exigibilité paramétrable et rappels de paiement.

Les écoles ne collectent pas au même moment. Shoumoul encaisse juillet AVANT
que juillet commence ; un collège à terme échu ne réclame juillet qu'en août.
Le même impayé doit donc apparaître « en retard » ou « à venir » selon
l'établissement — sans quoi le document remis à la famille contredit la
pratique de l'école.
"""
import datetime

from rest_framework.test import APITestCase

from apps.eleves.echeancier import construire_echeancier, date_exigibilite
from apps.eleves.models import Eleve, Section
from apps.eleves.rappels import eleves_a_rappeler, fenetre_rappel
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant
from apps.users.models import User


class EcheanceBase(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul', code_etablissement='CSE')
        self.user = User.objects.create_user(
            'a@a.sn', 'x', nom='Admin', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', nb_mensualites=12,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='INTERNAT', frais_inscription=0,
            frais_mensualite=60000, frais_uniforme=0, frais_fournitures=0)
        self.eleve = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, section=self.section,
            nom_complet='Awa NDIAYE', date_inscription=self.ex.date_debut,
            date_entree=self.ex.date_debut, mois_dus=[6, 7, 8],
            telephone_tuteur='770000000', nom_tuteur='Tuteur')

    def _lignes(self, today):
        # refresh_from_db : les endpoints écrivent en base, l'objet gardé en
        # mémoire par le test resterait sinon dans son état d'avant l'appel.
        self.eleve.refresh_from_db()
        ech = construire_echeancier(self.eleve, today=today)
        return {l['mois']: l for l in ech['lignes']}


class DateExigibiliteTest(EcheanceBase):
    def test_debut_mois_est_le_defaut(self):
        """Comportement historique : aucune école ne bouge sans y toucher."""
        self.assertEqual(self.tenant.echeance_mensualite, 'DEBUT_MOIS')
        self.assertEqual(date_exigibilite(self.tenant, 2026, 7),
                         datetime.date(2026, 7, 1))

    def test_anticipe_place_l_echeance_le_mois_precedent(self):
        self.tenant.echeance_mensualite = 'ANTICIPE'
        self.assertEqual(date_exigibilite(self.tenant, 2026, 7),
                         datetime.date(2026, 6, 1))

    def test_fin_mois_place_l_echeance_le_mois_suivant(self):
        self.tenant.echeance_mensualite = 'FIN_MOIS'
        self.assertEqual(date_exigibilite(self.tenant, 2026, 7),
                         datetime.date(2026, 8, 1))

    def test_le_jour_est_respecte(self):
        self.tenant.jour_echeance = 10
        self.assertEqual(date_exigibilite(self.tenant, 2026, 7),
                         datetime.date(2026, 7, 10))

    def test_janvier_en_anticipe_bascule_sur_decembre_precedent(self):
        self.tenant.echeance_mensualite = 'ANTICIPE'
        self.assertEqual(date_exigibilite(self.tenant, 2026, 1),
                         datetime.date(2025, 12, 1))

    def test_decembre_en_fin_de_mois_bascule_sur_janvier_suivant(self):
        self.tenant.echeance_mensualite = 'FIN_MOIS'
        self.assertEqual(date_exigibilite(self.tenant, 2026, 12),
                         datetime.date(2027, 1, 1))

    def test_le_jour_est_plafonne_au_dernier_jour_reel(self):
        """Un 28 en février doit donner le 28 février, pas une erreur."""
        self.tenant.jour_echeance = 28
        self.assertEqual(date_exigibilite(self.tenant, 2026, 2),
                         datetime.date(2026, 2, 28))


class EcheancierSelonEcheanceTest(EcheanceBase):
    """Le même impayé, trois écoles, trois lectures — au 15 juillet 2026."""

    JUILLET = datetime.date(2026, 7, 15)

    def test_debut_mois_juillet_est_echu(self):
        self.assertTrue(self._lignes(self.JUILLET)[7]['echu'])

    def test_anticipe_aout_est_deja_echu(self):
        """On paie avant : en juillet, août est déjà réclamable."""
        self.tenant.echeance_mensualite = 'ANTICIPE'
        self.tenant.save()
        self.assertTrue(self._lignes(self.JUILLET)[8]['echu'])

    def test_fin_mois_juillet_n_est_pas_encore_echu(self):
        """À terme échu : juillet ne se réclame qu'en août."""
        self.tenant.echeance_mensualite = 'FIN_MOIS'
        self.tenant.save()
        self.assertFalse(self._lignes(self.JUILLET)[7]['echu'])

    def test_le_montant_des_retards_suit_le_reglage(self):
        def retards():
            return construire_echeancier(
                self.eleve, today=self.JUILLET)['synthese']['retards']

        self.tenant.echeance_mensualite = 'FIN_MOIS'
        self.tenant.save()
        a_terme_echu = retards()

        self.tenant.echeance_mensualite = 'ANTICIPE'
        self.tenant.save()
        anticipe = retards()

        # Payer d'avance rend forcément plus de mois exigibles qu'à terme échu.
        self.assertGreater(anticipe, a_terme_echu)


class MoisAInscriptionTest(EcheanceBase):
    """Certaines écoles encaissent le 1er et/ou le dernier mois à l'inscription."""

    def test_le_dernier_mois_devient_exigible_des_l_entree(self):
        self.tenant.dernier_mois_a_inscription = True
        self.tenant.save()

        # Au 15 juin : août (dernier mois dû) est normalement à venir…
        ligne = self._lignes(datetime.date(2026, 6, 15))[8]

        self.assertTrue(ligne['a_inscription'])
        self.assertTrue(ligne['echu'])
        self.assertEqual(ligne['exigible_le'], self.eleve.date_entree)

    def test_sans_le_reglage_le_dernier_mois_reste_a_venir(self):
        ligne = self._lignes(datetime.date(2026, 6, 15))[8]
        self.assertFalse(ligne['a_inscription'])
        self.assertFalse(ligne['echu'])


class FenetreRappelTest(EcheanceBase):
    def test_ouverte_dans_la_fenetre(self):
        self.tenant.rappel_jour_debut, self.tenant.rappel_jour_limite = 1, 10
        f = fenetre_rappel(self.tenant, datetime.date(2026, 7, 5))
        self.assertTrue(f['ouverte'])
        self.assertFalse(f['depassee'])
        self.assertEqual(f['jours_restants'], 5)

    def test_depassee_apres_le_dernier_delai(self):
        self.tenant.rappel_jour_debut, self.tenant.rappel_jour_limite = 1, 10
        f = fenetre_rappel(self.tenant, datetime.date(2026, 7, 20))
        self.assertFalse(f['ouverte'])
        self.assertTrue(f['depassee'])

    def test_desactivee_ne_s_ouvre_jamais(self):
        self.tenant.rappel_actif = False
        f = fenetre_rappel(self.tenant, datetime.date(2026, 7, 5))
        self.assertFalse(f['ouverte'])
        self.assertFalse(f['depassee'])


class ElevesARappelerTest(EcheanceBase):
    def test_un_eleve_en_retard_est_a_rappeler(self):
        r = eleves_a_rappeler(self.tenant, self.ex, today=datetime.date(2026, 7, 15))

        self.assertEqual(r['nb'], 1)
        ligne = r['lignes'][0]
        self.assertEqual(ligne['nom_complet'], 'Awa NDIAYE')
        self.assertEqual(ligne['contact'], '770000000')
        self.assertGreater(ligne['total_exigible'], 0)

    def test_on_ne_relance_pas_sur_un_mois_non_exigible(self):
        """À terme échu au 5 juin : juin n'est pas encore réclamable."""
        self.tenant.echeance_mensualite = 'FIN_MOIS'
        self.tenant.save()

        r = eleves_a_rappeler(self.tenant, self.ex, today=datetime.date(2026, 6, 5))

        self.assertEqual(r['nb'], 0)

    def test_un_sortant_n_est_pas_relance(self):
        self.eleve.statut = 'ABANDONNE'
        self.eleve.save()
        r = eleves_a_rappeler(self.tenant, self.ex, today=datetime.date(2026, 7, 15))
        self.assertEqual(r['nb'], 0)

    def test_api(self):
        r = self.client.get('/api/eleves/rappels/')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertIn('fenetre', r.data)
        self.assertIn('lignes', r.data)


class ReglagesAPITest(EcheanceBase):
    def test_jour_hors_bornes_refuse(self):
        r = self.client.patch(f'/api/tenants/{self.tenant.id}/',
                              {'jour_echeance': 31}, format='json')
        self.assertEqual(r.status_code, 400, r.content[:200])

    def test_dernier_delai_avant_le_debut_refuse(self):
        r = self.client.patch(f'/api/tenants/{self.tenant.id}/',
                              {'rappel_jour_debut': 15, 'rappel_jour_limite': 5},
                              format='json')
        self.assertEqual(r.status_code, 400, r.content[:200])

    def test_reglage_valide_accepte(self):
        r = self.client.patch(f'/api/tenants/{self.tenant.id}/',
                              {'echeance_mensualite': 'ANTICIPE',
                               'jour_echeance': 25}, format='json')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.echeance_mensualite, 'ANTICIPE')


class ImputationManuelleTest(EcheanceBase):
    """Corriger la répartition du payé sans jamais créer d'argent."""

    def setUp(self):
        super().setUp()
        from apps.paiements.models import Paiement
        # 60 000 encaissés sans mois désigné → imputés d'office sur juin.
        Paiement.objects.create(
            tenant=self.tenant, exercice=self.ex, eleve=self.eleve,
            no_piece='REC-1', mode_paiement='ESPECE',
            montant_mensualite=60000, statut='ACTIF')

    def _post(self, imputation):
        return self.client.post(f'/api/eleves/{self.eleve.id}/imputation/',
                                {'imputation': imputation}, format='json')

    def test_l_imputation_automatique_solde_le_plus_ancien(self):
        lignes = self._lignes(datetime.date(2026, 7, 15))
        self.assertEqual(lignes[6]['paye'], 60000)
        self.assertEqual(lignes[7]['paye'], 0)

    def test_deplacer_le_paye_vers_un_autre_mois(self):
        r = self._post({'7': 60000})

        self.assertEqual(r.status_code, 200, r.content[:300])
        lignes = self._lignes(datetime.date(2026, 7, 15))
        self.assertEqual(lignes[6]['paye'], 0)
        self.assertEqual(lignes[7]['paye'], 60000)

    def test_repartir_sur_deux_mois(self):
        self._post({'6': 20000, '7': 40000})
        lignes = self._lignes(datetime.date(2026, 7, 15))
        self.assertEqual((lignes[6]['paye'], lignes[7]['paye']), (20000, 40000))

    def test_un_ecart_est_refuse_s_il_depasse_la_part_reprise(self):
        """Sans reprise, l'écart viendrait d'un encaissement réel : on refuse,
        c'est le paiement qu'il faut corriger."""
        r = self._post({'6': 10000, '7': 0, '8': 0})   # 10 000 pour 60 000 encaissés

        self.assertEqual(r.status_code, 400)
        self.assertIn('paiement', str(r.data).lower())

    def test_un_dict_vide_revient_a_l_automatique(self):
        self._post({'7': 60000})
        r = self._post({})

        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._lignes(datetime.date(2026, 7, 15))[6]['paye'], 60000)

    def test_refuse_un_mois_non_facture(self):
        self.assertEqual(self._post({'3': 60000}).status_code, 400)

    def test_refuse_un_montant_negatif(self):
        self.assertEqual(self._post({'6': -100, '7': 60100}).status_code, 400)

    def test_la_somme_des_lignes_egale_toujours_les_totaux(self):
        self._post({'6': 20000, '7': 40000})
        from apps.eleves.echeancier import construire_echeancier
        e = construire_echeancier(self.eleve, today=datetime.date(2026, 7, 15))
        somme = e['hors_mensualite']['paye'] + sum(l['paye'] for l in e['lignes'])
        self.assertEqual(somme, e['totaux']['paye'])


class ImputationDonneesMigreesTest(EcheanceBase):
    """Préciser mois par mois un « déjà payé » repris à la migration.

    La reprise enregistre un montant global sans détail mensuel. L'école
    connaît souvent la vraie ventilation : la saisir doit ajuster la reprise,
    JAMAIS la trésorerie — une reprise s'écrit 411/706/890, pas un franc de
    caisse.
    """

    def setUp(self):
        super().setUp()
        from apps.paiements.reprise import creer_paiement_reprise
        self.reprise = creer_paiement_reprise(
            self.tenant, self.ex, self.eleve,
            montants={'montant_inscription': 0, 'montant_mensualite': 60000,
                      'montant_uniforme': 0, 'montant_fournitures': 0})

    def _post(self, imputation):
        return self.client.post(f'/api/eleves/{self.eleve.id}/imputation/',
                                {'imputation': imputation}, format='json')

    def _tresorerie(self):
        from django.db.models import Sum
        from apps.comptabilite.models import JournalEntry
        agg = JournalEntry.objects.filter(
            tenant=self.tenant, exercice=self.ex,
            no_compte__startswith='5').aggregate(d=Sum('debit'), c=Sum('credit'))
        return float(agg['d'] or 0) - float(agg['c'] or 0)

    def test_saisir_plus_que_la_reprise_l_ajuste(self):
        avant = self._tresorerie()

        r = self._post({'6': 60000, '7': 60000, '8': 60000})   # 180 000

        self.assertEqual(r.status_code, 200, r.content[:400])
        self.assertEqual(r.data['reprise_ajustee'], 120000)
        lignes = self._lignes(datetime.date(2026, 7, 15))
        self.assertEqual(lignes[8]['paye'], 60000)
        self.assertEqual(self._tresorerie(), avant)     # ← rien n'a bougé

    def test_saisir_moins_ajuste_aussi_sans_toucher_la_caisse(self):
        avant = self._tresorerie()

        r = self._post({'6': 20000, '7': 0, '8': 0})

        self.assertEqual(r.status_code, 200, r.content[:400])
        self.assertEqual(r.data['reprise_ajustee'], -40000)
        self.assertEqual(self._tresorerie(), avant)

    def test_la_somme_des_lignes_egale_toujours_les_totaux(self):
        self._post({'6': 60000, '7': 60000, '8': 60000})
        self.eleve.refresh_from_db()
        e = construire_echeancier(self.eleve, today=datetime.date(2026, 7, 15))
        somme = e['hors_mensualite']['paye'] + sum(l['paye'] for l in e['lignes'])
        self.assertEqual(somme, e['totaux']['paye'])

    def test_descendre_sous_les_encaissements_reels_est_refuse(self):
        """La reprise est corrigeable, pas l'argent réellement reçu."""
        from apps.paiements.models import Paiement
        Paiement.objects.create(
            tenant=self.tenant, exercice=self.ex, eleve=self.eleve,
            no_piece='REC-9', mode_paiement='ESPECE',
            montant_mensualite=30000, statut='ACTIF')

        # 60 000 de reprise + 30 000 encaissés = 90 000 ; on descend à 10 000.
        r = self._post({'6': 10000, '7': 0, '8': 0})

        self.assertEqual(r.status_code, 400)
        self.assertIn('paiement', str(r.data).lower())
