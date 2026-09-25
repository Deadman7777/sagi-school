"""Construit le guide de formation à partir de sa source.

Source : `guide.html`, qui référence `captures/*.webp` et `assets/*.woff2`.
Produits :
  - docs/guide-formation-sagi-school.html    (un seul fichier, tout embarqué)
  - sama_assistant_hady/guide-formation-sagi-school.html  (même fichier)
  - docs/guide-formation-sagi-school.pdf     (les deux volets)
  - docs/guide-utilisateur-sagi-school.pdf   (volet 1)
  - docs/manuel-formateur-sagi-school.pdf    (volet 2)

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
MARQUE_VOLET_2 = '<!-- VOLET 2 -->'

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


def volet(html, numero):
    """Le même document réduit à un volet : même style, même couverture."""
    coupe = html.index(MARQUE_VOLET_2)
    fin = html.index('</div><!-- /bloc -->')
    if numero == 1:
        return html[:coupe] + html[fin:]
    couverture = html[:html.index('</header>') + len('</header>')].replace(
        "Guide d'utilisation<br>et support de formation", 'Manuel du formateur')
    return couverture + '\n' + html[coupe:fin] + html[fin:]


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


def main():
    source = (ICI / 'guide.html').read_text(encoding='utf-8')
    complet = embarquer(source)
    for cible in (DOCS / 'guide-formation-sagi-school.html',
                  RACINE / 'sama_assistant_hady' / 'guide-formation-sagi-school.html'):
        cible.write_text(complet, encoding='utf-8')
        print(f'  {cible.relative_to(RACINE)} — {len(complet) / 1e6:.1f} Mo')
    imprimer(complet, DOCS / 'guide-formation-sagi-school.pdf')
    imprimer(embarquer(volet(source, 1)), DOCS / 'guide-utilisateur-sagi-school.pdf')
    imprimer(embarquer(volet(source, 2)), DOCS / 'manuel-formateur-sagi-school.pdf')


if __name__ == '__main__':
    main()
