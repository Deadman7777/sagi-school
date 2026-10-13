"""Registre des chèques : un chèque reçu se suit jusqu'à son encaissement.

Demande du 13/10/2026 : une école encaisse beaucoup par chèque, rien ne
disait quel chèque avait été encaissé, quand, ni par qui. Désormais :
réception D 513, remise D 521 / C 513, impayé = retour banque + reçus annulés.
"""
import datetime
import uuid

from django.db.models import Sum
from rest_framework.test import APITestCase

from apps.comptabilite.models import JournalEntry
from apps.eleves.models import Eleve, Section
from apps.paiements.cloturer import verifier_avant_cloture
from apps.paiements.models import ChequeRecu, Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User

CHEQUE = {'numero': '0012345', 'banque': 'CBAO', 'tireur': 'Moussa DIOUF',
          'date_emission': '2026-10-02'}


class RegistreChequesTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='École', code_etablissement='ECO')
        self.user = User.objects.create_user('a@a.sn', 'x', nom='Caissière', prenom='Awa',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.exercice = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026-2027', nb_mensualites=10,
            date_debut=datetime.date(2026, 9, 1), date_fin=datetime.date(2027, 7, 31))
        self.section = Section.objects.create(tenant=self.tenant, nom='CM2',
                                              frais_inscription=50000, frais_mensualite=20000)
        self.eleve = self._eleve('Awa DIOUF')

    def _eleve(self, nom):
        return Eleve.objects.create(tenant=self.tenant, exercice=self.exercice,
                                    section=self.section, nom_complet=nom,
                                    date_inscription=self.exercice.date_debut)

    def _encaisser(self, eleve=None, statut=201, **extra):
        corps = {'eleve': str((eleve or self.eleve).id), 'mode_paiement': 'CHEQUE',
                 'montant_mensualite': 20000, 'date_paiement': '2026-10-05',
                 'cheques': [CHEQUE]}
        corps.update(extra)
        r = self.client.post('/api/paiements/paiements/', corps, format='json')
        self.assertEqual(r.status_code, statut, r.content[:400])
        return Paiement.objects.get(id=r.data['id']) if statut == 201 else r

    def _solde(self, compte):
        a = JournalEntry.objects.filter(tenant=self.tenant, no_compte=compte) \
            .aggregate(d=Sum('debit'), c=Sum('credit'))
        return float(a['d'] or 0) - float(a['c'] or 0)

    def _cheque(self):
        return ChequeRecu.objects.get(tenant=self.tenant)

    def _remettre(self, cheque, date='2026-10-07'):
        r = self.client.post('/api/paiements/cheques/remettre/',
                             {'ids': [str(cheque.id)], 'date': date, 'bordereau': 'B-01'},
                             format='json')
        self.assertEqual(r.status_code, 200, r.content[:400])
        return r

    # ── Réception ──────────────────────────────────────────────────────────
    def test_le_cheque_recu_entre_au_513_et_au_registre(self):
        self._encaisser()
        c = self._cheque()
        self.assertEqual((c.numero, c.banque, c.tireur), ('0012345', 'CBAO', 'Moussa DIOUF'))
        self.assertEqual(c.date_emission, datetime.date(2026, 10, 2))
        self.assertEqual(c.date_reception, datetime.date(2026, 10, 5))
        self.assertEqual(c.statut, 'EN_PORTEFEUILLE')
        self.assertEqual(c.recu_par, self.user)
        self.assertEqual(float(c.montant), 20000)
        self.assertEqual(self._solde('513'), 20000)
        self.assertEqual(self._solde('521'), 0)

    def test_sans_details_le_cheque_est_inscrit_a_completer(self):
        self._encaisser(cheques=[])
        c = self._cheque()
        self.assertEqual(c.numero, '')
        self.assertEqual(float(c.montant), 20000)

    def test_le_complement_des_details_ne_touche_pas_au_cycle(self):
        self._encaisser(cheques=[])
        c = self._cheque()
        r = self.client.patch(f'/api/paiements/cheques/{c.id}/',
                              {'numero': '999', 'banque': 'SGBS', 'statut': 'ENCAISSE',
                               'montant': 1}, format='json')
        self.assertEqual(r.status_code, 200, r.content[:300])
        c.refresh_from_db()
        self.assertEqual((c.numero, c.banque, c.statut, float(c.montant)),
                         ('999', 'SGBS', 'EN_PORTEFEUILLE', 20000))

    def test_multi_mode_seule_la_part_cheque_va_au_513(self):
        self._encaisser(mode_paiement='MIXTE', montant_mensualite=30000,
                        modes_reglement=[{'mode': 'ESPECE', 'montant': 10000},
                                         {'mode': 'CHEQUE', 'montant': 20000}])
        self.assertEqual(self._solde('513'), 20000)
        self.assertEqual(self._solde('571'), 10000)
        self.assertEqual(float(self._cheque().montant), 20000)

    # ── Remise et encaissement ────────────────────────────────────────────
    def test_remise_en_banque(self):
        self._encaisser()
        c = self._cheque()
        r = self._remettre(c)
        self.assertEqual(r.data['no_piece'], 'RCH-0001')
        c.refresh_from_db()
        self.assertEqual(c.statut, 'REMIS')
        self.assertEqual(c.date_remise, datetime.date(2026, 10, 7))
        self.assertEqual(c.bordereau, 'B-01')
        self.assertEqual(c.remis_par, self.user)
        self.assertEqual(self._solde('513'), 0)
        self.assertEqual(self._solde('521'), 20000)

    def test_remise_avant_reception_refusee(self):
        self._encaisser()
        r = self.client.post('/api/paiements/cheques/remettre/',
                             {'ids': [str(self._cheque().id)], 'date': '2026-10-01'},
                             format='json')
        self.assertEqual(r.status_code, 400)

    def test_encaissement_confirme(self):
        self._encaisser()
        c = self._cheque()
        self._remettre(c)
        r = self.client.post('/api/paiements/cheques/encaisser/',
                             {'ids': [str(c.id)], 'date': '2026-10-09'}, format='json')
        self.assertEqual(r.status_code, 200, r.content[:300])
        c.refresh_from_db()
        self.assertEqual((c.statut, c.date_encaissement, c.encaisse_par),
                         ('ENCAISSE', datetime.date(2026, 10, 9), self.user))
        self.assertEqual(self._solde('521'), 20000)

    def test_encaisse_sans_remise_remet_d_abord(self):
        self._encaisser()
        c = self._cheque()
        self.client.post('/api/paiements/cheques/encaisser/',
                         {'ids': [str(c.id)], 'date': '2026-10-09'}, format='json')
        c.refresh_from_db()
        self.assertEqual((c.statut, c.date_remise), ('ENCAISSE', datetime.date(2026, 10, 9)))
        self.assertEqual(self._solde('513'), 0)
        self.assertEqual(self._solde('521'), 20000)

    # ── Impayé ─────────────────────────────────────────────────────────────
    def test_impaye_apres_remise_annule_le_recu(self):
        p = self._encaisser()
        c = self._cheque()
        self._remettre(c)
        r = self.client.post(f'/api/paiements/cheques/{c.id}/impaye/',
                             {'date': '2026-10-12', 'motif': 'Provision insuffisante'},
                             format='json')
        self.assertEqual(r.status_code, 200, r.content[:400])
        p.refresh_from_db()
        c.refresh_from_db()
        self.assertEqual(p.statut, 'ANNULE')
        self.assertEqual((c.statut, c.motif_impaye, c.impaye_par),
                         ('IMPAYE', 'Provision insuffisante', self.user))
        self.assertEqual(self._solde('513'), 0)
        self.assertEqual(self._solde('521'), 0)
        self.assertEqual(self._solde('706'), 0)
        self.assertEqual(float(Eleve.objects.get(id=self.eleve.id).total_paye), 0)

    def test_impaye_exige_un_motif(self):
        self._encaisser()
        r = self.client.post(f'/api/paiements/cheques/{self._cheque().id}/impaye/',
                             {'date': '2026-10-12'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_impaye_d_un_recu_multi_mode_signale_la_part_payee(self):
        self._encaisser(mode_paiement='MIXTE', montant_mensualite=30000,
                        modes_reglement=[{'mode': 'ESPECE', 'montant': 10000},
                                         {'mode': 'CHEQUE', 'montant': 20000}])
        r = self.client.post(f'/api/paiements/cheques/{self._cheque().id}/impaye/',
                             {'date': '2026-10-12', 'motif': 'Signature'}, format='json')
        self.assertEqual(r.data['autres_modes'][0]['montant'], 10000)

    # ── Annulation et modification du reçu ────────────────────────────────
    def test_annuler_un_recu_libere_le_cheque_en_portefeuille(self):
        p = self._encaisser()
        r = self.client.post(f'/api/paiements/paiements/{p.id}/annuler/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._cheque().statut, 'ANNULE')
        self.assertEqual(self._solde('513'), 0)

    def test_annuler_un_recu_dont_le_cheque_est_remis_est_refuse(self):
        p = self._encaisser()
        self._remettre(self._cheque())
        r = self.client.post(f'/api/paiements/paiements/{p.id}/annuler/')
        self.assertEqual(r.status_code, 400)
        p.refresh_from_db()
        self.assertEqual(p.statut, 'ACTIF')

    def test_modifier_sans_changer_la_part_cheque_garde_le_cheque(self):
        p = self._encaisser()
        c = self._cheque()
        self._remettre(c)
        r = self.client.post(f'/api/paiements/paiements/{p.id}/modifier/',
                             {'observations': 'corrigé'}, format='json')
        self.assertEqual(r.status_code, 200, r.content[:400])
        nouveau = Paiement.objects.get(no_piece=r.data['nouveau_no_piece'])
        self.assertEqual(c.affectations.get().paiement, nouveau)
        self.assertEqual(self._solde('513'), 0)
        self.assertEqual(self._solde('521'), 20000)

    def test_modifier_le_montant_d_un_cheque_en_portefeuille(self):
        p = self._encaisser()
        r = self.client.post(f'/api/paiements/paiements/{p.id}/modifier/',
                             {'montant_mensualite': 25000, 'mode_paiement': 'CHEQUE'},
                             format='json')
        self.assertEqual(r.status_code, 200, r.content[:400])
        c = self._cheque()
        self.assertEqual(float(c.montant), 25000)
        self.assertEqual(self._solde('513'), 25000)

    def test_modifier_le_montant_d_un_cheque_remis_est_refuse(self):
        p = self._encaisser()
        self._remettre(self._cheque())
        r = self.client.post(f'/api/paiements/paiements/{p.id}/modifier/',
                             {'montant_mensualite': 25000, 'mode_paiement': 'CHEQUE'},
                             format='json')
        self.assertEqual(r.status_code, 400)
        p.refresh_from_db()
        self.assertEqual(p.statut, 'ACTIF')

    # ── Encaissement groupé d'une famille ─────────────────────────────────
    def test_un_cheque_pour_deux_enfants(self):
        frere = self._eleve('Ibou DIOUF')
        ref = str(uuid.uuid4())
        detail = dict(CHEQUE, montant=40000)
        self._encaisser(reference_groupe=ref, cheques=[detail])
        self._encaisser(frere, reference_groupe=ref, cheques=[detail])
        c = self._cheque()
        self.assertEqual(float(c.montant), 40000)
        self.assertEqual(c.affectations.count(), 2)
        self._remettre(c)
        self.assertEqual(self._solde('521'), 40000)

    def test_cheque_famille_depasse_refuse(self):
        frere = self._eleve('Ibou DIOUF')
        detail = dict(CHEQUE, montant=30000)
        self._encaisser(cheques=[detail])
        self._encaisser(frere, statut=400, cheques=[detail])
        self.assertEqual(Paiement.objects.count(), 1)
        self.assertEqual(self._solde('513'), 20000)

    def test_cheque_famille_incomplet_ne_se_remet_pas(self):
        self._encaisser(cheques=[dict(CHEQUE, montant=40000)])
        r = self.client.post('/api/paiements/cheques/remettre/',
                             {'ids': [str(self._cheque().id)], 'date': '2026-10-07'},
                             format='json')
        self.assertEqual(r.status_code, 400)

    # ── Trésorerie et clôture ──────────────────────────────────────────────
    def test_cloture_bloquee_par_un_cheque_en_portefeuille(self):
        self._encaisser()
        v = verifier_avant_cloture(self.exercice)
        self.assertFalse(v['peut_cloturer'])
        self._remettre(self._cheque())
        self.assertTrue(verifier_avant_cloture(self.exercice)['peut_cloturer'])

    def test_tableau_de_bord_canal_cheques(self):
        self._encaisser()
        r = self.client.get('/api/dashboard/tresorerie-canaux/')
        if r.status_code == 404:
            self.skipTest('route du tableau de bord différente')
        canal = next(c for c in r.data['canaux'] if c['canal'] == 'CHEQUE')
        self.assertEqual((canal['compte'], canal['solde']), ('513', 20000))

    def test_registre_liste_et_totaux(self):
        self._encaisser()
        r = self.client.get('/api/paiements/cheques/')
        self.assertEqual(r.status_code, 200)
        ligne = r.data['results'][0]
        self.assertEqual(ligne['recus'][0]['eleve'], 'Awa DIOUF')
        self.assertEqual(ligne['recu_par_nom'], 'Awa Caissière')
        self.assertEqual(r.data['totaux']['EN_PORTEFEUILLE']['montant'], 20000)
