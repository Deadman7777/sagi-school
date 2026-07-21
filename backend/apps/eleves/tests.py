"""Tests de la migration Excel : colonnes « À jour » / « Dette actuelle ».

Exercice volontairement passé (2024-2025) → toutes les mensualités sont
échues, ce qui rend les assertions déterministes (indépendantes de la date
d'exécution) : le dû à ce jour = l'attendu annuel.
"""
import datetime
import io

from django.test import TestCase

from apps.tenants.models import Tenant
from apps.paiements.models import Exercice
from apps.paiements.reprise import creer_paiement_reprise
from .models import Eleve, Section
from .import_eleves import analyser, generer_template  # noqa: F401


def _xlsx(entetes, ligne):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(entetes)
    ws.append(ligne)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


class MigrationSituationTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='École Test')
        self.exercice = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2024-2025',
            date_debut=datetime.date(2024, 10, 1),
            date_fin=datetime.date(2025, 7, 31), nb_mensualites=9)
        self.section = Section.objects.create(
            tenant=self.tenant, nom='CI', frais_inscription=10000,
            frais_mensualite=5000, frais_uniforme=0, frais_fournitures=0)
        # dû annuel = 10000 + 5000×9 = 55 000

    def _analyser_une_ligne(self, **cols):
        """Construit un .xlsx d'une ligne (nom + section + colonnes données)."""
        from .import_eleves import COLONNES
        valeurs = {'nom_complet': 'Aliou Ba', 'section': 'CI'}
        valeurs.update(cols)
        entetes = list(COLONNES.values())
        ligne = [valeurs.get(cle, '') for cle in COLONNES]
        rapport = analyser(_xlsx(entetes, ligne), self.tenant, self.exercice)
        return rapport['lignes'][0]

    def _creer(self, ligne):
        eleve = Eleve.objects.create(
            tenant=self.tenant, exercice=self.exercice, section=self.section,
            numero=1, nom_complet='Aliou Ba', date_inscription=self.exercice.date_debut)
        creer_paiement_reprise(self.tenant, self.exercice, eleve, **ligne['reprise'])
        eleve.refresh_from_db()
        return eleve

    def test_a_jour(self):
        ligne = self._analyser_une_ligne(a_jour='O')
        self.assertEqual(ligne['statut'], 'OK')
        self.assertEqual(ligne['montant_reprise'], 55000)      # tout le dû échu
        eleve = self._creer(ligne)
        self.assertEqual(float(eleve.total_paye), 55000)
        self.assertEqual(float(eleve.reste_a_payer), 0)
        self.assertEqual(eleve.niveau_alerte, 'A_JOUR')

    def test_dette_actuelle(self):
        ligne = self._analyser_une_ligne(dette_actuelle='15000')
        self.assertEqual(ligne['statut'], 'OK')
        # payé = 55000 − 15000 = 40 000 (inscription 10000 + 6 mois × 5000)
        self.assertEqual(ligne['montant_reprise'], 40000)
        m = ligne['reprise']['montants']
        self.assertEqual(m['montant_inscription'], 10000)
        self.assertEqual(m['montant_mensualite'], 30000)
        eleve = self._creer(ligne)
        self.assertEqual(float(eleve.total_paye), 40000)
        self.assertEqual(float(eleve.reste_a_payer), 15000)    # = la dette saisie
        self.assertEqual(eleve.niveau_alerte, 'CRITIQUE')      # 3 mois d'arriérés

    def test_dette_zero_equivaut_a_jour(self):
        ligne = self._analyser_une_ligne(dette_actuelle='0')
        eleve = self._creer(ligne)
        self.assertEqual(float(eleve.reste_a_payer), 0)
        self.assertEqual(eleve.niveau_alerte, 'A_JOUR')

    def test_dette_plafonnee_au_du(self):
        ligne = self._analyser_une_ligne(dette_actuelle='999999')
        self.assertTrue(any('plafonnée' in a for a in ligne['avertissements']))
        eleve = self._creer(ligne)
        self.assertEqual(float(eleve.total_paye), 0)           # rien payé
        self.assertEqual(float(eleve.reste_a_payer), 55000)
