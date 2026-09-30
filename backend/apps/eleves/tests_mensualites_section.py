"""Tests : mensualités propres à une section — la 3ème paie juillet.

Le cas qui a motivé le lot : une école du CI à la 3ème, année scolaire
d'octobre à juin (9 mensualités), exercice d'octobre à septembre. Les 3ème
passent l'examen en juillet et paient ce mois en plus : 10 mensualités.

Ce qu'on vérifie avant tout, c'est la COHÉRENCE : le dû, le calendrier, les
mois échus, l'échéancier et l'API doivent tous dire 10 pour la 3ème et 9 pour
le CM2 — un seul écran resté à 9 et le juillet ne serait jamais réclamé.
"""
import datetime

from rest_framework.test import APITestCase

from apps.eleves.echeancier import construire_echeancier, mois_de_base
from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant
from apps.users.models import User

OCT_JUIN = [10, 11, 12, 1, 2, 3, 4, 5, 6]


class MensualitesSectionTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Collège Test', code_etablissement='CLT')
        self.user = User.objects.create_user(
            'd@c.sn', 'x', nom='Directeur', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026-2027', cloture=False, nb_mensualites=9,
            date_debut=datetime.date(2026, 10, 1), date_fin=datetime.date(2027, 9, 30))
        self.cm2 = Section.objects.create(tenant=self.tenant, nom='CM2',
                                          frais_inscription=20000, frais_mensualite=15000)
        self.troisieme = Section.objects.create(tenant=self.tenant, nom='3ème', nb_mensualites=10,
                                                frais_inscription=25000, frais_mensualite=20000)

    def _eleve(self, section, entree=datetime.date(2026, 10, 1)):
        return Eleve.objects.create(tenant=self.tenant, exercice=self.ex, section=section,
                                    nom_complet=f'Élève {section.nom}', date_inscription=entree)

    def test_la_3eme_paie_juillet_le_cm2_non(self):
        e3, cm2 = self._eleve(self.troisieme), self._eleve(self.cm2)
        self.assertEqual(e3.nb_mensualites_dues, 10)
        self.assertEqual(mois_de_base(e3), OCT_JUIN + [7])
        self.assertEqual(e3.total_attendu, 25000 + 20000 * 10)
        self.assertEqual(cm2.nb_mensualites_dues, 9)
        self.assertEqual(mois_de_base(cm2), OCT_JUIN)
        self.assertEqual(cm2.total_attendu, 20000 + 15000 * 9)

    def test_entree_en_cours_d_annee_garde_le_prorata(self):
        # Entrée en janvier : la 3ème doit janvier → juillet, le CM2 janvier → juin.
        e3 = self._eleve(self.troisieme, datetime.date(2027, 1, 10))
        cm2 = self._eleve(self.cm2, datetime.date(2027, 1, 10))
        self.assertEqual(mois_de_base(e3), [1, 2, 3, 4, 5, 6, 7])
        self.assertEqual(mois_de_base(cm2), [1, 2, 3, 4, 5, 6])

    def test_mois_echus_courent_jusqu_en_juillet_pour_la_3eme(self):
        e3, cm2 = self._eleve(self.troisieme), self._eleve(self.cm2)
        fin_juillet = datetime.date(2027, 7, 31)
        self.assertEqual(e3.mois_echus(fin_juillet), 10)
        self.assertEqual(cm2.mois_echus(fin_juillet), 9)

    def test_echeancier_et_api_disent_la_meme_chose(self):
        e3 = self._eleve(self.troisieme)
        ech = construire_echeancier(e3)
        self.assertEqual([l['mois'] for l in ech['lignes']], OCT_JUIN + [7])
        self.assertEqual(sum(float(l['du']) for l in ech['lignes']), 20000 * 10)

        r = self.client.get(f'/api/eleves/{e3.id}/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['nb_mensualites_dues'], 10)
        self.assertEqual(r.data['mois_dus_effectifs'], OCT_JUIN + [7])

    def test_mois_saisis_sur_la_fiche_priment_toujours(self):
        e3 = self._eleve(self.troisieme)
        e3.mois_dus = OCT_JUIN
        e3.save()
        self.assertEqual(e3.nb_mensualites_dues, 9)

    def test_parametrage_de_la_section(self):
        url = f'/api/eleves/sections/{self.cm2.id}/'
        self.assertEqual(self.client.patch(url, {'nb_mensualites': 10}, format='json').status_code, 200)
        self.cm2.refresh_from_db()
        self.assertEqual(self._eleve(self.cm2).nb_mensualites_dues, 10)
        self.assertEqual(self.client.patch(url, {'nb_mensualites': 13}, format='json').status_code, 400)
        # Vider le champ rend la main à l'exercice.
        self.assertEqual(self.client.patch(url, {'nb_mensualites': None}, format='json').status_code, 200)
        self.cm2.refresh_from_db()
        self.assertEqual(self._eleve(self.cm2).nb_mensualites_dues, 9)


class DerniereMensualiteInscriptionTest(APITestCase):
    """Réglage « la dernière mensualité est encaissée à l'inscription ».

    L'échéancier la rendait exigible dès l'entrée, mais le guichet
    d'inscription ne la proposait pas : la famille repartait sans l'avoir
    réglée et tombait aussitôt en retard sur un mois qu'on ne lui avait
    jamais présenté.
    """
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Collège Test', code_etablissement='CLT',
                                            echeance_mensualite='FIN_MOIS',
                                            dernier_mois_a_inscription=True)
        user = User.objects.create_user('d@c.sn', 'x', nom='Directeur',
                                        role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026-2027', cloture=False, nb_mensualites=9,
            date_debut=datetime.date(2026, 10, 1), date_fin=datetime.date(2027, 9, 30))
        self.cm2 = Section.objects.create(tenant=self.tenant, nom='CM2',
                                          frais_inscription=20000, frais_mensualite=15000)
        self.troisieme = Section.objects.create(tenant=self.tenant, nom='3ème', nb_mensualites=10,
                                                frais_inscription=25000, frais_mensualite=20000)

    def _saisie(self, section):
        e = Eleve.objects.create(tenant=self.tenant, exercice=self.ex, section=section,
                                 nom_complet='Élève', date_inscription=datetime.date(2026, 10, 1))
        r = self.client.get(f'/api/eleves/{e.id}/saisie-paiement/')
        self.assertEqual(r.status_code, 200)
        return e, r.data

    def test_le_guichet_propose_la_derniere_mensualite(self):
        _, d = self._saisie(self.cm2)
        self.assertTrue(d['dernier_mois_a_inscription'])
        self.assertEqual(d['dernier_mois'], 6)          # juin
        juin = next(m for m in d['mois_ecole'] if m['num'] == 6)
        self.assertTrue(juin['du'])
        self.assertEqual(juin['reste'], 15000)

    def test_pour_la_3eme_la_derniere_mensualite_est_juillet(self):
        _, d = self._saisie(self.troisieme)
        self.assertEqual(d['dernier_mois'], 7)

    def test_la_derniere_mensualite_est_exigible_des_l_entree(self):
        e, _ = self._saisie(self.cm2)
        ech = construire_echeancier(e, today=datetime.date(2026, 10, 2))
        par_mois = {l['mois']: l for l in ech['lignes']}
        self.assertTrue(par_mois[6]['echu'])        # juin : dû dès l'inscription
        self.assertFalse(par_mois[10]['echu'])      # octobre : à terme échu, en novembre
