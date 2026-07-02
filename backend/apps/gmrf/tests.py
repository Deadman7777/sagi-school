"""Tests du moteur de comptabilisation GMRF (intégration comptable)."""
import datetime
from decimal import Decimal

from django.test import TestCase
from django.db.models import Sum

from apps.tenants.models import Tenant
from apps.paiements.models import Exercice
from apps.comptabilite.models import JournalEntry
from .models import (NattCycle, NattCotisation, NattReception, TypeFinancement,
                     Financement, Pret, PretEcheance)
from . import services


class GmrfComptaTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='École Test')
        self.exercice = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2025-2026',
            date_debut=datetime.date(2025, 10, 1), date_fin=datetime.date(2026, 9, 30),
        )

    def _solde(self, no_compte):
        agg = JournalEntry.objects.filter(tenant=self.tenant, no_compte=no_compte).aggregate(
            d=Sum('debit'), c=Sum('credit'))
        return (agg['d'] or 0) - (agg['c'] or 0)

    def test_natt_cycle_complet_solde_a_zero(self):
        """10 participants × 50 000 × 10 mois : en fin de cycle, créance = dette =
        trésorerie = 0 (ni charge ni produit)."""
        cot = Decimal('50000')
        cycle = NattCycle.objects.create(
            tenant=self.tenant, reference='NATT-0001', nom='Tontine des enseignants',
            nb_participants=10, duree=10, periodicite='MENSUELLE', montant_cotisation=cot,
            date_debut=datetime.date(2025, 10, 5),
            compte_tresorerie='521', compte_creance='4718', compte_dette='4798',
        )
        NattCotisation.objects.bulk_create([
            NattCotisation(tenant=self.tenant, cycle=cycle, numero=i,
                           date_echeance=datetime.date(2025, 10, 5), montant=cot)
            for i in range(1, 11)
        ])

        # Paye les 3 premières cotisations (avant réception) -> créance
        for c in cycle.cotisations.filter(numero__lte=3):
            c.statut = 'PAYE'; c.date_paiement = datetime.date(2025, 11, 1); c.save()
            services.generer_ecriture_cotisation(c, self.tenant)

        self.assertEqual(self._solde('4718'), cot * 3)   # créance = 150 000
        self.assertEqual(self._solde('521'), -cot * 3)   # trésorerie sortie

        # Réception de la cagnotte à la 4e échéance : 10 × 50 000 = 500 000
        reception = NattReception.objects.create(
            tenant=self.tenant, cycle=cycle, numero_echeance=4,
            date_reception=datetime.date(2025, 12, 1), montant_recu=cot * 10,
            compte_tresorerie='521',
        )
        services.generer_ecriture_reception(reception, self.tenant)

        self.assertEqual(self._solde('4718'), 0)              # créance soldée
        self.assertEqual(self._solde('4798'), -cot * 7)       # dette = 350 000 (7 restantes)
        self.assertEqual(self._solde('521'), cot * 7)         # +500k -150k = +350k

        # Paye les 7 cotisations restantes (après réception) -> remboursent la dette
        for c in cycle.cotisations.filter(numero__gt=3):
            c.statut = 'PAYE'; c.date_paiement = datetime.date(2026, 1, 1); c.save()
            services.generer_ecriture_cotisation(c, self.tenant)

        # Fin de cycle : tout est soldé, aucun impact charge/produit
        self.assertEqual(self._solde('4718'), 0)
        self.assertEqual(self._solde('4798'), 0)
        self.assertEqual(self._solde('521'), 0)

        # Équilibre général débit = crédit
        agg = JournalEntry.objects.filter(tenant=self.tenant).aggregate(d=Sum('debit'), c=Sum('credit'))
        self.assertEqual(agg['d'], agg['c'])

    def test_financement_don_genere_produit(self):
        tf = TypeFinancement.objects.create(
            tenant=self.tenant, code='DON', libelle='Don', categorie='DON',
            nature_comptable='PRODUIT', compte_ressource='7588',
        )
        f = Financement.objects.create(
            tenant=self.tenant, reference='GRF-0001', type_financement=tf,
            libelle='Don fondation X', montant=Decimal('1000000'),
            date_reception=datetime.date(2025, 11, 10), compte_tresorerie='521',
            compte_ressource='7588', statut='RECU',
        )
        services.generer_ecriture_financement(f, self.tenant)
        self.assertEqual(self._solde('521'), Decimal('1000000'))    # trésorerie +
        self.assertEqual(self._solde('7588'), Decimal('-1000000'))  # produit (crédit)

        # Annulation : extourne
        services.annuler_ecriture_financement(f, self.tenant)
        self.assertEqual(self._solde('521'), 0)
        self.assertEqual(self._solde('7588'), 0)

    # ── Prêts ──────────────────────────────────────────────────────────────
    def _creer_pret(self, mode, taux=Decimal('12'), montant=Decimal('1200000'), nb=12):
        pret = Pret.objects.create(
            tenant=self.tenant, reference=f'PRET-{mode[:4]}', type_pret='BANCAIRE',
            organisme_preteur='Banque X', montant=montant, taux_interet=taux,
            duree_mois=nb, periodicite='MENSUELLE', mode_amortissement=mode,
            date_deblocage=datetime.date(2025, 11, 1),
            compte_tresorerie='521', compte_emprunt='162', compte_interets='671',
        )
        rows = services.calcul_amortissement(montant, taux, nb, 'MENSUELLE', mode)
        PretEcheance.objects.bulk_create([
            PretEcheance(tenant=self.tenant, pret=pret, numero=r['numero'],
                         date_echeance=datetime.date(2025, 12, 1),
                         capital_debut=r['capital_debut'], montant_echeance=r['montant_echeance'],
                         part_capital=r['part_capital'], part_interet=r['part_interet'],
                         capital_fin=r['capital_fin'])
            for r in rows
        ])
        return pret

    def test_amortissement_somme_capital_egale_montant(self):
        for mode in ('CONSTANT', 'CAPITAL_CONSTANT', 'IN_FINE'):
            rows = services.calcul_amortissement(Decimal('1200000'), Decimal('12'), 12, 'MENSUELLE', mode)
            total_cap = sum(r['part_capital'] for r in rows)
            self.assertEqual(total_cap, Decimal('1200000'), f"mode {mode}")
            self.assertEqual(rows[-1]['capital_fin'], Decimal('0'), f"mode {mode}")

    def test_pret_deblocage_et_remboursement_complet(self):
        pret = self._creer_pret('CONSTANT')
        services.generer_ecriture_deblocage_pret(pret, self.tenant)
        # Déblocage : trésorerie +1.2M, emprunt crédité 1.2M
        self.assertEqual(self._solde('521'), Decimal('1200000'))
        self.assertEqual(self._solde('162'), Decimal('-1200000'))

        total_interets = sum(e.part_interet for e in pret.echeances.all())
        for e in pret.echeances.all():
            e.statut = 'PAYE'; e.date_paiement = datetime.date(2026, 1, 1); e.save()
            services.generer_ecriture_echeance(e, self.tenant)

        # Emprunt soldé, intérêts en charge, trésorerie = -(intérêts) net
        self.assertEqual(self._solde('162'), 0)                       # capital remboursé
        self.assertEqual(self._solde('671'), total_interets)          # charge d'intérêts (débit)
        self.assertEqual(self._solde('521'), -total_interets)         # +1.2M -1.2M capital -intérêts
        # Équilibre général
        agg = JournalEntry.objects.filter(tenant=self.tenant).aggregate(d=Sum('debit'), c=Sum('credit'))
        self.assertEqual(agg['d'], agg['c'])

    def test_pret_taux_zero(self):
        rows = services.calcul_amortissement(Decimal('1000000'), Decimal('0'), 10, 'MENSUELLE', 'CONSTANT')
        self.assertEqual(sum(r['part_interet'] for r in rows), Decimal('0'))
        self.assertEqual(sum(r['part_capital'] for r in rows), Decimal('1000000'))

    # ── Analyse / retards ──────────────────────────────────────────────────
    def test_maj_retards_bascule_echeances_depassees(self):
        from .views import _maj_retards
        hier = datetime.date.today() - datetime.timedelta(days=1)
        demain = datetime.date.today() + datetime.timedelta(days=1)
        cycle = NattCycle.objects.create(
            tenant=self.tenant, reference='NATT-R', nom='T', nb_participants=5, duree=5,
            montant_cotisation=Decimal('10000'), date_debut=hier)
        c_retard = NattCotisation.objects.create(tenant=self.tenant, cycle=cycle, numero=1,
                                                 date_echeance=hier, montant=Decimal('10000'))
        c_ok = NattCotisation.objects.create(tenant=self.tenant, cycle=cycle, numero=2,
                                             date_echeance=demain, montant=Decimal('10000'))
        _maj_retards(self.tenant)
        c_retard.refresh_from_db(); c_ok.refresh_from_db()
        self.assertEqual(c_retard.statut, 'EN_RETARD')
        self.assertEqual(c_ok.statut, 'A_PAYER')

    def test_analyse_endpoint_ratios(self):
        from django.test import RequestFactory
        from .views import AnalyseGMRFView
        tf = TypeFinancement.objects.create(tenant=self.tenant, code='DON', libelle='Don',
                                            categorie='DON', compte_ressource='7588')
        Financement.objects.create(tenant=self.tenant, reference='GRF-1', type_financement=tf,
                                   libelle='Don', montant=Decimal('500000'),
                                   date_reception=datetime.date.today(), compte_ressource='7588',
                                   compte_tresorerie='521', statut='RECU')
        pret = self._creer_pret('CONSTANT', montant=Decimal('1000000'), nb=12)
        req = RequestFactory().get('/api/gmrf/analyse/')
        req.tenant = self.tenant
        resp = AnalyseGMRFView().get(req)
        self.assertEqual(resp.status_code, 200)
        r = resp.data['ratios']
        # dette = capital restant prêt (1M, rien remboursé) ; ressources = don 500k + prêt 1M
        self.assertEqual(r['capital_restant_prets'], 1000000)
        self.assertEqual(r['ressources_mobilisees'], 1500000)
        self.assertTrue(any(x['categorie'] == 'Dons' for x in resp.data['repartition']))
        self.assertEqual(len(resp.data['evolution']), 12)
        self.assertEqual(len(resp.data['echeancier']), 12)

    # ── PDF & documents ────────────────────────────────────────────────────
    def test_pdf_pret_et_natt(self):
        from django.test import RequestFactory
        from .pdf_views import PretPDFView, NattPDFView
        pret = self._creer_pret('CONSTANT', nb=6)
        cycle = NattCycle.objects.create(
            tenant=self.tenant, reference='NATT-PDF', nom='Tontine', nb_participants=5, duree=5,
            montant_cotisation=Decimal('20000'), date_debut=datetime.date(2025, 11, 1))
        NattCotisation.objects.create(tenant=self.tenant, cycle=cycle, numero=1,
                                      date_echeance=datetime.date(2025, 11, 1), montant=Decimal('20000'))
        rf = RequestFactory()
        for view, pk in [(PretPDFView(), pret.id), (NattPDFView(), cycle.id)]:
            req = rf.get('/pdf/'); req.tenant = self.tenant
            resp = view.get(req, pk)
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp['Content-Type'], 'application/pdf')
            self.assertTrue(resp.content[:4] == b'%PDF')

    def test_documents_ajout_suppression(self):
        from django.test import RequestFactory
        from .views import DocumentsView
        pret = self._creer_pret('IN_FINE', nb=3)
        f = RequestFactory()
        view = DocumentsView()
        # Ajout
        req = f.post('/x/'); req.tenant = self.tenant
        req.data = {'nom': 'contrat.pdf', 'data': 'data:application/pdf;base64,AAAA'}
        resp = view.post(req, 'pret', pret.id)
        self.assertEqual(resp.status_code, 201)
        pret.refresh_from_db()
        self.assertEqual(len(pret.documents), 1)
        self.assertEqual(pret.documents[0]['nom'], 'contrat.pdf')
        # Suppression
        req2 = f.delete('/x/?index=0'); req2.tenant = self.tenant
        req2.query_params = {'index': '0'}
        resp2 = view.delete(req2, 'pret', pret.id)
        self.assertEqual(resp2.status_code, 200)
        pret.refresh_from_db()
        self.assertEqual(len(pret.documents), 0)
