"""Test : recopier les matières d'une classe vers d'autres classes.

Un établissement à filières partage un tronc commun. Saisir les mêmes matières
classe par classe, c'est plusieurs centaines de saisies au paramétrage d'un
centre de formation — et des coefficients qui divergent d'une classe à l'autre
au premier oubli.
"""
from rest_framework.test import APITestCase

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.academique.models import Classe, Matiere, NiveauScolaire


class CopierMatieresTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='CEDT LE G15')
        self.user = User.objects.create_user('dir@g15.sn', 'x', nom='Directeur',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        niveau = NiveauScolaire.objects.create(tenant=self.tenant, nom='BTS',
                                               code='SUPERIEUR')
        self.source = Classe.objects.create(tenant=self.tenant, niveau=niveau,
                                            nom='Génie civil — 1re année')
        self.cible1 = Classe.objects.create(tenant=self.tenant, niveau=niveau,
                                            nom='Géomatique — 1re année')
        self.cible2 = Classe.objects.create(tenant=self.tenant, niveau=niveau,
                                            nom='Électrotechnique — 1re année')
        for i, (nom, coef) in enumerate([('Mathématiques appliquées', 3),
                                         ('Anglais technique', 2),
                                         ('Dessin technique', 3)], 1):
            Matiere.objects.create(tenant=self.tenant, classe=self.source, nom=nom,
                                   coefficient=coef, note_max=20, ordre=i)

    def _copier(self, cibles, ecraser=False):
        return self.client.post(
            f'/api/academique/classes/{self.source.id}/copier-matieres/',
            {'cibles': [str(c.id) for c in cibles], 'ecraser': ecraser},
            format='json')

    def test_les_matieres_arrivent_avec_leurs_coefficients(self):
        r = self._copier([self.cible1, self.cible2])
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data['matieres'], 3)

        for cible in (self.cible1, self.cible2):
            matieres = Matiere.objects.filter(classe=cible).order_by('ordre')
            self.assertEqual(matieres.count(), 3)
            self.assertEqual(
                [(m.nom, float(m.coefficient)) for m in matieres],
                [('Mathématiques appliquées', 3.0), ('Anglais technique', 2.0),
                 ('Dessin technique', 3.0)])

    def test_relancer_ne_cree_aucun_doublon(self):
        self._copier([self.cible1])
        r = self._copier([self.cible1])
        self.assertEqual(Matiere.objects.filter(classe=self.cible1).count(), 3)
        self.assertEqual(r.data['rapport'][0]['creees'], 0)
        self.assertEqual(r.data['rapport'][0]['inchangees'], 3)

    def test_une_matiere_propre_a_la_cible_est_preservee(self):
        Matiere.objects.create(tenant=self.tenant, classe=self.cible1,
                               nom='Photogrammétrie', coefficient=4, note_max=20)
        self._copier([self.cible1])
        noms = set(Matiere.objects.filter(classe=self.cible1)
                   .values_list('nom', flat=True))
        self.assertIn('Photogrammétrie', noms)
        self.assertEqual(len(noms), 4)

    def test_ecraser_aligne_un_coefficient_divergent(self):
        Matiere.objects.create(tenant=self.tenant, classe=self.cible1,
                               nom='Anglais technique', coefficient=1, note_max=20)
        self._copier([self.cible1], ecraser=True)
        m = Matiere.objects.get(classe=self.cible1, nom='Anglais technique')
        self.assertEqual(float(m.coefficient), 2.0)

    def test_sans_ecraser_le_coefficient_de_la_cible_est_respecte(self):
        Matiere.objects.create(tenant=self.tenant, classe=self.cible1,
                               nom='Anglais technique', coefficient=1, note_max=20)
        self._copier([self.cible1], ecraser=False)
        m = Matiere.objects.get(classe=self.cible1, nom='Anglais technique')
        self.assertEqual(float(m.coefficient), 1.0)

    def test_la_classe_source_ne_se_recopie_pas_sur_elle_meme(self):
        r = self._copier([self.source])
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Matiere.objects.filter(classe=self.source).count(), 3)
