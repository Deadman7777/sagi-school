"""Niveau → Section → Classe : un vrai rangement, pas une correspondance de noms.

Avant septembre 2026, le front rapprochait une classe et une section quand
`classe.niveau.nom == section.nom`. Conséquences : renommer une section
détachait silencieusement ses classes, et deux sections homonymes dans deux
écoles se mélangeaient à l'écran.

Ce que ces tests rendent impossible :
- une classe qui perd sa section parce qu'on a renommé la section ;
- un niveau saisi deux fois (sur la section et sur la classe) qui diverge ;
- un élève qu'on ne pourrait pas inscrire sans classe (mémorisation seule).
"""
import datetime

from rest_framework.test import APITestCase

from apps.academique.models import Classe, NiveauScolaire
from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant
from apps.users.models import User


class HierarchieTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Daara Tahfiiz', code_etablissement='DTH')
        self.user = User.objects.create_user('dir@dth.sn', 'x', nom='Dir',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.elementaire = NiveauScolaire.objects.create(
            tenant=self.tenant, nom='Niveau élémentaire', code='ELEMENTAIRE', note_max=20)
        self.section = Section.objects.create(tenant=self.tenant, nom='Internat Tahfiiz',
                                              frais_mensualite=25000, niveau=self.elementaire)
        self.classe = Classe.objects.create(tenant=self.tenant, section=self.section, nom='CIA')

    def test_la_classe_herite_du_niveau_de_sa_section(self):
        # Le niveau n'est saisi QUE sur la section : deux saisies divergeraient.
        self.assertEqual(self.classe.niveau_id, self.elementaire.id)

    def test_renommer_la_section_ne_detache_pas_ses_classes(self):
        # C'est le bug de la correspondance par nom : le lien tenait au libellé.
        self.section.nom = 'Internat Tahfiiz (garçons)'
        self.section.save()
        self.classe.refresh_from_db()
        self.assertEqual(self.classe.section_id, self.section.id)
        self.assertEqual(list(self.section.classes.all()), [self.classe])

    def test_changer_le_niveau_de_la_section_suit_sur_la_classe(self):
        college = NiveauScolaire.objects.create(tenant=self.tenant, nom='Collège',
                                                code='COLLEGE', note_max=20)
        self.section.niveau = college
        self.section.save()
        self.classe.save()
        self.classe.refresh_from_db()
        self.assertEqual(self.classe.niveau_id, college.id)

    def test_l_api_rend_la_section_et_le_niveau(self):
        r = self.client.get('/api/academique/classes/')
        ligne = (r.data.get('results') or r.data)[0]
        self.assertEqual(ligne['section'], self.section.id)
        self.assertEqual(ligne['section_nom'], 'Internat Tahfiiz')
        self.assertEqual(ligne['niveau_nom'], 'Niveau élémentaire')

    def test_un_eleve_peut_n_avoir_aucune_classe(self):
        # Daara : dans une même section, les uns suivent un programme en classe,
        # les autres ne font que mémoriser le Coran et ne sont dans aucune classe.
        ex = Exercice.objects.create(tenant=self.tenant, annee_scolaire='2026', nb_mensualites=9,
                                     date_debut=datetime.date(2026, 1, 1),
                                     date_fin=datetime.date(2026, 12, 31))
        r = self.client.post('/api/eleves/liste/', {
            'exercice': str(ex.id), 'section': str(self.section.id), 'classe': None,
            'nom_complet': 'Moussa FALL', 'date_inscription': '2026-01-05',
        }, format='json')
        self.assertIn(r.status_code, (200, 201), r.data)
        memorisant = Eleve.objects.get(nom_complet='Moussa FALL')
        self.assertIsNone(memorisant.classe_id)
        self.assertEqual(memorisant.section_id, self.section.id)
