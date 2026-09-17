"""Fiche élève : parents (profession, résidence), attitudes, champs libres de l'école,
et modules ouverts utilisateur par utilisateur.

Ce que ces tests rendent impossible :
- perdre une réponse à un champ de l'école en modifiant autre chose sur la fiche ;
- enregistrer n'importe quoi dans un champ typé (nombre, date, liste) ;
- laisser le personnel définir les champs ou s'ouvrir des modules lui-même ;
- un module ouvert à un utilisateur au-delà de ce que la licence permet.
"""
import datetime

from rest_framework.test import APITestCase

from apps.eleves.models import ChampFiche, Eleve, Section
from apps.licences.models import Licence
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant
from apps.users.models import User


class Base(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='École Les Palmiers', code_etablissement='PAL')
        self.admin = User.objects.create_user('dir@palmiers.sn', 'x', nom='Directeur',
                                              role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.admin)
        today = datetime.date.today()
        self.ex = Exercice.objects.create(tenant=self.tenant, annee_scolaire='2026-2027', nb_mensualites=10,
                                          date_debut=datetime.date(today.year, today.month, 1),
                                          date_fin=datetime.date(today.year + 1, today.month, 1)
                                          - datetime.timedelta(days=1))
        self.section = Section.objects.create(tenant=self.tenant, nom='CI', frais_mensualite=20000)

    def _champ(self, libelle, **extra):
        data = {'libelle': libelle, 'type_champ': 'TEXTE', 'groupe': 'AUTRE'}
        data.update(extra)
        r = self.client.post('/api/eleves/champs/', data, format='json')
        self.assertEqual(r.status_code, 201, r.content[:300])
        return r.data

    def _eleve(self, **extra):
        data = {'nom_complet': 'Awa NDIAYE', 'section': str(self.section.id), 'genre': 'F'}
        data.update(extra)
        r = self.client.post('/api/eleves/', data, format='json')
        return r


class FicheEtendueTest(Base):
    def test_profession_residence_et_attitudes_enregistrees(self):
        r = self._eleve(nom_pere='Ousmane NDIAYE', profession_pere='Menuisier',
                        residence_pere='Guédiawaye', nom_mere='Fatou SOW',
                        profession_mere='Commerçante', residence_mere='Rufisque',
                        attitudes_particulieres='Très timide, ne mange pas seule.')
        self.assertEqual(r.status_code, 201, r.content[:300])
        e = Eleve.objects.get(pk=r.data['id'])
        self.assertEqual((e.profession_pere, e.residence_mere), ('Menuisier', 'Rufisque'))
        self.assertIn('timide', e.attitudes_particulieres)

    def test_la_fiche_pdf_porte_les_nouvelles_informations(self):
        champ = self._champ('Quartier')
        r = self._eleve(profession_pere='Menuisier', residence_pere='Guédiawaye',
                        attitudes_particulieres='Ne supporte pas le bruit.',
                        champs_perso={champ['id']: 'Keury Souf'})
        pdf = self.client.get(f"/api/eleves/{r.data['id']}/fiche-pdf/")
        self.assertEqual(pdf.status_code, 200, pdf.content[:200])
        self.assertTrue(pdf.content.startswith(b'%PDF'))

        from django.template.loader import render_to_string
        from apps.eleves.views import champs_perso_pour_pdf
        e = Eleve.objects.get(pk=r.data['id'])
        html = render_to_string('pdf/fiche_eleve.html', {
            'tenant': self.tenant, 'eleve': e, 'section_nom': 'CI', 'exercice': self.ex,
            'date_edition': datetime.datetime.now(), 'total_theorique': 0, 'montant_pec_annuel': 0,
            'total_attendu': 0, 'total_paye': 0, 'reste': 0, 'motif_pec': '', 'type_pec': '',
            'champs_perso': champs_perso_pour_pdf(self.tenant, e)})
        for attendu in ('Menuisier', 'Guédiawaye', 'Ne supporte pas le bruit.', 'Quartier', 'Keury Souf'):
            self.assertIn(attendu, html)


class ChampsLibresTest(Base):
    def test_types_valides_et_refus(self):
        nombre = self._champ('Nombre de frères', type_champ='NOMBRE')
        liste = self._champ('Transport', type_champ='LISTE', options=['Navette', 'À pied'])
        oui_non = self._champ('Cantine', type_champ='OUI_NON')
        date_champ = self._champ('Date du vaccin', type_champ='DATE')
        r = self._eleve(champs_perso={nombre['id']: '3', liste['id']: 'Navette',
                                      oui_non['id']: True, date_champ['id']: '2026-01-15'})
        self.assertEqual(r.status_code, 201, r.content[:300])
        valeurs = Eleve.objects.get(pk=r.data['id']).champs_perso
        self.assertEqual(valeurs[nombre['id']], 3.0)
        self.assertEqual(valeurs[date_champ['id']], '2026-01-15')
        self.assertIs(valeurs[oui_non['id']], True)

        for mauvais in ({nombre['id']: 'beaucoup'}, {liste['id']: 'Charrette'},
                        {date_champ['id']: '15 janvier'}):
            r = self._eleve(nom_complet='Test', champs_perso=mauvais)
            self.assertEqual(r.status_code, 400, mauvais)

    def test_liste_sans_choix_refusee(self):
        r = self.client.post('/api/eleves/champs/', {'libelle': 'Transport', 'type_champ': 'LISTE',
                                                     'options': ['Navette']}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_champ_obligatoire_exige_a_la_creation(self):
        champ = self._champ('Quartier', obligatoire=True)
        self.assertEqual(self._eleve().status_code, 400)
        self.assertEqual(self._eleve(champs_perso={champ['id']: 'Keury Souf'}).status_code, 201)

    def test_modifier_autre_chose_ne_perd_pas_les_reponses(self):
        champ = self._champ('Quartier')
        eleve = self._eleve(champs_perso={champ['id']: 'Keury Souf'}).data
        r = self.client.patch(f"/api/eleves/{eleve['id']}/", {'profession_pere': 'Pêcheur'}, format='json')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(Eleve.objects.get(pk=eleve['id']).champs_perso, {champ['id']: 'Keury Souf'})

    def test_reponse_videe_est_retiree(self):
        champ = self._champ('Quartier')
        eleve = self._eleve(champs_perso={champ['id']: 'Keury Souf'}).data
        self.client.patch(f"/api/eleves/{eleve['id']}/", {'champs_perso': {champ['id']: ''}}, format='json')
        self.assertEqual(Eleve.objects.get(pk=eleve['id']).champs_perso, {})

    def test_nb_renseignes_et_seule_la_direction_definit_les_champs(self):
        champ = self._champ('Quartier')
        self._eleve(champs_perso={champ['id']: 'Keury Souf'})
        reponse = self.client.get('/api/eleves/champs/').data
        liste = reponse['results'] if isinstance(reponse, dict) else reponse
        self.assertEqual(liste[0]['nb_renseignes'], 1)
        scolarite = User.objects.create_user('scol@palmiers.sn', 'x', nom='Scolarité',
                                             role='ADMIN_SCOLARITE', tenant=self.tenant)
        self.client.force_authenticate(scolarite)
        self.assertEqual(self.client.get('/api/eleves/champs/').status_code, 200)   # lecture OK
        self.assertEqual(self.client.post('/api/eleves/champs/', {'libelle': 'X'}, format='json').status_code, 403)
        self.assertEqual(self.client.delete(f"/api/eleves/champs/{champ['id']}/").status_code, 403)


class ModulesParUtilisateurTest(Base):
    def setUp(self):
        super().setUp()
        Licence.objects.create(tenant=self.tenant, cle_licence=Licence.generer_cle('PAL'), type='PRO',
                               statut='ACTIVE', date_debut=datetime.date.today(),
                               date_fin=datetime.date.today() + datetime.timedelta(days=365))

    def test_l_ecole_ouvre_des_modules_a_un_utilisateur(self):
        r = self.client.post('/api/auth/users/', {
            'nom': 'Aïda', 'email': 'aida@palmiers.sn', 'password': 'secret123', 'role': 'LECTEUR',
            'tenant': str(self.tenant.id), 'modules_autorises': ['eleves', 'paiements']}, format='json')
        self.assertEqual(r.status_code, 201, r.content[:300])
        user = User.objects.get(pk=r.data['id'])
        self.assertEqual(user.modules_autorises, ['eleves', 'paiements'])

        from core.permissions import has_module_access
        self.assertTrue(has_module_access(user, 'eleves'))
        self.assertTrue(has_module_access(user, 'dashboard'))     # toujours ouvert
        self.assertFalse(has_module_access(user, 'rh'))

    def test_le_jeton_limite_aux_modules_de_l_utilisateur_sans_depasser_la_licence(self):
        user = User.objects.create_user('aida@palmiers.sn', 'secret123', nom='Aïda', role='LECTEUR',
                                        tenant=self.tenant,
                                        modules_autorises=['eleves', 'rh'])   # rh hors licence PRO
        from apps.users.serializers import CustomTokenSerializer as Jeton
        jeton = Jeton.get_token(user)
        self.assertIn('/eleves', jeton['modules'])
        self.assertNotIn('/rh', jeton['modules'])                  # la licence reste le plafond
        self.assertIn('/parametres', jeton['modules'])
        self.assertTrue(jeton['modules_perso'])

    def test_sans_choix_le_role_fait_foi(self):
        user = User.objects.create_user('rh@palmiers.sn', 'x', nom='RH', role='ADMIN_RH', tenant=self.tenant)
        from core.permissions import has_module_access
        self.assertTrue(has_module_access(user, 'rh'))
        self.assertFalse(has_module_access(user, 'eleves'))
