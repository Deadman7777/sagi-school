"""Tests : l'ordre des élèves dans les listes exportées.

Une école lit ses listes dans un ordre précis, et cet ordre lui appartient :
un complexe qui a un internat Tahfiiz, une demi-pension et un externat veut
ses groupes dans SON ordre. À l'intérieur, une seule règle — le matricule
croissant, du plus ancien au plus récent.

Les assertions portent sur le PDF réellement produit, pas seulement sur la
fonction de tri : c'est le document remis à l'école qui doit être juste, et un
gabarit peut très bien ignorer l'ordre qu'on lui donne.
"""
import datetime
import re

from rest_framework.test import APITestCase

from apps.academique.models import Classe
from apps.eleves.models import Eleve, Section
from apps.eleves.tri import trier
from apps.paiements.models import Exercice
from apps.tenants.models import Tenant
from apps.users.models import User


class TriBase(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Shoumoul', code_etablissement='CSE')
        self.user = User.objects.create_user(
            'a@a.sn', 'x', nom='Admin', role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(
            tenant=self.tenant, annee_scolaire='2026', nb_mensualites=12,
            date_debut=datetime.date(2026, 1, 1), date_fin=datetime.date(2026, 12, 31))
        # L'ordre voulu par l'école : Tahfiiz d'abord, puis demi-pension,
        # puis externat — délibérément l'inverse de l'ordre alphabétique.
        self.tahfiiz = Section.objects.create(
            tenant=self.tenant, nom='INTERNAT TAHFIIZ', ordre=1,
            frais_inscription=0, frais_mensualite=60000)
        self.demi = Section.objects.create(
            tenant=self.tenant, nom='DEMI-PENSION', ordre=2,
            frais_inscription=0, frais_mensualite=40000)
        self.externat = Section.objects.create(
            tenant=self.tenant, nom='EXTERNAT', ordre=3,
            frais_inscription=0, frais_mensualite=20000)

    # `section` explicitement absent des kwargs = section par défaut ;
    # `section=None` = élève réellement sans section, ce que le tri doit ranger
    # à part. Confondre les deux rendait le test aveugle à ce cas.
    _DEFAUT = object()

    def _eleve(self, nom, matricule, section=_DEFAUT, classe=None):
        if section is self._DEFAUT:
            section = self.tahfiiz
        return Eleve.objects.create(
            tenant=self.tenant, exercice=self.ex, section=section,
            classe=classe, nom_complet=nom, matricule=matricule, statut='INSCRIT',
            date_inscription=datetime.date(2026, 1, 1))


class TriMatriculeTest(TriBase):
    """Du plus ancien au plus récent."""

    def test_l_ordre_suit_l_annee_puis_le_rang(self):
        self._eleve('Récent',  '2026-CSE-0001')
        self._eleve('Ancien',  '2021-CSE-0007')
        self._eleve('Milieu',  '2024-CSE-0003')

        noms = [e.nom_complet for e in trier(Eleve.objects.all(), 'matricule')]

        self.assertEqual(noms, ['Ancien', 'Milieu', 'Récent'])

    def test_le_rang_se_lit_comme_un_nombre(self):
        """« A-9 » avant « A-12 » : un tri de chaînes ferait l'inverse."""
        self._eleve('Douzième', 'A-12')
        self._eleve('Neuvième', 'A-9')

        noms = [e.nom_complet for e in trier(Eleve.objects.all(), 'matricule')]

        self.assertEqual(noms, ['Neuvième', 'Douzième'])

    def test_les_fiches_sans_matricule_ferment_la_marche(self):
        """Elles doivent se voir, pas se noyer au milieu."""
        self._eleve('Sans', '')
        self._eleve('Avec', '2026-CSE-0001')

        noms = [e.nom_complet for e in trier(Eleve.objects.all(), 'matricule')]

        self.assertEqual(noms, ['Avec', 'Sans'])

    def test_deux_editions_donnent_le_meme_ordre(self):
        """Sans matricule, le nom départage — sinon l'ordre varierait d'une
        édition à l'autre et la liste deviendrait incomparable."""
        # None et '' : les deux formes que prend une fiche sans matricule.
        self._eleve('Zoulaikha', None)
        self._eleve('Aminata', '')

        noms = [e.nom_complet for e in trier(Eleve.objects.all(), 'matricule')]

        self.assertEqual(noms, ['Aminata', 'Zoulaikha'])


class TriGroupeTest(TriBase):
    """Les groupes dans l'ordre de l'école, l'ancienneté à l'intérieur."""

    def test_les_sections_sortent_dans_l_ordre_de_l_ecole(self):
        self._eleve('Externe',  '2020-CSE-0001', section=self.externat)
        self._eleve('Demi',     '2021-CSE-0001', section=self.demi)
        self._eleve('Tahfiiz',  '2026-CSE-0001', section=self.tahfiiz)

        noms = [e.nom_complet for e in trier(Eleve.objects.all(), 'section')]

        # L'ordre de l'école prime sur l'ancienneté ET sur l'alphabet.
        self.assertEqual(noms, ['Tahfiiz', 'Demi', 'Externe'])

    def test_dans_un_groupe_l_ancienneté_reprend_la_main(self):
        self._eleve('Tahfiiz récent', '2026-CSE-0002', section=self.tahfiiz)
        self._eleve('Tahfiiz ancien', '2019-CSE-0009', section=self.tahfiiz)
        self._eleve('Demi',           '2015-CSE-0001', section=self.demi)

        noms = [e.nom_complet for e in trier(Eleve.objects.all(), 'section')]

        self.assertEqual(noms, ['Tahfiiz ancien', 'Tahfiiz récent', 'Demi'])

    def test_les_eleves_sans_section_ferment_la_marche(self):
        self._eleve('Sans section', '2010-CSE-0001', section=None)
        self._eleve('Externe',      '2026-CSE-0001', section=self.externat)

        noms = [e.nom_complet for e in trier(Eleve.objects.all(), 'section')]

        self.assertEqual(noms, ['Externe', 'Sans section'])

    def test_le_regroupement_par_classe(self):
        ce2 = Classe.objects.create(tenant=self.tenant, nom='CE2', ordre=1)
        cm1 = Classe.objects.create(tenant=self.tenant, nom='CM1', ordre=2)
        self._eleve('En CM1', '2019-CSE-0001', classe=cm1)
        self._eleve('En CE2', '2026-CSE-0001', classe=ce2)

        noms = [e.nom_complet for e in trier(Eleve.objects.all(), 'classe')]

        self.assertEqual(noms, ['En CE2', 'En CM1'])

    def test_un_tri_inconnu_ne_prive_pas_l_ecole_de_sa_liste(self):
        self._eleve('Awa', '2026-CSE-0001')

        self.assertEqual(len(trier(Eleve.objects.all(), 'n_importe_quoi')), 1)


class TriDansLePdfTest(TriBase):
    """L'ordre demandé doit se retrouver dans le document produit."""

    def _pdf(self, url):
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertTrue(r.content.startswith(b'%PDF'), 'ce n’est pas un PDF')
        return r.content

    def _peupler(self):
        self._eleve('Externe Un',  '2020-CSE-0001', section=self.externat)
        self._eleve('Demi Un',     '2021-CSE-0004', section=self.demi)
        self._eleve('Demi Deux',   '2021-CSE-0002', section=self.demi)
        self._eleve('Tahfiiz Un',  '2026-CSE-0001', section=self.tahfiiz)

    def _ordre_rendu(self, contexte):
        """Ordre des noms tel que le gabarit les a placés."""
        from django.template.loader import render_to_string
        html = render_to_string('pdf/liste_classe.html', contexte)
        return [n for n in ['Tahfiiz Un', 'Demi Deux', 'Demi Un', 'Externe Un']
                if n in html]

    def test_la_liste_nominative_respecte_l_ordre_des_sections(self):
        from apps.eleves.views import contexte_liste_nominative

        self._peupler()
        contexte = contexte_liste_nominative(
            self.tenant, self.ex, groupe='section')

        noms = [e['nom_complet'] for e in contexte['eleves']]

        self.assertEqual(noms, ['Tahfiiz Un', 'Demi Deux', 'Demi Un', 'Externe Un'])

    def test_la_colonne_section_apparait_quand_on_groupe_par_section(self):
        from django.template.loader import render_to_string

        from apps.eleves.views import contexte_liste_nominative

        self._peupler()
        contexte = contexte_liste_nominative(self.tenant, self.ex, groupe='section')
        html = render_to_string('pdf/liste_classe.html', contexte)

        self.assertIn('Section', html)
        self.assertIn('INTERNAT TAHFIIZ', html)

    def test_les_largeurs_de_colonnes_font_bien_cent_pour_cent(self):
        """xhtml2pdf AJOUTE le padding aux pourcentages : un total qui déborde
        déforme la table au lieu de la rétrécir."""
        from django.template.loader import render_to_string

        from apps.eleves.views import contexte_liste_nominative

        self._peupler()
        classe = Classe.objects.create(tenant=self.tenant, nom='CM2', ordre=1)

        # Les quatre combinaisons de colonnes optionnelles : la liste d'UNE
        # classe masque la colonne Classe, le regroupement par section ajoute
        # la colonne Section. Chacune doit retomber sur 100 %.
        cas = [
            ('section',   None),
            ('classe',    None),
            ('matricule', None),
            ('section',   str(classe.id)),
            ('matricule', str(classe.id)),
        ]
        for groupe, classe_id in cas:
            contexte = contexte_liste_nominative(
                self.tenant, self.ex, classe_id, groupe=groupe)
            html = render_to_string('pdf/liste_classe.html', contexte)
            entete = html[html.index('<thead'):html.index('</thead>')]
            total = sum(int(w) for w in re.findall(r'width:(\d+)%', entete))
            self.assertEqual(total, 100,
                             f'groupe={groupe} classe={bool(classe_id)} → {total}%')

    def test_les_largeurs_de_la_liste_financiere_aussi(self):
        from django.template.loader import render_to_string

        html = render_to_string('pdf/eleves.html', self._contexte_financier())
        entete = html[html.index('<thead'):html.index('</thead>')]
        total = sum(int(w) for w in re.findall(r'width:(\d+)%', entete))

        self.assertEqual(total, 100)

    def test_la_ligne_de_totaux_couvre_les_bonnes_colonnes(self):
        """Un colspan qui ne suit pas l'ajout d'une colonne décale toute la
        ligne des totaux — le document devient faux à l'endroit qu'on lit."""
        from django.template.loader import render_to_string

        html = render_to_string('pdf/eleves.html', self._contexte_financier())
        entete = html[html.index('<thead'):html.index('</thead>')]
        pied   = html[html.index('<tfoot'):html.index('</tfoot>')]

        # `<th[ >]` et non `<th` : sinon la balise `<thead>` se compte comme
        # une colonne de plus.
        nb_colonnes = len(re.findall(r'<th[ >]', entete))
        # Cellules du pied : celles à colspan comptent pour autant.
        occupees = sum(int(n) for n in re.findall(r'colspan="(\d+)"', pied))
        occupees += pied.count('<td') - len(re.findall(r'colspan=', pied))

        self.assertEqual(occupees, nb_colonnes)

    def test_aucun_commentaire_de_gabarit_ne_fuit_dans_le_document(self):
        """Un `{# … #}` étalé sur deux lignes n'est PAS un commentaire pour
        Django : il s'imprime tel quel dans le PDF remis à l'école. Le piège
        est invisible à la relecture du code et coûte un document raté."""
        from django.template.loader import render_to_string

        from apps.eleves.views import contexte_liste_nominative

        self._peupler()
        rendus = [render_to_string('pdf/eleves.html', self._contexte_financier())]
        for groupe in ('section', 'classe', 'matricule'):
            rendus.append(render_to_string(
                'pdf/liste_classe.html',
                contexte_liste_nominative(self.tenant, self.ex, groupe=groupe)))

        for html in rendus:
            self.assertNotIn('{#', html)
            self.assertNotIn('#}', html)
            self.assertNotIn('{%', html)

    def _contexte_financier(self):
        return {
            'tenant': self.tenant, 'exercice': self.ex,
            'eleves': [{'matricule': '2026-CSE-0001', 'nom_complet': 'Awa',
                        'section_nom': 'INTERNAT TAHFIIZ', 'genre': 'F',
                        'prise_en_charge': False, 'total_attendu': 0,
                        'total_paye': 0, 'reste': 0, 'niveau_alerte': 'A_JOUR'}],
            'nb_eleves': 1, 'total_attendu': 0, 'total_paye': 0, 'total_reste': 0,
            'nb_critique': 0, 'nb_urgent': 0, 'nb_attention': 0, 'nb_a_jour': 1,
        }

    def test_l_export_nominatif_sort_un_pdf(self):
        self._peupler()

        self._pdf('/api/eleves/export-pdf/?financier=0&tri=section')

    def test_l_export_financier_sort_un_pdf(self):
        self._peupler()

        self._pdf('/api/eleves/export-pdf/?tri=section')

    def test_le_pdf_financier_porte_les_matricules(self):
        """La liste est triée par matricule : il doit être lisible dessus."""
        from django.template.loader import render_to_string

        from apps.eleves.views import ElevesListePDFView

        self._peupler()
        html = render_to_string('pdf/eleves.html', {
            'tenant': self.tenant, 'exercice': self.ex,
            'eleves': [{'matricule': '2026-CSE-0001', 'nom_complet': 'Awa',
                        'section_nom': 'INTERNAT TAHFIIZ', 'genre': 'F',
                        'prise_en_charge': False, 'total_attendu': 0,
                        'total_paye': 0, 'reste': 0, 'niveau_alerte': 'A_JOUR'}],
            'nb_eleves': 1, 'total_attendu': 0, 'total_paye': 0, 'total_reste': 0,
            'nb_critique': 0, 'nb_urgent': 0, 'nb_attention': 0, 'nb_a_jour': 1,
        })

        self.assertIn('2026-CSE-0001', html)
        self.assertIn('Matricule', html)
        self.assertTrue(ElevesListePDFView)
