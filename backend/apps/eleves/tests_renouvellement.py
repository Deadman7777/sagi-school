"""Tests : un ancien élève doit son renouvellement, pas son inscription.

Un daara n'inscrit un ndongo qu'UNE fois, à son arrivée. Les années suivantes
il paie un renouvellement — souvent moins cher, et qui porte le nom que
l'établissement lui donne.

Le système réclamait l'inscription à tout le monde, chaque année. Les écoles
s'en sortaient en inscrivant sur CHAQUE ancien élève une fausse prise en charge
égale à l'inscription, pour que le total annuel dû reste juste : une donnée
fausse, recopiée à la main tous les ans, qui faisait passer une école entière
pour prise en charge et rendait le suivi des vraies prises en charge illisible.

Deux garde-fous tenus ici :

  · une école qui n'active rien ne voit RIEN changer — l'inscription reste due
    chaque année, comme dans une école classique ;
  · sans date d'entrée, l'élève est un nouvel entrant. On ne retire jamais un
    dû sur une donnée absente.
"""
import datetime

from rest_framework.test import APITestCase

from apps.eleves.echeancier import construire_echeancier
from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant
from apps.users.models import User


class RenouvellementTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Daara', code_etablissement='DAA')
        self.user = User.objects.create_user(
            'a@a.sn', 'x', nom='Admin', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        # Année scolaire d'octobre à juillet — le cas du daara de l'exemple.
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2025-2026', nb_mensualites=10,
            date_debut=datetime.date(2025, 10, 1), date_fin=datetime.date(2026, 7, 31))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='Tahfiiz', frais_inscription=50000,
            frais_renouvellement=15000, frais_mensualite=20000,
            frais_uniforme=0, frais_fournitures=0)

    def _eleve(self, date_entree=None, **kw):
        """Un ndongo. Sans date d'entrée précisée, il arrive cette année."""
        champs = dict(
            tenant=self.tenant, exercice=self.ex, section=self.section,
            nom_complet='Modou FALL', date_inscription=self.ex.date_debut)
        champs.update(kw)
        e = Eleve.objects.create(**champs)
        if date_entree is not None:
            e.date_entree = date_entree
            e.save()
        return Eleve.objects.select_related('tenant', 'section', 'exercice').get(pk=e.pk)

    def _activer(self, mois=None, libelle='Renouvellement'):
        self.tenant.renouvellement_actif = True
        self.tenant.libelle_renouvellement = libelle
        self.tenant.mois_renouvellement = mois
        self.tenant.save()

    def _saisie(self, eleve):
        r = self.client.get(f'/api/eleves/{eleve.id}/saisie-paiement/')
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.data

    # ── L'école qui n'active rien ne voit rien changer ────────────────────
    def test_sans_le_reglage_l_inscription_reste_due_a_tous(self):
        ancien = self._eleve(date_entree=datetime.date(2021, 10, 5))

        self.assertFalse(ancien.renouvellement_du)
        self.assertEqual(ancien.frais_entree, 50000)
        self.assertEqual(ancien.libelle_frais_entree, 'Inscription')

    def test_sans_le_reglage_le_total_annuel_est_inchange(self):
        ancien = self._eleve(date_entree=datetime.date(2021, 10, 5))

        self.assertEqual(ancien.total_attendu, 50000 + 20000 * 10)

    # ── Le cas rapporté ───────────────────────────────────────────────────
    def test_un_nouvel_entrant_doit_son_inscription(self):
        """Entré le 10 octobre 2025, dans l'exercice qui commence en octobre."""
        self._activer()
        nouveau = self._eleve(date_entree=datetime.date(2025, 10, 10))

        self.assertFalse(nouveau.renouvellement_du)
        self.assertEqual(nouveau.frais_entree, 50000)

    def test_son_camarade_de_l_an_dernier_doit_le_renouvellement(self):
        self._activer()
        ancien = self._eleve(date_entree=datetime.date(2024, 11, 3))

        self.assertTrue(ancien.renouvellement_du)
        self.assertEqual(ancien.frais_entree, 15000)
        self.assertEqual(ancien.libelle_frais_entree, 'Renouvellement')

    def test_le_total_annuel_suit_le_renouvellement(self):
        """Le motif du contournement : sans ça, il fallait 35 000 de fausse
        prise en charge pour que le total tombe juste."""
        self._activer()
        ancien = self._eleve(date_entree=datetime.date(2024, 11, 3))

        self.assertEqual(ancien.total_attendu, 15000 + 20000 * 10)
        self.assertEqual(ancien.montant_pec_annuel, 0)

    def test_l_ecole_donne_son_propre_nom(self):
        self._activer(libelle='Droit de rentrée')
        ancien = self._eleve(date_entree=datetime.date(2020, 10, 1))

        self.assertEqual(ancien.libelle_frais_entree, 'Droit de rentrée')

    def test_une_entree_en_janvier_reste_de_la_promo_precedente(self):
        """L'année scolaire court d'octobre à juillet : janvier 2026 appartient
        à la promo 2025, donc ce ndongo est un nouvel entrant."""
        self._activer()
        janvier = self._eleve(date_entree=datetime.date(2026, 1, 15))

        self.assertFalse(janvier.renouvellement_du)

    # ── On ne retire jamais un dû sur une donnée absente ──────────────────
    def test_une_fiche_sans_historique_est_un_nouvel_entrant(self):
        """`date_inscription` ne peut pas être vide (NOT NULL, défaut du jour) :
        une fiche créée sans rien renseigner d'autre tombe donc dans l'exercice
        courant, et son élève doit son inscription."""
        self._activer()
        e = self._eleve()
        Eleve.objects.filter(pk=e.pk).update(date_entree=None, annee_entree='')
        e = Eleve.objects.select_related('tenant', 'section', 'exercice').get(pk=e.pk)

        self.assertFalse(e.renouvellement_du)
        self.assertEqual(e.frais_entree, 50000)

    def test_a_defaut_de_date_d_entree_la_promo_tranche(self):
        self._activer()
        e = self._eleve()
        Eleve.objects.filter(pk=e.pk).update(date_entree=None, annee_entree='2023-2024')
        e = Eleve.objects.select_related('tenant', 'section', 'exercice').get(pk=e.pk)

        self.assertTrue(e.renouvellement_du)

    def test_a_defaut_de_tout_la_date_d_inscription_tranche(self):
        """Le formulaire de création intitule `date_inscription` « Date
        d'entrée » : c'est là que les écoles migrées ont saisi la vraie date."""
        self._activer()
        e = self._eleve(date_inscription=datetime.date(2022, 10, 4))
        Eleve.objects.filter(pk=e.pk).update(date_entree=None, annee_entree='')
        e = Eleve.objects.select_related('tenant', 'section', 'exercice').get(pk=e.pk)

        self.assertTrue(e.renouvellement_du)

    def test_une_date_d_inscription_recalee_sur_l_exercice_ne_ment_pas(self):
        """Elle est repositionnée chaque année pour le prorata : elle doit alors
        dire « nouveau », le repli sûr — jamais inventer un renouvellement."""
        self._activer()
        e = self._eleve(date_inscription=self.ex.date_debut)
        Eleve.objects.filter(pk=e.pk).update(date_entree=None, annee_entree='')
        e = Eleve.objects.select_related('tenant', 'section', 'exercice').get(pk=e.pk)

        self.assertFalse(e.renouvellement_du)

    # ── Prise en charge : plafonnée au dû réel ────────────────────────────
    def test_la_prise_en_charge_ne_depasse_pas_le_renouvellement(self):
        """Plafonner sur l'inscription laisserait une prise en charge de 50 000
        écraser un dû de 15 000 et rendrait un reste négatif."""
        self._activer()
        ancien = self._eleve(date_entree=datetime.date(2021, 10, 1))
        ancien.pec_inscription = 50000
        ancien.save()
        ancien = Eleve.objects.select_related('tenant', 'section', 'exercice').get(pk=ancien.pk)

        self.assertEqual(ancien.montant_pec_inscription, 15000)
        self.assertEqual(ancien.du_hors_mensualite, 0)

    # ── L'écran de saisie ─────────────────────────────────────────────────
    def test_la_saisie_propose_le_renouvellement_et_son_nom(self):
        self._activer(libelle='Réinscription')
        ancien = self._eleve(date_entree=datetime.date(2023, 10, 1))
        d = self._saisie(ancien)

        self.assertEqual(d['fees_bruts']['inscription'], 15000)
        self.assertEqual(d['fees_nets']['inscription'], 15000)
        self.assertEqual(d['libelle_entree'], 'Réinscription')
        self.assertTrue(d['est_renouvelant'])

    def test_la_saisie_d_un_nouvel_entrant_ne_change_pas(self):
        self._activer()
        nouveau = self._eleve(date_entree=datetime.date(2025, 10, 10))
        d = self._saisie(nouveau)

        self.assertEqual(d['fees_bruts']['inscription'], 50000)
        self.assertEqual(d['libelle_entree'], 'Inscription')
        self.assertFalse(d['est_renouvelant'])

    # ── Exigibilité : la campagne commence quand l'école le décide ────────
    # Ces trois-là comparent DEUX échéanciers au même jour, l'un avec le
    # renouvellement différé et l'autre non : les mensualités échues comptent
    # pareil des deux côtés, et l'écart isole exactement l'effet du réglage.
    def _a_la_date(self, eleve, jour, mois_renouv):
        self.tenant.mois_renouvellement = mois_renouv
        self.tenant.save()
        relu = Eleve.objects.select_related('tenant', 'section', 'exercice').get(pk=eleve.pk)
        return construire_echeancier(relu, today=jour)

    def test_avant_le_mois_fixe_le_renouvellement_n_est_pas_en_retard(self):
        """« Les renouvellements se règlent à partir de janvier » : en novembre,
        la somme est due mais ne doit ni compter dans les retards ni déclencher
        une relance, sinon tous les anciens élèves y passent dès la rentrée."""
        self._activer(mois=1)
        ancien = self._eleve(date_entree=datetime.date(2023, 10, 1))
        novembre = datetime.date(2025, 11, 15)

        differe  = self._a_la_date(ancien, novembre, 1)
        immediat = self._a_la_date(ancien, novembre, None)

        self.assertFalse(differe['hors_mensualite']['echu'])
        self.assertEqual(differe['hors_mensualite']['reste'], 15000)
        # Les 15 000 basculent des retards vers les « à venir »…
        self.assertEqual(immediat['synthese']['retards']
                         - differe['synthese']['retards'], 15000)
        self.assertEqual(differe['synthese']['mois_a_venir']
                         - immediat['synthese']['mois_a_venir'], 15000)
        # …sans que le dû de l'année bouge d'un franc : seul le moment où on le
        # réclame change.
        self.assertEqual(differe['synthese']['total_restant_du'],
                         immediat['synthese']['total_restant_du'])

    def test_a_partir_du_mois_fixe_il_devient_exigible(self):
        self._activer(mois=1)
        ancien = self._eleve(date_entree=datetime.date(2023, 10, 1))
        janvier = datetime.date(2026, 1, 5)

        differe  = self._a_la_date(ancien, janvier, 1)
        immediat = self._a_la_date(ancien, janvier, None)

        self.assertTrue(differe['hors_mensualite']['echu'])
        self.assertEqual(differe['synthese']['retards'],
                         immediat['synthese']['retards'])

    def test_sans_mois_fixe_il_est_exigible_des_la_rentree(self):
        """Comportement de l'inscription, inchangé."""
        self._activer(mois=None)
        ancien = self._eleve(date_entree=datetime.date(2023, 10, 1))
        ech = construire_echeancier(ancien, today=datetime.date(2025, 10, 2))

        self.assertTrue(ech['hors_mensualite']['echu'])
        self.assertEqual(ech['hors_mensualite']['reste'], 15000)
        self.assertEqual(ech['synthese']['mois_a_venir'],
                         ech['totaux']['reste'] - ech['synthese']['retards'])

    def test_l_inscription_d_un_nouvel_entrant_reste_exigible_tout_de_suite(self):
        """Le mois fixé ne concerne QUE le renouvellement : un nouveau qui n'a
        pas payé son inscription est en retard dès son entrée."""
        self._activer(mois=1)
        nouveau = self._eleve(date_entree=datetime.date(2025, 10, 10))
        novembre = datetime.date(2025, 11, 15)

        differe  = self._a_la_date(nouveau, novembre, 1)
        immediat = self._a_la_date(nouveau, novembre, None)

        self.assertTrue(differe['hors_mensualite']['echu'])
        self.assertEqual(differe['hors_mensualite']['reste'], 50000)
        self.assertEqual(differe['synthese']['retards'],
                         immediat['synthese']['retards'])

    def test_la_ligne_hors_mensualite_porte_le_nom_de_l_ecole(self):
        self._activer(libelle='Droit de rentrée')
        ancien = self._eleve(date_entree=datetime.date(2023, 10, 1))

        self.assertEqual(
            construire_echeancier(ancien)['hors_mensualite']['libelle'],
            'Droit de rentrée')

    def test_hors_renouvellement_la_ligne_reste_traduisible(self):
        """Un libellé français ici s'afficherait tel quel dans un tableau arabe :
        vide, la clé traduite reprend la main (même règle que `cle`)."""
        self._activer()
        nouveau = self._eleve(date_entree=datetime.date(2025, 10, 10))

        self.assertEqual(
            construire_echeancier(nouveau)['hors_mensualite']['libelle'], '')

    # ── L'échéancier reste cohérent avec lui-même ─────────────────────────
    def test_le_total_de_l_echeancier_egale_le_total_attendu(self):
        self._activer(mois=1)
        ancien = self._eleve(date_entree=datetime.date(2023, 10, 1))
        ech = construire_echeancier(ancien)

        self.assertEqual(ech['totaux']['du'], ancien.total_attendu)

    def test_retards_et_a_venir_couvrent_tout_le_reste(self):
        self._activer(mois=1)
        ancien = self._eleve(date_entree=datetime.date(2023, 10, 1))
        ech = construire_echeancier(ancien, today=datetime.date(2025, 11, 15))
        s = ech['synthese']

        self.assertEqual(round(s['retards'] + s['mois_a_venir'], 2),
                         ech['totaux']['reste'])
