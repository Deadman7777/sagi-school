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


class BaseFamille(APITestCase):
    """Décor commun aux deux lots. Sans test : une classe de tests dont on
    hérite rejoue toute sa batterie dans chaque descendante."""

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


class FamilleTest(BaseFamille):
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


class RegroupementTest(BaseFamille):
    """Regrouper l'existant — lot 2.

    Une école qui arrive avec deux mille fiches ne créera pas ses familles une
    par une. On lui propose les groupes déduits des numéros de parents ; elle
    valide.

    Ce que ces tests rendent impossible :
    - un rapprochement sur le seul nom (tous les NDIAYE d'une école) ;
    - une fratrie coupée en deux parce que c'est la mère qui relie trois
      enfants et le père les deux autres ;
    - un regroupement qui déplace un élève déjà rattaché à une autre famille ;
    - une fratrie qui se défait au passage à l'année suivante.
    """

    def _fratrie(self, noms, **contacts):
        return [self._eleve(nom, **contacts) for nom in noms]

    def test_le_meme_numero_rapproche_la_fratrie(self):
        from apps.eleves.familles import fratries_probables

        self._fratrie(['Awa NDIAYE', 'Moussa NDIAYE', 'Fatou NDIAYE'],
                      nom_pere='Ousmane NDIAYE', telephone_pere='77 123 45 67')
        self._eleve('Sans lien DIOP', nom_pere='Modou DIOP', telephone_pere='76 000 11 22')

        groupes = fratries_probables(self.tenant, self.ex)
        self.assertEqual(len(groupes), 1)
        self.assertEqual(groupes[0]['nb'], 3)
        self.assertEqual(groupes[0]['confiance'], 'SURE')
        self.assertEqual(groupes[0]['nom_propose'], 'Famille NDIAYE')
        self.assertEqual(groupes[0]['contact']['nom'], 'Ousmane NDIAYE')

    def test_le_numero_est_reconnu_quelle_que_soit_son_ecriture(self):
        """« +221 77 123 45 67 », « 77-123-45-67 » et « 77 123 45 67 » sont le
        même numéro. Comparer les chaînes telles quelles ne rapprochait rien."""
        from apps.eleves.familles import cle_telephone, fratries_probables

        self.assertEqual(cle_telephone('+221 77 123 45 67'), cle_telephone('77 123 45 67'))
        self.assertEqual(cle_telephone('77-123-45-67'), cle_telephone('771234567'))
        # Deux numéros sur la fiche : c'est le premier qui compte.
        self.assertEqual(cle_telephone('77 123 45 67 / 76 011 82 29'),
                         cle_telephone('77 123 45 67'))
        # Un reliquat de saisie n'est pas un numéro : rapprocher là-dessus
        # fusionnerait des familles sans aucun lien.
        self.assertIsNone(cle_telephone('77'))
        self.assertIsNone(cle_telephone('----'))

        self._eleve('Awa NDIAYE', nom_pere='Ousmane NDIAYE', telephone_pere='+221 77 123 45 67')
        self._eleve('Moussa NDIAYE', nom_pere='Ousmane NDIAYE', telephone_pere='77-123-45-67')
        groupes = fratries_probables(self.tenant, self.ex)
        self.assertEqual(len(groupes), 1)
        self.assertEqual(groupes[0]['nb'], 2)

    def test_la_fratrie_reliee_par_deux_parents_reste_entiere(self):
        """Le père relie deux enfants, la mère trois, et le père est aussi sur
        l'une des trois fiches : c'est UN foyer, pas deux."""
        from apps.eleves.familles import fratries_probables

        self._eleve('Awa NDIAYE', nom_pere='Ousmane NDIAYE', telephone_pere='77 123 45 67')
        self._eleve('Moussa NDIAYE', nom_pere='Ousmane NDIAYE', telephone_pere='77 123 45 67')
        self._eleve('Fatou NDIAYE', nom_pere='Ousmane NDIAYE', telephone_pere='77 123 45 67',
                    nom_mere='Awa DIOP', telephone_mere='76 555 22 11')
        self._eleve('Ibrahima NDIAYE', nom_mere='Awa DIOP', telephone_mere='76 555 22 11')
        self._eleve('Aminata NDIAYE', nom_mere='Awa DIOP', telephone_mere='76 555 22 11')

        groupes = fratries_probables(self.tenant, self.ex)
        self.assertEqual(len(groupes), 1)
        self.assertEqual(groupes[0]['nb'], 5)

    def test_le_seul_nom_ne_rapproche_personne(self):
        """Sans numéro commun, deux NDIAYE restent deux familles.

        Rapprocher sur le patronyme constituerait, dans une école sénégalaise,
        une famille de quarante enfants sans lien entre eux.
        """
        from apps.eleves.familles import fratries_probables

        self._eleve('Awa NDIAYE', nom_pere='Ousmane NDIAYE', telephone_pere='77 111 11 11')
        self._eleve('Moussa NDIAYE', nom_pere='Cheikh NDIAYE', telephone_pere='77 222 22 22')
        self.assertEqual(fratries_probables(self.tenant, self.ex), [])

    def test_noms_differents_sur_un_meme_numero_demandent_verification(self):
        from apps.eleves.familles import fratries_probables

        self._eleve('Awa NDIAYE', nom_tuteur='Oncle SECK', telephone_tuteur='77 123 45 67')
        self._eleve('Moussa FALL', nom_tuteur='Oncle SECK', telephone_tuteur='77 123 45 67')
        groupe = fratries_probables(self.tenant, self.ex)[0]
        self.assertEqual(groupe['confiance'], 'A_VERIFIER')
        self.assertEqual(groupe['noms_famille'], ['FALL', 'NDIAYE'])

    def test_un_eleve_deja_rattache_n_est_plus_propose(self):
        from apps.eleves.familles import fratries_probables

        famille = self._famille()
        self._eleve('Awa NDIAYE', famille=famille,
                    nom_pere='Ousmane NDIAYE', telephone_pere='77 123 45 67')
        self._eleve('Moussa NDIAYE', nom_pere='Ousmane NDIAYE', telephone_pere='77 123 45 67')
        # Un seul élève libre sur ce numéro : plus de groupe à proposer.
        self.assertEqual(fratries_probables(self.tenant, self.ex), [])

    # ── Validation par l'école ───────────────────────────────────────────
    def test_l_ecole_valide_et_les_familles_sont_creees(self):
        enfants = self._fratrie(['Awa NDIAYE', 'Moussa NDIAYE', 'Fatou NDIAYE'],
                                nom_pere='Ousmane NDIAYE', telephone_pere='77 123 45 67')
        r = self.client.get('/api/eleves/familles/fratries-probables/')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(r.data['nb'], 1)
        self.assertEqual(r.data['nb_eleves'], 3)

        groupe = r.data['groupes'][0]
        r = self.client.post('/api/eleves/familles/regrouper/', {'groupes': [{
            'nom': groupe['nom_propose'],
            'contact': groupe['contact'],
            'eleve_ids': [e['id'] for e in groupe['eleves']]}]}, format='json')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(r.data['nb_familles'], 1)
        self.assertEqual(r.data['nb_eleves'], 3)

        famille = Famille.objects.get(nom='Famille NDIAYE')
        self.assertEqual(famille.eleves.count(), 3)
        self.assertEqual(famille.responsable_principal.nom, 'Ousmane NDIAYE')
        self.assertEqual(famille.responsable_principal.telephone, '77 123 45 67')
        # Et le contact des fiches suit, sans qu'on ait touché aux élèves.
        for enfant in enfants:
            enfant.refresh_from_db()
            self.assertEqual(contact_effectif(enfant)['origine'], 'FAMILLE')

    def test_revalider_deux_fois_ne_deplace_personne(self):
        """L'écran peut être rechargé et revalidé : un élève déjà rattaché est
        ignoré, jamais déplacé — sinon une correction faite à la main entre
        deux passages serait défaite en silence."""
        deja = self._famille('Famille corrigée à la main')
        garde = self._eleve('Awa NDIAYE', famille=deja,
                            nom_pere='Ousmane NDIAYE', telephone_pere='77 123 45 67')
        libre = self._eleve('Moussa NDIAYE',
                            nom_pere='Ousmane NDIAYE', telephone_pere='77 123 45 67')

        r = self.client.post('/api/eleves/familles/regrouper/', {'groupes': [{
            'nom': 'Famille NDIAYE',
            'contact': {'nom': 'Ousmane NDIAYE', 'telephone': '77 123 45 67', 'lien': 'PERE'},
            'eleve_ids': [str(garde.id), str(libre.id)]}]}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['nb_eleves'], 1)
        self.assertEqual(r.data['nb_ignores'], 1)
        garde.refresh_from_db()
        self.assertEqual(garde.famille_id, deja.id)

    def test_un_groupe_entierement_deja_rattache_ne_cree_pas_de_famille_vide(self):
        deja = self._famille()
        eleve = self._eleve('Awa NDIAYE', famille=deja)
        avant = Famille.objects.count()
        r = self.client.post('/api/eleves/familles/regrouper/', {'groupes': [
            {'nom': 'Famille NDIAYE', 'eleve_ids': [str(eleve.id)]}]}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Famille.objects.count(), avant)

    # ── D'une année sur l'autre ──────────────────────────────────────────
    def test_la_famille_suit_l_eleve_a_la_reinscription(self):
        """Sans cela, toute la fratrie se défait à chaque passage d'exercice et
        l'école doit regrouper de nouveau chaque année."""
        from apps.paiements.report_reliquats import reporter_reliquats

        famille = self._famille()
        self._eleve('Awa NDIAYE', famille=famille)
        suivant = Exercice.objects.create(tenant=self.tenant, annee_scolaire='2027',
                                          date_debut=datetime.date(2027, 1, 1),
                                          date_fin=datetime.date(2027, 12, 31))
        reporter_reliquats(self.ex, suivant)
        nouvelle = Eleve.objects.get(exercice=suivant, nom_complet='Awa NDIAYE')
        self.assertEqual(nouvelle.famille_id, famille.id)

    # ── Import Excel ─────────────────────────────────────────────────────
    def test_la_colonne_famille_de_l_import_regroupe_les_freres(self):
        """Deux lignes portant le même libellé entrent dans le même foyer —
        une seule famille créée, pas une par ligne."""
        from apps.eleves.views import EleveViewSet

        cache = {}
        premier = EleveViewSet._famille_import(
            self.tenant, 'Famille NDIAYE', cache,
            {'nom_pere': 'Ousmane NDIAYE', 'telephone_pere': '77 123 45 67'})
        second = EleveViewSet._famille_import(
            self.tenant, 'Famille NDIAYE', cache, {'nom_pere': 'Ousmane NDIAYE'})
        self.assertEqual(premier.id, second.id)
        self.assertEqual(premier.responsable_principal.telephone, '77 123 45 67')

        # Un deuxième import qui cite le code déjà attribué retombe sur la
        # même famille : sinon la fratrie se couperait en deux.
        encore = EleveViewSet._famille_import(self.tenant, premier.code, {}, {})
        self.assertEqual(encore.id, premier.id)
        # Colonne vide : rien n'est créé, l'école regroupera d'un clic.
        self.assertIsNone(EleveViewSet._famille_import(self.tenant, '', {}, {}))


class RappelParFamilleTest(BaseFamille):
    """Un rappel par famille — lot 5.

    Un père de cinq enfants recevait cinq SMS le même jour, sur le même
    numéro. L'école payait cinq segments et passait pour désorganisée auprès
    de la famille qu'elle relance.

    Ce que ces tests rendent impossible :
    - plusieurs messages au même parent pour la même campagne ;
    - un compteur qui annonce des envois par élève alors que l'école paie
      des messages ;
    - « vos 1 enfants » quand un seul enfant de la fratrie est en retard ;
    - un rappel groupé sur des élèves que l'école n'a jamais reconnus comme
      une même famille.
    """

    def setUp(self):
        super().setUp()
        self.tenant.rappel_actif = True
        self.tenant.rappel_jour_debut = 1
        self.tenant.rappel_jour_limite = 28
        self.tenant.save()
        self.jour = datetime.date(2026, 12, 15)

    def _en_retard(self, nom, famille=None, **kwargs):
        # Section à 15 000 F/mois, aucun paiement : l'élève doit tout.
        return self._eleve(nom, famille=famille, **kwargs)

    def test_une_fratrie_ne_recoit_qu_un_message(self):
        from apps.eleves.rappels import envoyer_rappels

        famille = self._famille()
        for nom in ('Awa NDIAYE', 'Moussa NDIAYE', 'Fatou NDIAYE',
                    'Ibrahima NDIAYE', 'Aminata NDIAYE'):
            self._en_retard(nom, famille=famille)

        rapport = envoyer_rappels(self.tenant, self.ex, today=self.jour)
        # Un seul message simulé, pour cinq élèves.
        self.assertEqual(rapport['simules'], 1)
        self.assertEqual(rapport['nb_eleves'], 5)
        # Mais cinq traces : le verrou mensuel et l'historique restent par
        # élève.
        from apps.eleves.models import RappelEnvoye
        self.assertEqual(RappelEnvoye.objects.count(), 5)
        self.assertEqual(
            RappelEnvoye.objects.values_list('destinataire', flat=True).distinct().count(), 1)

    def test_le_message_parle_de_la_fratrie_et_du_total(self):
        from apps.eleves.rappels import composer_message, groupes_a_rappeler

        famille = self._famille()
        for nom in ('Awa NDIAYE', 'Moussa NDIAYE', 'Fatou NDIAYE'):
            self._en_retard(nom, famille=famille)
        groupe = groupes_a_rappeler(self.tenant, self.ex, today=self.jour)['groupes'][0]
        message = composer_message(self.tenant, groupe, self.jour)
        self.assertIn('vos 3 enfants', message)
        # Le montant du message est celui de la FAMILLE, pas d'un enfant.
        self.assertEqual(groupe['total_exigible'],
                         round(sum(l['total_exigible'] for l in groupe['eleves']), 2))

    def test_un_seul_enfant_en_retard_garde_un_message_nominatif(self):
        from apps.eleves.rappels import composer_message, groupes_a_rappeler

        famille = self._famille()
        self._en_retard('Awa NDIAYE', famille=famille)
        # Sa sœur est à jour : elle ne doit rien, donc elle n'est pas relancée.
        soeur = self._eleve('Fatou NDIAYE', famille=famille)
        Paiement.objects.create(tenant=self.tenant, exercice=self.ex, eleve=soeur,
                                montant_inscription=25000, montant_mensualite=180000)

        groupe = groupes_a_rappeler(self.tenant, self.ex, today=self.jour)['groupes'][0]
        self.assertEqual(groupe['nb_eleves'], 1)
        message = composer_message(self.tenant, groupe, self.jour)
        self.assertIn('Awa NDIAYE', message)
        self.assertNotIn('enfants', message)

    def test_sans_famille_chacun_recoit_son_message(self):
        """Deux élèves qui partagent un numéro mais qu'aucune école n'a
        reconnus comme une fratrie restent deux messages : deux foyers peuvent
        se partager un téléphone, et leur écrire « vos 2 enfants » serait faux.
        """
        from apps.eleves.rappels import groupes_a_rappeler

        self._en_retard('Awa NDIAYE', telephone_pere='77 123 45 67')
        self._en_retard('Moussa FALL', telephone_pere='77 123 45 67')
        groupes = groupes_a_rappeler(self.tenant, self.ex, today=self.jour)
        self.assertEqual(groupes['nb_messages'], 2)

    def test_un_enfant_deja_prevenu_ne_relance_pas_toute_la_fratrie(self):
        from apps.eleves.models import RappelEnvoye
        from apps.eleves.rappels import envoyer_rappels

        famille = self._famille()
        premier = self._en_retard('Awa NDIAYE', famille=famille)
        RappelEnvoye.objects.create(tenant=self.tenant, eleve=premier, periode='2026-12',
                                    canal='SMS', destinataire='770000001',
                                    message='déjà parti', statut='SIMULE')
        self._en_retard('Moussa NDIAYE', famille=famille)

        rapport = envoyer_rappels(self.tenant, self.ex, today=self.jour)
        self.assertEqual(rapport['simules'], 1)
        self.assertEqual(rapport['nb_eleves'], 1)      # le frère seul
        self.assertEqual(rapport['ignores'], 1)
        # Et rien n'est reparti pour l'aîné.
        self.assertEqual(RappelEnvoye.objects.filter(eleve=premier).count(), 1)

    def test_renvoyer_le_meme_jour_ne_renvoie_rien(self):
        from apps.eleves.rappels import envoyer_rappels

        famille = self._famille()
        for nom in ('Awa NDIAYE', 'Moussa NDIAYE'):
            self._en_retard(nom, famille=famille)
        envoyer_rappels(self.tenant, self.ex, today=self.jour)
        second = envoyer_rappels(self.tenant, self.ex, today=self.jour)
        self.assertEqual(second['simules'], 0)
        self.assertEqual(second['ignores'], 2)

    def test_l_ecran_annonce_les_messages_et_les_eleves(self):
        famille = self._famille()
        for nom in ('Awa NDIAYE', 'Moussa NDIAYE', 'Fatou NDIAYE'):
            self._en_retard(nom, famille=famille)
        self._en_retard('Seul DIOP', telephone_pere='76 000 00 00')

        r = self.client.get('/api/eleves/liste/rappels/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['nb'], 4)            # quatre élèves en retard
        self.assertEqual(r.data['nb_messages'], 2)   # mais deux SMS à payer
