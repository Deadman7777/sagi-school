"""Tests : l'échéancier mensuel d'un élève.

L'invariant qui compte : la somme des lignes doit ÉGALER les totaux. C'est
exactement ce qui manquait au compte de résultat, où une ligne de détail
contredisait le total auquel elle participait.
"""
import datetime

from rest_framework.test import APITestCase

from apps.eleves.echeancier import construire_echeancier, mois_factures
from apps.eleves.models import Eleve, EleveService, Section, Service
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User


class EcheancierBase(APITestCase):
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
        # Le cas Fatimatou : 5 mois facturés, PEC de 135 000 sur l'inscription,
        # service mensuel de 13 000.
        self.eleve = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, section=self.section,
            nom_complet='Fatimatou Binetou NDIAYE',
            date_inscription=datetime.date(2026, 6, 25),
            pec_inscription=135000, pec_mensualite=0,
            mois_dus=[8, 9, 10, 11, 12])
        self.service = Service.objects.create(
            tenant=self.tenant, nom='Internat', montant=13000, periodicite='MENSUEL')
        EleveService.objects.create(
            tenant=self.tenant, eleve=self.eleve, service=self.service)

    def _payer(self, mensualite=0, inscription=0, mois=None):
        return Paiement.objects.create(
            tenant=self.tenant, exercice=self.ex, eleve=self.eleve,
            no_piece=f'REC-{Paiement.objects.count() + 1}', mode_paiement='ESPECE',
            montant_mensualite=mensualite, montant_inscription=inscription,
            mois_regles=mois or [], statut='ACTIF')

    def _e(self):
        return construire_echeancier(self.eleve, today=datetime.date(2026, 9, 15))


class EcheancierTest(EcheancierBase):
    # ── Structure ─────────────────────────────────────────────────────────
    def test_une_ligne_par_mois_facture(self):
        e = self._e()
        self.assertEqual([l['mois'] for l in e['lignes']], [8, 9, 10, 11, 12])
        self.assertEqual(e['lignes'][0]['nom'], 'Août')

    def test_du_mensuel_inclut_les_services(self):
        # 60 000 de mensualité + 13 000 de service
        self.assertEqual(self._e()['lignes'][0]['du'], 73000)

    def test_l_inscription_est_hors_mensualite(self):
        hors = self._e()['hors_mensualite']
        self.assertEqual(hors['du'], 50000)      # 185 000 − 135 000 de PEC

    def test_prorata_deroule_en_calendrier_quand_aucun_mois_saisi(self):
        self.eleve.mois_dus = []
        self.eleve.save()
        # 12 mensualités, entrée en juin → 7 mois dus, juin→décembre
        self.assertEqual(mois_factures(self.eleve), [6, 7, 8, 9, 10, 11, 12])

    # ── L'invariant : les lignes somment aux totaux ───────────────────────
    def test_la_somme_des_lignes_egale_les_totaux(self):
        self._payer(inscription=50000)
        self._payer(mensualite=73000, mois=[8])
        self._payer(mensualite=40000)            # sans mois désigné

        e = self._e()
        somme_du    = e['hors_mensualite']['du']    + sum(l['du'] for l in e['lignes'])
        somme_paye  = e['hors_mensualite']['paye']  + sum(l['paye'] for l in e['lignes'])
        somme_reste = e['hors_mensualite']['reste'] + sum(l['reste'] for l in e['lignes'])

        self.assertEqual(somme_du,    e['totaux']['du'])
        self.assertEqual(somme_paye,  e['totaux']['paye'])
        self.assertEqual(somme_reste, e['totaux']['reste'])

    def test_le_total_du_correspond_au_total_attendu_de_la_fiche(self):
        self.assertEqual(self._e()['totaux']['du'], self.eleve.total_attendu)
        self.assertEqual(self._e()['totaux']['du'], 415000)

    # ── Imputation ────────────────────────────────────────────────────────
    def test_un_paiement_qui_designe_ses_mois_les_solde(self):
        self._payer(mensualite=146000, mois=[8, 9])   # 2 × 73 000

        lignes = {l['mois']: l for l in self._e()['lignes']}

        self.assertEqual(lignes[8]['statut'], 'SOLDE')
        self.assertEqual(lignes[9]['statut'], 'SOLDE')
        self.assertEqual(lignes[10]['statut'], 'IMPAYE')

    def test_un_paiement_sans_mois_solde_les_plus_anciens(self):
        self._payer(mensualite=73000)

        lignes = {l['mois']: l for l in self._e()['lignes']}

        self.assertEqual(lignes[8]['statut'], 'SOLDE')
        self.assertEqual(lignes[9]['paye'], 0)

    def test_paiement_partiel_signale_comme_tel(self):
        self._payer(mensualite=30000)

        ligne = self._e()['lignes'][0]

        self.assertEqual(ligne['statut'], 'PARTIEL')
        self.assertEqual(ligne['reste'], 43000)

    def test_une_avance_ne_disparait_pas(self):
        """Payer plus que le dû de l'année ne doit pas perdre le surplus,
        sinon la somme des lignes serait inférieure au total payé."""
        self._payer(mensualite=500000)           # > 5 × 73 000

        e = self._e()

        self.assertEqual(sum(l['paye'] for l in e['lignes']), 500000)

    def test_un_paiement_annule_ne_solde_rien(self):
        p = self._payer(mensualite=73000, mois=[8])
        p.statut = 'ANNULE'
        p.save()

        self.assertEqual(self._e()['lignes'][0]['statut'], 'IMPAYE')

    # ── Échéance ──────────────────────────────────────────────────────────
    def test_les_mois_a_venir_ne_sont_pas_echus(self):
        lignes = {l['mois']: l for l in self._e()['lignes']}   # au 15/09/2026
        self.assertTrue(lignes[8]['echu'])
        self.assertTrue(lignes[9]['echu'])
        self.assertFalse(lignes[10]['echu'])

    # ── Cas limites ───────────────────────────────────────────────────────
    def test_fiche_de_creance_sans_echeancier(self):
        self.eleve.fiche_creance = True
        self.eleve.save()
        self.assertEqual(self._e()['lignes'], [])

    def test_api(self):
        r = self.client.get(f'/api/eleves/{self.eleve.id}/echeancier/')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(len(r.data['lignes']), 5)
        self.assertEqual(r.data['totaux']['du'], 415000)


class SyntheseTest(EcheancierBase):
    """La synthèse remise à la famille : exigible aujourd'hui vs à venir."""

    def test_les_retards_ne_comptent_que_les_mois_echus(self):
        # Au 15/09/2026 : août et septembre échus, oct/nov/déc à venir.
        s = self._e()['synthese']

        # 2 mois échus × 73 000 + inscription 50 000 non réglée
        self.assertEqual(s['retards'], 196000)
        self.assertEqual(s['mois_a_venir'], 219000)      # 3 × 73 000

    def test_l_inscription_compte_dans_les_retards(self):
        """Elle est due dès l'entrée : jamais « à venir »."""
        self._payer(mensualite=146000, mois=[8, 9])      # les 2 mois échus soldés

        s = self._e()['synthese']

        self.assertEqual(s['retards'], 50000)            # reste l'inscription

    def test_total_anterieurs_additionne_retards_et_ardoise(self):
        self.eleve.reliquat_anterieur = 300000
        self.eleve.save()

        s = self._e()['synthese']

        self.assertEqual(s['impaye_anterieur'], 300000)
        self.assertEqual(s['total_anterieurs'], s['retards'] + 300000)

    def test_total_restant_du_ajoute_les_mois_a_venir(self):
        self.eleve.reliquat_anterieur = 300000
        self.eleve.save()

        s = self._e()['synthese']

        self.assertEqual(s['total_restant_du'],
                         s['total_anterieurs'] + s['mois_a_venir'])
        # 196 000 + 300 000 + 219 000
        self.assertEqual(s['total_restant_du'], 715000)

    def test_sans_ardoise_le_total_egale_le_reste_de_l_annee(self):
        e = self._e()
        self.assertEqual(e['synthese']['total_restant_du'], e['totaux']['reste'])


class SituationPDFTest(EcheancierBase):
    """Le PDF remis à la famille porte bien le détail mensuel et la cascade."""

    def test_le_pdf_se_genere(self):
        self._payer(inscription=50000)
        self._payer(mensualite=73000, mois=[8])

        r = self.client.get(f'/api/eleves/{self.eleve.id}/situation-pdf/')

        self.assertEqual(r.status_code, 200, r.content[:400])
        self.assertEqual(r['Content-Type'], 'application/pdf')
        self.assertGreater(len(r.content), 1000)

    def test_le_pdf_se_genere_sans_aucun_paiement(self):
        """C'est le cas où le détail est le plus utile — il ne doit pas planter."""
        r = self.client.get(f'/api/eleves/{self.eleve.id}/situation-pdf/')
        self.assertEqual(r.status_code, 200, r.content[:400])

    def test_le_pdf_se_genere_avec_une_ardoise(self):
        self.eleve.reliquat_anterieur = 300000
        self.eleve.save()
        r = self.client.get(f'/api/eleves/{self.eleve.id}/situation-pdf/')
        self.assertEqual(r.status_code, 200, r.content[:400])
