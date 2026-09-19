"""Le foyer payeur d'une fratrie — lot 1 : le groupe et le contact.

Mr NDIAYE a cinq enfants dans l'école. Ses coordonnées étaient saisies cinq
fois, l'école ne savait pas ce que la famille lui devait au total, et les
rappels partaient cinq fois au même numéro.

Ce que ces tests rendent impossible :
- un regroupement qui change un montant (regrouper n'est pas remiser) ;
- deux numéros différents pour le même enfant selon l'écran consulté ;
- une famille sans personne à appeler, ou avec deux « principaux » ;
- un code de famille en doublon quand une deuxième école s'installe ;
- la disparition d'élèves quand on supprime leur famille.
"""
import datetime

from django.db import IntegrityError, transaction
from rest_framework.test import APITestCase

from apps.eleves.familles import contact_effectif, situation_famille
from apps.eleves.models import Eleve, Famille, ResponsableFamille, Section
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User


class FamilleTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='École du Cap', code_etablissement='CAP')
        self.user = User.objects.create_user('dir@cap.sn', 'x', nom='Dir',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.section = Section.objects.create(tenant=self.tenant, nom='Élémentaire',
                                              frais_inscription=25000, frais_mensualite=15000)
        self.ex = Exercice.objects.create(tenant=self.tenant, annee_scolaire='2026',
                                          date_debut=datetime.date(2026, 1, 1),
                                          date_fin=datetime.date(2026, 12, 31))

    def _famille(self, nom='Famille NDIAYE', responsables=(('Ousmane NDIAYE', 'PERE', '770000001'),)):
        famille = Famille.objects.create(tenant=self.tenant, nom=nom)
        for i, (nom_r, lien, tel) in enumerate(responsables):
            ResponsableFamille.objects.create(tenant=self.tenant, famille=famille, nom=nom_r,
                                              lien=lien, telephone=tel, principal=(i == 0))
        return famille

    def _eleve(self, nom, famille=None, **kwargs):
        return Eleve.objects.create(tenant=self.tenant, exercice=self.ex, section=self.section,
                                    nom_complet=nom, famille=famille,
                                    date_inscription=datetime.date(2026, 1, 1), **kwargs)

    # ── Le groupe ────────────────────────────────────────────────────────
    def test_le_code_est_attribue_et_se_suit(self):
        premiere = self._famille('Famille NDIAYE')
        deuxieme = self._famille('Famille FALL')
        self.assertEqual(premiere.code, 'FAM-0001')
        self.assertEqual(deuxieme.code, 'FAM-0002')

    def test_le_code_repart_a_un_dans_chaque_ecole(self):
        """Le code est séquentiel PAR école.

        Un compteur global ferait entrer la première famille d'une nouvelle
        école en collision avec celle d'une école déjà installée — 500 sur la
        toute première saisie du nouveau client.
        """
        autre = Tenant.objects.create(nom='École de Thiès', code_etablissement='THS')
        self._famille('Famille NDIAYE')
        chez_l_autre = Famille.objects.create(tenant=autre, nom='Famille DIOP')
        self.assertEqual(chez_l_autre.code, 'FAM-0001')

    def test_un_seul_responsable_principal(self):
        famille = self._famille()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ResponsableFamille.objects.create(tenant=self.tenant, famille=famille,
                                              nom='Awa NDIAYE', lien='MERE',
                                              telephone='770000002', principal=True)

    def test_l_api_n_accepte_qu_un_principal_et_en_designe_un_a_defaut(self):
        # L'école coche deux fois : on arbitre au lieu de renvoyer une 500.
        r = self.client.post('/api/eleves/familles/', {
            'nom': 'Famille NDIAYE',
            'responsables': [
                {'nom': 'Ousmane NDIAYE', 'lien': 'PERE', 'telephone': '770000001',
                 'principal': True},
                {'nom': 'Awa NDIAYE', 'lien': 'MERE', 'telephone': '770000002',
                 'principal': True},
            ]}, format='json')
        self.assertEqual(r.status_code, 201, r.content[:300])
        famille = Famille.objects.get(id=r.data['id'])
        self.assertEqual(famille.responsables.filter(principal=True).count(), 1)
        self.assertEqual(famille.responsable_principal.nom, 'Ousmane NDIAYE')

        # Personne de coché : le premier saisi devient le contact, sinon la
        # famille est enregistrée sans personne à appeler.
        r = self.client.post('/api/eleves/familles/', {
            'nom': 'Famille FALL',
            'responsables': [{'nom': 'Modou FALL', 'lien': 'PERE', 'telephone': '770000003'}]},
            format='json')
        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(Famille.objects.get(id=r.data['id']).responsable_principal.nom,
                         'Modou FALL')

    # ── Le contact : une seule réponse ───────────────────────────────────
    def test_le_contact_vient_de_la_famille_quand_elle_existe(self):
        famille = self._famille()
        eleve = self._eleve('Awa NDIAYE', famille=famille,
                            nom_pere='Ousmane NDIAYE', telephone_pere='770000009')
        contact = contact_effectif(eleve)
        self.assertEqual(contact['telephone'], '770000001')
        self.assertEqual(contact['origine'], 'FAMILLE')

    def test_sans_famille_le_contact_reste_celui_de_la_fiche(self):
        """Les milliers de fiches jamais regroupées ne doivent rien perdre."""
        eleve = self._eleve('Moussa FALL', nom_tuteur='Oncle FALL',
                            telephone_tuteur='770000004', telephone_pere='770000005')
        contact = contact_effectif(eleve)
        self.assertEqual(contact['telephone'], '770000004')   # le tuteur d'abord
        self.assertEqual(contact['origine'], 'TUTEUR')

    def test_famille_sans_numero_on_retombe_sur_la_fiche(self):
        # Une famille créée sans téléphone ne doit pas rendre l'élève
        # injoignable alors que la fiche porte un numéro.
        famille = self._famille(responsables=(('Ousmane NDIAYE', 'PERE', ''),))
        eleve = self._eleve('Awa NDIAYE', famille=famille, telephone_pere='770000006')
        self.assertEqual(contact_effectif(eleve)['telephone'], '770000006')

    def test_les_rappels_utilisent_le_meme_contact_que_la_fiche(self):
        """Deux écrans, un seul numéro.

        C'est la raison d'être de contact_effectif : tant que chaque écran
        enchaînait « tuteur or père or mère » pour son compte, ajouter la
        famille comme source aurait suffi à les faire diverger.
        """
        from apps.eleves.rappels import eleves_a_rappeler

        famille = self._famille()
        eleve = self._eleve('Awa NDIAYE', famille=famille, telephone_pere='770000009')
        lignes = eleves_a_rappeler(self.tenant, self.ex,
                                   today=datetime.date(2026, 12, 31))['lignes']
        ligne = next(l for l in lignes if l['eleve_id'] == str(eleve.id))
        self.assertEqual(ligne['contact'], contact_effectif(eleve)['telephone'])
        self.assertEqual(ligne['famille_nom'], 'Famille NDIAYE')

    # ── La situation d'ensemble ──────────────────────────────────────────
    def test_la_situation_additionne_les_enfants_sans_rien_recalculer(self):
        famille = self._famille()
        enfants = [self._eleve(nom, famille=famille)
                   for nom in ('Awa NDIAYE', 'Moussa NDIAYE', 'Fatou NDIAYE',
                               'Ibrahima NDIAYE', 'Aminata NDIAYE')]
        Paiement.objects.create(tenant=self.tenant, exercice=self.ex, eleve=enfants[0],
                                montant_inscription=25000)
        situation = situation_famille(famille, self.ex)
        self.assertEqual(situation['nb_enfants'], 5)
        self.assertEqual(situation['total_paye'], 25000)
        # Aucun montant n'est recalculé ici : le total est la somme exacte de
        # ce que les fiches annoncent, et regrouper ne remise rien.
        self.assertEqual(situation['total_attendu'],
                         round(sum(float(e.total_attendu) for e in enfants), 2))
        self.assertEqual(situation['reste_a_payer'],
                         round(sum(float(e.reste_a_payer_global) for e in enfants), 2))

    def test_regrouper_ne_change_aucun_montant(self):
        seul = self._eleve('Awa NDIAYE')
        avant = float(seul.total_attendu)
        famille = self._famille()
        seul.famille = famille
        seul.save()
        self.assertEqual(float(Eleve.objects.get(id=seul.id).total_attendu), avant)

    # ── L'API ────────────────────────────────────────────────────────────
    def test_rattacher_et_detacher_depuis_la_famille(self):
        famille = self._famille()
        enfants = [self._eleve(f'Enfant {i} NDIAYE') for i in range(5)]
        ids = [str(e.id) for e in enfants]

        r = self.client.post(f'/api/eleves/familles/{famille.id}/rattacher/',
                             {'eleve_ids': ids}, format='json')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(r.data['nb'], 5)
        self.assertEqual(Eleve.objects.filter(famille=famille).count(), 5)

        r = self.client.post(f'/api/eleves/familles/{famille.id}/rattacher/',
                             {'eleve_ids': ids[:2], 'detacher': True}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Eleve.objects.filter(famille=famille).count(), 3)

    def test_supprimer_la_famille_ne_supprime_pas_les_eleves(self):
        famille = self._famille()
        self._eleve('Awa NDIAYE', famille=famille)
        r = self.client.delete(f'/api/eleves/familles/{famille.id}/')
        self.assertEqual(r.status_code, 204)
        eleve = Eleve.objects.get(nom_complet='Awa NDIAYE')
        self.assertIsNone(eleve.famille_id)

    def test_une_ecole_ne_voit_pas_les_familles_d_une_autre(self):
        autre = Tenant.objects.create(nom='École de Thiès', code_etablissement='THS')
        Famille.objects.create(tenant=autre, nom='Famille DIOP')
        self._famille('Famille NDIAYE')
        r = self.client.get('/api/eleves/familles/')
        self.assertEqual(r.status_code, 200)
        noms = [f['nom'] for f in (r.data['results'] if 'results' in r.data else r.data)]
        self.assertEqual(noms, ['Famille NDIAYE'])

    def test_la_liste_annonce_le_nombre_d_enfants(self):
        famille = self._famille()
        for i in range(3):
            self._eleve(f'Enfant {i} NDIAYE', famille=famille)
        r = self.client.get('/api/eleves/familles/')
        ligne = (r.data['results'] if 'results' in r.data else r.data)[0]
        self.assertEqual(ligne['nb_enfants'], 3)
        self.assertEqual(ligne['contact']['telephone'], '770000001')
