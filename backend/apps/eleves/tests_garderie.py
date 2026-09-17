"""Garderie facturée à la journée.

Ce que ces tests rendent impossible :
- **un dû inventé** pour un enfant gardé à la journée : sans présence, il ne doit rien ;
- **deux calculs** du même dû — la fiche, le guichet, le récapitulatif et le
  total annuel lisent tous l'échéancier ;
- **réécrire le passé** : un tarif révisé ne change pas les jours déjà gardés ;
- **perdre un jour gardé** hors du calendrier des mensualités (mois d'été) ;
- **un appel incohérent** : jour à venir, hors année scolaire, enfant au mois.
"""
import datetime

from rest_framework.test import APITestCase

from apps.eleves.echeancier import construire_echeancier, precharger
from apps.eleves.models import Eleve, PresenceGarderie, Section
from apps.paiements.models import Exercice, Paiement
from apps.tenants.models import Tenant
from apps.users.models import User

J = datetime.date


class GarderieTest(APITestCase):
    # L'appel refuse un jour à venir : les dates de test sont passées.
    AUJOURDHUI = datetime.date.today()

    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Crèche Les Poussins', code_etablissement='CRE')
        self.user = User.objects.create_user('dir@creche.sn', 'x', nom='Directrice',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        debut = J(self.AUJOURDHUI.year - 1, self.AUJOURDHUI.month, 1)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2025-2026', nb_mensualites=10,
            date_debut=debut, date_fin=J(self.AUJOURDHUI.year + 1, self.AUJOURDHUI.month, 1)
            - datetime.timedelta(days=1))
        self.garderie = Section.objects.create(
            tenant=self.tenant, nom='Garderie ponctuelle', frais_inscription=10000,
            frais_mensualite=0, mode_tarif='JOURNEE', tarif_demi_journee=3000, tarif_journee=5000)
        self.creche = Section.objects.create(
            tenant=self.tenant, nom='Crèche 08H-17H', frais_inscription=25000, frais_mensualite=40000)
        self.awa = Eleve.objects.create(tenant=self.tenant, exercice=self.ex, section=self.garderie,
                                        nom_complet='Awa NDIAYE', date_inscription=debut)
        self.modou = Eleve.objects.create(tenant=self.tenant, exercice=self.ex, section=self.creche,
                                          nom_complet='Modou FALL', date_inscription=debut)
        # Trois jours du mois dernier (toujours passés, toujours dans l'année).
        precedent = self.AUJOURDHUI.replace(day=1) - datetime.timedelta(days=1)
        self.mois = precedent.month
        self.jours = [precedent.replace(day=d) for d in (2, 3, 4)]

    def _appel(self, jour, *presences):
        return self.client.post('/api/eleves/garderie/appel/', {
            'date': jour.isoformat(),
            'presences': [{'eleve': str(e.id), 'formule': f} for e, f in presences]}, format='json')

    def _ligne(self, eleve, mois):
        eleve = Eleve.objects.get(pk=eleve.pk)
        return next(l for l in construire_echeancier(eleve)['lignes'] if l['mois'] == mois)

    def test_sans_presence_l_enfant_ne_doit_que_son_inscription(self):
        self.assertEqual(Eleve.objects.get(pk=self.awa.pk).total_attendu, 10000)

    def test_le_du_du_mois_suit_les_jours_de_presence(self):
        self.assertEqual(self._appel(self.jours[0], (self.awa, 'DEMI_JOURNEE')).status_code, 200)
        self._appel(self.jours[1], (self.awa, 'JOURNEE'))
        self._appel(self.jours[2], (self.awa, 'DEMI_JOURNEE'))
        self.assertEqual(self._ligne(self.awa, self.mois)['du'], 11000)
        self.assertEqual(Eleve.objects.get(pk=self.awa.pk).total_attendu, 21000)

    def test_meme_montant_au_guichet_dans_la_fiche_et_le_recap(self):
        self._appel(self.jours[0], (self.awa, 'JOURNEE'))
        self._appel(self.jours[1], (self.awa, 'JOURNEE'))
        saisie = self.client.get(f'/api/eleves/{self.awa.id}/saisie-paiement/').data
        guichet = next(m for m in saisie['mois_ecole'] if m['num'] == self.mois)
        recap = self.client.get('/api/eleves/garderie/recap/', {'mois': self.mois}).data
        ligne_recap = next(e for e in recap['enfants'] if e['eleve'] == str(self.awa.id))
        self.assertEqual(guichet['montant'], 10000)
        self.assertEqual(ligne_recap['du'], 10000)
        self.assertEqual((ligne_recap['demi'], ligne_recap['journee']), (0, 2))
        precharge = precharger(Eleve.objects.filter(pk=self.awa.pk)).get()
        self.assertEqual(precharge.total_attendu, Eleve.objects.get(pk=self.awa.pk).total_attendu)

    def test_paiement_a_la_semaine_s_impute_sur_le_mois(self):
        for jour in self.jours:
            self._appel(jour, (self.awa, 'JOURNEE'))
        Paiement.objects.create(tenant=self.tenant, exercice=self.ex, eleve=self.awa, no_piece='P1',
                                mode_paiement='ESPECE', montant_mensualite=10000,
                                mois_regles=[self.mois], statut='ACTIF')
        ligne = self._ligne(self.awa, self.mois)
        self.assertEqual((ligne['du'], ligne['paye'], ligne['reste'], ligne['statut']),
                         (15000, 10000, 5000, 'PARTIEL'))

    def test_changer_de_formule_puis_retirer_la_presence(self):
        self._appel(self.jours[0], (self.awa, 'JOURNEE'))
        r = self._appel(self.jours[0], (self.awa, 'DEMI_JOURNEE'))
        self.assertEqual(r.data, {'ajoutes': 0, 'modifies': 1, 'retires': 0})
        self.assertEqual(self._ligne(self.awa, self.mois)['du'], 3000)
        self._appel(self.jours[0], (self.awa, None))
        self.assertFalse(PresenceGarderie.objects.exists())

    def test_tarif_revise_ne_reecrit_pas_les_jours_gardes(self):
        self._appel(self.jours[0], (self.awa, 'JOURNEE'))
        self.garderie.tarif_journee = 6000
        self.garderie.save()
        self._appel(self.jours[1], (self.awa, 'JOURNEE'))
        self.assertEqual(self._ligne(self.awa, self.mois)['du'], 11000)

    def test_jour_hors_calendrier_des_mensualites_reste_du(self):
        # 10 mensualités sur un exercice de 12 mois : les deux derniers mois ne
        # sont pas au calendrier, un jour gardé alors ne doit pas se perdre.
        dernier = (self.ex.date_debut.month + 10 - 1) % 12 + 1
        annee = self.ex.date_debut.year + (1 if dernier < self.ex.date_debut.month else 0)
        jour = J(annee, dernier, 5)
        if jour > self.AUJOURDHUI:
            self.skipTest("mois hors calendrier pas encore passé à la date du test")
        self._appel(jour, (self.awa, 'JOURNEE'))
        self.assertEqual(self._ligne(self.awa, dernier)['du'], 5000)

    def test_appel_refuse_un_jour_a_venir_et_un_enfant_au_mois(self):
        demain = self.AUJOURDHUI + datetime.timedelta(days=1)
        self.assertEqual(self._appel(demain, (self.awa, 'JOURNEE')).status_code, 400)
        r = self._appel(self.jours[0], (self.modou, 'JOURNEE'))
        self.assertEqual(r.status_code, 400)
        self.assertFalse(PresenceGarderie.objects.exists())

    def test_appel_ne_liste_que_les_enfants_a_la_journee(self):
        r = self.client.get('/api/eleves/garderie/appel/', {'date': self.jours[0].isoformat()})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual([e['nom_complet'] for e in r.data['enfants']], ['Awa NDIAYE'])
        self.assertEqual(r.data['enfants'][0]['tarif_journee'], 5000)

    def test_enfant_au_mois_inchange(self):
        self.assertEqual(self._ligne(self.modou, self.ex.date_debut.month)['du'], 40000)

    def test_section_a_la_journee_sans_tarif_refusee_et_mensualite_remise_a_zero(self):
        r = self.client.post('/api/eleves/sections/', {'nom': 'Garderie', 'mode_tarif': 'JOURNEE',
                                                      'frais_mensualite': 30000}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.client.post('/api/eleves/sections/', {'nom': 'Garderie', 'mode_tarif': 'JOURNEE',
                                                      'frais_mensualite': 30000, 'tarif_journee': 5000},
                             format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data['frais_mensualite'], 0)

    def test_recu_detaille_les_jours(self):
        self._appel(self.jours[0], (self.awa, 'DEMI_JOURNEE'))
        self._appel(self.jours[1], (self.awa, 'JOURNEE'))
        p = Paiement.objects.create(tenant=self.tenant, exercice=self.ex, eleve=self.awa, no_piece='P2',
                                    mode_paiement='ESPECE', montant_mensualite=8000,
                                    mois_regles=[self.mois], statut='ACTIF')
        r = self.client.get(f'/api/paiements/paiements/{p.id}/recu/')
        self.assertEqual(r.status_code, 200, r.content[:300])
        libelles = ' '.join(str(l) for l in r.data['lignes'])
        self.assertIn('Garderie', libelles)
        self.assertIn('1 × ½ journée, 1 × journée', libelles)
