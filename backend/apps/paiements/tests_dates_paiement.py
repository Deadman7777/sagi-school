"""Tests : la date d'un règlement est celle du règlement, pas celle du serveur.

Le cas rapporté (Complexe Shoumoul Excellence, 19/08/2026) : après la bascule
en cloud, le tableau de bord et l'écran des paiements affichaient partout la
même date — celle de l'import. `date_paiement` était déclaré `auto_now_add`,
et Django applique ce champ jusque dans le `bulk_create` de `importer_ecole` :
les 62 règlements de l'année ont été réécrits au jour de la bascule, et
`TruncMonth('date_paiement')` a empilé l'année entière sur un seul mois.

Ce qui est vérifié ici, c'est la COHÉRENCE entre les deux tables qui datent le
même événement : un règlement et l'écriture qui le constate ne peuvent pas
porter des dates différentes. C'est cette règle qui a été violée, et c'est elle
que `reparer_dates_paiement` rétablit — le journal, lui, avait gardé la vérité.
"""
import datetime
from io import StringIO

from django.core.management import call_command
from rest_framework.test import APITestCase

from apps.comptabilite.models import JournalEntry
from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User


class DatesPaiementTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul', code_etablissement='SHO')
        self.user = User.objects.create_user(
            'a@sho.sn', 'x', nom='Admin', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', nb_mensualites=12,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))
        self.section = Section.objects.create(
            tenant=self.tenant, nom='CM2', frais_inscription=100000,
            frais_mensualite=50000, frais_uniforme=0, frais_fournitures=0)
        self.eleve = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, section=self.section,
            nom_complet='Awa NDIAYE', date_inscription=self.ex.date_debut)

    def _encaisser(self, **extra):
        corps = {'eleve': str(self.eleve.id), 'montant_mensualite': 50000,
                 'mode_paiement': 'ESPECE'}
        corps.update(extra)
        return self.client.post('/api/paiements/paiements/', corps, format='json')

    # ── La date saisie est celle qui compte ───────────────────────────────
    def test_une_date_saisie_est_conservee(self):
        """Le cœur du bug : `auto_now_add` écrasait toute date fournie."""
        r = self._encaisser(date_paiement='2026-03-14')

        self.assertEqual(r.status_code, 201, r.content[:300])
        p = Paiement.objects.get(pk=r.data['id'])
        self.assertEqual(p.date_paiement, datetime.date(2026, 3, 14))

    def test_l_ecriture_porte_la_meme_date_que_le_reglement(self):
        """Deux tables datent le même événement : elles doivent s'accorder."""
        r = self._encaisser(date_paiement='2026-03-14')

        p = Paiement.objects.get(pk=r.data['id'])
        dates = set(JournalEntry.objects
                    .filter(tenant=self.tenant, source_id=p.id)
                    .values_list('date_ecriture', flat=True))
        self.assertEqual(dates, {p.date_paiement})

    def test_sans_date_fournie_la_saisie_reste_celle_d_aujourd_hui(self):
        """Le comportement historique, à ne pas casser : le front n'envoie rien."""
        r = self._encaisser()

        self.assertEqual(r.status_code, 201, r.content[:300])
        p = Paiement.objects.get(pk=r.data['id'])
        self.assertEqual(p.date_paiement, datetime.date.today())

    def test_une_date_hors_exercice_est_refusee(self):
        """Sinon un produit apparaîtrait dans une année qui n'est pas la sienne."""
        r = self._encaisser(date_paiement='2025-03-14')

        self.assertEqual(r.status_code, 400)
        self.assertIn('2026', str(r.content, 'utf-8'))

    # ── La réparation de l'existant ───────────────────────────────────────
    def test_reparer_dates_paiement_rend_au_reglement_la_date_du_journal(self):
        """Reproduit la bascule : la date écrasée, le journal intact."""
        r = self._encaisser(date_paiement='2026-03-14')
        p = Paiement.objects.get(pk=r.data['id'])

        # Ce que l'import a fait : la date du jour posée par-dessus, sans
        # toucher aux écritures (DateField ordinaire, transporté tel quel).
        jour_de_l_import = datetime.date(2026, 8, 19)
        Paiement.objects.filter(pk=p.pk).update(date_paiement=jour_de_l_import)

        call_command('reparer_dates_paiement', tenant='Shoumoul',
                     appliquer=True, stdout=StringIO())

        p.refresh_from_db()
        self.assertEqual(p.date_paiement, datetime.date(2026, 3, 14))

    def test_sans_appliquer_la_commande_n_ecrit_rien(self):
        r = self._encaisser(date_paiement='2026-03-14')
        p = Paiement.objects.get(pk=r.data['id'])
        Paiement.objects.filter(pk=p.pk).update(
            date_paiement=datetime.date(2026, 8, 19))

        call_command('reparer_dates_paiement', tenant='Shoumoul',
                     stdout=StringIO())

        p.refresh_from_db()
        self.assertEqual(p.date_paiement, datetime.date(2026, 8, 19))

    def test_un_reglement_sans_ecriture_est_signale_et_laisse_tel_quel(self):
        """On ne devine pas une date : sans contrepartie, aucune source ne fait foi."""
        orphelin = Paiement.objects.create(
            tenant=self.tenant, exercice=self.ex, eleve=self.eleve,
            no_piece='REC-9999', mode_paiement='ESPECE',
            montant_mensualite=1000, statut='ACTIF',
            date_paiement=datetime.date(2026, 8, 19))
        sortie = StringIO()

        call_command('reparer_dates_paiement', tenant='Shoumoul',
                     appliquer=True, stdout=sortie)

        orphelin.refresh_from_db()
        self.assertEqual(orphelin.date_paiement, datetime.date(2026, 8, 19))
        self.assertIn('REC-9999', sortie.getvalue())
