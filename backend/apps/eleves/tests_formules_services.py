"""Formules horaires de la crèche et frais d'adhésion des services.

Ce que ces tests rendent impossible :
- **réécrire les mois passés** quand un enfant change de formule en cours d'année ;
- **réclamer un kimono deux fois** : l'équipement n'est dû qu'à la première adhésion ;
- **un premier mois payé à l'inscription qui reste dû** sur la fiche ;
- **confondre un kimono payé et une mensualité d'avance** dans l'échéancier.
"""
import datetime

from rest_framework.test import APITestCase

from apps.eleves.echeancier import construire_echeancier, precharger
from apps.eleves.models import Eleve, EleveService, FormuleEleve, FormuleSection, Section, Service
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User

J = datetime.date


class Base(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Complexe Les Étoiles', code_etablissement='ETO')
        self.user = User.objects.create_user('dir@etoiles.sn', 'x', nom='Directeur',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(tenant=self.tenant, annee_scolaire='2026-2027', nb_mensualites=10,
                                          date_debut=J(2026, 10, 1), date_fin=J(2027, 7, 31))
        self.creche = Section.objects.create(tenant=self.tenant, nom='Crèche', frais_inscription=25000,
                                             frais_mensualite=30000)
        self.f13 = FormuleSection.objects.create(tenant=self.tenant, section=self.creche,
                                                 nom='08H-13H', frais_mensualite=30000, ordre=1)
        self.f17 = FormuleSection.objects.create(tenant=self.tenant, section=self.creche,
                                                 nom='08H-17H', frais_mensualite=40000, ordre=2)
        self.f19 = FormuleSection.objects.create(tenant=self.tenant, section=self.creche,
                                                 nom='08H-19H', frais_mensualite=55000, ordre=3)

    def _eleve(self, **extra):
        data = {'nom_complet': 'Fatou SOW', 'section': str(self.creche.id),
                'date_inscription': '2026-10-01', 'genre': 'F'}
        data.update(extra)
        r = self.client.post('/api/eleves/', data, format='json')
        self.assertEqual(r.status_code, 201, r.content[:400])
        return Eleve.objects.get(pk=r.data['id'])

    def _lignes(self, eleve):
        return {l['mois']: l for l in construire_echeancier(Eleve.objects.get(pk=eleve.pk))['lignes']}


class FormulesTest(Base):
    def test_formule_choisie_a_l_inscription_vaut_toute_l_annee(self):
        e = self._eleve(formule=str(self.f17.id))
        lignes = self._lignes(e)
        self.assertEqual({l['du'] for l in lignes.values()}, {40000})
        self.assertEqual(Eleve.objects.get(pk=e.pk).total_attendu, 25000 + 10 * 40000)

    def test_changement_date_ne_touche_pas_les_mois_passes(self):
        e = self._eleve(formule=str(self.f13.id))
        r = self.client.post(f'/api/eleves/{e.id}/changer-formule/',
                             {'formule': str(self.f19.id), 'mois_debut': 1}, format='json')
        self.assertEqual(r.status_code, 200, r.content[:300])
        lignes = self._lignes(e)
        self.assertEqual([lignes[m]['du'] for m in (10, 11, 12)], [30000] * 3)
        self.assertEqual([lignes[m]['du'] for m in (1, 2, 7)], [55000] * 3)
        self.assertEqual(Eleve.objects.get(pk=e.pk).total_attendu, 25000 + 3 * 30000 + 7 * 55000)
        precharge = precharger(Eleve.objects.filter(pk=e.pk)).get()
        self.assertEqual(precharge.total_attendu, Eleve.objects.get(pk=e.pk).total_attendu)
        self.assertEqual([h['nom'] for h in r.data['formules_historique']], ['08H-13H', '08H-19H'])

    def test_le_guichet_montre_le_tarif_de_chaque_mois(self):
        e = self._eleve(formule=str(self.f13.id))
        self.client.post(f'/api/eleves/{e.id}/changer-formule/',
                         {'formule': str(self.f17.id), 'mois_debut': 2}, format='json')
        saisie = self.client.get(f'/api/eleves/{e.id}/saisie-paiement/').data
        par_mois = {m['num']: m['montant'] for m in saisie['mois_ecole']}
        self.assertEqual((par_mois[1], par_mois[2]), (30000, 40000))

    def test_prise_en_charge_plafonnee_au_tarif_du_mois(self):
        e = self._eleve(formule=str(self.f13.id))
        e.pec_mensualite = 35000
        e.save()
        self.client.post(f'/api/eleves/{e.id}/changer-formule/',
                         {'formule': str(self.f19.id), 'mois_debut': 1}, format='json')
        lignes = self._lignes(e)
        self.assertEqual((lignes[10]['du'], lignes[1]['du']), (0, 20000))

    def test_formule_d_une_autre_section_refusee_et_effacee_au_changement_de_section(self):
        autre = Section.objects.create(tenant=self.tenant, nom='CI', frais_mensualite=15000)
        f_ci = FormuleSection.objects.create(tenant=self.tenant, section=autre, nom='Journée', frais_mensualite=20000)
        r = self.client.post('/api/eleves/', {'nom_complet': 'Awa', 'section': str(self.creche.id),
                                              'formule': str(f_ci.id), 'genre': 'F'}, format='json')
        self.assertEqual(r.status_code, 400)
        e = self._eleve(formule=str(self.f17.id))
        r = self.client.patch(f'/api/eleves/{e.id}/', {'section': str(autre.id)}, format='json')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertFalse(FormuleEleve.objects.filter(eleve=e).exists())
        self.assertEqual(self._lignes(e)[10]['du'], 15000)

    def test_section_sans_formule_inchangee(self):
        cm2 = Section.objects.create(tenant=self.tenant, nom='CM2', frais_mensualite=20000)
        e = self._eleve(section=str(cm2.id))
        self.assertEqual(self._lignes(e)[10]['du'], 20000)

    def test_formule_attribuee_ne_se_supprime_pas(self):
        self._eleve(formule=str(self.f17.id))
        self.assertEqual(self.client.delete(f'/api/eleves/formules/{self.f17.id}/').status_code, 409)
        self.assertEqual(self.client.delete(f'/api/eleves/formules/{self.f19.id}/').status_code, 204)


class AdhesionServicesTest(Base):
    def setUp(self):
        super().setUp()
        self.primaire = Section.objects.create(tenant=self.tenant, nom='CE1', frais_inscription=30000,
                                               frais_mensualite=20000)
        r = self.client.post('/api/eleves/services/', {
            'nom': 'Taekwondo', 'montant': 7000, 'periodicite': 'MENSUEL', 'premier_mois_a_inscription': True,
            'composition_adhesion': [{'libelle': "Droit d'inscription", 'montant': 12000},
                                     {'libelle': 'Kimono', 'montant': 10000, 'premiere_fois': True}]},
            format='json')
        self.assertEqual(r.status_code, 201, r.content[:300])
        self.tkd = Service.objects.get(pk=r.data['id'])

    def _inscrit(self, **extra):
        return self._eleve(section=str(self.primaire.id), abonnements=[str(self.tkd.id)], **extra)

    def test_premiere_adhesion_droit_et_kimono(self):
        e = Eleve.objects.get(pk=self._inscrit().pk)
        self.assertTrue(e.abonnements.get().premiere_adhesion)
        self.assertEqual(e.du_hors_mensualite, 30000 + 12000 + 10000)
        self.assertEqual(self._lignes(e)[10]['du'], 20000 + 7000)

    def test_ancien_adherent_ne_rachete_pas_le_kimono(self):
        ancien_ex = Exercice.objects.create(tenant=self.tenant, annee_scolaire='2025-2026', cloture=True,
                                            date_debut=J(2025, 10, 1), date_fin=J(2026, 7, 31))
        avant = Eleve.objects.create(tenant=self.tenant, exercice=ancien_ex, section=self.primaire,
                                     nom_complet='Fatou SOW', date_inscription=J(2025, 10, 1))
        EleveService.objects.create(tenant=self.tenant, eleve=avant, service=self.tkd)
        e = self._inscrit(eleve_precedent=str(avant.id))
        e = Eleve.objects.get(pk=e.pk)
        self.assertFalse(e.abonnements.get().premiere_adhesion)
        self.assertEqual(e.du_hors_mensualite, 30000 + 12000)
        # L'école corrige : l'enfant n'avait pas de kimono en fait.
        r = self.client.patch(f'/api/eleves/{e.id}/', {'premieres_adhesions': {str(self.tkd.id): True}},
                              format='json')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(Eleve.objects.get(pk=e.pk).du_hors_mensualite, 30000 + 12000 + 10000)

    def test_inscription_avec_service_et_premier_mois_solde_le_mois(self):
        e = self._inscrit()
        saisie = self.client.get(f'/api/eleves/{e.id}/saisie-paiement/').data
        self.assertTrue(saisie['premier_mois_a_inscription'])
        self.assertEqual(saisie['premier_mois'], 10)
        self.assertEqual({a['libelle']: a['reste'] for a in saisie['adhesions']},
                         {"Droit d'inscription": 12000, 'Kimono': 10000})
        cles = {a['libelle']: a['cle'] for a in saisie['adhesions']}
        Paiement.objects.create(
            tenant=self.tenant, exercice=self.ex, eleve=e, no_piece='INS-1', mode_paiement='ESPECE',
            statut='ACTIF', montant_inscription=30000, montant_mensualite=20000, mois_regles=[10],
            montant_divers=12000 + 10000 + 7000,
            services_regles=[
                {'nom': "Taekwondo — Droit d'inscription", 'montant': 12000, 'nature': 'ADHESION',
                 'cle': cles["Droit d'inscription"]},
                {'nom': 'Taekwondo — Kimono', 'montant': 10000, 'nature': 'ADHESION', 'cle': cles['Kimono']},
                {'nom': 'Taekwondo (Octobre)', 'montant': 7000, 'nature': 'MENSUEL'}])
        ech = construire_echeancier(Eleve.objects.get(pk=e.pk))
        octobre = next(l for l in ech['lignes'] if l['mois'] == 10)
        self.assertEqual((octobre['statut'], octobre['a_inscription']), ('SOLDE', True))
        self.assertEqual(ech['hors_mensualite']['reste'], 0)
        novembre = next(l for l in ech['lignes'] if l['mois'] == 11)
        self.assertEqual(novembre['paye'], 0)
        saisie = self.client.get(f'/api/eleves/{e.id}/saisie-paiement/').data
        self.assertEqual({a['reste'] for a in saisie['adhesions']}, {0})

    def test_ancien_recu_sans_nature_reste_mensuel(self):
        e = self._inscrit()
        Paiement.objects.create(tenant=self.tenant, exercice=self.ex, eleve=e, no_piece='OLD-1',
                                mode_paiement='ESPECE', statut='ACTIF', montant_divers=7000,
                                services_regles=[{'nom': 'Taekwondo', 'montant': 7000}])
        octobre = self._lignes(e)[10]
        self.assertEqual(octobre['paye'], 7000)

    def test_recu_itemise_les_frais_du_service(self):
        e = self._inscrit()
        p = Paiement.objects.create(
            tenant=self.tenant, exercice=self.ex, eleve=e, no_piece='INS-2', mode_paiement='ESPECE',
            statut='ACTIF', montant_inscription=30000, montant_divers=22000,
            services_regles=[{'nom': "Taekwondo — Droit d'inscription", 'montant': 12000, 'nature': 'ADHESION'},
                             {'nom': 'Taekwondo — Kimono', 'montant': 10000, 'nature': 'ADHESION'}])
        r = self.client.get(f'/api/paiements/paiements/{p.id}/recu/')
        self.assertEqual(r.status_code, 200, r.content[:300])
        libelles = ' | '.join(str(l) for l in r.data['lignes'])
        self.assertIn('Taekwondo — Kimono', libelles)
        self.assertNotIn('Frais divers', libelles)

    def test_composition_de_service_validee(self):
        r = self.client.post('/api/eleves/services/', {
            'nom': 'Judo', 'montant': 5000, 'periodicite': 'MENSUEL',
            'composition_adhesion': [{'libelle': 'Kimono', 'montant': -1}]}, format='json')
        self.assertEqual(r.status_code, 400)
