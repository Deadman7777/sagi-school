"""Tests : sortie posée par erreur, et famille reprise à l'inscription.

1. Un élève passé « Transféré » par erreur partait chez les anciens. La
   réintégration exige un retour POSTÉRIEUR à la sortie : le jour même, elle
   refusait, et l'école le réinscrivait en double. L'annulation de sortie
   rend la fiche telle qu'avant, sans rien retirer.

2. Un frère ou une sœur arrive : choisir la famille reprend les coordonnées
   des parents au lieu de les faire retaper.
"""
import datetime

from rest_framework.test import APITestCase

from apps.eleves.familles import coordonnees_nouvel_enfant
from apps.eleves.models import Eleve, Famille, MouvementEleve, ResponsableFamille, Section
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User


class Base(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Collège Test', code_etablissement='CLT')
        user = User.objects.create_user('d@c.sn', 'x', nom='Directeur',
                                        role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(user)
        aujourdhui = datetime.date.today()
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026-2027', nb_mensualites=9,
            date_debut=aujourdhui - datetime.timedelta(days=60),
            date_fin=aujourdhui + datetime.timedelta(days=300))
        self.section = Section.objects.create(tenant=self.tenant, nom='CM2',
                                              frais_inscription=20000, frais_mensualite=15000)


class AnnulationSortieTest(Base):
    def setUp(self):
        super().setUp()
        self.eleve = Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, section=self.section, nom_complet='Awa NDIAYE',
            statut='INSCRIT', date_inscription=self.ex.date_debut)
        Paiement.objects.create(tenant=self.tenant, exercice=self.ex, eleve=self.eleve,
                                no_piece='REC-0001', mode_paiement='ESPECE',
                                montant_mensualite=15000, mois_regles=[self.ex.date_debut.month],
                                statut='ACTIF')
        r = self.client.patch(f'/api/eleves/{self.eleve.id}/', {'statut': 'TRANSFERE'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.du_avant = None

    def _annuler(self, motif='Transféré coché par erreur'):
        return self.client.post(f'/api/eleves/{self.eleve.id}/annuler-sortie/',
                                {'motif': motif}, format='json')

    def test_la_reintegration_refuse_le_jour_meme_et_oriente(self):
        r = self.client.get(f'/api/eleves/{self.eleve.id}/reintegration/',
                            {'date_retour': datetime.date.today().isoformat()})
        self.assertFalse(r.data['possible'])
        self.assertIn("jamais parti", r.data['error'])

    def test_annuler_rend_l_eleve_present_sans_rien_retirer(self):
        mois_avant = list(self.eleve.mois_dus)
        r = self._annuler()
        self.assertEqual(r.status_code, 200, r.data)
        self.eleve.refresh_from_db()
        self.assertEqual(self.eleve.statut, 'INSCRIT')
        self.assertIsNone(self.eleve.date_sortie)
        self.assertEqual(self.eleve.mois_dus, mois_avant)
        self.assertEqual(self.eleve.nb_mensualites_dues, 9)
        self.assertEqual(self.eleve.paiements.filter(statut='ACTIF').count(), 1)
        # Aucune fiche en double.
        self.assertEqual(Eleve.objects.filter(tenant=self.tenant).count(), 1)
        # Revenu dans la liste des élèves.
        ids = [e['id'] for e in (lambda d: d.get('results', d))(self.client.get('/api/eleves/').data)]
        self.assertIn(str(self.eleve.id), ids)

    def test_la_sortie_annulee_reste_tracee(self):
        self._annuler()
        types = list(MouvementEleve.objects.filter(eleve=self.eleve)
                     .values_list('type_mouvement', flat=True))
        self.assertIn('SORTIE', types)
        self.assertIn('ANNULATION', types)

    def test_motif_obligatoire_et_eleve_deja_present(self):
        self.assertEqual(self._annuler(motif='  ').status_code, 400)
        self.assertEqual(self._annuler().status_code, 200)
        r = self._annuler()
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data['code'], 'DEJA_PRESENT')

    def test_exercice_cloture_refuse(self):
        self.ex.cloture = True
        self.ex.save()
        r = self._annuler()
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data['code'], 'EXERCICE')


class FamilleNouvelInscritTest(Base):
    def setUp(self):
        super().setUp()
        self.famille = Famille.objects.create(tenant=self.tenant, nom='Famille NDIAYE',
                                              adresse='Keur Massar')
        ResponsableFamille.objects.create(tenant=self.tenant, famille=self.famille, nom='Moussa NDIAYE',
                                          lien='PERE', telephone='771234567', profession='Commerçant',
                                          principal=True)
        ResponsableFamille.objects.create(tenant=self.tenant, famille=self.famille, nom='Fatou SALL',
                                          lien='MERE', telephone='781234567')

    def test_les_responsables_remplissent_pere_et_mere(self):
        c = coordonnees_nouvel_enfant(self.famille)
        self.assertEqual((c['nom_pere'], c['telephone_pere'], c['profession_pere']),
                         ('Moussa NDIAYE', '771234567', 'Commerçant'))
        self.assertEqual((c['nom_mere'], c['telephone_mere']), ('Fatou SALL', '781234567'))
        self.assertEqual(c['adresse'], 'Keur Massar')

    def test_la_fiche_d_un_aine_complete_ce_qui_manque(self):
        Eleve.objects.create(tenant=self.tenant, exercice=self.ex, section=self.section,
                             famille=self.famille, nom_complet='Aîné NDIAYE',
                             nom_tuteur='Oncle Ibrahima', telephone_tuteur='701112233',
                             lien_tuteur='Oncle', residence_mere='Pikine')
        c = coordonnees_nouvel_enfant(self.famille)
        self.assertEqual(c['nom_pere'], 'Moussa NDIAYE')       # la famille prime
        self.assertEqual(c['nom_tuteur'], 'Oncle Ibrahima')    # repli sur l'aîné
        self.assertEqual(c['residence_mere'], 'Pikine')

    def test_famille_sans_responsable_reprend_l_aine(self):
        f = Famille.objects.create(tenant=self.tenant, nom='Famille FALL')
        Eleve.objects.create(tenant=self.tenant, exercice=self.ex, section=self.section, famille=f,
                             nom_complet='Aîné FALL', nom_pere='Abdou FALL', telephone_pere='760000000')
        r = self.client.get(f'/api/eleves/familles/{f.id}/coordonnees/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['nom_pere'], 'Abdou FALL')

    def test_le_nouvel_inscrit_est_rattache_a_la_famille(self):
        c = self.client.get(f'/api/eleves/familles/{self.famille.id}/coordonnees/').data
        data = {'nom_complet': 'Cadet NDIAYE', 'section': str(self.section.id), 'genre': 'F',
                'date_naissance': '2018-05-01', 'lieu_naissance': 'Dakar',
                'date_inscription': datetime.date.today().isoformat(),
                'famille': str(self.famille.id), **{k: v for k, v in c.items() if v}}
        r = self.client.post('/api/eleves/', data, format='json')
        self.assertEqual(r.status_code, 201, r.content[:400])
        e = Eleve.objects.get(nom_complet='Cadet NDIAYE')
        self.assertEqual(e.famille_id, self.famille.id)
        self.assertEqual(e.telephone_pere, '771234567')

    def test_une_famille_d_une_autre_ecole_est_introuvable(self):
        autre = Tenant.objects.create(nom='Autre', code_etablissement='AUT')
        f = Famille.objects.create(tenant=autre, nom='Famille étrangère')
        r = self.client.get(f'/api/eleves/familles/{f.id}/coordonnees/')
        self.assertEqual(r.status_code, 404)
