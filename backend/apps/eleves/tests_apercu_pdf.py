"""Rend un vrai PDF de liste dans le scratchpad, pour inspection visuelle.

Ne s'exécute que si SAGI_APERCU_PDF est dans l'environnement : ce n'est pas
une assertion, c'est un outil de relecture.
"""
import datetime
import os
import unittest

from rest_framework.test import APITestCase

from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User

DOSSIER = os.environ.get('SAGI_APERCU_PDF', '')


@unittest.skipUnless(DOSSIER, 'aperçu désactivé (SAGI_APERCU_PDF absent)')
class ApercuListesTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            nom='COMPLEXE SHOUMOUL EXCELLENCE', code_etablissement='CSE',
            ville='Rufisque', telephone='+221 70 328 61 51')
        self.user = User.objects.create_user(
            'a@a.sn', 'x', nom='Admin', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', nb_mensualites=12,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))
        sections = [
            ('INTERNAT TAHFIIZ', 1, 60000), ('DEMI-PENSION', 2, 40000),
            ('EXTERNAT', 3, 20000),
        ]
        self.sections = {
            nom: Section.objects.create(
                tenant=self.tenant, nom=nom, ordre=ordre,
                frais_inscription=185000, frais_mensualite=mens)
            for nom, ordre, mens in sections}

        noms = ['Fatimatou Binetou NDIAYE', 'Mouhamadou Lamine DIOP',
                'Aïcha SOW', 'Serigne Saliou FALL', 'Khadija BA',
                'Ibrahima SARR', 'Mariama CISSÉ', 'Ousmane GUEYE']
        for i, nom in enumerate(noms):
            section = list(self.sections.values())[i % 3]
            eleve = Eleve.objects.create(
                tenant=self.tenant, exercice=self.ex, section=section,
                nom_complet=nom, statut='INSCRIT',
                matricule=f'{2019 + i % 5}-CSE-{i + 1:04d}',
                genre='F' if i % 2 else 'G',
                date_naissance=datetime.date(2012, (i % 12) + 1, 15),
                date_inscription=datetime.date(2026, 1, 1),
                mois_dus=[1, 2, 3, 4, 5, 6])
            if i % 3:
                Paiement.objects.create(
                    tenant=self.tenant, exercice=self.ex, eleve=eleve,
                    no_piece=f'REC-{i}', mode_paiement='ESPECE',
                    montant_mensualite=float(section.frais_mensualite) * 2,
                    mois_regles=[1, 2], statut='ACTIF')

    def _ecrire(self, url, fichier):
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200, r.content[:300])
        chemin = os.path.join(DOSSIER, fichier)
        with open(chemin, 'wb') as f:
            f.write(r.content)
        print(f'\n  → {chemin} ({len(r.content)} octets)')

    def test_apercus(self):
        self._ecrire('/api/eleves/export-pdf/?tri=section', 'liste_financiere.pdf')
        self._ecrire('/api/eleves/export-pdf/?financier=0&tri=section',
                     'liste_nominative_section.pdf')
        self._ecrire('/api/eleves/export-pdf/?financier=0&tri=matricule',
                     'liste_nominative_matricule.pdf')
