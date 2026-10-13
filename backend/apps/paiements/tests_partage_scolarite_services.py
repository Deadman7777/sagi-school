"""Le dû de l'élève et le cahier mensuel, scolarité et services à part.

Demande du 13/10/2026 : dans le total dû de chaque élève, et dans le cahier
mensuel, distinguer la scolarité des services pour les suivre séparément.
La somme des deux parts est toujours celle de l'échéancier.
"""
import datetime

from apps.eleves.echeancier import construire_echeancier, partage_scolarite_services
from apps.eleves.models import Eleve
from apps.paiements.cahier_mensuel import cahier_mensuel

from rest_framework.test import APITestCase

from . import tests_recus_separes as base

AUJOURDHUI = datetime.date(2026, 10, 20)


class PartageScolariteServicesTest(APITestCase):
    # Même école que les reçus séparés (scolarité 140 000, transport 30 000),
    # sans rejouer ses tests.
    setUp = base.RecusSeparesTest.setUp
    _eleve = base.RecusSeparesTest._eleve
    _encaisser = base.RecusSeparesTest._encaisser
    _transport = base.RecusSeparesTest._transport

    def _partage(self, eleve):
        e = Eleve.objects.get(pk=eleve.pk)
        ech = construire_echeancier(e, today=AUJOURDHUI)
        return ech, partage_scolarite_services(e, ech)

    def test_rien_paye(self):
        ech, p = self._partage(self._eleve('Awa NDIAYE'))
        octobre = p['mois'][10]
        self.assertEqual((octobre['scolarite']['du'], octobre['services']['du']), (140000, 30000))
        self.assertEqual((octobre['scolarite']['reste'], octobre['services']['reste']), (140000, 30000))
        self.assertEqual(p['scolarite']['du'] + p['services']['du'], ech['totaux']['du'])
        self.assertEqual(p['services']['du'], 30000 * 9)

    def test_recu_de_scolarite_seul_laisse_le_transport_du(self):
        eleve = self._eleve('Awa NDIAYE')
        self._encaisser(eleve, montant_mensualite=140000, mois_regles=[10])
        _, p = self._partage(eleve)
        octobre = p['mois'][10]
        self.assertEqual((octobre['scolarite']['reste'], octobre['services']['reste']), (0, 30000))
        self.assertEqual((octobre['scolarite']['paye'], octobre['services']['paye']), (140000, 0))

    def test_recu_de_transport_seul_laisse_la_scolarite_due(self):
        eleve = self._eleve('Awa NDIAYE')
        self._transport(eleve)
        _, p = self._partage(eleve)
        octobre = p['mois'][10]
        self.assertEqual((octobre['scolarite']['reste'], octobre['services']['reste']), (140000, 0))

    def test_les_parts_somment_toujours_l_echeancier(self):
        eleve = self._eleve('Awa NDIAYE')
        self._encaisser(eleve, montant_mensualite=100000, mois_regles=[10])
        ech, p = self._partage(eleve)
        for l in ech['lignes']:
            parts = p['mois'][l['mois']]
            self.assertAlmostEqual(parts['scolarite']['reste'] + parts['services']['reste'], l['reste'])
            self.assertAlmostEqual(parts['scolarite']['du'] + parts['services']['du'], l['du'])
        self.assertAlmostEqual(p['scolarite']['reste'] + p['services']['reste'], ech['totaux']['reste'])

    def test_api_echeancier_porte_le_partage(self):
        eleve = self._eleve('Awa NDIAYE')
        d = self.client.get(f'/api/eleves/{eleve.id}/echeancier/').json()
        self.assertEqual(d['services']['du'], 30000 * 9)
        self.assertEqual(d['lignes'][0]['services']['du'], 30000)

    def test_cahier_mensuel_separe_scolarite_et_services(self):
        a, b = self._eleve('Awa NDIAYE'), self._eleve('Binta FALL')
        self._encaisser(a, montant_mensualite=140000, mois_regles=[10])
        self._transport(b)
        c = cahier_mensuel(self.tenant, self.ex, 2026, 10, today=AUJOURDHUI)
        t = c['scolarite']['totaux']
        self.assertEqual((t['scolarite']['attendu'], t['scolarite']['encaisse'], t['scolarite']['reste']),
                         (280000, 140000, 140000))
        self.assertEqual((t['services']['attendu'], t['services']['encaisse'], t['services']['reste']),
                         (60000, 30000, 30000))
        self.assertEqual((t['services']['nb_payes'], t['services']['nb_impayes']), (1, 1))
        lignes = {x['nom_complet']: x for x in c['scolarite']['partiels']}
        self.assertEqual(lignes['Awa NDIAYE']['services']['reste'], 30000)
