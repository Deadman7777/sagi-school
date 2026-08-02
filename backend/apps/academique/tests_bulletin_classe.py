"""Test : le bulletin imprime la CLASSE de l'élève, pas sa section tarifaire.

La section est un niveau de tarif. L'imprimer sur un bulletin affiche
« Élémentaire » là où il faut lire « CM2 ». Chez un centre de formation dont
les grilles distinguent les auditeurs par nationalité, cela imprimait
« 1re année — Étranger » sur le bulletin, à la place de la filière suivie.
"""
import datetime

from rest_framework.test import APITestCase

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.paiements.models import Exercice
from apps.eleves.models import Eleve, Section
from apps.academique.models import (Classe, Evaluation, Matiere, NiveauScolaire,
                                    Note, TypeEvaluation)


class BulletinClasseTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='CEDT LE G15', periode_scolaire='SEMESTRE',
                                            nb_periodes=2)
        self.user = User.objects.create_user('dir@g15.sn', 'x', nom='Directeur',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026-2027', cloture=False,
            date_debut=datetime.date(2026, 10, 1), date_fin=datetime.date(2027, 6, 30))

        # La section porte le TARIF, la classe porte la FILIÈRE : les deux
        # libellés diffèrent, c'est tout l'intérêt de la distinction.
        self.section = Section.objects.create(tenant=self.tenant,
                                              nom='1re année — Étranger',
                                              frais_mensualite=100000)
        niveau = NiveauScolaire.objects.create(tenant=self.tenant, nom='BTS',
                                               code='SUPERIEUR')
        self.classe = Classe.objects.create(tenant=self.tenant, niveau=niveau,
                                            nom='Génie civil — 1re année')

        matiere = Matiere.objects.create(tenant=self.tenant, classe=self.classe,
                                         nom='Béton armé', coefficient=5, note_max=20)
        type_eval = TypeEvaluation.objects.create(tenant=self.tenant,
                                                  nom='Composition', poids=2)
        self.evaluation = Evaluation.objects.create(
            tenant=self.tenant, matiere=matiere, type_eval=type_eval,
            trimestre='S1', date_eval=datetime.date(2027, 1, 20), note_max=20)

    def _auditeur(self, nom, classe):
        e = Eleve.objects.create(tenant=self.tenant, exercice=self.ex,
                                 section=self.section, classe=classe, nom_complet=nom)
        Note.objects.create(tenant=self.tenant, eleve=e,
                            evaluation=self.evaluation, valeur=15)
        return e

    def _bulletin(self, eleve):
        self.client.post('/api/academique/calculer/',
                         {'classe_id': str(self.classe.id), 'trimestre': 'S1'},
                         format='json')
        r = self.client.get(f'/api/academique/bulletin/{eleve.id}/S1/')
        self.assertEqual(r.status_code, 200, r.content)
        return r.data

    def test_le_bulletin_porte_la_filiere_pas_la_grille_tarifaire(self):
        auditeur = self._auditeur('Kofi MENSAH', self.classe)
        data = self._bulletin(auditeur)
        self.assertEqual(data['eleve']['classe'], 'Génie civil — 1re année')
        self.assertNotEqual(data['eleve']['classe'], self.section.nom)

    def test_repli_sur_la_section_quand_aucune_classe_n_est_posee(self):
        """Fiches anciennes : la section reste le seul libellé disponible."""
        ancien = self._auditeur('Fiche ancienne', None)
        # Le calcul retrouve les fiches sans classe dont la section porte le nom
        # de la classe : on aligne les deux pour couvrir ce repli.
        self.section.nom = self.classe.nom
        self.section.save()
        data = self._bulletin(ancien)
        self.assertEqual(data['eleve']['classe'], self.classe.nom)
