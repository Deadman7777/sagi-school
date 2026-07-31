"""Tests : le budget cesse d'être un simple miroir du plan comptable.

Deux défauts signalés le même jour, une seule racine — la ligne de budget ÉTAIT
son numéro de compte.

1. Dix postes budgétaires saisis, six lignes affichées. `update_or_create` sur
   (compte, projet) écrasait la ligne précédente dès que deux postes
   partageaient un compte — « Loyer école » et « Loyer internat » sont tous deux
   du 622. Chaque ajout suivant gonflait le total d'une ligne existante sans
   jamais en créer une nouvelle : le total montait, le tableau ne bougeait pas.

2. Toute charge passée sur le compte comptait comme réalisée, budgétée ou non.
   Or une école utilise le même 658 pour une dépense prévue et trois qui ne le
   sont pas. Et une charge de personnel saisie à côté du bulletin de paie se
   retrouvait comptée deux fois sur le même poste.

La ligne est désormais identifiée par son id, décrite par son libellé, et le
mode de réalisation se choisit par ligne — `COMPTE` restant le défaut pour que
personne ne voie ses chiffres bouger sans l'avoir demandé.
"""
import datetime

from rest_framework.test import APITestCase

from apps.comptabilite.models import BudgetLigne, JournalEntry
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant
from apps.users.models import User


class BudgetLignesTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='École', code_etablissement='ECO')
        self.user = User.objects.create_user(
            'a@a.sn', 'x', nom='Admin', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', nb_mensualites=12,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))

    # ── Helpers ───────────────────────────────────────────────────────────
    def _ligne(self, no_compte, libelle, m01=0, **kw):
        corps = {'no_compte': no_compte, 'libelle': libelle, 'm01': m01}
        corps.update(kw)
        r = self.client.post('/api/comptabilite/budget/', corps, format='json')
        self.assertIn(r.status_code, (200, 201), r.content[:300])
        return r.data['id']

    def _budget(self):
        r = self.client.get('/api/comptabilite/budget/')
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.data

    def _charge(self, no_compte, montant, libelle='Dépense', **kw):
        corps = {'no_compte': no_compte, 'montant': montant, 'libelle': libelle,
                 'date': '2026-01-15', 'mode_reglement': 'ESPECE'}
        corps.update(kw)
        r = self.client.post('/api/comptabilite/charges/', corps, format='json')
        self.assertEqual(r.status_code, 201, r.content[:300])
        return r.data

    def _realise(self, libelle):
        ligne = next(l for l in self._budget()['lignes'] if l['libelle'] == libelle)
        return ligne['total_realise']

    # ── 1. Plusieurs postes sur un même compte ────────────────────────────
    def test_deux_postes_sur_le_meme_compte_font_deux_lignes(self):
        """Le cas rapporté : la seconde écrasait la première."""
        self._ligne('622', 'Loyer école',   m01=300000)
        self._ligne('622', 'Loyer internat', m01=200000)

        lignes = self._budget()['lignes']
        self.assertEqual(len(lignes), 2)
        self.assertEqual(sorted(l['libelle'] for l in lignes),
                         ['Loyer internat', 'Loyer école'])

    def test_dix_postes_donnent_dix_lignes(self):
        """Dix saisis, six affichés — le symptôme exact du rapport."""
        for i in range(10):
            self._ligne('658', f'Poste {i}', m01=1000 * (i + 1))

        self.assertEqual(len(self._budget()['lignes']), 10)

    def test_le_total_suit_le_nombre_de_lignes(self):
        """Le total montait alors que les lignes restaient au même nombre :
        c'est ce qui rendait le bug visible sans l'expliquer."""
        for i in range(4):
            self._ligne('658', f'Poste {i}', m01=1000)
        b = self._budget()

        self.assertEqual(len(b['lignes']), 4)
        self.assertEqual(b['totaux']['total']['prevu'], 4000)

    def test_modifier_une_ligne_ne_cree_pas_de_doublon(self):
        lid = self._ligne('622', 'Loyer école', m01=300000)

        self.client.post('/api/comptabilite/budget/',
                         {'id': lid, 'no_compte': '622', 'libelle': 'Loyer école',
                          'm01': 350000}, format='json')

        lignes = self._budget()['lignes']
        self.assertEqual(len(lignes), 1)
        self.assertEqual(lignes[0]['total_prevu'], 350000)

    def test_modifier_une_ligne_ne_touche_pas_sa_voisine(self):
        self._ligne('622', 'Loyer école', m01=300000)
        lid = self._ligne('622', 'Loyer internat', m01=200000)

        self.client.post('/api/comptabilite/budget/',
                         {'id': lid, 'no_compte': '622', 'libelle': 'Loyer internat',
                          'm01': 250000}, format='json')

        par_libelle = {l['libelle']: l['total_prevu'] for l in self._budget()['lignes']}
        self.assertEqual(par_libelle, {'Loyer école': 300000, 'Loyer internat': 250000})

    def test_une_ligne_peut_changer_de_compte(self):
        lid = self._ligne('658', 'Électricité', m01=50000)

        self.client.post('/api/comptabilite/budget/',
                         {'id': lid, 'no_compte': '6052', 'libelle': 'Électricité',
                          'm01': 50000}, format='json')

        lignes = self._budget()['lignes']
        self.assertEqual(len(lignes), 1)
        self.assertEqual(lignes[0]['no_compte'], '6052')

    # ── 2. Le réalisé ne ramasse plus tout le compte ──────────────────────
    def test_par_defaut_le_compte_alimente_le_realise(self):
        """Comportement d'origine, conservé : une école qui ne touche à rien ne
        voit pas ses chiffres changer."""
        self._ligne('6052', 'Électricité', m01=100000)
        self._charge('6052', 40000)

        self.assertEqual(self._realise('Électricité'), 40000)

    def test_en_mode_imputation_une_charge_hors_budget_ne_compte_pas(self):
        """Le cas rapporté : le même compte sert à des dépenses non budgétées."""
        self._ligne('658', 'Frais de concours', m01=100000, mode_realise='IMPUTATION')
        self._charge('658', 40000, libelle='Réparation portail')   # hors budget

        self.assertEqual(self._realise('Frais de concours'), 0)

    def test_en_mode_imputation_la_charge_rattachee_compte(self):
        lid = self._ligne('658', 'Frais de concours', m01=100000,
                          mode_realise='IMPUTATION')
        self._charge('658', 40000, budget_ligne_id=lid)

        self.assertEqual(self._realise('Frais de concours'), 40000)

    def test_deux_lignes_sur_un_compte_ne_se_volent_pas_leur_realise(self):
        a = self._ligne('622', 'Loyer école', m01=300000, mode_realise='IMPUTATION')
        b = self._ligne('622', 'Loyer internat', m01=200000, mode_realise='IMPUTATION')
        self._charge('622', 300000, libelle='Loyer école janvier', budget_ligne_id=a)
        self._charge('622', 150000, libelle='Loyer internat janvier', budget_ligne_id=b)

        self.assertEqual(self._realise('Loyer école'), 300000)
        self.assertEqual(self._realise('Loyer internat'), 150000)

    def test_comptabiliser_depuis_la_ligne_impute_d_office(self):
        """Sans cela, une ligne en mode imputation ne verrait pas sa propre
        dépense — celle qu'elle vient elle-même de générer."""
        lid = self._ligne('624', 'Entretien', m01=100000, mode_realise='IMPUTATION')

        r = self.client.post(f'/api/comptabilite/budget/{lid}/comptabiliser/',
                             {'montant': 60000, 'date': '2026-01-20'}, format='json')
        self.assertEqual(r.status_code, 200, r.content[:300])

        self.assertEqual(self._realise('Entretien'), 60000)

    # ── Charges de personnel : ne pas compter deux fois ───────────────────
    def _paie(self, montant, no_compte='661', jour=15):
        JournalEntry.objects.create(
            tenant=self.tenant, exercice=self.ex, no_piece='PAIE-0001',
            date_ecriture=datetime.date(2026, 1, jour), source='PAIE',
            no_compte=no_compte, debit=montant, credit=0, libelle='Salaires', ordre=1)

    def test_le_mode_paie_ignore_une_charge_saisie_a_cote_du_bulletin(self):
        """Un salaire déjà porté par la paie, ressaisi en charge, comptait deux
        fois sur le poste « personnel »."""
        self._ligne('661', 'Salaires', m01=1000000, mode_realise='PAIE')
        self._paie(800000)
        self._charge('661', 800000, libelle='Salaire janvier (doublon)')

        self.assertEqual(self._realise('Salaires'), 800000)

    def test_sans_ce_mode_le_doublon_est_bien_compte_deux_fois(self):
        """Le comportement d'origine, montré tel quel : c'est lui qu'on corrige,
        et c'est pour ça que le mode ne peut pas rester implicite."""
        self._ligne('661', 'Salaires', m01=1000000)          # mode COMPTE
        self._paie(800000)
        self._charge('661', 800000, libelle='Salaire janvier (doublon)')

        self.assertEqual(self._realise('Salaires'), 1600000)

    def test_la_meme_regle_vaut_pour_les_charges_locatives(self):
        """« Vous pouvez appliquer la même règle pour les charges locatives » :
        l'imputation suffit, aucun traitement particulier par nature de compte."""
        lid = self._ligne('622', 'Loyer école', m01=300000, mode_realise='IMPUTATION')
        self._charge('622', 300000, budget_ligne_id=lid)
        self._charge('622', 90000, libelle='Location salle ponctuelle')  # hors budget

        self.assertEqual(self._realise('Loyer école'), 300000)

    # ── L'annulation dénoue le réalisé ────────────────────────────────────
    def test_annuler_une_charge_imputee_la_retire_du_realise(self):
        lid = self._ligne('624', 'Entretien', m01=100000, mode_realise='IMPUTATION')
        self._charge('624', 60000, budget_ligne_id=lid)
        debit = JournalEntry.objects.get(no_compte='624', debit=60000,
                                         budget_ligne_id=lid)

        r = self.client.delete(f'/api/comptabilite/charges/{debit.id}/')
        self.assertEqual(r.status_code, 200, r.content[:300])

        self.assertEqual(self._realise('Entretien'), 0)

    def test_l_imputation_ne_porte_que_sur_le_debit_de_charge(self):
        """La porter aussi sur le règlement compterait la dépense deux fois."""
        lid = self._ligne('624', 'Entretien', m01=100000, mode_realise='IMPUTATION')
        self._charge('624', 60000, budget_ligne_id=lid)

        imputees = JournalEntry.objects.filter(budget_ligne_id=lid)
        self.assertEqual(imputees.count(), 1)
        self.assertEqual(imputees.first().no_compte, '624')

    # ── Recherche dans les charges ────────────────────────────────────────
    def test_la_recherche_de_charge_filtre_sur_le_libelle(self):
        self._charge('6052', 40000, libelle='Facture SENELEC janvier')
        self._charge('622', 300000, libelle='Loyer école')

        r = self.client.get('/api/comptabilite/charges/?q=senelec')
        self.assertEqual(len(r.data), 1)
        self.assertIn('SENELEC', r.data[0]['libelle'])

    def test_la_recherche_de_charge_trouve_par_compte(self):
        self._charge('6052', 40000, libelle='Facture SENELEC janvier')
        self._charge('622', 300000, libelle='Loyer école')

        r = self.client.get('/api/comptabilite/charges/?q=622')
        self.assertEqual([c['no_compte'] for c in r.data], ['622'])

    def test_sans_recherche_tout_est_rendu(self):
        self._charge('6052', 40000, libelle='Facture SENELEC janvier')
        self._charge('622', 300000, libelle='Loyer école')

        self.assertEqual(len(self.client.get('/api/comptabilite/charges/').data), 2)

    # ── Lignes vivant sur un autre exercice (école migrée) ────────────────
    def test_les_lignes_d_un_autre_exercice_sont_signalees(self):
        """Une école migrée a plusieurs exercices ; ses lignes restent sur celui
        qui était actif quand elle les a saisies. L'écran n'en montrait qu'un,
        sans dire lequel : des lignes bien présentes passaient pour perdues."""
        self._ligne('622', 'Loyer', m01=100000)
        ancien = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2025', nb_mensualites=12,
            date_debut=datetime.date(2025, 1, 1), date_fin=datetime.date(2025, 12, 31))
        BudgetLigne.objects.create(tenant=self.tenant, exercice=ancien,
                                   no_compte='605', libelle='Ancienne ligne', m01=5000)

        autres = self._budget()['autres_exercices']

        self.assertEqual(len(autres), 1)
        self.assertEqual(autres[0]['annee'], '2025')
        self.assertEqual(autres[0]['nb_lignes'], 1)

    def test_on_peut_consulter_le_budget_d_un_autre_exercice(self):
        self._ligne('622', 'Loyer', m01=100000)
        ancien = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2025', nb_mensualites=12,
            date_debut=datetime.date(2025, 1, 1), date_fin=datetime.date(2025, 12, 31))
        BudgetLigne.objects.create(tenant=self.tenant, exercice=ancien,
                                   no_compte='605', libelle='Ancienne ligne', m01=5000)

        r = self.client.get(f'/api/comptabilite/budget/?exercice={ancien.id}')

        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual([l['libelle'] for l in r.data['lignes']], ['Ancienne ligne'])

    def test_sans_autre_exercice_la_liste_est_vide(self):
        """Le cas de toute école n'ayant qu'un exercice : aucun message."""
        self._ligne('622', 'Loyer', m01=100000)

        self.assertEqual(self._budget()['autres_exercices'], [])
