"""Tests du moteur de comptabilisation GMRF (intégration comptable)."""
import datetime
from decimal import Decimal

from django.test import TestCase
from django.db.models import Sum

from apps.tenants.models import Tenant
from apps.paiements.models import Exercice
from apps.comptabilite.models import JournalEntry
from .models import NattCycle, NattCotisation, NattReception, TypeFinancement, Financement
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
