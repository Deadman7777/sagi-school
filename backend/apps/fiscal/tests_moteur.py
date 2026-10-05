"""Fiscalité paramétrable : profil, exonérations, paramètres datés.

Ce que ces tests rendent impossible :
- une école existante qui voit ses obligations changer sans avoir rien
  déclaré (profil par défaut = comportement d'avant) ;
- une association sans but lucratif à qui l'on réclame l'IS ;
- une exonération datée ignorée, ou appliquée hors de sa période ;
- un nouveau taux de loi de finances appliqué rétroactivement ;
- une école qui modifie un taux national.
"""
import datetime

from rest_framework.test import APITestCase

from apps.comptabilite.models import Activite, JournalEntry
from apps.fiscal.models import ObligationFiscale, ParametreFiscal, ProfilFiscal
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant
from apps.users.models import User


class Base(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Institut Excellence', ninea='777', rccm='SN-THS-1')
        self.user = User.objects.create_user('dir@ie.sn', 'x', nom='Dir', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(tenant=self.tenant, annee_scolaire='2025-2026',
                                          date_debut=datetime.date(2025, 10, 1),
                                          date_fin=datetime.date(2026, 7, 31))
        # Produits 50 M, charges 30 M → résultat 20 M.
        for compte, d, c in (('571', 50_000_000, 0), ('706', 0, 50_000_000),
                             ('605', 30_000_000, 0), ('521', 0, 30_000_000)):
            JournalEntry.objects.create(tenant=self.tenant, exercice=self.ex, no_piece='X',
                                        date_ecriture=datetime.date(2025, 12, 1), no_compte=compte,
                                        debit=d, credit=c, libelle='x')

    def obligations(self):
        r = self.client.get('/api/fiscal/obligations/')
        self.assertEqual(r.status_code, 200, r.content)
        return {o['code']: o for o in r.json()['obligations']}


class MoteurTest(Base):
    def test_referentiel_installe(self):
        self.assertGreaterEqual(ObligationFiscale.objects.count(), 8)
        self.assertTrue(ParametreFiscal.objects.filter(code='IS_TAUX', tenant__isnull=True).exists())

    def test_profil_par_defaut_comme_avant(self):
        o = self.obligations()
        self.assertEqual(o['IS']['montant'], 6_000_000)          # 30 % de 20 M > IMF
        self.assertEqual(o['IS']['statut'], 'ESTIMATION')
        self.assertEqual(o['TVA']['statut'], 'EXONERE')
        self.assertEqual(o['CEL']['statut'], 'A_SAISIR')
        self.assertEqual(o['IS']['comptes']['debit'], '891')

    def test_association_sans_but_lucratif(self):
        ProfilFiscal.objects.create(tenant=self.tenant, forme_juridique='ASSOCIATION', but_lucratif=False)
        o = self.obligations()
        self.assertEqual(o['IS']['statut'], 'NON_APPLICABLE')
        self.assertEqual(o['IS']['montant'], 0)

    def test_exoneration_datee(self):
        exo = {'obligation': 'IS', 'motif': 'Agrément Code des investissements', 'reference': 'Arrêté 12',
               'date_debut': '2025-01-01', 'date_fin': '2026-12-31'}
        r = self.client.patch('/api/fiscal/profil/', {'exonerations': [exo]}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.obligations()['IS']['statut'], 'EXONERE')
        exo['date_fin'] = '2026-06-30'                              # échue avant la clôture
        self.client.patch('/api/fiscal/profil/', {'exonerations': [exo]}, format='json')
        self.assertEqual(self.obligations()['IS']['statut'], 'ESTIMATION')
        r = self.client.patch('/api/fiscal/profil/', {'exonerations': [{'obligation': 'IS'}]}, format='json')
        self.assertEqual(r.status_code, 400)                        # motif obligatoire

    def test_taux_date_non_retroactif(self):
        ParametreFiscal.objects.create(code='IS_TAUX', libelle='IS', valeur=25, unite='%',
                                       date_effet=datetime.date(2026, 8, 1))
        self.assertEqual(self.obligations()['IS']['montant'], 6_000_000)   # clôture 31/07 : 30 %
        ParametreFiscal.objects.create(code='IS_TAUX', libelle='IS', valeur=27, unite='%',
                                       date_effet=datetime.date(2026, 1, 1))
        self.assertEqual(self.obligations()['IS']['montant'], 5_400_000)

    def test_surcharge_de_l_ecole_et_droits(self):
        r = self.client.post('/api/fiscal/parametres/', {
            'code': 'IS_TAUX', 'libelle': 'IS — régime conventionné', 'valeur': 15, 'unite': '%',
            'date_effet': '2025-01-01'}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(self.obligations()['IS']['montant'], 3_000_000)
        r = self.client.post('/api/fiscal/parametres/', {
            'code': 'IS_TAUX', 'libelle': 'x', 'valeur': 1, 'unite': '%', 'date_effet': '2025-01-01',
            'national': True}, format='json')
        self.assertEqual(r.status_code, 403)
        national = ParametreFiscal.objects.get(code='IS_TAUX', tenant__isnull=True)
        self.assertEqual(self.client.patch(f'/api/fiscal/parametres/?id={national.id}', {'valeur': 1},
                                           format='json').status_code, 403)
        # Une autre école ne voit pas la surcharge.
        autre = Tenant.objects.create(nom='Autre', ninea='1', rccm='2')
        u2 = User.objects.create_user('d@autre.sn', 'x', nom='D', role='ADMIN_ECOLE', tenant=autre)
        self.client.force_authenticate(u2)
        valeurs = self.client.get('/api/fiscal/parametres/').json()['en_vigueur']
        self.assertEqual(valeurs['IS_TAUX']['valeur'], 30)

    def test_tva_des_activites_taxables(self):
        ProfilFiscal.objects.create(tenant=self.tenant, assujetti_tva=True)
        act = Activite.objects.create(tenant=self.tenant, code='TR', libelle='Transport',
                                      compte_produit='7062', regime_tva='TAXABLE')
        r = self.client.post('/api/comptabilite/factures-activite/', {
            'activite': str(act.id), 'date_facture': '2026-02-01', 'client_nom': 'Client',
            'lignes': [{'libelle': 'Location', 'quantite': 1, 'prix_unitaire': 100000}]}, format='json').json()
        self.client.post(f"/api/comptabilite/factures-activite/{r['id']}/valider/")
        o = self.obligations()
        self.assertEqual(o['TVA']['montant'], 18000)
        self.assertEqual(o['TVA']['statut'], 'ESTIMATION')

    def test_comptabiliser_avec_les_comptes_du_referentiel(self):
        r = self.client.post('/api/fiscal/comptabiliser/', {'code': 'CEL', 'montant': 250000}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(JournalEntry.objects.filter(source='FISCAL_CEL', no_compte='6414', debit=250000).exists())
