"""Diagnostic « santé de la migration ».

Le tableau n'est utile que s'il détecte VRAIMENT les trous silencieux d'une
reprise de données : une section sans tarif (tout le monde doit 0 FCFA), un
élève sans section, un matricule jamais rebasé, un journal déséquilibré.
Et il ne doit jamais bloquer : aucun contrôle n'est rendu au niveau erreur.
"""
import datetime

from rest_framework.test import APITestCase

from apps.comptabilite.models import JournalEntry
from apps.eleves.matricules import identite_nouvel_eleve
from apps.eleves.models import Eleve, Section
from apps.eleves.sante_migration import diagnostiquer
from apps.paiements.models import Exercice, Paiement
from apps.paiements.reliquat_migration import definir_impaye_anterieur
from apps.tenants.models import Tenant
from apps.users.models import User


class SanteMigrationBase(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul', code_etablissement='SHE')
        self.user = User.objects.create_user('a@a.sn', 'x', nom='A',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2025-2026', nb_mensualites=10,
            date_debut=datetime.date(2025, 10, 1), date_fin=datetime.date(2026, 7, 31))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='Externat', frais_inscription=50000,
            frais_mensualite=25000)

    def _eleve(self, nom, **extra):
        extra.setdefault('section', self.section)
        return Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, nom_complet=nom,
            date_inscription=self.ex.date_debut,
            **identite_nouvel_eleve(self.tenant, self.ex), **extra)

    def _controle(self, rapport, cle):
        return next(c for c in rapport['controles'] if c['cle'] == cle)


class ControlesTest(SanteMigrationBase):
    def test_aucun_niveau_bloquant(self):
        """Le tableau oriente, il n'interdit rien."""
        self._eleve('Fatou MBAYE')
        rapport = diagnostiquer(self.tenant, self.ex)
        self.assertTrue(all(c['niveau'] in ('ok', 'info', 'attention')
                            for c in rapport['controles']))

    def test_eleve_sans_aucune_situation_financiere(self):
        self._eleve('Fatou MBAYE')
        c = self._controle(diagnostiquer(self.tenant, self.ex), 'situation_financiere')
        self.assertEqual((c['nb'], c['total'], c['niveau']), (1, 1, 'info'))

    def test_un_paiement_suffit_a_decrire_la_situation(self):
        eleve = self._eleve('Fatou MBAYE')
        Paiement.objects.create(tenant=self.tenant, exercice=self.ex, eleve=eleve,
                                no_piece='REC-0001', montant_mensualite=25000)
        c = self._controle(diagnostiquer(self.tenant, self.ex), 'situation_financiere')
        self.assertEqual((c['nb'], c['niveau']), (0, 'ok'))

    def test_une_ardoise_seule_suffit_aussi(self):
        eleve = self._eleve('Fatou MBAYE')
        definir_impaye_anterieur(eleve, 45000)
        rapport = diagnostiquer(self.tenant, self.ex)
        self.assertEqual(self._controle(rapport, 'situation_financiere')['nb'], 0)
        ardoises = self._controle(rapport, 'impayes_anterieurs')
        self.assertEqual((ardoises['nb'], ardoises['montant']), (1, 45000.0))

    def test_section_sans_tarif_detectee(self):
        """Piège classique : la section existe, personne ne doit rien."""
        muette = Section.objects.create(tenant=self.tenant, nom='Coranique')
        self._eleve('Moussa NDIAYE', section=muette)
        rapport = diagnostiquer(self.tenant, self.ex)
        c = self._controle(rapport, 'sections_sans_tarif')
        self.assertEqual((c['nb'], c['niveau']), (1, 'attention'))
        self.assertEqual(rapport['eleves_sans_tarif'], 1)

    def test_eleve_sans_section(self):
        self._eleve('Sans niveau', section=None)
        c = self._controle(diagnostiquer(self.tenant, self.ex), 'sans_section')
        self.assertEqual((c['nb'], c['niveau']), (1, 'attention'))

    def test_matricule_non_rebase(self):
        Eleve.objects.create(tenant=self.tenant, exercice=self.ex, numero=1,
                             section=self.section, nom_complet='Ancien format',
                             matricule='2026-ETB-000001',
                             date_inscription=self.ex.date_debut)
        c = self._controle(diagnostiquer(self.tenant, self.ex), 'identite_entree')
        self.assertEqual((c['nb'], c['niveau']), (1, 'attention'))

    def test_identite_complete_ne_remonte_pas(self):
        self._eleve('Fatou MBAYE')
        c = self._controle(diagnostiquer(self.tenant, self.ex), 'identite_entree')
        self.assertEqual((c['nb'], c['niveau']), (0, 'ok'))

    def test_journal_desequilibre(self):
        JournalEntry.objects.create(
            tenant=self.tenant, exercice=self.ex, no_piece='X-0001',
            date_ecriture=self.ex.date_debut, no_compte='411', debit=1000, credit=0,
            libelle='Écriture bancale')
        c = self._controle(diagnostiquer(self.tenant, self.ex), 'journal_equilibre')
        self.assertEqual((c['niveau'], c['montant']), ('attention', 1000.0))

    def test_journal_equilibre(self):
        eleve = self._eleve('Fatou MBAYE')
        definir_impaye_anterieur(eleve, 45000)     # 411 D / 890 C
        c = self._controle(diagnostiquer(self.tenant, self.ex), 'journal_equilibre')
        self.assertEqual(c['niveau'], 'ok')


class CreancesTest(SanteMigrationBase):
    def test_creances_incluent_l_ardoise_et_le_du_de_l_annee(self):
        eleve = self._eleve('Fatou MBAYE')          # dû annuel 300 000
        definir_impaye_anterieur(eleve, 45000)
        rapport = diagnostiquer(self.tenant, self.ex)
        self.assertEqual(rapport['total_creances'], 345000.0)

    def test_creances_incluent_les_fiches_de_sortis(self):
        """L'argent dû par un diplômé parti compte aussi — c'est justement
        pour ça que sa fiche de créance existe."""
        Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, numero=99, statut='DIPLOME',
            nom_complet='Parti endetté', matricule='2024-SHE-0099',
            annee_entree='2024-2025', date_entree=datetime.date(2024, 10, 1),
            date_inscription=self.ex.date_debut,
            fiche_creance=True, reliquat_anterieur=50000)
        rapport = diagnostiquer(self.tenant, self.ex)
        self.assertEqual(rapport['nb_eleves'], 0)          # pas un élève
        self.assertEqual(rapport['total_creances'], 50000.0)   # mais un dû


class ApiTest(SanteMigrationBase):
    def test_api(self):
        self._eleve('Fatou MBAYE')
        r = self.client.get('/api/eleves/sante-migration/')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['exercice'], '2025-2026')
        self.assertEqual(r.data['nb_eleves'], 1)
        self.assertIn('controles', r.data)

    def test_api_sans_exercice_actif(self):
        self.ex.cloture = True
        self.ex.save()
        r = self.client.get('/api/eleves/sante-migration/')
        self.assertEqual(r.status_code, 400)

    def test_isolation_tenant(self):
        autre = Tenant.objects.create(nom='Voisine', code_etablissement='VOI')
        ex = Exercice.objects.create(
            tenant=autre, annee_scolaire='2025-2026', nb_mensualites=10,
            date_debut=datetime.date(2025, 10, 1), date_fin=datetime.date(2026, 7, 31))
        Eleve.objects.create(tenant=autre, exercice=ex, numero=1, nom_complet='Voisin',
                             date_inscription=ex.date_debut)
        self._eleve('Fatou MBAYE')
        self.assertEqual(diagnostiquer(self.tenant, self.ex)['nb_eleves'], 1)


class ProduitsNegatifsTest(SanteMigrationBase):
    """7e contrôle : un net de classe 70 négatif est comptablement impossible.

    Le tableau de bord borne le total à 0 et affiche « Total Recettes : 0 »
    sans rien signaler — c'est resté invisible des mois chez Shoumoul.
    """

    def _je(self, compte, debit, credit, source='MIGRATION'):
        JournalEntry.objects.create(
            tenant=self.tenant, exercice=self.ex, no_piece='X',
            date_ecriture=self.ex.date_debut, no_compte=compte,
            debit=debit, credit=credit, source=source, ordre=1)

    def test_produits_positifs_rien_a_signaler(self):
        self._je('571', 1000000, 0)
        self._je('706', 0, 1000000)
        c = self._controle(diagnostiquer(self.tenant, self.ex), 'produits_negatifs')
        self.assertEqual(c['niveau'], 'ok')

    def test_net_negatif_signale_avec_son_montant(self):
        self._je('706', 0, 1000000)
        self._je('706', 1600000, 0, 'RECAL_MIGRATION')   # neutralisations empilées

        c = self._controle(diagnostiquer(self.tenant, self.ex), 'produits_negatifs')

        self.assertEqual(c['niveau'], 'attention')
        self.assertEqual(c['montant'], 600000)

    def test_le_controle_reste_non_bloquant(self):
        self._je('706', 0, 1000000)
        self._je('706', 1600000, 0, 'RECAL_MIGRATION')
        rapport = diagnostiquer(self.tenant, self.ex)
        self.assertTrue(all(c['niveau'] in ('ok', 'info', 'attention')
                            for c in rapport['controles']))
