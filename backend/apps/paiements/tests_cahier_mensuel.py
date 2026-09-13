"""« Mon cahier de notes mensuel » et le tableau de bord en temps réel.

Règles vérifiées — pas des montants :
  - le cahier range chaque élève dans UNE catégorie (payé / partiel / impayé)
    et ses totaux sont la somme de ses lignes ;
  - le cahier et le suivi mensuel annoncent la même scolarité attendue ;
  - un élève passé en abandon quitte l'effectif du tableau de bord à l'instant
    même (plus de cache), mais ce qu'il devait au jour du départ reste visible ;
  - les charges budgétées du mois se lisent avec le même réalisé que l'écran
    Budget.
"""
import datetime
from unittest import mock

from rest_framework.test import APITestCase

from apps.comptabilite.models import BudgetLigne, JournalEntry
from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User

AUJOURDHUI = datetime.date(2026, 3, 20)


class CahierBase(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul', code_etablissement='CSE')
        self.user = User.objects.create_user(
            'a@a.sn', 'x', nom='Admin', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', nb_mensualites=12,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='CM2', frais_inscription=0,
            frais_mensualite=30000, frais_uniforme=0, frais_fournitures=0)
        self.awa = self._eleve('Awa NDIAYE')
        self.moussa = self._eleve('Moussa DIOP')
        self.fatou = self._eleve('Fatou SALL')
        self._payer(self.awa, 30000, [3])       # mars payé
        self._payer(self.moussa, 10000, [3])    # mars partiel
        # Fatou : rien pour mars

    def _eleve(self, nom, **kw):
        base = dict(tenant=self.tenant, exercice=self.ex, section=self.section,
                    nom_complet=nom, statut='INSCRIT',
                    date_inscription=datetime.date(2026, 1, 1))
        base.update(kw)
        return Eleve.objects.create(**base)

    def _payer(self, eleve, montant, mois, jour=datetime.date(2026, 3, 5)):
        return Paiement.objects.create(
            tenant=self.tenant, exercice=self.ex, eleve=eleve,
            no_piece=f'REC-{Paiement.objects.count() + 1:04d}', mode_paiement='ESPECE',
            montant_mensualite=montant, mois_regles=mois, statut='ACTIF',
            date_paiement=jour)

    def _cahier(self, mois=3, annee=2026):
        from apps.paiements.cahier_mensuel import cahier_mensuel
        return cahier_mensuel(self.tenant, self.ex, annee, mois, today=AUJOURDHUI)


class CahierScolariteTest(CahierBase):
    def test_chaque_eleve_dans_une_seule_categorie(self):
        s = self._cahier()['scolarite']
        self.assertEqual([e['nom_complet'] for e in s['payes']], ['Awa NDIAYE'])
        self.assertEqual([e['nom_complet'] for e in s['partiels']], ['Moussa DIOP'])
        self.assertEqual([e['nom_complet'] for e in s['impayes']], ['Fatou SALL'])

    def test_les_totaux_sont_la_somme_des_lignes(self):
        s = self._cahier()['scolarite']
        lignes = s['payes'] + s['partiels'] + s['impayes']
        self.assertEqual(s['totaux']['attendu'], sum(l['du'] for l in lignes))
        self.assertEqual(s['totaux']['encaisse'], sum(l['paye'] for l in lignes))
        self.assertEqual(s['totaux']['reste'], sum(l['reste'] for l in lignes))
        self.assertEqual(s['totaux']['attendu'],
                         s['totaux']['encaisse'] + s['totaux']['reste'])

    def test_un_paiement_deplace_l_eleve_en_temps_reel(self):
        self._payer(self.fatou, 30000, [3])
        s = self._cahier()['scolarite']
        self.assertIn('Fatou SALL', [e['nom_complet'] for e in s['payes']])

    def test_abandon_avant_l_echeance_sort_du_cahier(self):
        self.fatou.statut = 'ABANDONNE'
        self.fatou.date_sortie = datetime.date(2026, 2, 15)
        self.fatou.save()
        s = self._cahier()['scolarite']
        noms = [e['nom_complet'] for e in s['payes'] + s['partiels'] + s['impayes']]
        self.assertNotIn('Fatou SALL', noms)
        # … mais février, exigible avant son départ, elle le devait.
        fev = self._cahier(mois=2)['scolarite']
        self.assertIn('Fatou SALL', [e['nom_complet'] for e in fev['impayes']])

    def test_meme_attendu_que_le_suivi_mensuel(self):
        self.fatou.statut = 'ABANDONNE'
        self.fatou.date_sortie = datetime.date(2026, 2, 15)
        self.fatou.save()
        suivi = self.client.get('/api/eleves/suivi-mensuel/').data
        for mois in (1, 2, 3):
            ligne = next(r for r in suivi['global'] if r['mois_num'] == mois)
            self.assertEqual(ligne['scolarite_prevue'],
                             self._cahier(mois=mois)['scolarite']['totaux']['attendu'],
                             f'mois {mois}')

    def test_api_et_pdf(self):
        r = self.client.get('/api/paiements/cahier-mensuel/?annee=2026&mois=3')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(r.data['libelle_mois'], 'Mars 2026')
        pdf = self.client.get('/api/paiements/cahier-mensuel/pdf/?annee=2026&mois=3')
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf['Content-Type'], 'application/pdf')

    def test_mois_hors_exercice_refuse(self):
        r = self.client.get('/api/paiements/cahier-mensuel/?annee=2027&mois=3')
        self.assertEqual(r.status_code, 400)


class CahierChargesTest(CahierBase):
    def _ligne(self, compte, libelle, mars):
        return BudgetLigne.objects.create(
            tenant=self.tenant, exercice=self.ex, no_compte=compte,
            libelle=libelle, m03=mars)

    def _charge(self, compte, montant, jour=datetime.date(2026, 3, 10)):
        JournalEntry.objects.create(
            tenant=self.tenant, exercice=self.ex, no_piece='CHG-0001',
            date_ecriture=jour, no_compte=compte, debit=montant, credit=0,
            libelle='charge', source='CHARGE')

    def test_etats_et_ecarts(self):
        self._ligne('622', 'Loyer', 200000)
        self._ligne('6052', 'Électricité', 50000)
        self._ligne('628', 'Téléphone', 20000)
        self._charge('622', 200000)
        self._charge('6052', 20000)
        self._charge('628', 25000)
        ch = self._cahier()['charges']
        etats = {l['libelle']: l['etat'] for l in ch['lignes']}
        self.assertEqual(etats, {'Loyer': 'PAYEE', 'Électricité': 'PARTIELLE',
                                 'Téléphone': 'DEPASSEMENT'})
        self.assertEqual(ch['totaux']['prevu'], sum(l['prevu'] for l in ch['lignes']))
        self.assertEqual(ch['totaux']['ecart'], ch['totaux']['prevu'] - ch['totaux']['realise'])

    def test_meme_realise_que_l_ecran_budget(self):
        self._ligne('622', 'Loyer', 200000)
        self._charge('622', 150000)
        budget = self.client.get('/api/comptabilite/budget/').data
        mars_budget = next(m for m in budget['mois_totaux'] if m['mois'] == 3)
        self.assertEqual(self._cahier()['charges']['totaux']['realise'], mars_budget['realise'])


class TableauDeBordTempsReelTest(CahierBase):
    def _kpis(self):
        with mock.patch('django.utils.timezone.now',
                        return_value=datetime.datetime(2026, 3, 20, 10, 0,
                                                       tzinfo=datetime.timezone.utc)):
            r = self.client.get('/api/dashboard/kpis/')
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.data

    def test_abandon_retire_de_l_effectif_immediatement(self):
        self.assertEqual(self._kpis()['eleves']['total'], 3)
        # Le changement de statut passe par l'API, comme à l'écran.
        r = self.client.patch(f'/api/eleves/{self.fatou.id}/', {'statut': 'ABANDONNE'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        d = self._kpis()
        self.assertEqual(d['eleves']['total'], 2)
        self.assertEqual(d['eleves']['abandonnes'], 1)

    def test_meme_effectif_que_le_module_eleves(self):
        self.moussa.statut = 'TRANSFERE'
        self.moussa.date_sortie = datetime.date(2026, 3, 1)
        self.moussa.save()
        liste = self.client.get('/api/eleves/').data
        nb_liste = liste['count'] if isinstance(liste, dict) else len(liste)
        self.assertEqual(self._kpis()['eleves']['total'], nb_liste)

    def test_dette_du_sortant_reste_visible(self):
        self.fatou.statut = 'ABANDONNE'
        self.fatou.date_sortie = datetime.date(2026, 2, 15)
        self.fatou.save()
        kpis = self._kpis()['kpis']
        self.assertGreater(kpis['impayes_sortants'], 0)
        self.assertEqual(kpis['nb_sortants_debiteurs'], 1)

    def test_pilotage_egal_au_cahier(self):
        pil = self._kpis()['pilotage']
        cahier = self._cahier()
        self.assertEqual(pil['libelle_mois'], 'Mars 2026')
        self.assertEqual(pil['attendu'], cahier['synthese']['attendu'])
        self.assertEqual(pil['nb_impayes'], cahier['scolarite']['totaux']['nb_impayes'])
