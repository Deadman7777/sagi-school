"""Scolarité et transport encaissés sur deux reçus distincts.

Constat à une installation (08/10/2026) : l'école encaisse la scolarité
(140 000 / mois) et le transport (30 000 / mois) sur deux reçus séparés, et
plusieurs personnes reçoivent l'argent du transport (Laurence, Pape…).

Règle : séparer ou regrouper les reçus change la façon d'encaisser, JAMAIS ce
que la famille doit. On le teste en comparant les deux façons, pas en
asservant des valeurs isolées.
"""
import datetime

from rest_framework.test import APITestCase

from apps.eleves.echeancier import construire_echeancier
from apps.eleves.models import Eleve, EleveService, Section, Service
from apps.paiements.models import Exercice, Paiement, Receveur
from apps.tenants.models import Tenant
from apps.users.models import User

RENTREE = datetime.date(2026, 10, 1)


class RecusSeparesTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Les Pins', code_etablissement='PIN',
                                            recus_services_separes=True)
        user = User.objects.create_user('d@pins.sn', 'x', nom='Caissière', role='ADMIN_ECOLE',
                                        tenant=self.tenant)
        self.client.force_authenticate(user)
        self.ex = Exercice.objects.create(tenant=self.tenant, annee_scolaire='2026-2027',
                                          nb_mensualites=9, date_debut=RENTREE,
                                          date_fin=datetime.date(2027, 6, 30))
        self.section = Section.objects.create(tenant=self.tenant, nom='6e', frais_inscription=0,
                                              frais_mensualite=140000)
        self.transport = Service.objects.create(tenant=self.tenant, nom='Transport',
                                                montant=30000, periodicite='MENSUEL')

    def _eleve(self, nom):
        e = Eleve.objects.create(tenant=self.tenant, exercice=self.ex, section=self.section,
                                 nom_complet=nom, date_inscription=RENTREE)
        EleveService.objects.create(tenant=self.tenant, eleve=e, service=self.transport)
        return e

    def _encaisser(self, eleve, attendu=201, **corps):
        corps.update(eleve=str(eleve.id), mode_paiement=corps.get('mode_paiement', 'ESPECE'))
        r = self.client.post('/api/paiements/paiements/', corps, format='json')
        self.assertEqual(r.status_code, attendu, r.content[:400])
        return r

    def _transport(self, eleve, montant=30000, mois=(10,), **corps):
        return self._encaisser(eleve, montant_divers=montant, mois_regles=list(mois),
                               services_regles=[{'nom': 'Transport', 'montant': montant,
                                                 'nature': 'MENSUEL',
                                                 'service': str(self.transport.id)}], **corps)

    def _octobre(self, eleve):
        d = self.client.get(f'/api/eleves/{eleve.id}/saisie-paiement/').json()
        return d, next(m for m in d['mois_ecole'] if m['num'] == 10)

    def test_deux_recus_ou_un_seul_meme_du(self):
        separe, groupe = self._eleve('Awa SEPARE'), self._eleve('Binta GROUPE')
        self._encaisser(separe, montant_mensualite=140000, mois_regles=[10])
        self._transport(separe)
        self._encaisser(groupe, montant_mensualite=140000, montant_divers=30000, mois_regles=[10],
                        services_regles=[{'nom': 'Transport', 'montant': 30000, 'nature': 'MENSUEL',
                                          'service': str(self.transport.id)}])
        e1 = construire_echeancier(Eleve.objects.get(pk=separe.pk), today=RENTREE)
        e2 = construire_echeancier(Eleve.objects.get(pk=groupe.pk), today=RENTREE)
        self.assertEqual(e1['totaux'], e2['totaux'])
        self.assertEqual([(l['mois'], l['du'], l['paye'], l['statut']) for l in e1['lignes']],
                         [(l['mois'], l['du'], l['paye'], l['statut']) for l in e2['lignes']])
        oct1 = next(l for l in e1['lignes'] if l['mois'] == 10)
        self.assertEqual((oct1['du'], oct1['reste'], oct1['statut']), (170000, 0, 'SOLDE'))

    def test_guichet_partage_le_reste_du_mois(self):
        eleve = self._eleve('Awa NDIAYE')
        d, octobre = self._octobre(eleve)
        self.assertTrue(d['recus_services_separes'])
        self.assertEqual(octobre['reste_scolarite'], 140000)
        self.assertEqual(octobre['reste_services'], {str(self.transport.id): 30000})

        # Reçu de scolarité : le mois reste ouvert pour le transport seul.
        self._encaisser(eleve, montant_mensualite=140000, mois_regles=[10])
        _, octobre = self._octobre(eleve)
        self.assertEqual(octobre['reste'], 30000)
        self.assertEqual(octobre['reste_scolarite'], 0)
        self.assertEqual(octobre['reste_services'], {str(self.transport.id): 30000})

        # Reçu de transport partiel : la part de chacun suit.
        self._transport(eleve, montant=10000)
        _, octobre = self._octobre(eleve)
        self.assertEqual(octobre['reste'], 20000)
        self.assertEqual(octobre['reste_services'][str(self.transport.id)], 20000)
        self.assertEqual(octobre['reste_scolarite'], 0)

    def test_transport_d_abord_puis_scolarite(self):
        eleve = self._eleve('Coumba FALL')
        self._transport(eleve)
        _, octobre = self._octobre(eleve)
        self.assertEqual((octobre['reste_scolarite'], octobre['reste']), (140000, 140000))
        self.assertEqual(octobre['reste_services'][str(self.transport.id)], 0)

    def test_ancien_recu_sans_id_de_service_reconnu_par_son_nom(self):
        eleve = self._eleve('Dieynaba SOW')
        self._encaisser(eleve, montant_divers=30000, mois_regles=[10],
                        services_regles=[{'nom': 'Transport', 'montant': 30000, 'nature': 'MENSUEL'}])
        _, octobre = self._octobre(eleve)
        self.assertEqual(octobre['reste_services'][str(self.transport.id)], 0)
        self.assertEqual(octobre['reste_scolarite'], 140000)

    # ── Receveurs ─────────────────────────────────────────────────────────
    def test_receveur_sur_le_recu_et_dans_la_liste(self):
        laurence = self.client.post('/api/paiements/receveurs/', {'nom': ' Laurence '},
                                    format='json').json()
        self.assertEqual(laurence['nom'], 'Laurence')
        eleve = self._eleve('Awa NDIAYE')
        r = self._transport(eleve, receveur=laurence['id'])
        self.assertEqual(r.json()['receveur_nom'], 'Laurence')
        recu = self.client.get(f"/api/paiements/paiements/{r.json()['id']}/recu/").json()
        self.assertEqual(recu['receveur_nom'], 'Laurence')
        liste = self.client.get('/api/paiements/paiements/', {'receveur': laurence['id']}).json()
        liste = liste.get('results', liste)
        self.assertEqual([p['id'] for p in liste], [r.json()['id']])

    def test_receveur_doublon_suppression_et_desactivation(self):
        r = self.client.post('/api/paiements/receveurs/', {'nom': 'Pape'}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.client.post('/api/paiements/receveurs/', {'nom': 'pape'},
                                          format='json').status_code, 400)
        pape = Receveur.objects.get(id=r.json()['id'])
        self._transport(self._eleve('Awa NDIAYE'), receveur=str(pape.id))
        self.assertEqual(self.client.delete(f'/api/paiements/receveurs/{pape.id}/').status_code, 409)
        self.client.patch(f'/api/paiements/receveurs/{pape.id}/', {'actif': False}, format='json')
        self._transport(self._eleve('Binta BA'), attendu=400, receveur=str(pape.id))

    def test_receveur_d_une_autre_ecole_refuse(self):
        autre = Tenant.objects.create(nom='Autre', code_etablissement='AUT')
        etranger = Receveur.objects.create(tenant=autre, nom='Intrus')
        self._transport(self._eleve('Awa NDIAYE'), attendu=400, receveur=str(etranger.id))
        liste = self.client.get('/api/paiements/receveurs/').json()
        self.assertEqual(liste.get('results', liste) if isinstance(liste, dict) else liste, [])

    # ── Modifier un reçu de transport ────────────────────────────────────
    def test_modifier_garde_services_et_receveur(self):
        laurence = Receveur.objects.create(tenant=self.tenant, nom='Laurence')
        eleve = self._eleve('Awa NDIAYE')
        p = Paiement.objects.get(id=self._transport(eleve, receveur=str(laurence.id)).json()['id'])
        r = self.client.post(f'/api/paiements/paiements/{p.id}/modifier/',
                             {'montant_divers': 25000, 'mode_paiement': 'ESPECE'}, format='json')
        self.assertEqual(r.status_code, 200, r.content[:300])
        nouveau = Paiement.objects.get(no_piece=r.data['nouveau_no_piece'])
        self.assertEqual(nouveau.receveur_id, laurence.id)
        self.assertEqual([l['montant'] for l in nouveau.services_regles], [25000])
        self.assertEqual(float(nouveau.part_accessoire), 25000)
        _, octobre = self._octobre(eleve)
        self.assertEqual(octobre['reste_services'][str(self.transport.id)], 5000)
