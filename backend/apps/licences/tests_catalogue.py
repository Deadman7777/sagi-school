"""Le catalogue ne peut plus promettre ce que le logiciel ne fait pas.

La version précédente du document annonçait une « gestion des emplois du
temps » inexistante et une gestion fiscale en licence Pro alors que `/fiscal`
n'est ouvert qu'en Avancé et Taxawu Daara. Elle circulait chez des prospects.

Ces tests ne vérifient pas une mise en page : ils vérifient que **tout ce que
le document affirme sur le périmètre se retrouve dans `MODULES_PAR_TYPE`**, et
réciproquement. Une fonctionnalité retirée du logiciel sans être retirée du
catalogue les fait échouer.
"""
import re

from django.template.loader import render_to_string
from django.test import SimpleTestCase

from apps.assistant.perimetre import MODULES, modules_de
from apps.licences.management.commands.generer_catalogue import (
    DESTINATION_TEXTE, _contexte)
from apps.licences.models import Licence


def _bloc_licence(texte, libelle):
    """Le passage du document consacré à une licence, et lui seul."""
    debut = texte.index(f'--- Licence {libelle} ')
    suite = texte.find('--- Licence ', debut + 1)
    fin = suite if suite != -1 else texte.index("SERVICES DE DÉPLOIEMENT")
    return texte[debut:fin]


class CatalogueGenere(SimpleTestCase):
    """Le document produit maintenant, à partir du code tel qu'il est."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.contexte = _contexte()
        cls.texte = render_to_string('catalogue/catalogue.txt', cls.contexte)
        cls.html = render_to_string('catalogue/catalogue.html', cls.contexte)

    def test_chaque_licence_annonce_exactement_ses_modules(self):
        for code, libelle in Licence.TYPE_CHOICES:
            attendus = [nom for nom, _ in modules_de(code)]
            bloc = _bloc_licence(self.texte, libelle)
            annonces = re.findall(r'^   - ([^:]+) :', bloc, re.M)
            self.assertEqual(
                annonces, attendus,
                f"Licence {libelle} : le catalogue annonce {annonces}, "
                f"le logiciel ouvre {attendus}.")

    def test_aucune_fonctionnalite_inventee(self):
        """Le défaut historique : une promesse sans module derrière."""
        for absent in ('emploi du temps', 'emplois du temps'):
            self.assertNotIn(absent, self.texte.lower())
            self.assertNotIn(absent, self.html.lower())

    def test_le_fiscal_n_est_pas_vendu_en_pro(self):
        """L'autre défaut : un module annoncé sur une licence qui ne l'ouvre pas."""
        nom_fiscal = MODULES['/fiscal'][0]
        for code, libelle in Licence.TYPE_CHOICES:
            ouvre = '/fiscal' in Licence.MODULES_PAR_TYPE.get(code, [])
            bloc = _bloc_licence(self.texte, libelle)
            annonce = bool(re.search(rf'^   - {nom_fiscal} :', bloc, re.M))
            self.assertEqual(annonce, ouvre,
                             f"Licence {libelle} : fiscal annoncé={annonce}, ouvert={ouvre}.")

    def test_le_nombre_de_modules_affiche_est_le_bon(self):
        for code, libelle in Licence.TYPE_CHOICES:
            bloc = _bloc_licence(self.texte, libelle)
            declare = int(re.search(r'Modules ouverts \((\d+)\)', bloc).group(1))
            self.assertEqual(declare, len(modules_de(code)),
                             f"Licence {libelle} : compte annoncé faux.")

    def test_les_tarifs_sont_ceux_du_catalogue_serveur(self):
        """Le devis et le catalogue doivent facturer la même chose."""
        from apps.licences.catalogue import TARIFS_MENSUEL
        for l in self.contexte['licences']:
            self.assertEqual(l['prix_mensuel'], int(TARIFS_MENSUEL[l['code']]))


class CorpusDeSama(SimpleTestCase):
    """Le document versionné que lit l'assistant.

    `perimetre.py` lui dit déjà la vérité depuis le code ; si le catalogue de
    son corpus la contredit, il a deux réponses possibles à la même question.
    Le fichier commité doit donc rester aligné sur le générateur.
    """

    def setUp(self):
        self.corpus = DESTINATION_TEXTE.read_text(encoding='utf-8')

    def test_le_corpus_ne_promet_pas_d_emploi_du_temps(self):
        # Singulier ET pluriel : « emplois du temps » ne contient pas la
        # sous-chaîne « emploi du temps », et passait donc au travers.
        self.assertIsNone(re.search(r'emplois? du temps', self.corpus, re.I))

    def test_le_corpus_annonce_les_memes_modules_que_le_code(self):
        for code, libelle in Licence.TYPE_CHOICES:
            attendus = [nom for nom, _ in modules_de(code)]
            bloc = _bloc_licence(self.corpus, libelle)
            annonces = re.findall(r'^   - ([^:]+) :', bloc, re.M)
            self.assertEqual(
                annonces, attendus,
                f"Corpus de SAMA, licence {libelle} : régénérer avec "
                f"`manage.py generer_catalogue`.")
