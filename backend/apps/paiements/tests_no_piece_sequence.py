"""Tests : le numéro de reçu suivant se calcule sur des NOMBRES.

Une école encaissait normalement, une autre renvoyait 500 sur chaque paiement.
Toutes deux sur la même base, le même code, le même exercice — seule leur
histoire différait.

Le numéro suivant venait de `Max('no_piece')`, un maximum ALPHABÉTIQUE :

    max('REC-0100', 'REP-0005') == 'REP-0005'

parce que « P » vient après « C ». Une école qui a fait une reprise de migration
(pièces REP-NNNN, dans la même table que les reçus) tôt dans sa vie, puis cent
encaissements, voyait donc le calcul repartir de 5 → REC-0006 → déjà pris →
IntegrityError sur `uniq_no_piece_par_tenant` → 500. Et il ne pouvait plus
JAMAIS émettre un reçu : chaque tentative retombait sur le même numéro.

L'école sans reprise, elle, n'avait que des REC- : son maximum alphabétique
coïncidait avec son maximum numérique et tout fonctionnait.
"""
import datetime

from rest_framework.test import APITestCase

from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User


class SequenceNoPieceTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Daara', code_etablissement='DAA')
        self.user = User.objects.create_user(
            'a@a.sn', 'x', nom='Admin', role='ADMIN_ECOLE', tenant=self.tenant)
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

    def _piece(self, no_piece, montant=1000):
        return Paiement.objects.create(
            tenant=self.tenant, exercice=self.ex, eleve=self.eleve,
            no_piece=no_piece, mode_paiement='ESPECE',
            montant_mensualite=montant, statut='ACTIF')

    def _encaisser(self, montant=50000):
        return self.client.post('/api/paiements/paiements/', {
            'eleve': str(self.eleve.id), 'exercice': str(self.ex.id),
            'montant_mensualite': montant, 'mode_paiement': 'ESPECE',
        }, format='json')

    # ── Le cas des deux écoles ────────────────────────────────────────────
    def test_une_reprise_ancienne_ne_bloque_plus_les_encaissements(self):
        """Le cas rapporté : REP-0005 écrasait REC-0100 au classement."""
        for i in range(1, 11):
            self._piece(f'REC-{i:04d}')
        self._piece('REP-0005')          # reprise de migration, numéro bas

        r = self._encaisser()

        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(r.data['no_piece'], 'REC-0011')

    def test_l_ecole_sans_reprise_continue_de_fonctionner(self):
        """L'autre école du rapport — le comportement à ne pas casser."""
        for i in range(1, 11):
            self._piece(f'REC-{i:04d}')

        r = self._encaisser()

        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(r.data['no_piece'], 'REC-0011')

    def test_la_premiere_piece_d_une_ecole_neuve(self):
        r = self._encaisser()

        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(r.data['no_piece'], 'REC-0001')

    def test_deux_encaissements_de_suite_ne_se_marchent_pas_dessus(self):
        self._piece('REP-0003')

        self.assertEqual(self._encaisser().status_code, 201)
        self.assertEqual(self._encaisser().status_code, 201)

        pieces = list(Paiement.objects.filter(tenant=self.tenant)
                      .values_list('no_piece', flat=True))
        self.assertEqual(len(pieces), len(set(pieces)))

    def test_le_numero_depasse_les_quatre_chiffres_sans_collision(self):
        """Au-delà de 9999 le zéro-padding ne cadre plus : le tri alphabétique
        se trompait alors même entre REC- (REC-10000 < REC-9999)."""
        self._piece('REC-9999')
        self._piece('REC-10000')

        r = self._encaisser()

        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(r.data['no_piece'], 'REC-10001')

    def test_un_numero_sans_chiffre_n_arrete_pas_la_sequence(self):
        """Données migrées à la main : une pièce peut ne rien contenir de
        numérique. Elle ne doit ni compter, ni faire échouer le calcul."""
        self._piece('REC-0004')
        self._piece('OUVERTURE')

        r = self._encaisser()

        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(r.data['no_piece'], 'REC-0005')

    # ── Isolation entre écoles ────────────────────────────────────────────
    def test_chaque_ecole_a_sa_propre_sequence(self):
        autre = Tenant.objects.create(nom='Autre', code_etablissement='AUT')
        ex_autre = Exercice.objects.create(
            tenant=autre, annee_scolaire='2026', nb_mensualites=12,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))
        section = Section.objects.create(tenant=autre, nom='CM2',
                                         frais_mensualite=50000)
        eleve = Eleve.objects.create(
            tenant=autre, exercice=ex_autre, section=section,
            nom_complet='Modou FALL', date_inscription=datetime.date(2026, 1, 1))
        Paiement.objects.create(
            tenant=autre, exercice=ex_autre, eleve=eleve,
            no_piece='REC-0500', mode_paiement='ESPECE',
            montant_mensualite=1000, statut='ACTIF')

        # L'école courante n'a rien : son premier reçu reste REC-0001.
        r = self._encaisser()

        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(r.data['no_piece'], 'REC-0001')
