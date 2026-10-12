"""Dû de l'école à son personnel, réglé par compensation sur la scolarité.

Suivi du 12/10/2026 : des parents d'élèves travaillent dans l'établissement.
L'école leur doit des salaires de l'année passée ; cette année, ils règlent
l'inscription et la scolarité de leurs enfants avec cette créance.
"""
import datetime
from decimal import Decimal

from rest_framework.test import APITestCase

from apps.comptabilite.models import JournalEntry
from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice, Paiement
from apps.rh.models import BulletinPaie, Employe, VersementPersonnel
from apps.tenants.models import Tenant
from apps.users.models import User


class DettePersonnelBase(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='École', code_etablissement='ECO')
        self.user = User.objects.create_user('d@e.sn', 'x', nom='Directeur',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026-2027', nb_mensualites=9,
            date_debut=datetime.date(2026, 10, 1), date_fin=datetime.date(2027, 7, 31))
        self.section = Section.objects.create(tenant=self.tenant, nom='CM2',
                                              frais_inscription=32000, frais_mensualite=15000)
        self.employe = Employe.objects.create(
            tenant=self.tenant, matricule='EMP-0001', nom_complet='Awa NDIAYE',
            type_employe='ENSEIGNANT', poste='Institutrice',
            salaire_base=Decimal('150000'), date_embauche=datetime.date(2020, 10, 1))
        self.enfant = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, section=self.section,
            nom_complet='Fatou SARR', date_inscription=self.ex.date_debut,
            parent_employe=self.employe)

    # ── Aides ──
    def _reliquat(self, montant, note='Salaires 2025-2026'):
        r = self.client.patch(f'/api/rh/employes/{self.employe.id}/',
                              {'reliquat_anterieur': montant, 'reliquat_note': note},
                              format='json')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.employe.refresh_from_db()
        return r

    def _situation(self):
        r = self.client.get(f'/api/rh/employes/{self.employe.id}/situation-dette/')
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.data

    def _encaisser(self, eleve=None, **corps):
        corps['eleve'] = str((eleve or self.enfant).id)
        corps.setdefault('mode_paiement', 'COMPENSATION')
        return self.client.post('/api/paiements/paiements/', corps, format='json')

    def _ecritures(self, source, source_id):
        return {(e.no_compte, float(e.debit), float(e.credit))
                for e in JournalEntry.objects.filter(tenant=self.tenant, source=source,
                                                     source_id=source_id)}

    def _bulletin(self, mois, annee, net, montant_verse=None):
        b = BulletinPaie.objects.create(
            tenant=self.tenant, employe=self.employe, mois=mois, annee=annee,
            salaire_base=net, salaire_brut=net, net_a_payer=net, statut='BROUILLON')
        corps = {} if montant_verse is None else {'montant_verse': montant_verse}
        r = self.client.post(f'/api/rh/bulletins/{b.id}/valider/', corps, format='json')
        self.assertEqual(r.status_code, 200, r.content[:300])
        b.refresh_from_db()
        return b


class ReliquatPersonnelTest(DettePersonnelBase):
    def test_reliquat_passe_en_a_nouveau(self):
        self._reliquat(100000)
        self.assertEqual(self._ecritures('RELIQ_PERSO', self.employe.id),
                         {('890', 100000.0, 0.0), ('422', 0.0, 100000.0)})
        s = self._situation()
        self.assertEqual(s['totaux']['reste'], 100000)
        self.assertEqual(s['lignes'][0]['type'], 'RELIQUAT')
        self.assertEqual(s['lignes'][0]['libelle'], 'Salaires 2025-2026')
        self.assertEqual([e['nom_complet'] for e in s['enfants']], ['Fatou SARR'])

    def test_corriger_le_reliquat_remplace_l_a_nouveau(self):
        self._reliquat(100000)
        self._reliquat(80000)
        self.assertEqual(self._ecritures('RELIQ_PERSO', self.employe.id),
                         {('890', 80000.0, 0.0), ('422', 0.0, 80000.0)})

    def test_reliquat_sous_le_deja_regle_refuse(self):
        self._reliquat(100000)
        self.assertEqual(self._encaisser(montant_inscription=32000).status_code, 201)
        r = self.client.patch(f'/api/rh/employes/{self.employe.id}/',
                              {'reliquat_anterieur': 20000}, format='json')
        self.assertEqual(r.status_code, 400, r.content[:300])
        self.employe.refresh_from_db()
        self.assertEqual(self.employe.reliquat_anterieur, 100000)


class CompensationTest(DettePersonnelBase):
    def setUp(self):
        super().setUp()
        self._reliquat(100000)

    def test_inscription_reglee_par_compensation(self):
        r = self._encaisser(montant_inscription=32000)
        self.assertEqual(r.status_code, 201, r.content[:300])
        p = Paiement.objects.get(id=r.data['id'])
        self.assertEqual(p.employe_compense, self.employe)
        # Produit constaté, dette 422 soldée d'autant, rien en trésorerie.
        lignes = self._ecritures('PAIEMENT', p.id)
        self.assertIn(('706', 0.0, 32000.0), lignes)
        self.assertIn(('422', 32000.0, 0.0), lignes)
        self.assertFalse(any(c.startswith('5') for c, _, _ in lignes))
        s = self._situation()
        self.assertEqual(s['totaux']['compense'], 32000)
        self.assertEqual(s['totaux']['reste'], 68000)
        self.assertEqual(s['compensations'][0]['eleve'], 'Fatou SARR')
        # L'élève, lui, a bien payé son inscription.
        self.enfant.refresh_from_db()
        self.assertEqual(float(self.enfant.total_paye), 32000)

    def test_compensation_et_especes_sur_le_meme_recu(self):
        r = self._encaisser(montant_inscription=32000, montant_mensualite=15000,
                            mode_paiement='MIXTE',
                            modes_reglement=[{'mode': 'COMPENSATION', 'montant': 40000},
                                             {'mode': 'ESPECE', 'montant': 7000}])
        self.assertEqual(r.status_code, 201, r.content[:300])
        lignes = self._ecritures('PAIEMENT', r.data['id'])
        self.assertIn(('422', 40000.0, 0.0), lignes)
        self.assertIn(('571', 7000.0, 0.0), lignes)
        self.assertEqual(self._situation()['totaux']['reste'], 60000)

    def test_compensation_au_dela_du_du_refusee(self):
        r = self._encaisser(montant_inscription=32000, montant_mensualite=15000 * 5)
        self.assertEqual(r.status_code, 400)
        self.assertIn('doit encore', str(r.data))
        self.assertEqual(Paiement.objects.count(), 0)

    def test_eleve_sans_parent_employe_refuse(self):
        autre = Eleve.objects.create(tenant=self.tenant, exercice=self.ex, section=self.section,
                                     nom_complet='Modou FALL', date_inscription=self.ex.date_debut)
        r = self._encaisser(eleve=autre, montant_inscription=32000)
        self.assertEqual(r.status_code, 400)
        self.assertIn('aucun membre du personnel', str(r.data))

    def test_annuler_le_recu_rend_la_dette(self):
        r = self._encaisser(montant_inscription=32000)
        self.client.post(f"/api/paiements/paiements/{r.data['id']}/annuler/")
        self.assertEqual(self._situation()['totaux']['reste'], 100000)

    def test_modifier_un_recu_compense(self):
        r = self._encaisser(montant_inscription=32000, montant_mensualite=15000)
        p = Paiement.objects.get(id=r.data['id'])
        # Le reçu lui-même ne compte pas dans le plafond : 47 000 → 60 000
        # reste sous les 100 000 dus.
        r2 = self.client.post(f'/api/paiements/paiements/{p.id}/modifier/',
                              {'montant_inscription': 32000, 'montant_mensualite': 28000,
                               'mode_paiement': 'COMPENSATION'}, format='json')
        self.assertEqual(r2.status_code, 200, r2.content[:300])
        nouveau = Paiement.objects.get(no_piece=r2.data['nouveau_no_piece'])
        self.assertEqual(nouveau.employe_compense, self.employe)
        self.assertEqual(self._situation()['totaux']['reste'], 40000)

    def test_le_guichet_connait_le_du_du_parent(self):
        self._encaisser(montant_inscription=32000)
        r = self.client.get(f'/api/eleves/{self.enfant.id}/saisie-paiement/')
        self.assertEqual(r.data['parent_employe']['nom_complet'], 'Awa NDIAYE')
        self.assertEqual(r.data['parent_employe']['reste_du'], 68000)

    def test_le_lien_parent_ne_traverse_pas_les_ecoles(self):
        autre = Tenant.objects.create(nom='Autre', code_etablissement='AUT')
        etranger = Employe.objects.create(
            tenant=autre, nom_complet='X', type_employe='APPUI', poste='Gardien',
            date_embauche=datetime.date(2020, 1, 1))
        r = self.client.patch(f'/api/eleves/{self.enfant.id}/',
                              {'parent_employe': str(etranger.id)}, format='json')
        self.assertEqual(r.status_code, 400)


class MoisParMoisTest(DettePersonnelBase):
    def test_bulletin_partiellement_verse(self):
        b = self._bulletin(10, 2026, 150000, montant_verse=100000)
        self.assertEqual(b.montant_verse, 100000)
        lignes = self._ecritures('PAIE', b.id)
        self.assertIn(('571', 0.0, 100000.0), lignes)       # seule la part versée sort
        ecr = JournalEntry.objects.filter(tenant=self.tenant, source='PAIE', source_id=b.id,
                                          no_compte='422')
        solde_422 = sum(float(e.credit) - float(e.debit) for e in ecr)
        self.assertEqual(solde_422, 50000)                   # le reste reste dû
        s = self._situation()
        octobre = s['lignes'][0]
        self.assertEqual((octobre['du'], octobre['verse'], octobre['reste'], octobre['statut']),
                         (150000, 100000, 50000, 'PARTIEL'))

    def test_bulletin_valide_sans_montant_est_paye_comme_avant(self):
        b = self._bulletin(10, 2026, 150000)
        self.assertIsNone(b.montant_verse)
        self.assertIn(('571', 0.0, 150000.0), self._ecritures('PAIE', b.id))
        self.assertEqual(self._situation()['totaux']['reste'], 0)

    def test_reglements_imputes_sur_la_dette_la_plus_ancienne(self):
        self._reliquat(40000)
        self._bulletin(10, 2026, 150000, montant_verse=100000)   # reste 50 000
        self._bulletin(11, 2026, 150000, montant_verse=120000)   # reste 30 000
        self.assertEqual(self._encaisser(montant_inscription=32000,
                                         montant_mensualite=15000).status_code, 201)
        s = self._situation()
        reliquat, octobre, novembre = s['lignes']
        self.assertEqual(reliquat['statut'], 'SOLDE')          # 40 000 sur 47 000
        self.assertEqual(octobre['reste'], 43000)              # 7 000 imputés
        self.assertEqual(novembre['reste'], 30000)
        self.assertEqual(s['totaux']['reste'], 73000)

    def test_versement_en_especes(self):
        self._reliquat(60000)
        r = self.client.post(f'/api/rh/employes/{self.employe.id}/verser/',
                             {'montant': 25000, 'mode_paiement': 'CAISSE',
                              'date_versement': '2026-10-20'}, format='json')
        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(r.data['totaux']['reste'], 35000)
        v = VersementPersonnel.objects.get()
        self.assertEqual(v.no_piece, 'VRP-0001')
        self.assertEqual(self._ecritures('VERS_PERSO', v.id),
                         {('422', 25000.0, 0.0), ('571', 0.0, 25000.0)})
        # Au-delà du dû : refusé.
        r = self.client.post(f'/api/rh/employes/{self.employe.id}/verser/',
                             {'montant': 50000}, format='json')
        self.assertEqual(r.status_code, 400)
        # Annulation : extourne, la dette revient.
        r = self.client.post(f'/api/rh/employes/{self.employe.id}/annuler-versement/',
                             {'versement': str(v.id)}, format='json')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(r.data['totaux']['reste'], 60000)
        self.assertEqual(self._ecritures('ANNUL_VERS_PERSO', v.id),
                         {('422', 0.0, 25000.0), ('571', 25000.0, 0.0)})

    def test_tableau_de_suivi(self):
        self._reliquat(100000)
        self._encaisser(montant_inscription=32000)
        r = self.client.get('/api/rh/employes/dettes/')
        self.assertEqual(r.status_code, 200)
        ligne = r.data['results'][0]
        self.assertEqual((ligne['nom_complet'], ligne['reste'], ligne['nb_enfants']),
                         ('Awa NDIAYE', 68000, 1))
