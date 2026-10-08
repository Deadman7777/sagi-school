"""Garde-fou : le même enfant inscrit deux fois par erreur (08/10/2026).

La seconde saisie est refusée en nommant la fiche existante — date, heure et
auteur de l'enregistrement — sauf confirmation explicite (vrai homonyme).
"""
import datetime

from rest_framework.test import APITestCase

from apps.eleves.doublons import cle_nom
from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant
from apps.users.models import User

RENTREE = datetime.date(2026, 10, 1)


class DoublonsEleveTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Les Pins', code_etablissement='PIN')
        self.user = User.objects.create_user('a@pins.sn', 'x', nom='Aïssatou NDAW',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(tenant=self.tenant, annee_scolaire='2026-2027',
                                          nb_mensualites=9, date_debut=RENTREE,
                                          date_fin=datetime.date(2027, 6, 30))
        self.section = Section.objects.create(tenant=self.tenant, nom='CP', frais_mensualite=20000)

    def _fiche(self, **extra):
        corps = {'nom_complet': 'Awa NDIAYE', 'section': str(self.section.id), 'genre': 'F',
                 'date_naissance': '2019-03-12', 'lieu_naissance': 'Dakar',
                 'date_inscription': '2026-10-01', 'nom_mere': 'Fatou SOW',
                 'telephone_mere': '771234567'}
        corps.update(extra)
        return self.client.post('/api/eleves/', corps, format='json')

    def test_cle_nom_ignore_casse_accents_espaces_et_ordre(self):
        self.assertEqual(cle_nom('Àwa  NDIAYE'), cle_nom('ndiaye awa'))
        self.assertNotEqual(cle_nom('Awa NDIAYE'), cle_nom('Awa NDIAYE FALL'))

    def test_seconde_saisie_refusee_avec_date_heure_et_auteur(self):
        r = self._fiche()
        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(Eleve.objects.get(id=r.json()['id']).cree_par, 'Aïssatou NDAW')

        r2 = self._fiche(nom_complet='ndiaye  Awa')
        self.assertEqual(r2.status_code, 409, r2.content[:300])
        corps = r2.json()
        self.assertEqual(corps['code'], 'DOUBLON')
        d = corps['doublons'][0]
        self.assertEqual((d['certitude'], d['meme_exercice'], d['cree_par']),
                         ('CERTAIN', True, 'Aïssatou NDAW'))
        self.assertRegex(d['cree_le_texte'], r'^\d\d/\d\d/\d{4} à \d\d:\d\d$')
        self.assertIn(d['cree_le_texte'], corps['error'])
        self.assertIn('Aïssatou NDAW', corps['error'])
        self.assertEqual(Eleve.objects.filter(tenant=self.tenant).count(), 1)

    def test_confirmation_explicite_cree_l_homonyme(self):
        self._fiche()
        r = self._fiche(forcer_doublon=True)
        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(Eleve.objects.filter(tenant=self.tenant).count(), 2)

    def test_homonyme_ne_le_meme_jour_mais_autre_date_sans_parent_commun(self):
        self._fiche()
        r = self._fiche(date_naissance='2018-01-05', telephone_mere='781112233')
        self.assertEqual(r.status_code, 201, r.content[:300])

    def test_date_mal_saisie_mais_meme_parent_est_probable(self):
        self._fiche()
        r = self._fiche(date_naissance='2019-12-03', telephone_mere='+221 77 123 45 67')
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()['doublons'][0]['certitude'], 'PROBABLE')

    def test_fiche_d_un_autre_exercice_signalee_sans_bloquer(self):
        ancien = Exercice.objects.create(tenant=self.tenant, annee_scolaire='2025-2026',
                                         nb_mensualites=9, cloture=True,
                                         date_debut=datetime.date(2025, 10, 1),
                                         date_fin=datetime.date(2026, 6, 30))
        Eleve.objects.create(tenant=self.tenant, exercice=ancien, section=self.section,
                             nom_complet='Awa NDIAYE', date_naissance=datetime.date(2019, 3, 12))
        verif = self.client.get('/api/eleves/doublons/', {'nom_complet': 'awa ndiaye',
                                                          'date_naissance': '2019-03-12'}).json()
        self.assertEqual(len(verif['doublons']), 1)
        self.assertFalse(verif['doublons'][0]['meme_exercice'])
        self.assertEqual(self._fiche().status_code, 201)

    def test_verification_exclut_la_fiche_en_cours_de_modification(self):
        eleve_id = self._fiche().json()['id']
        verif = self.client.get('/api/eleves/doublons/', {'nom_complet': 'Awa NDIAYE',
                                                          'date_naissance': '2019-03-12',
                                                          'exclure': eleve_id}).json()
        self.assertEqual(verif['doublons'], [])

    def test_autre_ecole_invisible(self):
        autre = Tenant.objects.create(nom='Autre', code_etablissement='AUT')
        ex = Exercice.objects.create(tenant=autre, annee_scolaire='2026-2027', nb_mensualites=9,
                                     date_debut=RENTREE, date_fin=datetime.date(2027, 6, 30))
        Eleve.objects.create(tenant=autre, exercice=ex, nom_complet='Awa NDIAYE',
                             date_naissance=datetime.date(2019, 3, 12))
        self.assertEqual(self._fiche().status_code, 201)
