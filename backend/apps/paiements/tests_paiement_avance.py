"""Paiement d'avance : les familles règlent avant la rentrée.

Cas rapporté le 17/09/2026, dans une école dont l'année va du 01/10/2026 au
30/06/2027 : les parents payaient l'inscription dès septembre et la saisie était
refusée (« hors de l'exercice »). Ce qui est vérifié ici :

- une avance est acceptée et rattachée au PREMIER mois de l'année (octobre),
  jamais au mois où l'argent est entré ;
- une date trop ancienne, ou postérieure à la fin de l'année, reste refusée ;
- le suivi mensuel et le cahier de caisse montrent cet argent — il ne disparaît
  pas dans un mois hors calendrier.
"""
import datetime

from rest_framework.test import APITestCase

from apps.comptabilite.models import JournalEntry
from apps.eleves.models import Eleve, Section
from apps.paiements.cahier_mensuel import caisse_du_mois
from apps.paiements.dates import mois_de_rattachement, plus_tot_accepte
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User

J = datetime.date


class PaiementAvanceTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Crèche Les Poussins', code_etablissement='POU')
        self.user = User.objects.create_user('dir@poussins.sn', 'x', nom='Directrice',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(tenant=self.tenant, annee_scolaire='2026-2027', nb_mensualites=9,
                                          date_debut=J(2026, 10, 1), date_fin=J(2027, 6, 30))
        self.section = Section.objects.create(tenant=self.tenant, nom='CI', frais_inscription=25000,
                                              frais_mensualite=30000)
        self.eleve = Eleve.objects.create(tenant=self.tenant, exercice=self.ex, section=self.section,
                                          nom_complet='Awa NDIAYE', date_inscription=J(2026, 10, 1))

    def _payer(self, jour, **extra):
        data = {'eleve': str(self.eleve.id), 'exercice': str(self.ex.id), 'montant_inscription': 25000,
                'mode_paiement': 'ESPECE', 'date_paiement': jour.isoformat()}
        data.update(extra)
        return self.client.post('/api/paiements/paiements/', data, format='json')

    def test_inscription_payee_en_septembre_acceptee(self):
        r = self._payer(J(2026, 9, 12))
        self.assertEqual(r.status_code, 201, r.content[:300])
        p = Paiement.objects.get(pk=r.data['id'])
        self.assertEqual(p.date_paiement, J(2026, 9, 12))        # la vraie date du règlement
        self.assertEqual(p.exercice_id, self.ex.id)
        # L'écriture porte la même date que le reçu : les deux tables datent
        # le même événement (voir tests_dates_paiement).
        self.assertEqual({e.date_ecriture for e in JournalEntry.objects.filter(source_id=p.id)},
                         {J(2026, 9, 12)})

    def test_rattachee_au_premier_mois_de_l_annee(self):
        self.assertEqual(mois_de_rattachement(self.ex, J(2026, 9, 12)), (2026, 10))
        self.assertEqual(mois_de_rattachement(self.ex, J(2026, 11, 3)), (2026, 11))

    def test_le_suivi_mensuel_montre_l_avance_en_octobre(self):
        self._payer(J(2026, 9, 12))
        lignes = self.client.get('/api/eleves/suivi-mensuel/').data['global']
        octobre = next(m for m in lignes if (m['mois_num'], m['annee']) == (10, 2026))
        self.assertEqual((octobre['inscription'], octobre['nb']), (25000, 1))
        # Le suivi ne déroule que les mois de l'année : septembre n'y est pas,
        # et l'avance ne doit donc pas s'y perdre.
        self.assertEqual([m['mois_num'] for m in lignes][0], 10)
        self.assertEqual(sum(m['inscription'] for m in lignes), 25000)

    def test_le_cahier_de_caisse_compte_l_avance_sur_octobre(self):
        self._payer(J(2026, 9, 12))
        self.assertEqual(caisse_du_mois(self.tenant, self.ex, 2026, 10)['entrees'], 25000)
        self.assertEqual(caisse_du_mois(self.tenant, self.ex, 2026, 11)['entrees'], 0)

    def test_avance_trop_ancienne_ou_apres_la_fin_refusee(self):
        self.assertEqual(plus_tot_accepte(self.ex), J(2026, 7, 1))
        self.assertEqual(self._payer(J(2026, 6, 30)).status_code, 400)
        r = self._payer(J(2027, 7, 15))
        self.assertEqual(r.status_code, 400)
        self.assertIn('postérieur', str(r.data))

    def test_avance_sur_une_mensualite_solde_le_mois_designe(self):
        from apps.eleves.echeancier import construire_echeancier
        r = self._payer(J(2026, 9, 20), montant_inscription=0, montant_mensualite=30000, mois_regles=[10])
        self.assertEqual(r.status_code, 201, r.content[:300])
        lignes = {l['mois']: l for l in construire_echeancier(Eleve.objects.get(pk=self.eleve.pk))['lignes']}
        self.assertEqual((lignes[10]['paye'], lignes[10]['statut']), (30000, 'SOLDE'))
