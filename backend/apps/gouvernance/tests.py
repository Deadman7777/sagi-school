"""Tests du socle Gouvernance (Projet + GED)."""
import base64
import datetime
from decimal import Decimal

from rest_framework.test import APITestCase

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.paiements.models import Exercice
from django.db.models import Sum

from apps.comptabilite.models import JournalEntry, Immobilisation
from .models import Provision, CompteBancaire, Rapprochement, LigneReleve
from .models import (Projet, PieceJustificative, TransfertTresorerie,
                     Ressource, AffectationRessource)

PNG_1PX = base64.b64encode(b'\x89PNG\r\n\x1a\n0123456789').decode()
DATA_URI = f'data:image/png;base64,{PNG_1PX}'


class GouvernanceBaseTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='École A')
        self.autre  = Tenant.objects.create(nom='École B')
        self.user = User.objects.create_user(
            'admin@a.sn', 'x', nom='Admin A', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.exercice = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2025-2026',
            date_debut=datetime.date(2025, 10, 1), date_fin=datetime.date(2026, 9, 30))


class ProjetTest(GouvernanceBaseTest):
    def test_creation_code_auto_sequentiel_par_tenant(self):
        r = self.client.post('/api/gouvernance/projets/', {'libelle': 'Rénovation'}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data['code'], 'PROJ-0001')
        r2 = self.client.post('/api/gouvernance/projets/', {'libelle': 'Cantine'}, format='json')
        self.assertEqual(r2.data['code'], 'PROJ-0002')

    def test_code_sequence_independante_entre_tenants(self):
        """Le même code PROJ-0001 doit pouvoir exister dans deux écoles."""
        Projet.objects.create(tenant=self.tenant, code='PROJ-0001', libelle='A')
        # Aucune collision d'unicité globale attendue.
        Projet.objects.create(tenant=self.autre, code='PROJ-0001', libelle='B')
        self.assertEqual(Projet.objects.filter(code='PROJ-0001').count(), 2)

    def test_consommation_lue_depuis_le_ledger(self):
        p = Projet.objects.create(tenant=self.tenant, code='PROJ-0001',
                                  libelle='Info', budget_prevu=Decimal('1000000'))
        # Charge 200 000 + immobilisation 300 000 taggées sur le projet.
        JournalEntry.objects.create(
            tenant=self.tenant, exercice=self.exercice, no_piece='CHG-1',
            date_ecriture=datetime.date(2025, 11, 1), no_compte='6054',
            libelle='Fournitures', debit=Decimal('200000'), source='CHARGE', projet=p)
        JournalEntry.objects.create(
            tenant=self.tenant, exercice=self.exercice, no_piece='INV-1',
            date_ecriture=datetime.date(2025, 11, 1), no_compte='244',
            libelle='Ordinateurs', debit=Decimal('300000'), source='INVEST', projet=p)
        # Une écriture de trésorerie (classe 5) ne doit PAS compter comme conso.
        JournalEntry.objects.create(
            tenant=self.tenant, exercice=self.exercice, no_piece='INV-1',
            date_ecriture=datetime.date(2025, 11, 1), no_compte='521',
            libelle='Banque', credit=Decimal('300000'), source='INVEST', projet=p)

        r = self.client.get(f'/api/gouvernance/projets/{p.id}/')
        self.assertEqual(r.data['montant_consomme'], 500000.0)
        self.assertEqual(r.data['montant_restant'], 500000.0)
        self.assertEqual(r.data['taux_consommation'], 50.0)

    def test_liste_isolee_par_tenant(self):
        Projet.objects.create(tenant=self.tenant, code='PROJ-0001', libelle='A')
        Projet.objects.create(tenant=self.autre,  code='PROJ-0009', libelle='B autre')
        r = self.client.get('/api/gouvernance/projets/')
        codes = [p['code'] for p in r.data]
        self.assertEqual(codes, ['PROJ-0001'])

    def test_suppression_projet_mouvemente_desactive(self):
        p = Projet.objects.create(tenant=self.tenant, code='PROJ-0001', libelle='A')
        JournalEntry.objects.create(
            tenant=self.tenant, exercice=self.exercice, no_piece='CHG-1',
            date_ecriture=datetime.date(2025, 11, 1), no_compte='6054',
            libelle='x', debit=Decimal('1000'), source='CHARGE', projet=p)
        r = self.client.delete(f'/api/gouvernance/projets/{p.id}/')
        self.assertEqual(r.status_code, 200)
        p.refresh_from_db()
        self.assertFalse(p.est_actif)  # conservé (écriture liée), non supprimé
        # L'écriture garde son rattachement.
        self.assertTrue(JournalEntry.objects.filter(projet_id=p.id).exists())

    def test_suppression_projet_vierge_reelle(self):
        p = Projet.objects.create(tenant=self.tenant, code='PROJ-0001', libelle='A')
        r = self.client.delete(f'/api/gouvernance/projets/{p.id}/')
        self.assertEqual(r.status_code, 204)
        self.assertFalse(Projet.objects.filter(id=p.id).exists())


class PieceJustificativeTest(GouvernanceBaseTest):
    def test_depot_liste_et_contenu(self):
        p = Projet.objects.create(tenant=self.tenant, code='PROJ-0001', libelle='A')
        r = self.client.post('/api/gouvernance/pieces/', {
            'objet_type': 'PROJET', 'objet_id': str(p.id),
            'type_piece': 'CONVENTION', 'nom': 'Convention.png', 'contenu': DATA_URI,
        }, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data['mime_type'], 'image/png')
        self.assertGreater(r.data['taille'], 0)
        self.assertNotIn('contenu', r.data)  # la liste/méta n'expose pas le base64

        liste = self.client.get('/api/gouvernance/pieces/',
                                {'objet_type': 'PROJET', 'objet_id': str(p.id)})
        self.assertEqual(len(liste.data), 1)

        full = self.client.get(f"/api/gouvernance/pieces/{r.data['id']}/")
        self.assertEqual(full.data['contenu'], DATA_URI)

    def test_refus_objet_type_inconnu(self):
        r = self.client.post('/api/gouvernance/pieces/', {
            'objet_type': 'ZZZ', 'objet_id': '00000000-0000-0000-0000-000000000001',
            'contenu': DATA_URI}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_refus_format_non_datauri(self):
        r = self.client.post('/api/gouvernance/pieces/', {
            'objet_type': 'PROJET', 'objet_id': '00000000-0000-0000-0000-000000000001',
            'contenu': 'pas-un-data-uri'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_liste_requiert_objet(self):
        r = self.client.get('/api/gouvernance/pieces/')
        self.assertEqual(r.status_code, 400)

    def test_isolation_tenant_sur_get_detail(self):
        piece = PieceJustificative.objects.create(
            tenant=self.autre, objet_type='PROJET',
            objet_id='00000000-0000-0000-0000-000000000001',
            nom='secret', contenu=DATA_URI)
        r = self.client.get(f'/api/gouvernance/pieces/{piece.id}/')
        self.assertEqual(r.status_code, 404)  # pièce d'une autre école invisible


class TransfertTresorerieTest(GouvernanceBaseTest):
    def _solde(self, compte):
        agg = JournalEntry.objects.filter(tenant=self.tenant, no_compte=compte).aggregate(
            d=Sum('debit'), c=Sum('credit'))
        return (agg['d'] or Decimal('0')) - (agg['c'] or Decimal('0'))

    def _equilibre(self, no_piece):
        agg = JournalEntry.objects.filter(tenant=self.tenant, no_piece=no_piece).aggregate(
            d=Sum('debit'), c=Sum('credit'))
        return agg['d'], agg['c']

    def test_transfert_banque_vers_caisse(self):
        """Banque→Caisse 100 000 : 571 +100k, 521 −100k, 585 = 0, pièce équilibrée."""
        r = self.client.post('/api/gouvernance/transferts/', {
            'compte_source': '521', 'compte_destination': '571',
            'montant': 100000, 'motif': 'Alimentation caisse',
        }, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['reference'], 'TRF-0001')
        self.assertEqual(self._solde('571'), Decimal('100000'))
        self.assertEqual(self._solde('521'), Decimal('-100000'))
        self.assertEqual(self._solde('585'), Decimal('0'))  # virements internes soldés
        d, c = self._equilibre('TRF-0001')
        self.assertEqual(d, c)  # écriture équilibrée

    def test_neutralite_tresorerie_totale(self):
        """Un transfert sans frais ne change pas la trésorerie totale."""
        self.client.post('/api/gouvernance/transferts/', {
            'compte_source': '521', 'compte_destination': '5521', 'montant': 50000,
        }, format='json')
        total = sum(self._solde(c) for c in ('571', '521', '5521', '5522', '5523', '585'))
        self.assertEqual(total, Decimal('0'))

    def test_transfert_avec_frais(self):
        """Banque→Wave 100 000 + 500 de frais : Wave +100k, 521 −100 500, 6312 +500."""
        r = self.client.post('/api/gouvernance/transferts/', {
            'compte_source': '521', 'compte_destination': '5521',
            'montant': 100000, 'frais': 500,
        }, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(self._solde('5521'), Decimal('100000'))
        self.assertEqual(self._solde('521'), Decimal('-100500'))
        self.assertEqual(self._solde('6312'), Decimal('500'))  # frais en charge
        self.assertEqual(self._solde('585'), Decimal('0'))
        d, c = self._equilibre('TRF-0001')
        self.assertEqual(d, c)

    def test_annulation_extourne_tout(self):
        r = self.client.post('/api/gouvernance/transferts/', {
            'compte_source': '521', 'compte_destination': '571',
            'montant': 100000, 'frais': 500,
        }, format='json')
        tid = r.data['id']
        ra = self.client.delete(f'/api/gouvernance/transferts/{tid}/')
        self.assertEqual(ra.status_code, 200)
        # Tout est revenu à zéro après extourne.
        for compte in ('571', '521', '585', '6312'):
            self.assertEqual(self._solde(compte), Decimal('0'), compte)
        self.assertEqual(TransfertTresorerie.objects.get(id=tid).statut, 'ANNULE')

    def test_annulation_double_refusee(self):
        r = self.client.post('/api/gouvernance/transferts/', {
            'compte_source': '521', 'compte_destination': '571', 'montant': 1000,
        }, format='json')
        tid = r.data['id']
        self.client.delete(f'/api/gouvernance/transferts/{tid}/')
        r2 = self.client.delete(f'/api/gouvernance/transferts/{tid}/')
        self.assertEqual(r2.status_code, 400)

    def test_refus_source_egale_destination(self):
        r = self.client.post('/api/gouvernance/transferts/', {
            'compte_source': '521', 'compte_destination': '521', 'montant': 1000,
        }, format='json')
        self.assertEqual(r.status_code, 400)

    def test_refus_montant_nul(self):
        r = self.client.post('/api/gouvernance/transferts/', {
            'compte_source': '521', 'compte_destination': '571', 'montant': 0,
        }, format='json')
        self.assertEqual(r.status_code, 400)

    def test_canaux_soldes(self):
        self.client.post('/api/gouvernance/transferts/', {
            'compte_source': '521', 'compte_destination': '571', 'montant': 30000,
        }, format='json')
        r = self.client.get('/api/gouvernance/canaux/')
        soldes = {c['compte']: c['solde'] for c in r.data['canaux']}
        self.assertEqual(soldes['571'], 30000.0)
        self.assertEqual(soldes['521'], -30000.0)

    def test_reference_sequence_par_tenant(self):
        self.client.post('/api/gouvernance/transferts/', {
            'compte_source': '521', 'compte_destination': '571', 'montant': 1000}, format='json')
        r2 = self.client.post('/api/gouvernance/transferts/', {
            'compte_source': '521', 'compte_destination': '571', 'montant': 2000}, format='json')
        self.assertEqual(r2.data['reference'], 'TRF-0002')


class RessourceTest(GouvernanceBaseTest):
    def _creer_ressource(self, montant=1000000, **extra):
        r = self.client.post('/api/gouvernance/ressources/', {
            'type_ressource': 'PRET', 'libelle': 'Prêt équipement',
            'montant': montant, **extra}, format='json')
        return r

    def test_creation_reference_auto(self):
        r = self._creer_ressource()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['reference'], 'RES-0001')
        self.assertEqual(r.data['montant_restant'], 1000000.0)

    def test_charge_liee_alimente_la_consommation(self):
        """Une charge liée à la ressource incrémente sa consommation (lue au ledger)."""
        rid = self._creer_ressource(montant=1000000).data['id']
        c = self.client.post('/api/comptabilite/charges/', {
            'no_compte': '6054', 'montant': 200000, 'libelle': 'Fournitures',
            'ressource_id': rid}, format='json')
        self.assertEqual(c.status_code, 201, c.data)
        detail = self.client.get(f'/api/gouvernance/ressources/{rid}/')
        self.assertEqual(detail.data['montant_consomme'], 200000.0)
        self.assertEqual(detail.data['montant_restant'], 800000.0)
        # L'écriture de charge (6xx débit) porte bien la ressource.
        self.assertTrue(JournalEntry.objects.filter(
            tenant=self.tenant, ressource_id=rid, no_compte='6054', debit=200000).exists())

    def test_immobilisation_liee_compte_dans_la_consommation(self):
        rid = self._creer_ressource(montant=1000000).data['id']
        i = self.client.post('/api/comptabilite/immobilisations/', {
            'libelle': 'Ordinateurs', 'valeur_entree': 300000, 'duree_utilisation': 3,
            'no_compte_immobilisation': '244', 'ressource_id': rid}, format='json')
        self.assertEqual(i.status_code, 201, i.data)
        detail = self.client.get(f'/api/gouvernance/ressources/{rid}/')
        self.assertEqual(detail.data['montant_consomme'], 300000.0)  # 2xx compté

    def test_controle_depassement_enveloppe(self):
        """Une charge dépassant le disponible est refusée."""
        rid = self._creer_ressource(montant=100000).data['id']
        c = self.client.post('/api/comptabilite/charges/', {
            'no_compte': '6054', 'montant': 150000, 'libelle': 'Trop',
            'ressource_id': rid}, format='json')
        self.assertEqual(c.status_code, 400)
        # Aucune écriture ne doit avoir été créée pour cette ressource.
        self.assertFalse(JournalEntry.objects.filter(tenant=self.tenant, ressource_id=rid).exists())

    def test_charge_sans_ressource_inchangee(self):
        """Non-régression : une charge sans dimension fonctionne comme avant."""
        c = self.client.post('/api/comptabilite/charges/', {
            'no_compte': '6054', 'montant': 50000, 'libelle': 'Normale'}, format='json')
        self.assertEqual(c.status_code, 201, c.data)
        self.assertFalse(JournalEntry.objects.filter(
            tenant=self.tenant, no_piece=c.data['no_piece'], ressource__isnull=False).exists())

    def test_affectation_et_controle(self):
        rid = self._creer_ressource(montant=1000000).data['id']
        a = self.client.post('/api/gouvernance/affectations/', {
            'ressource_id': rid, 'type_emploi': 'EQUIPEMENT',
            'libelle': 'Ordinateurs', 'montant_affecte': 600000}, format='json')
        self.assertEqual(a.status_code, 201, a.data)
        detail = self.client.get(f'/api/gouvernance/ressources/{rid}/')
        self.assertEqual(detail.data['montant_affecte'], 600000.0)
        self.assertEqual(detail.data['disponible_a_affecter'], 400000.0)
        # Sur-affectation refusée.
        a2 = self.client.post('/api/gouvernance/affectations/', {
            'ressource_id': rid, 'type_emploi': 'TRAVAUX',
            'libelle': 'Travaux', 'montant_affecte': 500000}, format='json')
        self.assertEqual(a2.status_code, 400)

    def test_tracabilite(self):
        rid = self._creer_ressource(montant=1000000).data['id']
        self.client.post('/api/gouvernance/affectations/', {
            'ressource_id': rid, 'type_emploi': 'EQUIPEMENT',
            'libelle': 'PC', 'montant_affecte': 300000}, format='json')
        self.client.post('/api/comptabilite/charges/', {
            'no_compte': '6054', 'montant': 120000, 'libelle': 'Cables',
            'ressource_id': rid}, format='json')
        r = self.client.get(f'/api/gouvernance/ressources/{rid}/tracabilite/')
        self.assertEqual(len(r.data['affectations']), 1)
        self.assertEqual(len(r.data['consommations']), 1)
        self.assertEqual(r.data['consommations'][0]['nature'], 'CHARGE')
        self.assertEqual(r.data['consommations'][0]['montant'], 120000.0)

    def test_suppression_ressource_consommee_cloturee(self):
        rid = self._creer_ressource(montant=1000000).data['id']
        self.client.post('/api/comptabilite/charges/', {
            'no_compte': '6054', 'montant': 10000, 'libelle': 'x',
            'ressource_id': rid}, format='json')
        r = self.client.delete(f'/api/gouvernance/ressources/{rid}/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Ressource.objects.get(id=rid).statut, 'CLOTUREE')

    def test_isolation_tenant(self):
        Ressource.objects.create(tenant=self.autre, reference='RES-0001',
                                 libelle='autre', montant=Decimal('500'))
        r = self.client.get('/api/gouvernance/ressources/')
        self.assertEqual(r.data, [])

    def test_annulation_charge_denoue_la_consommation(self):
        """Annuler une charge liée (contre-écriture taggée) ramène la
        consommation nette de la ressource à zéro → enveloppe de nouveau dispo."""
        rid = self._creer_ressource(montant=1000000).data['id']
        c = self.client.post('/api/comptabilite/charges/', {
            'no_compte': '6054', 'montant': 200000, 'libelle': 'À annuler',
            'ressource_id': rid}, format='json')
        # Récupère la ligne de charge (6xx débit) pour l'annuler.
        ligne = JournalEntry.objects.get(
            tenant=self.tenant, no_piece=c.data['no_piece'], no_compte='6054', debit=200000)
        self.assertEqual(self.client.get(f'/api/gouvernance/ressources/{rid}/').data['montant_consomme'], 200000.0)

        self.client.delete(f'/api/comptabilite/charges/{ligne.id}/')
        detail = self.client.get(f'/api/gouvernance/ressources/{rid}/')
        self.assertEqual(detail.data['montant_consomme'], 0.0)      # dénoué
        self.assertEqual(detail.data['montant_restant'], 1000000.0)


class Lot3TracabiliteTest(GouvernanceBaseTest):
    def _ressource(self, montant=2000000):
        return self.client.post('/api/gouvernance/ressources/', {
            'type_ressource': 'PRET', 'libelle': 'Prêt BNDE', 'organisme': 'BNDE',
            'montant': montant}, format='json').data['id']

    def _projet(self):
        return self.client.post('/api/gouvernance/projets/', {
            'libelle': 'Salle informatique', 'budget_prevu': 1000000}, format='json').data['id']

    def test_immobilisation_enrichie(self):
        """L'immobilisation stocke sa ressource/projet et expose son financement."""
        rid = self._ressource()
        pid = self._projet()
        i = self.client.post('/api/comptabilite/immobilisations/', {
            'libelle': 'Ordinateurs', 'valeur_entree': 500000, 'duree_utilisation': 3,
            'no_compte_immobilisation': '244', 'ressource_id': rid, 'projet_id': pid,
        }, format='json')
        self.assertEqual(i.status_code, 201, i.data)
        self.assertEqual(i.data['mode_financement'], 'Prêt')
        self.assertEqual(i.data['ressource_id'], rid)
        self.assertEqual(i.data['projet_id'], pid)
        self.assertEqual(i.data['montant_finance'], 500000.0)
        # Stocké sur le modèle (pas seulement au ledger).
        immo = Immobilisation.objects.get(id=i.data['id'])
        self.assertEqual(str(immo.ressource_id), rid)
        self.assertEqual(str(immo.projet_id), pid)

    def test_immobilisation_sans_financement(self):
        i = self.client.post('/api/comptabilite/immobilisations/', {
            'libelle': 'Table', 'valeur_entree': 50000, 'duree_utilisation': 5,
            'no_compte_immobilisation': '241'}, format='json')
        self.assertEqual(i.data['mode_financement'], 'Fonds propres / trésorerie')
        self.assertEqual(i.data['montant_finance'], 0.0)

    def test_projet_tracabilite(self):
        rid = self._ressource()
        pid = self._projet()
        # Une charge et une immobilisation sous le projet, financées par la ressource.
        self.client.post('/api/comptabilite/charges/', {
            'no_compte': '6054', 'montant': 100000, 'libelle': 'Câbles',
            'ressource_id': rid, 'projet_id': pid}, format='json')
        self.client.post('/api/comptabilite/immobilisations/', {
            'libelle': 'PC', 'valeur_entree': 400000, 'duree_utilisation': 3,
            'no_compte_immobilisation': '244', 'ressource_id': rid, 'projet_id': pid}, format='json')
        r = self.client.get(f'/api/gouvernance/projets/{pid}/tracabilite/')
        natures = {e['nature']: e['montant'] for e in r.data['emplois']}
        self.assertEqual(natures.get('Fonctionnement'), 100000.0)  # 6054
        self.assertEqual(natures.get('Immobilisations'), 400000.0)  # 244
        self.assertEqual(len(r.data['immobilisations']), 1)
        self.assertEqual(len(r.data['origines']), 1)  # 1 ressource
        self.assertEqual(r.data['origines'][0]['montant'], 500000.0)

    def test_tracabilite_globale(self):
        rid = self._ressource(montant=1000000)
        self.client.post('/api/comptabilite/charges/', {
            'no_compte': '661', 'montant': 300000, 'libelle': 'Salaires',
            'ressource_id': rid}, format='json')
        self.client.post('/api/comptabilite/charges/', {
            'no_compte': '6052', 'montant': 40000, 'libelle': 'Électricité'}, format='json')
        r = self.client.get('/api/gouvernance/tracabilite/')
        usages = {u['nature']: u['montant'] for u in r.data['usages']}
        self.assertEqual(usages.get('Salaires'), 300000.0)
        self.assertEqual(usages.get('Fonctionnement'), 40000.0)
        # Origine ressource présente avec sa consommation.
        pret = [o for o in r.data['origines'] if o['type'] == 'Prêt']
        self.assertEqual(len(pret), 1)
        self.assertEqual(pret[0]['consomme'], 300000.0)
        self.assertEqual(r.data['impact']['nb_ressources'], 1)


class ProvisionTest(GouvernanceBaseTest):
    def _solde(self, compte):
        agg = JournalEntry.objects.filter(tenant=self.tenant, no_compte=compte).aggregate(
            d=Sum('debit'), c=Sum('credit'))
        return (agg['d'] or Decimal('0')) - (agg['c'] or Decimal('0'))

    def test_dotation_risque(self):
        r = self.client.post('/api/gouvernance/provisions/', {
            'type_provision': 'RISQUE', 'libelle': 'Litige prud’homal', 'montant': 500000},
            format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['reference'], 'PROV-0001')
        self.assertEqual(self._solde('6911'), Decimal('500000'))   # dotation (charge)
        self.assertEqual(self._solde('191'), Decimal('-500000'))   # provision (passif)
        self.assertEqual(r.data['montant_actuel'], 500000.0)

    def test_creance_douteuse_compte_491(self):
        r = self.client.post('/api/gouvernance/provisions/', {
            'type_provision': 'CREANCE_DOUTEUSE', 'libelle': 'Client X', 'montant': 100000,
            'tiers': 'Parent X'}, format='json')
        self.assertEqual(self._solde('491'), Decimal('-100000'))

    def test_reprise_partielle_puis_totale(self):
        rid = self.client.post('/api/gouvernance/provisions/', {
            'type_provision': 'RISQUE', 'libelle': 'Risque', 'montant': 500000}, format='json').data['id']
        # Reprise partielle 200 000
        r1 = self.client.post(f'/api/gouvernance/provisions/{rid}/reprise/', {'montant': 200000}, format='json')
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r1.data['montant_actuel'], 300000.0)
        self.assertEqual(r1.data['statut'], 'ACTIVE')
        self.assertEqual(self._solde('7911'), Decimal('-200000'))  # reprise (produit, crédit)
        self.assertEqual(self._solde('191'), Decimal('-300000'))   # provision réduite
        # Reprise du solde → soldée
        r2 = self.client.post(f'/api/gouvernance/provisions/{rid}/reprise/', {'montant': 300000}, format='json')
        self.assertEqual(r2.data['statut'], 'SOLDEE')
        self.assertEqual(self._solde('191'), Decimal('0'))

    def test_reprise_superieure_refusee(self):
        rid = self.client.post('/api/gouvernance/provisions/', {
            'type_provision': 'RISQUE', 'libelle': 'R', 'montant': 100000}, format='json').data['id']
        r = self.client.post(f'/api/gouvernance/provisions/{rid}/reprise/', {'montant': 150000}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_annulation_extourne(self):
        rid = self.client.post('/api/gouvernance/provisions/', {
            'type_provision': 'RISQUE', 'libelle': 'R', 'montant': 100000}, format='json').data['id']
        self.client.post(f'/api/gouvernance/provisions/{rid}/reprise/', {'montant': 40000}, format='json')
        self.client.delete(f'/api/gouvernance/provisions/{rid}/')
        for compte in ('6911', '191', '7911'):
            self.assertEqual(self._solde(compte), Decimal('0'), compte)
        self.assertEqual(Provision.objects.get(id=rid).statut, 'ANNULEE')

    def test_reglementee_comptes_hao(self):
        r = self.client.post('/api/gouvernance/provisions/', {
            'type_provision': 'REGLEMENTEE', 'libelle': 'Prov. réglementée', 'montant': 300000},
            format='json')
        self.assertEqual(self._solde('851'), Decimal('300000'))    # dotation HAO
        self.assertEqual(self._solde('151'), Decimal('-300000'))   # provision réglementée

    def test_bilan_equilibre_apres_provisions(self):
        """Le bilan reste équilibré (actif = passif) après provisions de chaque nature,
        y compris réglementée (15x + HAO 85x)."""
        for typ, m in [('RISQUE', 400000), ('CREANCE_DOUTEUSE', 150000), ('REGLEMENTEE', 250000)]:
            self.client.post('/api/gouvernance/provisions/', {
                'type_provision': typ, 'libelle': typ, 'montant': m}, format='json')
        bilan = self.client.get('/api/comptabilite/bilan/')
        self.assertEqual(bilan.data['actif']['total_actif'],
                         bilan.data['passif']['total_passif'])


class RapprochementBancaireTest(GouvernanceBaseTest):
    def setUp(self):
        super().setUp()
        self.cb = CompteBancaire.objects.create(
            tenant=self.tenant, libelle='Banque principale', no_compte_comptable='521')
        # Livres : un encaissement 100 000 (D 521) et un chèque émis 50 000 (C 521).
        JournalEntry.objects.create(
            tenant=self.tenant, exercice=self.exercice, no_piece='REC-1',
            date_ecriture=datetime.date(2025, 11, 3), no_compte='521',
            libelle='Encaissement virement', debit=Decimal('100000'), source='PAIEMENT')
        JournalEntry.objects.create(
            tenant=self.tenant, exercice=self.exercice, no_piece='CHG-1',
            date_ecriture=datetime.date(2025, 11, 20), no_compte='521',
            libelle='Chèque fournisseur', credit=Decimal('50000'), source='CHARGE')

    def _creer_rapprochement(self):
        return self.client.post('/api/gouvernance/rapprochements/', {
            'compte_bancaire_id': str(self.cb.id),
            'date_rapprochement': '2025-11-30', 'solde_releve': 98000,
            'lignes': [
                # L'encaissement figure au relevé (ENTREE 100 000).
                {'date_operation': '2025-11-04', 'libelle': 'Virement reçu', 'montant': 100000, 'sens': 'ENTREE'},
                # Agios bancaires 2 000 non comptabilisés (SORTIE).
                {'date_operation': '2025-11-28', 'libelle': 'Agios', 'montant': 2000, 'sens': 'SORTIE'},
                # Le chèque de 50 000 n'est PAS encore débité → absent du relevé.
            ],
        }, format='json')

    def test_solde_comptable_et_ecart(self):
        r = self._creer_rapprochement()
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['solde_comptable'], 50000.0)   # 0 + 100000 − 50000
        self.assertEqual(r.data['ecart'], 48000.0)             # 98000 − 50000

    def test_rapprochement_auto(self):
        rid = self._creer_rapprochement().data['id']
        auto = self.client.post(f'/api/gouvernance/rapprochements/{rid}/auto/')
        self.assertEqual(auto.data['rapproches'], 1)           # l'encaissement 100 000
        detail = self.client.get(f'/api/gouvernance/rapprochements/{rid}/')
        entree = [l for l in detail.data['lignes'] if l['sens'] == 'ENTREE'][0]
        self.assertEqual(entree['statut'], 'RAPPROCHEE')
        # Le chèque de 50 000 reste une écriture non pointée.
        non_pointees = detail.data['ecritures_non_pointees']
        self.assertTrue(any(e['montant'] == 50000.0 for e in non_pointees))

    def test_regularisation_agios(self):
        rid = self._creer_rapprochement().data['id']
        detail = self.client.get(f'/api/gouvernance/rapprochements/{rid}/')
        agios = [l for l in detail.data['lignes'] if l['libelle'] == 'Agios'][0]
        reg = self.client.post(
            f"/api/gouvernance/rapprochements/{rid}/lignes/{agios['id']}/regulariser/",
            {'compte_contrepartie': '631'}, format='json')
        self.assertEqual(reg.status_code, 201, reg.data)
        self.assertEqual(reg.data['statut'], 'REGULARISEE')
        # Écriture générée : D 631 / C 521.
        self.assertTrue(JournalEntry.objects.filter(
            tenant=self.tenant, source='RAPPRO_REG', no_compte='631', debit=2000).exists())
        self.assertTrue(JournalEntry.objects.filter(
            tenant=self.tenant, source='RAPPRO_REG', no_compte='521', credit=2000).exists())
        # Solde comptable réduit de 2 000.
        detail2 = self.client.get(f'/api/gouvernance/rapprochements/{rid}/')
        self.assertEqual(detail2.data['solde_comptable'], 48000.0)

    def test_rapprochement_manuel(self):
        rid = self._creer_rapprochement().data['id']
        detail = self.client.get(f'/api/gouvernance/rapprochements/{rid}/')
        entree = [l for l in detail.data['lignes'] if l['sens'] == 'ENTREE'][0]
        je = JournalEntry.objects.get(tenant=self.tenant, no_compte='521', debit=Decimal('100000'))
        r = self.client.patch(
            f"/api/gouvernance/rapprochements/{rid}/lignes/{entree['id']}/",
            {'journal_entry_id': str(je.id)}, format='json')
        self.assertEqual(r.data['statut'], 'RAPPROCHEE')
        self.assertEqual(r.data['journal_entry_id'], str(je.id))

    def test_validation(self):
        rid = self._creer_rapprochement().data['id']
        v = self.client.post(f'/api/gouvernance/rapprochements/{rid}/valider/')
        self.assertEqual(v.data['valide'], True)
        self.assertEqual(Rapprochement.objects.get(id=rid).statut, 'VALIDE')

    def test_isolation_tenant(self):
        self._creer_rapprochement()
        # Une autre école ne voit pas ce compte bancaire.
        autre_user = User.objects.create_user('b@b.sn', 'x', nom='B', role='ADMIN_ECOLE', tenant=self.autre)
        self.client.force_authenticate(autre_user)
        r = self.client.get('/api/gouvernance/comptes-bancaires/')
        self.assertEqual(r.data, [])


class DashboardGouvernanceTest(GouvernanceBaseTest):
    def test_dashboard_consolide(self):
        # Une ressource (prêt 1M) et deux dépenses liées : charge 300k + immo 400k.
        rid = self.client.post('/api/gouvernance/ressources/', {
            'type_ressource': 'PRET', 'libelle': 'Prêt', 'montant': 1000000}, format='json').data['id']
        self.client.post('/api/comptabilite/charges/', {
            'no_compte': '661', 'montant': 300000, 'libelle': 'Salaires', 'ressource_id': rid}, format='json')
        self.client.post('/api/comptabilite/immobilisations/', {
            'libelle': 'PC', 'valeur_entree': 400000, 'duree_utilisation': 3,
            'no_compte_immobilisation': '244', 'ressource_id': rid}, format='json')
        # Un transfert interne (ne doit PAS compter comme flux entrant/sortant).
        self.client.post('/api/gouvernance/transferts/', {
            'compte_source': '521', 'compte_destination': '571', 'montant': 50000}, format='json')

        d = self.client.get('/api/gouvernance/dashboard/').data
        # Ressources
        self.assertEqual(d['ressources']['total_obtenu'], 1000000.0)
        self.assertEqual(d['ressources']['total_consomme'], 700000.0)   # 300k + 400k
        self.assertEqual(d['ressources']['total_disponible'], 300000.0)
        # Investissements
        self.assertEqual(d['investissements']['nombre'], 1)
        self.assertEqual(d['investissements']['valeur_brute'], 400000.0)
        # Trésorerie : seule la charge réglée (571) est un flux sortant ; le
        # virement interne de 50 000 est bien EXCLU (sinon on aurait 350 000).
        self.assertEqual(d['tresorerie']['flux_entrants'], 0.0)
        self.assertEqual(d['tresorerie']['flux_sortants'], 300000.0)
        # Pilotage
        self.assertEqual(d['pilotage']['taux_consommation'], 70.0)
        usages = {u['nature']: u['montant'] for u in d['pilotage']['utilisation']}
        self.assertEqual(usages.get('Salaires'), 300000.0)
        self.assertEqual(usages.get('Immobilisations'), 400000.0)

    def test_alerte_ressource_quasi_epuisee(self):
        rid = self.client.post('/api/gouvernance/ressources/', {
            'type_ressource': 'DON', 'libelle': 'Don limité', 'montant': 100000}, format='json').data['id']
        self.client.post('/api/comptabilite/charges/', {
            'no_compte': '6054', 'montant': 95000, 'libelle': 'Achat', 'ressource_id': rid}, format='json')
        d = self.client.get('/api/gouvernance/dashboard/').data
        self.assertTrue(any('consommée à 95%' in a['message'] for a in d['pilotage']['alertes']))
