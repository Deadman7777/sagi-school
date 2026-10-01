"""Tests : le point de trésorerie, jour par jour, par mode et par responsable.

Demandé le 01/10/2026 pour une école de ~900 élèves où deux chargés de
scolarité tiennent la caisse, chacun avec son identifiant. Chaque soir : combien
d'opérations, combien est entré et sorti, par mode, par qui, et ce que la
trésorerie doit contenir. Le mois entier se relit de la même façon.

Les chiffres sont ceux du journal : le solde du point doit être EXACTEMENT
celui des canaux du tableau de bord (un seul calcul par grandeur).
"""
import datetime

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.comptabilite.models import JournalEntry
from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User


class PointTresorerieTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='LPE', code_etablissement='LPE')
        self.admin = self._compte('dir@lpe.sn', 'Diallo', 'Fatou', 'ADMIN_ECOLE')
        self.awa = self._compte('awa@lpe.sn', 'Ndiaye', 'Awa', 'ADMIN_SCOLARITE')
        self.moussa = self._compte('moussa@lpe.sn', 'Sow', 'Moussa', 'ADMIN_SCOLARITE')
        self.today = timezone.localdate()
        self.exercice = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026-2027', nb_mensualites=10,
            date_debut=self.today.replace(day=1) - datetime.timedelta(days=40),
            date_fin=self.today + datetime.timedelta(days=300),
            solde_initial_caisse=100000)
        self.section = Section.objects.create(
            tenant=self.tenant, nom='CP', frais_inscription=50000,
            frais_mensualite=30000, frais_uniforme=0, frais_fournitures=0)
        self.eleve = Eleve.objects.create(
            tenant=self.tenant, exercice=self.exercice, section=self.section,
            nom_complet='Rouguiyatou DIOUF', date_inscription=self.exercice.date_debut)

    def _compte(self, email, nom, prenom, role):
        return User.objects.create_user(email, 'x', nom=nom, prenom=prenom,
                                        role=role, tenant=self.tenant)

    def _en_tant_que(self, user):
        self.client.force_authenticate(user)

    def _encaisser(self, user, montant, mode='ESPECE', ventilation=None):
        self._en_tant_que(user)
        corps = {'eleve': str(self.eleve.id), 'mode_paiement': mode,
                 'montant_mensualite': montant, 'date_paiement': self.today.isoformat()}
        if ventilation:
            corps['modes_reglement'] = ventilation
        r = self.client.post('/api/paiements/paiements/', corps, format='json')
        self.assertEqual(r.status_code, 201, r.content[:300])
        return Paiement.objects.get(id=r.data['id'])

    def _charge(self, user, montant):
        self._en_tant_que(user)
        r = self.client.post('/api/comptabilite/charges/', {
            'no_compte': '658', 'montant': montant, 'libelle': 'Craies',
            'date': self.today.isoformat()}, format='json')
        self.assertIn(r.status_code, (200, 201), r.content[:300])

    def _point(self, **params):
        self._en_tant_que(self.admin)
        r = self.client.get('/api/paiements/point-tresorerie/', params)
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.data

    def _journee(self):
        """Awa : 70 000 (50 000 espèces + 20 000 Wave) ; Moussa : 30 000
        espèces ; la direction paie 10 000 de fournitures en espèces."""
        self._encaisser(self.awa, 70000, ventilation=[
            {'mode': 'ESPECE', 'montant': 50000}, {'mode': 'WAVE', 'montant': 20000}])
        self._encaisser(self.moussa, 30000)
        self._charge(self.admin, 10000)

    def _resp(self, point, user):
        return next(r for r in point['responsables'] if r['id'] == str(user.id))

    # ── Qui a saisi quoi ───────────────────────────────────────────────────
    def test_chaque_ecriture_porte_son_auteur(self):
        p_awa = self._encaisser(self.awa, 30000)
        p_moussa = self._encaisser(self.moussa, 30000)

        for p, user in ((p_awa, self.awa), (p_moussa, self.moussa)):
            auteurs = set(JournalEntry.objects.filter(source_id=p.id)
                          .values_list('saisi_par_id', flat=True))
            self.assertEqual(auteurs, {user.id})

    def test_l_annulation_est_au_nom_de_celui_qui_annule(self):
        p = self._encaisser(self.awa, 30000)
        self._annuler(self.moussa, p)

        self.assertEqual(set(JournalEntry.objects.filter(source='ANNUL_PAIEMENT')
                             .values_list('saisi_par_id', flat=True)), {self.moussa.id})

    # ── Le point de la journée ─────────────────────────────────────────────
    def test_entrees_et_sorties_du_jour_par_mode(self):
        self._journee()

        j = self._point(debut=self.today.isoformat(), fin=self.today.isoformat())['jours'][0]

        self.assertEqual(j['nb_operations'], 3)
        self.assertEqual(j['entrees']['total'], 100000)
        self.assertEqual(j['entrees']['par_mode']['ESPECE'], 80000)
        self.assertEqual(j['entrees']['par_mode']['WAVE'], 20000)
        self.assertEqual(j['sorties']['total'], 10000)
        self.assertEqual(j['solde'], 90000)
        # 100 000 en caisse au départ, + 90 000 dans la journée.
        self.assertEqual(j['solde_fin']['total'], 190000)
        self.assertEqual(j['solde_fin']['par_mode']['ESPECE'], 170000)

    def test_chaque_responsable_a_son_point(self):
        self._journee()

        point = self._point(debut=self.today.isoformat(), fin=self.today.isoformat())

        awa, moussa, dir_ = (self._resp(point, u) for u in (self.awa, self.moussa, self.admin))
        self.assertEqual((awa['nom'], awa['nb_operations'], awa['entrees']['total']),
                         ('Awa Ndiaye', 1, 70000))
        self.assertEqual(awa['entrees']['par_mode']['WAVE'], 20000)
        self.assertEqual((moussa['nb_operations'], moussa['entrees']['total']), (1, 30000))
        self.assertEqual((dir_['sorties']['total'], dir_['solde']), (10000, -10000))

    def test_la_journee_detaille_ses_operations(self):
        self._journee()

        ops = self._point(debut=self.today.isoformat(), fin=self.today.isoformat())['operations']

        self.assertEqual(len(ops), 4)      # reçu multi-mode = 2 lignes (espèces + Wave)
        self.assertEqual({o['responsable'] for o in ops},
                         {'Awa Ndiaye', 'Moussa Sow', 'Fatou Diallo'})

    def _annuler(self, user, paiement):
        self._en_tant_que(user)
        r = self.client.post(f'/api/paiements/paiements/{paiement.id}/annuler/')
        self.assertEqual(r.status_code, 200, r.content[:300])

    def test_un_recu_annule_le_jour_meme_n_a_jamais_existe(self):
        """L'erreur de saisie de la cliente : l'argent n'a jamais bougé."""
        self._encaisser(self.awa, 30000)
        self._annuler(self.awa, self._encaisser(self.awa, 50000))

        point = self._point(debut=self.today.isoformat(), fin=self.today.isoformat())
        j = point['jours'][0]

        self.assertEqual((j['entrees']['total'], j['sorties']['total']), (30000, 0))
        self.assertEqual(j['annulations']['total'], 0)
        self.assertEqual((j['nb_operations'], j['nb_annulations']), (1, 1))
        # Hors des totaux, mais toujours dans le détail de la journée.
        self.assertEqual(sum(o['annulee_jour'] for o in point['operations']), 2)

    def test_une_annulation_un_autre_jour_a_sa_colonne(self):
        """Les entrées restent ce qui a été saisi : jamais négatives."""
        p = self._encaisser(self.awa, 50000)
        hier = self.today - datetime.timedelta(days=1)
        Paiement.objects.filter(id=p.id).update(date_paiement=hier)
        JournalEntry.objects.filter(source_id=p.id).update(date_ecriture=hier)
        self._annuler(self.moussa, p)

        j = self._point(debut=self.today.isoformat(), fin=self.today.isoformat())['jours'][0]

        self.assertEqual((j['entrees']['total'], j['sorties']['total']), (0, 0))
        self.assertEqual(j['annulations']['total'], -50000)
        self.assertEqual(j['solde'], -50000)
        self.assertEqual(self._resp({'responsables': j['responsables']}, self.moussa)['nb_annulations'], 1)

    def test_une_charge_annulee_n_est_pas_une_entree(self):
        """La contre-écriture d'une charge garde source=CHARGE : elle doit
        quand même être reconnue comme une annulation."""
        self._charge(self.admin, 10000)
        ligne = JournalEntry.objects.filter(source='CHARGE', no_compte='658').first()
        self._en_tant_que(self.admin)
        r = self.client.delete(f'/api/comptabilite/charges/{ligne.id}/')
        self.assertIn(r.status_code, (200, 204), r.content[:300])

        j = self._point(debut=self.today.isoformat(), fin=self.today.isoformat())['jours'][0]

        self.assertEqual((j['entrees']['total'], j['sorties']['total'], j['solde']), (0, 0, 0))
        self.assertEqual(j['nb_annulations'], 1)

    # ── Cohérence avec le tableau de bord ──────────────────────────────────
    def test_le_solde_est_celui_du_tableau_de_bord(self):
        self._journee()

        point = self._point(debut=self.today.isoformat(), fin=self.today.isoformat())
        self._en_tant_que(self.admin)
        canaux = self.client.get('/api/dashboard/tresorerie-canaux/').data

        self.assertEqual(point['solde_cloture']['total'], canaux['totaux']['solde'])

    def test_le_mois_cumule_ses_journees(self):
        self._journee()
        hier = self.today - datetime.timedelta(days=1)
        if hier.month == self.today.month:
            Paiement.objects.all().update(date_paiement=hier)
            JournalEntry.objects.filter(source='PAIEMENT').update(date_ecriture=hier)

        point = self._point()          # par défaut : le mois en cours
        mois = next(m for m in point['mois']
                    if (m['annee'], m['mois']) == (self.today.year, self.today.month))

        self.assertEqual(point['totaux']['entrees']['total'], 100000)
        self.assertEqual(mois['entrees']['total'], 100000)
        self.assertEqual(mois['solde_fin']['total'], point['solde_cloture']['total'])
        self.assertEqual(sum(j['solde'] for j in point['jours']), point['totaux']['solde'])

    # ── PDF ────────────────────────────────────────────────────────────────
    def test_le_pdf_du_jour_et_du_mois(self):
        from io import BytesIO
        from pypdf import PdfReader
        self._journee()
        self._en_tant_que(self.admin)

        for params in ({'debut': self.today.isoformat(), 'fin': self.today.isoformat()}, {}):
            r = self.client.get('/api/paiements/point-tresorerie/pdf/', params)
            self.assertEqual(r.status_code, 200, r.content[:300])
            pdf = PdfReader(BytesIO(r.content))
            self.assertLessEqual(len(pdf.pages), 2)
            texte = ''.join(p.extract_text() for p in pdf.pages)
            self.assertIn('Awa Ndiaye', texte)
            self.assertNotIn('{#', texte)
