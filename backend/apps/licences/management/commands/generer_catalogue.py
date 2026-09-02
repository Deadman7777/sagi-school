"""Produit le Catalogue Officiel des Offres et Tarifs à partir du logiciel.

**Pourquoi cette commande existe.** La version précédente du catalogue était un
PDF sans source au dépôt, rédigé à la main. Elle annonçait une « gestion des
emplois du temps » qui n'existe dans aucun module, et une gestion fiscale en
licence Pro alors que `/fiscal` n'est ouvert qu'en Avancé et Taxawu Daara. Le
document circulait chez des prospects ; une promesse écrite qui ne se retrouve
pas à l'écran se paie au premier client.

Le périmètre des licences n'est donc plus rédigé : il est **interrogé** dans
`Licence.MODULES_PAR_TYPE`, la table que le contrôle d'accès applique
réellement. Ajoutez un module à une licence, régénérez, et le catalogue suit.
C'est le principe déjà retenu pour `apps/assistant/perimetre.py` et pour
`apps/licences/catalogue.py`.

Le texte commercial — positionnement, prestations de service, conditions —
n'existe pas dans le logiciel et reste écrit à la main dans
`apps/licences/contenu_catalogue.py`.

    python manage.py generer_catalogue --settings=config.settings.production

Trois artefacts sont produits côte à côte :

  * le **HTML**, source versionnée du document ;
  * le **PDF**, rendu par Chrome si l'exécutable est trouvé ;
  * le **texte**, que lit l'assistant SAMA — pour qu'il ne récite pas un
    catalogue périmé pendant que `perimetre.py` lui dit le contraire.
"""
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand
from django.template.loader import render_to_string

from apps.assistant.perimetre import modules_de
from apps.licences import contenu_catalogue as contenu
from apps.licences.catalogue import (MOYENS_PAIEMENT, REFERENCE_CATALOGUE,
                                     TARIFS_MENSUEL, VALIDITE_DEVIS_JOURS)
from apps.licences.models import Licence

VERSION = '2026 – 2027'

# Les emplacements où le document doit exister. Trois copies traînaient dans le
# dépôt avec le même contenu faux ; elles sont désormais écrites d'un seul geste
# plutôt que recopiées à la main.
RACINE = Path(__file__).resolve().parents[5]
DESTINATIONS_PDF = [
    RACINE / 'CATALOGUE_OFFICIEL_DES_OFFRES_ET_TARIFS.pdf',
    RACINE / 'partenariat' / 'CATALOGUE_OFFICIEL_DES_OFFRES_ET_TARIFS.pdf',
    RACINE / 'sama_assistant_hady' / 'CATALOGUE_OFFICIEL_DES_OFFRES_ET_TARIFS.pdf',
]
DESTINATION_HTML = RACINE / 'docs' / 'catalogue-offres-et-tarifs.html'
DESTINATION_TEXTE = (RACINE / 'backend' / 'apps' / 'assistant' / 'connaissances'
                     / 'CATALOGUE_OFFICIEL_DES_OFFRES_ET_TARIFS.txt')

CHROMES = ('google-chrome', 'chromium', 'chromium-browser', 'google-chrome-stable')

ENTREPRISE = {
    'adresse': 'Colobane 1, Rufisque — Sénégal',
    'email': 'hadygesman@gmail.com',
    'telephones': '+221 78 429 78 30 / +221 70 328 61 51',
    'ninea': '012673986',
    'rccm': 'SN.DKR.2025.A.48268',
}

MOIS = ('janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet',
        'août', 'septembre', 'octobre', 'novembre', 'décembre')


def _contexte():
    """Le catalogue, licences comprises — le périmètre venant du code."""
    licences = []
    for code, libelle in Licence.TYPE_CHOICES:
        textes = contenu.POSITIONNEMENT.get(code, {})
        licences.append({
            'code': code,
            'libelle': libelle,
            'prix_mensuel': int(TARIFS_MENSUEL.get(code, 0)),
            'accroche': textes.get('accroche', ''),
            'positionnement': textes.get('positionnement', ''),
            'remarque': textes.get('remarque', ''),
            'modules': [{'nom': n, 'detail': d} for n, d in modules_de(code)],
        })

    aujourdhui = date.today()
    return {
        'version': VERSION,
        'reference': REFERENCE_CATALOGUE,
        'etabli_le': f'{aujourdhui.day} {MOIS[aujourdhui.month - 1]} {aujourdhui.year}',
        'licences': licences,
        'domaines': contenu.DOMAINES_INTERVENTION,
        'cibles': contenu.CIBLES_PLATEFORME,
        'deploiement': contenu.DEPLOIEMENT,
        'accompagnement': contenu.ACCOMPAGNEMENT,
        'combinees': contenu.OFFRES_COMBINEES,
        'modalites': contenu.MODALITES_PAIEMENT,
        'moyens_paiement': list(MOYENS_PAIEMENT),
        'validite_devis_jours': VALIDITE_DEVIS_JOURS,
        'engagements': contenu.ENGAGEMENTS,
        'entreprise': ENTREPRISE,
    }


def _rendre_pdf(html: str, sortie: Path) -> bool:
    """Rend le HTML en PDF avec Chrome. Faux si aucun Chrome n'est installé.

    Chrome plutôt que WeasyPrint : ce dernier traîne dans l'environnement de
    développement mais n'est pas déclaré dans `requirements/base.txt`, et le
    projet est passé à xhtml2pdf — dont le moteur CSS ne rendrait pas cette
    mise en page. Chrome, lui, est déjà utilisé par la suite de tests du site
    institutionnel, et il n'ajoute aucune dépendance Python.
    """
    binaire = next((shutil.which(c) for c in CHROMES if shutil.which(c)), None)
    if not binaire:
        return False

    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / 'catalogue.html'
        source.write_text(html, encoding='utf-8')
        subprocess.run(
            [binaire, '--headless=new', '--disable-gpu', '--no-sandbox',
             f'--user-data-dir={tmp}/profil',
             '--no-pdf-header-footer', '--print-to-pdf-no-header',
             f'--print-to-pdf={sortie}', source.as_uri()],
            check=True, capture_output=True, timeout=180,
        )
    return sortie.exists()


class Command(BaseCommand):
    help = "Produit le catalogue commercial à partir du périmètre réel des licences."

    def add_arguments(self, parseur):
        parseur.add_argument('--html-seulement', action='store_true',
                             help='N’écrit que le HTML, sans rendre le PDF.')

    def handle(self, *args, **options):
        contexte = _contexte()

        html = render_to_string('catalogue/catalogue.html', contexte)
        DESTINATION_HTML.parent.mkdir(parents=True, exist_ok=True)
        DESTINATION_HTML.write_text(html, encoding='utf-8')
        self.stdout.write(f'HTML   {DESTINATION_HTML}')

        texte = render_to_string('catalogue/catalogue.txt', contexte)
        DESTINATION_TEXTE.write_text(texte, encoding='utf-8')
        self.stdout.write(f'Texte  {DESTINATION_TEXTE}  (corpus de SAMA)')

        if options['html_seulement']:
            return

        premier = DESTINATIONS_PDF[0]
        premier.parent.mkdir(parents=True, exist_ok=True)
        if not _rendre_pdf(html, premier):
            self.stderr.write(self.style.WARNING(
                'Aucun Chrome trouvé : le PDF n’a pas été rendu. '
                'Le HTML et le texte, eux, sont à jour.'))
            return

        self.stdout.write(f'PDF    {premier}')
        for autre in DESTINATIONS_PDF[1:]:
            if autre.parent.exists():
                shutil.copyfile(premier, autre)
                self.stdout.write(f'       {autre}')

        # Le rappel qui compte : ces deux égalités sont des décisions
        # commerciales, pas des anomalies techniques — mais elles se voient
        # maintenant dans le document.
        perimetre = {c: set(Licence.MODULES_PAR_TYPE.get(c, []))
                     for c, _ in Licence.TYPE_CHOICES}
        if perimetre.get('TAXAWU_DAARA') == perimetre.get('AVANCE'):
            self.stdout.write(self.style.WARNING(
                '\nÀ savoir : Taxawu Daara et Avancé ouvrent exactement les mêmes '
                'modules. Le catalogue le dit, et fonde l’écart de prix sur '
                'l’éligibilité au programme, pas sur le périmètre.'))
        if perimetre.get('PRO') == perimetre.get('ESSAI'):
            self.stdout.write(self.style.WARNING(
                'À savoir : la licence Pro ouvre les mêmes modules que l’essai '
                'gratuit. L’essai est limité à trente jours, mais le périmètre '
                'est identique.'))
