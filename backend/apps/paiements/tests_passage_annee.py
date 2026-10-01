"""Tests : passage de fin d'année — passe, redouble ou sort.

Demandé le 01/10/2026 : « on ferme un exercice et on passe au suivant sans
réécrire les élèves ». Règles validées : tout le monde passe par défaut dans
la section suivante (ordre configuré), la direction coche les redoublants et
les sorties ; la dernière section propose « diplômé ».
"""
import datetime

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.academique.models import Classe, NiveauScolaire
from apps.eleves.models import Eleve, Famille, MouvementEleve, Section
from apps.paiements.cloturer import annee_suivante
from apps.paiements.models import Exercice, Paiement
from apps.paiements.passage import plan_sections
from apps.paiements.report_reliquats import reporter_reliquats
from apps.tenants.models import Tenant
from apps.users.models import User

URL = '/api/paiements/passage-annee/'


class PassageAnneeTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='LPE', code_etablissement='LPE')
        self.admin = User.objects.create_user('dir@lpe.sn', 'x', nom='Diallo',
                                              role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.admin)
        self.ex1 = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2025-2026', nb_mensualites=10,
            date_debut=datetime.date(2025, 10, 1), date_fin=datetime.date(2026, 7, 31))
        self.ex2 = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026-2027', nb_mensualites=10,
            date_debut=datetime.date(2026, 10, 1), date_fin=datetime.date(2027, 7, 31))
        self._cloturer(self.ex1)

        elem = NiveauScolaire.objects.create(tenant=self.tenant, nom='Élémentaire',
                                             code='ELEMENTAIRE', ordre=1)
        lycee = NiveauScolaire.objects.create(tenant=self.tenant, nom='Lycée', code='LYCEE', ordre=2)
        self.ci = self._section('CI', 1, elem, 40000)
        self.cp = self._section('CP', 2, elem, 45000)
        self.cm2 = self._section('CM2', 3, elem, 50000)
        self.seconde = self._section('2nde', 10, lycee, 60000)
        self.premiere_l = self._section('1ère L', 11, lycee, 65000)
        self.premiere_s = self._section('1ère S', 11, lycee, 65000)
        self.tl = self._section('TL', 12, lycee, 70000)
        self.ts = self._section('TS', 12, lycee, 70000)
        # Sans niveau : une formule, pas une classe.
        self.internat = Section.objects.create(tenant=self.tenant, nom='Internat', ordre=50,
                                               frais_inscription=10000, frais_mensualite=30000)
        self.classe_cp = Classe.objects.create(tenant=self.tenant, nom='CP A', section=self.cp)

        self.famille = Famille.objects.create(tenant=self.tenant, nom='Famille DIOUF')
        self.awa = self._eleve('Awa DIOUF', self.ci, 1, famille=self.famille,
                               nom_pere='Moussa DIOUF', telephone_pere='770000001')
        self.binta = self._eleve('Binta SOW', self.ci, 2)
        self.cheikh = self._eleve('Cheikh FALL', self.cm2, 3)
        self.dieynaba = self._eleve('Dieynaba KA', self.premiere_l, 4)
        self.el_hadji = self._eleve('El Hadji NDIAYE', self.seconde, 5)
        self.fatou = self._eleve('Fatou BA', self.internat, 6)

    def _cloturer(self, ex):
        ex.cloture, ex.date_cloture = True, timezone.now()
        ex.save()

    def _section(self, nom, ordre, niveau, inscription):
        return Section.objects.create(tenant=self.tenant, nom=nom, ordre=ordre, niveau=niveau,
                                      frais_inscription=inscription, frais_mensualite=20000)

    def _eleve(self, nom, section, n, **extra):
        return Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex1, nom_complet=nom, section=section,
            matricule=f'2025-LPE-{n:04d}', numero=n,
            date_inscription=self.ex1.date_debut, **extra)

    def _apercu(self):
        r = self.client.get(URL)
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.data

    def _ligne(self, apercu, eleve):
        return next(e for e in apercu['eleves'] if e['id'] == str(eleve.id))

    def _appliquer(self, decisions):
        r = self.client.post(URL, {'decisions': decisions}, format='json')
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.data

    def _tout_par_defaut(self, sauf=None):
        """Les décisions proposées, avec quelques changements cochés par la direction."""
        sauf = sauf or {}
        decisions = []
        for e in self._apercu()['eleves']:
            d = {'eleve_id': e['id'], **e['proposition']}
            d.update(sauf.get(e['id'], {}))
            decisions.append(d)
        return decisions

    def _fiche(self, eleve):
        return Eleve.objects.filter(exercice=self.ex2, eleve_precedent=eleve).first()

    # ── Propositions ───────────────────────────────────────────────────────
    def test_par_defaut_tout_le_monde_passe_a_la_section_suivante(self):
        ap = self._apercu()

        self.assertEqual(ap['source']['annee'], '2025-2026')
        self.assertEqual(ap['cible']['annee'], '2026-2027')
        self.assertEqual(self._ligne(ap, self.awa)['proposition'],
                         {'decision': 'PASSE', 'section_id': str(self.cp.id), 'motif': ''})

    def test_la_derniere_section_propose_diplome(self):
        """TL est la dernière : un élève de TL sort diplômé."""
        tl = self._eleve('Gora DIOP', self.tl, 7)
        self.assertEqual(self._ligne(self._apercu(), tl)['proposition']['motif'], 'DIPLOME')

    def test_la_serie_est_suivie(self):
        """1ère L → TL, pas TS."""
        self.assertEqual(self._ligne(self._apercu(), self.dieynaba)['proposition']['section_id'],
                         str(self.tl.id))

    def test_deux_series_possibles_la_direction_choisit(self):
        """2nde → 1ère L ou 1ère S : rien n'est deviné."""
        self.assertIsNone(self._ligne(self._apercu(), self.el_hadji)['proposition']['section_id'])

    def test_une_section_sans_niveau_ne_progresse_pas(self):
        """L'internat n'est pas une classe : l'élève y est reconduit."""
        self.assertEqual(self._ligne(self._apercu(), self.fatou)['proposition']['section_id'],
                         str(self.internat.id))

    def test_sans_college_le_cm2_termine_son_cycle(self):
        """École élémentaire + lycée : le CM2 ne « passe » pas en 2nde."""
        self.assertEqual(self._ligne(self._apercu(), self.cheikh)['proposition'],
                         {'decision': 'SORT', 'section_id': None, 'motif': 'DIPLOME'})

    def test_avec_un_college_le_cm2_passe_en_6eme(self):
        college = NiveauScolaire.objects.create(tenant=self.tenant, nom='Collège',
                                                code='COLLEGE', ordre=2)
        sixieme = self._section('6ème', 5, college, 55000)
        self.assertEqual(self._ligne(self._apercu(), self.cheikh)['proposition']['section_id'],
                         str(sixieme.id))

    def test_ordre_non_configure_est_signale(self):
        Section.objects.filter(tenant=self.tenant, niveau__isnull=False).update(ordre=0)
        plan, a_configurer = plan_sections(self.tenant)
        self.assertTrue(a_configurer)
        self.assertIsNone(plan[self.ci.id]['suivante'])

    def test_une_ecole_sans_niveaux_progresse_selon_l_ordre(self):
        """Le cas d'IFA : PS, MS, GS sans niveau rattaché."""
        tenant = Tenant.objects.create(nom='IFA', code_etablissement='IFA')
        ps = Section.objects.create(tenant=tenant, nom='Petite Section', ordre=1)
        ms = Section.objects.create(tenant=tenant, nom='Moyenne Section', ordre=2)
        gs = Section.objects.create(tenant=tenant, nom='Grande Section', ordre=3)
        plan, a_configurer = plan_sections(tenant)
        self.assertFalse(a_configurer)
        self.assertEqual(plan[ps.id]['suivante'], ms)
        self.assertTrue(plan[gs.id]['derniere'])

    def test_une_ecole_sans_ordre_ni_niveau_est_signalee(self):
        """Toutes les sections à 0 : rien n'est deviné, l'école est prévenue."""
        tenant = Tenant.objects.create(nom='IFA', code_etablissement='IFA')
        ps = Section.objects.create(tenant=tenant, nom='Petite Section')
        Section.objects.create(tenant=tenant, nom='Moyenne Section')
        plan, a_configurer = plan_sections(tenant)
        self.assertTrue(a_configurer)
        self.assertIsNone(plan[ps.id]['suivante'])
        self.assertFalse(plan[ps.id]['derniere'])

    # ── Application ────────────────────────────────────────────────────────
    def test_le_passage_cree_les_fiches_avec_l_identite(self):
        rap = self._appliquer(self._tout_par_defaut(sauf={
            str(self.el_hadji.id): {'section_id': str(self.premiere_s.id)}}))

        self.assertEqual(rap['nb_erreurs'], 0, rap['erreurs'])
        fiche = self._fiche(self.awa)
        self.assertEqual(fiche.section_id, self.cp.id)
        self.assertEqual((fiche.matricule, fiche.numero), ('2025-LPE-0001', 1))
        self.assertEqual(fiche.famille_id, self.famille.id)
        self.assertEqual((fiche.nom_pere, fiche.telephone_pere), ('Moussa DIOUF', '770000001'))
        self.assertFalse(fiche.redoublant)
        # Une seule classe en CP : l'élève y est rangé.
        self.assertEqual(fiche.classe_id, self.classe_cp.id)
        # Les frais sont ceux de la nouvelle section.
        self.assertEqual(fiche.date_inscription, self.ex2.date_debut)
        self.assertEqual(self._fiche(self.el_hadji).section_id, self.premiere_s.id)

    def test_le_redoublant_reste_dans_sa_section(self):
        self._appliquer(self._tout_par_defaut(sauf={
            str(self.binta.id): {'decision': 'REDOUBLE'}}))

        fiche = self._fiche(self.binta)
        self.assertEqual((fiche.section_id, fiche.redoublant), (self.ci.id, True))

    def test_le_diplome_sort_et_sa_sortie_est_tracee(self):
        tl = self._eleve('Gora DIOP', self.tl, 7)
        self._appliquer([{'eleve_id': str(tl.id), 'decision': 'SORT', 'motif': 'DIPLOME'}])

        tl.refresh_from_db()
        self.assertEqual((tl.statut, tl.date_sortie), ('DIPLOME', self.ex1.date_fin))
        self.assertIsNone(self._fiche(tl))
        self.assertTrue(MouvementEleve.objects.filter(eleve=tl, type_mouvement='SORTIE').exists())

    def test_sans_section_choisie_l_eleve_est_en_erreur_sans_bloquer_les_autres(self):
        rap = self._appliquer(self._tout_par_defaut())     # 2nde : aucune section proposée

        self.assertEqual(rap['nb_erreurs'], 1)
        self.assertEqual(rap['erreurs'][0]['nom_complet'], 'El Hadji NDIAYE')
        self.assertIsNotNone(self._fiche(self.awa))

    # ── Avec le report des impayés ─────────────────────────────────────────
    def test_l_eleve_endette_deja_reporte_passe_sans_doublon(self):
        """La clôture a déjà recopié l'endetté dans SA section, avec sa dette :
        le passage met cette fiche à jour, il n'en crée pas une deuxième."""
        Paiement.objects.create(tenant=self.tenant, exercice=self.ex1, eleve=self.awa,
                                no_piece='REC-0001', montant_inscription=40000)
        reporter_reliquats(self.ex1, self.ex2)
        self.assertEqual(self._fiche(self.awa).section_id, self.ci.id)
        # Le report seul n'est pas une décision : l'assistant propose toujours CP.
        ligne = self._ligne(self._apercu(), self.awa)
        self.assertFalse(ligne['deja']['passe'])
        self.assertEqual(ligne['proposition']['section_id'], str(self.cp.id))

        rap = self._appliquer(self._tout_par_defaut(sauf={
            str(self.el_hadji.id): {'section_id': str(self.premiere_l.id)}}))

        self.assertEqual(Eleve.objects.filter(exercice=self.ex2, eleve_precedent=self.awa).count(), 1)
        fiche = self._fiche(self.awa)
        self.assertEqual(fiche.section_id, self.cp.id)
        self.assertGreater(float(fiche.reliquat_anterieur), 0)
        self.assertGreaterEqual(rap['mises_a_jour'], 1)

    def test_l_endette_qui_sort_garde_sa_creance(self):
        Paiement.objects.create(tenant=self.tenant, exercice=self.ex1, eleve=self.cheikh,
                                no_piece='REC-0001', montant_inscription=10000)
        reporter_reliquats(self.ex1, self.ex2)

        self._appliquer([{'eleve_id': str(self.cheikh.id), 'decision': 'SORT', 'motif': 'TRANSFERE'}])

        fiche = self._fiche(self.cheikh)
        self.assertTrue(fiche.fiche_creance)
        self.assertGreater(float(fiche.reliquat_anterieur), 0)

    def test_le_passage_est_rejouable(self):
        self._eleve('Gora DIOP', self.tl, 7)            # diplômé au premier passage
        decisions = self._tout_par_defaut(sauf={
            str(self.el_hadji.id): {'section_id': str(self.premiere_s.id)}})
        self._appliquer(decisions)
        avant = Eleve.objects.filter(exercice=self.ex2).count()

        # La direction se ravise : Binta redouble finalement.
        for d in decisions:
            if d['eleve_id'] == str(self.binta.id):
                d['decision'] = 'REDOUBLE'
        rap = self._appliquer(decisions)

        self.assertEqual(Eleve.objects.filter(exercice=self.ex2).count(), avant)
        self.assertEqual(rap['creees'], 0)
        # Les diplômés du premier passage ne sont pas des erreurs au rejeu.
        self.assertEqual(rap['nb_erreurs'], 0, rap['erreurs'])
        self.assertEqual((self._fiche(self.binta).section_id, self._fiche(self.binta).redoublant),
                         (self.ci.id, True))
        # L'aperçu montre ce qui a déjà été fait.
        deja = self._ligne(self._apercu(), self.awa)['deja']
        self.assertEqual((deja['section'], deja['passe']), ('CP', True))

    # ── Droits ─────────────────────────────────────────────────────────────
    def test_reserve_a_la_direction(self):
        scol = User.objects.create_user('s@lpe.sn', 'x', nom='Scol', role='ADMIN_SCOLARITE',
                                        tenant=self.tenant)
        self.client.force_authenticate(scol)
        self.assertEqual(self.client.get(URL).status_code, 403)


class AnneeSuivanteTest(APITestCase):
    def test_noms_d_annee(self):
        self.assertEqual(annee_suivante('2025-2026'), '2026-2027')
        self.assertEqual(annee_suivante('2026'), '2027')            # Shoumoul, daaras
        self.assertEqual(annee_suivante('Année 2026'), 'Année 2027')

    def test_cloture_puis_passage_de_bout_en_bout(self):
        """Une école sur une année « 2026 » clôture, puis fait passer ses élèves."""
        tenant = Tenant.objects.create(nom='Shoumoul', code_etablissement='SHO')
        admin = User.objects.create_user('a@sho.sn', 'x', nom='A', role='ADMIN_ECOLE', tenant=tenant)
        self.client.force_authenticate(admin)
        ex = Exercice.objects.create(tenant=tenant, annee_scolaire='2026', nb_mensualites=10,
                                     date_debut=datetime.date(2026, 1, 1),
                                     date_fin=datetime.date(2026, 12, 31))
        niveau = NiveauScolaire.objects.create(tenant=tenant, nom='Élém', code='ELEMENTAIRE')
        ci = Section.objects.create(tenant=tenant, nom='CI', ordre=1, niveau=niveau, frais_mensualite=1000)
        cp = Section.objects.create(tenant=tenant, nom='CP', ordre=2, niveau=niveau, frais_mensualite=1000)
        e = Eleve.objects.create(tenant=tenant, exercice=ex, nom_complet='Ndeye SECK', section=ci,
                                 matricule='2026-SHO-0001', numero=1, date_inscription=ex.date_debut)

        r = self.client.post('/api/paiements/cloturer-exercice/',
                             {'confirme': True, 'creer_suivant': True, 'reporter_impayes': True},
                             format='json')
        self.assertEqual(r.status_code, 200, r.content[:300])
        cible = Exercice.objects.get(tenant=tenant, cloture=False)
        self.assertEqual(cible.annee_scolaire, '2027')

        ap = self.client.get(URL).data
        ligne = next(x for x in ap['eleves'] if x['id'] == str(e.id))
        r = self.client.post(URL, {'decisions': [{'eleve_id': str(e.id), **ligne['proposition']}]},
                             format='json')
        self.assertEqual(r.status_code, 200, r.content[:300])
        fiches = Eleve.objects.filter(exercice=cible, eleve_precedent=e)
        self.assertEqual(fiches.count(), 1)
        self.assertEqual(fiches.first().section_id, cp.id)
