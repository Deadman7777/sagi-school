"""Construit le guide utilisateur et le manuel du formateur, séparément.

Sources :
  - `guide.html`            : Guide d'utilisation, REMIS AUX ÉCOLES.
  - `manuel-formateur.html` : Manuel du formateur, document INTERNE HADY GESMAN.
Les deux référencent `captures/*.webp` et `assets/*.woff2`.

Produits (chaque fichier autonome, images et polices embarquées) :
  - docs/guide-utilisateur-sagi-school.html / .pdf
  - docs/manuel-formateur-sagi-school.html  / .pdf
  - sama_assistant_hady/guide-utilisateur-sagi-school.html (copie du guide
    utilisateur SEUL : le manuel formateur ne sort pas de HADY GESMAN)

Usage : python3 docs/formation/build.py   (Chrome et Ghostscript requis)
"""
import base64
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ICI = Path(__file__).resolve().parent
DOCS = ICI.parent
RACINE = DOCS.parent
CHROME = shutil.which('google-chrome') or shutil.which('chromium')

TYPES = {'.webp': 'image/webp', '.png': 'image/png', '.jpg': 'image/jpeg',
         '.woff2': 'font/woff2'}


def embarquer(html):
    """Remplace chaque fichier référencé par son contenu en data URI."""
    def data_uri(chemin):
        fichier = ICI / chemin
        return f'data:{TYPES[fichier.suffix]};base64,' + \
            base64.b64encode(fichier.read_bytes()).decode()
    html = re.sub(r'src="(captures/[^"]+)"', lambda m: f'src="{data_uri(m.group(1))}"', html)
    return re.sub(r'url\((assets/[^)]+)\)', lambda m: f'url({data_uri(m.group(1))})', html)


def imprimer(html, pdf):
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / 'guide.html'
        brut = Path(tmp) / 'brut.pdf'
        # Le PDF se lit sur papier : thème clair imposé, quel que soit le
        # réglage du poste qui le produit.
        source.write_text(html.replace('<html', '<html data-theme="light"', 1)
                          if '<html' in html else
                          '<html data-theme="light">' + html + '</html>', encoding='utf-8')
        subprocess.run([CHROME, '--headless', '--no-sandbox', '--disable-gpu',
                        '--no-pdf-header-footer', f'--print-to-pdf={brut}',
                        '--virtual-time-budget=20000', source.as_uri()],
                       check=True, capture_output=True)
        # Ghostscript recompresse les images : le PDF passe d'environ 15 Mo à 3.
        subprocess.run(['gs', '-q', '-dNOPAUSE', '-dBATCH', '-sDEVICE=pdfwrite',
                        '-dPDFSETTINGS=/ebook', '-dCompatibilityLevel=1.6',
                        f'-sOutputFile={pdf}', str(brut)], check=True)
    infos = subprocess.run(['pdfinfo', str(pdf)], capture_output=True, text=True).stdout
    pages = re.search(r'Pages:\s+(\d+)', infos).group(1)
    print(f'  {pdf.relative_to(RACINE)} — {pages} pages')


def ecrire(html, cible):
    cible.write_text(html, encoding='utf-8')
    print(f'  {cible.relative_to(RACINE)} — {len(html) / 1e6:.1f} Mo')


def main():
    guide = embarquer((ICI / 'guide.html').read_text(encoding='utf-8'))
    manuel = embarquer((ICI / 'manuel-formateur.html').read_text(encoding='utf-8'))
    # Garde-fou : le guide remis aux écoles ne contient rien du manuel interne.
    assert 'Manuel du formateur' not in guide, 'le manuel formateur a fui dans le guide utilisateur'

    ecrire(guide, DOCS / 'guide-utilisateur-sagi-school.html')
    ecrire(guide, RACINE / 'sama_assistant_hady' / 'guide-utilisateur-sagi-school.html')
    ecrire(manuel, DOCS / 'manuel-formateur-sagi-school.html')
    imprimer(guide, DOCS / 'guide-utilisateur-sagi-school.pdf')
    imprimer(manuel, DOCS / 'manuel-formateur-sagi-school.pdf')


if __name__ == '__main__':
    main()
