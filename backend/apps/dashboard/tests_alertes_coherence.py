"""Tests : le tableau de bord relance exactement qui la fiche dit de relancer.

La carte « Élèves à relancer » avait son propre calcul : mois écoulés depuis
`date_inscription` × mensualité uniforme. La fiche, elle, déroule un
échéancier qui tient compte des mois réellement facturés, du montant saisi
pour un mois donné, du réglage d'exigibilité de l'école et des corrections
d'imputation.

Deux calculs d'une même grandeur finissent toujours par diverger. Ici la
divergence a un coût direct : on appelle une famille qui ne doit rien.
"""
import datetime

from rest_framework.test import APITestCase

from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User


class AlertesCoherenceTest(APITestCase):
    """Chaque cas : la fiche dit « rien d'exigible », le tableau de bord doit
    se taire aussi."""

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

    def _eleve(self, **kw):
        base = dict(tenant=self.tenant, exercice=self.ex, section=self.section,
                    nom_complet='Awa NDIAYE', statut='INSCRIT',
                    date_inscription=datetime.date(2026, 1, 1))
        base.update(kw)
        return Eleve.objects.create(**base)

    def _alertes(self):
        r = self.client.get('/api/dashboard/alertes/')
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.data

    def _exigible_fiche(self, eleve, today=None):
        from apps.eleves.echeancier import construire_echeancier
        ech = construire_echeancier(Eleve.objects.get(pk=eleve.pk), today=today)
        return ech['synthese']['retards']

    # ── Le cas signalé : un mois mis à zéro ───────────────────────────────
    def test_un_mois_a_zero_ne_cree_pas_d_arriere(self):
        """Mois compris dans les frais d'inscription : plus rien n'est dû."""
        eleve = self._eleve(mois_dus=[1], montants_mois={'1': 0})

        self.assertEqual(self._exigible_fiche(eleve), 0)
        self.assertEqual(self._alertes(), [])

    def test_un_mois_reduit_ne_reclame_que_la_reduction(self):
        eleve = self._eleve(mois_dus=[1], montants_mois={'1': 30000})
        Paiement.objects.create(
            tenant=self.tenant, exercice=self.ex, eleve=eleve,
            no_piece='REC-1', mode_paiement='ESPECE',
            montant_mensualite=30000, mois_regles=[1], statut='ACTIF')

        self.assertEqual(self._exigible_fiche(eleve), 0)
        self.assertEqual(self._alertes(), [])

    def test_le_montant_affiche_est_celui_de_la_fiche(self):
        eleve = self._eleve(mois_dus=[1], montants_mois={'1': 30000})

        alertes = self._alertes()

        self.assertEqual(len(alertes), 1)
        self.assertEqual(alertes[0]['montant_arriere'], self._exigible_fiche(eleve))
        self.assertEqual(alertes[0]['montant_arriere'], 30000)

    # ── Les mois facturés, pas le calendrier ──────────────────────────────
    def test_seuls_les_mois_factures_comptent(self):
        """Facturé pour janvier seulement : les mois suivants ne sont pas dus."""
        eleve = self._eleve(mois_dus=[1])
        Paiement.objects.create(
            tenant=self.tenant, exercice=self.ex, eleve=eleve,
            no_piece='REC-1', mode_paiement='ESPECE',
            montant_mensualite=60000, mois_regles=[1], statut='ACTIF')

        self.assertEqual(self._exigible_fiche(eleve), 0)
        self.assertEqual(self._alertes(), [])

    # ── Le réglage d'exigibilité de l'école ───────────────────────────────
    def test_un_mois_pas_encore_exigible_ne_declenche_rien(self):
        """FIN_MOIS : la mensualité se règle le mois suivant."""
        self.tenant.echeance_mensualite = 'FIN_MOIS'
        self.tenant.jour_echeance = 5
        self.tenant.save()
        eleve = self._eleve(mois_dus=[12])   # décembre, exigible en janvier 2027

        self.assertEqual(self._exigible_fiche(eleve), 0)
        self.assertEqual(self._alertes(), [])

    # ── Correction manuelle de l'imputation (données migrées) ─────────────
    def test_l_imputation_corrigee_par_l_ecole_fait_foi(self):
        eleve = self._eleve(mois_dus=[1, 2])
        Paiement.objects.create(
            tenant=self.tenant, exercice=self.ex, eleve=eleve,
            no_piece='REC-1', mode_paiement='ESPECE',
            montant_mensualite=120000, statut='ACTIF')
        eleve.imputation_mois = {'1': 60000, '2': 60000}
        eleve.save()

        self.assertEqual(self._exigible_fiche(eleve), 0)
        self.assertEqual(self._alertes(), [])

    # ── Les exclusions ────────────────────────────────────────────────────
    def test_une_fiche_de_creance_n_est_jamais_relancee(self):
        self._eleve(fiche_creance=True, mois_dus=[1])

        self.assertEqual(self._alertes(), [])

    def test_un_sortant_n_est_pas_relance(self):
        self._eleve(mois_dus=[1], statut='ABANDONNE')

        self.assertEqual(self._alertes(), [])

    # ── Ce qui doit continuer de remonter ─────────────────────────────────
    def test_un_vrai_impaye_remonte_toujours(self):
        eleve = self._eleve(mois_dus=[1, 2, 3])

        alertes = self._alertes()

        self.assertEqual(len(alertes), 1)
        self.assertEqual(alertes[0]['montant_arriere'], 180000)
        self.assertEqual(alertes[0]['niveau_alerte'], 'CRITIQUE')
        self.assertEqual(alertes[0]['montant_arriere'], self._exigible_fiche(eleve))

    def test_les_mois_listes_sont_les_mois_reellement_impayes(self):
        eleve = self._eleve(mois_dus=[1, 2, 3])
        Paiement.objects.create(
            tenant=self.tenant, exercice=self.ex, eleve=eleve,
            no_piece='REC-1', mode_paiement='ESPECE',
            montant_mensualite=60000, mois_regles=[1], statut='ACTIF')

        alertes = self._alertes()

        self.assertEqual(alertes[0]['mois_arrieres'], ['Février', 'Mars'])
        self.assertEqual(alertes[0]['montant_arriere'], 120000)

    def test_un_paiement_partiel_laisse_le_reste_du_mois(self):
        eleve = self._eleve(mois_dus=[1])
        Paiement.objects.create(
            tenant=self.tenant, exercice=self.ex, eleve=eleve,
            no_piece='REC-1', mode_paiement='ESPECE',
            montant_mensualite=20000, mois_regles=[1], statut='ACTIF')

        self.assertEqual(self._alertes()[0]['montant_arriere'], 40000)

    # ── La prise en charge par un organisme ───────────────────────────────
    def test_on_ne_relance_pas_la_famille_pour_la_part_de_l_organisme(self):
        """Un boursier dont l'État n'a pas payé : la famille ne doit rien."""
        eleve = self._eleve(mois_dus=[1], pec_mensualite=60000)

        self.assertEqual(self._alertes(), [])


class AlertesPerformanceTest(APITestCase):
    """L'échéancier est construit par élève : sans préchargement, le tableau
    de bord d'une école de 300 fiches ouvrirait 300 requêtes de paiements."""

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

    def _peupler(self, nb):
        depart = Eleve.objects.filter(tenant=self.tenant).count()
        for i in range(depart, depart + nb):
            eleve = Eleve.objects.create(
                tenant=self.tenant, exercice=self.ex, section=self.section,
                nom_complet=f'Élève {i}', statut='INSCRIT', mois_dus=[1, 2, 3],
                date_inscription=datetime.date(2026, 1, 1))
            Paiement.objects.create(
                tenant=self.tenant, exercice=self.ex, eleve=eleve,
                no_piece=f'REC-{i}', mode_paiement='ESPECE',
                montant_mensualite=60000, mois_regles=[1], statut='ACTIF')

    def test_le_nombre_de_requetes_ne_depend_pas_de_l_effectif(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self._peupler(3)
        with CaptureQueriesContext(connection) as petit:
            self.client.get('/api/dashboard/alertes/')

        self._peupler(12)                       # 15 élèves au total
        with CaptureQueriesContext(connection) as grand:
            r = self.client.get('/api/dashboard/alertes/')

        self.assertEqual(len(r.data), 15)
        # Cinq fois plus d'élèves ne doit pas coûter une requête de plus :
        # tout est préchargé en bloc.
        self.assertLessEqual(len(grand), len(petit),
                             'une requête par élève : le préchargement a sauté')



class PerimetreCompteursTest(APITestCase):
    """Les compteurs du haut et la liste du bas comptent les mêmes élèves.

    Un « 3 CRITIQUE » au-dessus d'une liste qui n'en montre qu'un donne
    l'impression d'un logiciel qui se trompe — et fait douter du reste.
    """

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

    def _eleve(self, nom, **kw):
        base = dict(tenant=self.tenant, exercice=self.ex, section=self.section,
                    nom_complet=nom, statut='INSCRIT', mois_dus=[1, 2, 3],
                    date_inscription=datetime.date(2026, 1, 1))
        base.update(kw)
        return Eleve.objects.create(**base)

    def _kpis(self):
        r = self.client.get('/api/dashboard/kpis/')
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.data['eleves']

    def _liste(self):
        return self.client.get('/api/dashboard/alertes/').data

    def test_les_compteurs_egalent_le_nombre_de_lignes(self):
        self._eleve('En retard 1')
        self._eleve('En retard 2')
        self._eleve('Parti', statut='ABANDONNE')
        self._eleve('Créance', fiche_creance=True)

        kpis = self._kpis()
        en_alerte = kpis['critique'] + kpis['urgent'] + kpis['attention']

        self.assertEqual(en_alerte, len(self._liste()))
        self.assertEqual(en_alerte, 2)

    def test_l_effectif_total_compte_toujours_tout_le_monde(self):
        """Restreindre les alertes ne doit pas amputer l'effectif."""
        self._eleve('Présent')
        self._eleve('Parti', statut='ABANDONNE')

        self.assertEqual(self._kpis()['total'], 2)


class SortieTest(APITestCase):
    """Les arriérés d'un élève cessent de grossir le jour où il part."""

    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul', code_etablissement='CSE')
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', nb_mensualites=12,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='INTERNAT', frais_inscription=0,
            frais_mensualite=60000, frais_uniforme=0, frais_fournitures=0)

    def _situation(self, eleve, today):
        return Eleve.objects.get(pk=eleve.pk).situation_alerte(today)

    def test_l_horloge_s_arrete_a_la_date_de_sortie(self):
        eleve = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, section=self.section,
            nom_complet='Parti en mars', statut='ABANDONNE',
            date_inscription=datetime.date(2026, 1, 1),
            date_sortie=datetime.date(2026, 3, 31),
            mois_dus=[1, 2, 3, 4, 5, 6])

        etat = self._situation(eleve, datetime.date(2026, 12, 15))

        # Trois mois vécus, pas six : avril à juin ne lui sont pas réclamés.
        self.assertEqual(etat['nb_mois'], 3)
        self.assertEqual(etat['montant'], 180000)

    def test_sans_date_de_sortie_rien_ne_change(self):
        eleve = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, section=self.section,
            nom_complet='Toujours là', statut='INSCRIT',
            date_inscription=datetime.date(2026, 1, 1),
            mois_dus=[1, 2, 3, 4, 5, 6])

        etat = self._situation(eleve, datetime.date(2026, 12, 15))

        self.assertEqual(etat['nb_mois'], 6)
