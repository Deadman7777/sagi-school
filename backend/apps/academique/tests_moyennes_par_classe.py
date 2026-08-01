"""Test : les moyennes se calculent sur la CLASSE de l'élève.

Le rapprochement se faisait par nom de section. Il ne tombait juste que
pour une école dont une section porte le nom d'une classe. Dès que les
sections sont les niveaux tarifaires (Maternelle, Élémentaire…) et les
classes les vraies classes (CI, CE2, CM2…), le calcul ne trouvait aucun
élève : moyennes vides, puis bulletins « Aucune note calculée » alors que
les notes étaient bien en base.
"""
import datetime

from rest_framework.test import APITestCase

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.paiements.models import Exercice
from apps.eleves.models import Eleve, Section
from apps.academique.models import (Classe, Evaluation, Matiere, NiveauScolaire,
                                    Note, TypeEvaluation)


class MoyennesParClasseTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Les Palmiers')
        self.user = User.objects.create_user(
            'dir@palmiers.sn', 'x', nom='Directrice', role='ADMIN_ECOLE',
            tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2025-2026', cloture=False,
            date_debut=datetime.date(2025, 10, 1), date_fin=datetime.date(2026, 7, 31))

        # La section est le niveau tarifaire, la classe est la vraie classe :
        # les deux noms diffèrent, c'est le cas courant.
        self.section = Section.objects.create(
            tenant=self.tenant, nom='Élémentaire', frais_mensualite=22000)
        self.niveau = NiveauScolaire.objects.create(
            tenant=self.tenant, nom='Élémentaire', code='ELEMENTAIRE')
        self.classe = Classe.objects.create(
            tenant=self.tenant, nom='CM2', code='CM2', niveau=self.niveau)

        self.matiere = Matiere.objects.create(
            tenant=self.tenant, classe=self.classe, nom='Mathématiques',
            coefficient=5, note_max=20)
        self.type_eval = TypeEvaluation.objects.create(
            tenant=self.tenant, nom='Composition', poids=2)
        self.evaluation = Evaluation.objects.create(
            tenant=self.tenant, matiere=self.matiere, type_eval=self.type_eval,
            trimestre='T1', date_eval=datetime.date(2025, 12, 12), note_max=20)

    def _eleve(self, nom, note, classe=None):
        e = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, section=self.section,
            classe=classe if classe is not None else self.classe, nom_complet=nom)
        Note.objects.create(tenant=self.tenant, eleve=e,
                            evaluation=self.evaluation, valeur=note)
        return e

    def _calculer(self):
        return self.client.post('/api/academique/calculer/',
                                {'classe_id': str(self.classe.id), 'trimestre': 'T1'},
                                format='json')

    def test_les_eleves_de_la_classe_sont_pris_en_compte(self):
        self._eleve('Awa SECK', 16)
        self._eleve('Modou FALL', 12)

        r = self._calculer()
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(len(r.data['resultats']), 2)
        self.assertEqual(r.data['stats']['nb_eleves'], 2)
        self.assertEqual(r.data['stats']['moy_classe'], 14.0)

    def test_le_bulletin_suit_le_calcul(self):
        eleve = self._eleve('Awa SECK', 16)
        self._calculer()

        r = self.client.get(f'/api/academique/bulletin/{eleve.id}/T1/')
        self.assertEqual(r.status_code, 200, r.content)

    def test_repli_sur_la_section_pour_les_fiches_sans_classe(self):
        """Données anciennes : la section porte le nom de la classe."""
        section_cm2 = Section.objects.create(tenant=self.tenant, nom='CM2')
        ancien = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, section=section_cm2,
            classe=None, nom_complet='Fiche ancienne')
        Note.objects.create(tenant=self.tenant, eleve=ancien,
                            evaluation=self.evaluation, valeur=15)

        r = self._calculer()
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(len(r.data['resultats']), 1)
        self.assertEqual(r.data['resultats'][0]['eleve_nom'], 'Fiche ancienne')
