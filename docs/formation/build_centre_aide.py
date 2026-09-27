"""Centre d'aide interactif SAGI SCHOOL, construit à partir du guide utilisateur.

Le texte n'est PAS réécrit : chaque chapitre de `guide.html` devient un article,
chaque intertitre (h3) une rubrique repliable. Ce script ne fait que découper,
indexer pour la recherche et typer les blocs (étapes, alertes, captures,
checklists) ; toute la présentation vit dans le gabarit `centre_aide.html`.

Produit : docs/centre-aide/index.html (les captures et les polices restent dans
docs/formation/ et sont publiées à côté, sous captures/ et assets/).

Usage : python3 docs/formation/build_centre_aide.py
"""
import json
import re
import unicodedata
from pathlib import Path

from bs4 import BeautifulSoup

ICI = Path(__file__).resolve().parent
SORTIE = ICI.parent / 'centre-aide' / 'index.html'

# Catégories du centre d'aide : l'ordre du guide, regroupé par domaine.
CATEGORIES = [
    ('demarrer', 'Bien démarrer', 'Installation, licences et paramétrage initial',
     ['nouveautes', 'apercu', 'licences', 'demarrage', 'parametrage-az']),
    ('scolarite', 'Scolarité', 'Élèves, familles, garderie et notes',
     ['eleves', 'familles', 'garderie', 'academique']),
    ('finances', 'Finances', 'Encaissements, suivi, comptabilité et fiscalité',
     ['paiements', 'suivi', 'comptabilite', 'fiscal', 'gmrf', 'gouvernance']),
    ('personnel', 'Personnel', 'Salariés, paie et avances',
     ['rh']),
    ('administration', 'Administration', 'Réglages de l\'école, sauvegarde et clôture',
     ['parametres', 'licence-cloture']),
]

# Profils = rôles de l'application (menu de shell.component.ts), plus un
# parcours « mise en service » pour la personne qui installe.
PROFILS = [
    ('direction', 'Direction', 'Admin École : tout l\'établissement', None),
    ('installation', 'Mise en service', 'Premier paramétrage de l\'école',
     ['parametrage-az', 'demarrage', 'licences', 'parametres', 'licence-cloture']),
    ('scolarite', 'Scolarité', 'Inscriptions, encaissements, notes',
     ['apercu', 'eleves', 'familles', 'garderie', 'paiements', 'suivi', 'academique']),
    ('comptable', 'Comptabilité', 'Charges, états financiers, fiscal',
     ['apercu', 'paiements', 'suivi', 'comptabilite', 'fiscal', 'gmrf', 'gouvernance',
      'licence-cloture']),
    ('rh', 'Ressources humaines', 'Personnel, paie, avances',
     ['apercu', 'rh']),
    ('lecteur', 'Lecture seule', 'Consultation du tableau de bord',
     ['apercu', 'suivi']),
]


def slug(texte):
    t = unicodedata.normalize('NFKD', texte).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', t).strip('-')[:48]


def texte_brut(html):
    return ' '.join(BeautifulSoup(html, 'html.parser').get_text(' ').split())


def sans_pastille(el):
    """Titre sans la pastille « Nouveau » ; dit s'il la portait."""
    nouveau = False
    for p in el.select('.nouveau'):
        p.decompose()
        nouveau = True
    return ' '.join(el.get_text(' ').split()), nouveau


def typer(fragment):
    """Donne à chaque bloc du guide son rôle dans le centre d'aide."""
    for note in fragment.select('div.note'):
        genre = next((c for c in ('info', 'piege', 'erreur') if c in note['class']), 'info')
        note['class'] = ['alerte', f'alerte-{genre}']
    for ol in fragment.select('ol.pas'):
        ol['class'] = ['etapes']
    for fig in fragment.select('figure'):
        fig['class'] = ['capture'] + (['document'] if 'papier-doc' in fig.get('class', []) else [])
        img = fig.find('img')
        if img:
            img['loading'] = 'lazy'
            img['decoding'] = 'async'
    for span in fragment.select('span.nouveau'):
        span['class'] = ['badge-nouveau']
    return fragment


def checklist(el, cle):
    """Liste ou tableau → checklist cochable (état gardé dans le navigateur)."""
    lignes = []
    if el.name == 'ul':
        lignes = [li.decode_contents().strip() for li in el.find_all('li', recursive=False)]
    else:
        for tr in el.select('tbody tr'):
            tds = tr.find_all('td')
            lignes.append(f'{tds[1].decode_contents()}<span class="ou">{tds[2].decode_contents()}</span>')
    items = ''.join(
        f'<li><label><input type="checkbox" data-coche="{cle}-{i}"><span>{l}</span></label></li>'
        for i, l in enumerate(lignes))
    return BeautifulSoup(f'<ul class="checklist" data-liste="{cle}">{items}</ul>', 'html.parser')


def main():
    soupe = BeautifulSoup((ICI / 'guide.html').read_text(encoding='utf-8'), 'html.parser')
    libelles_nav = {a['href'][1:]: ' '.join(a.get_text(' ').split())
                    for a in soupe.select('nav a[href^="#"]')}
    meta = {dt.get_text(strip=True): dd.get_text(strip=True)
            for dt, dd in zip(soupe.select('.couv dt'), soupe.select('.couv dd'))}

    articles = {}
    for sec in soupe.select('main section'):
        aid = sec['id']
        eyebrow = sec.find('span', class_='eyebrow', recursive=False)
        h2 = sec.find('h2', recursive=False)
        titre, nouveau = sans_pastille(h2)
        chapeau = sec.find('p', class_='chapeau', recursive=False)
        licences = [{'nom': p.get_text(strip=True), 'inclus': 'oui' in p.get('class', [])}
                    for p in sec.select(':scope > .pastilles .pastille')]

        intro, rubriques, courante = [], [], None
        for enfant in sec.find_all(recursive=False):
            if enfant in (eyebrow, h2, chapeau) or 'pastilles' in (enfant.get('class') or []):
                continue
            if enfant.name == 'h3':
                t, n = sans_pastille(enfant)
                courante = {'id': f'{aid}--{slug(t)}', 'titre': t, 'nouveau': n, 'blocs': []}
                rubriques.append(courante)
                continue
            (courante['blocs'] if courante else intro).append(enfant)

        def rendre(blocs, cle):
            frag = BeautifulSoup('', 'html.parser')
            for b in blocs:
                frag.append(b)
            typer(frag)
            return str(frag)

        rubs = []
        for r in rubriques:
            blocs = r['blocs']
            if aid == 'parametrage-az':
                # Les pièces à réunir et la liste de contrôle finale deviennent
                # des checklists cochables.
                blocs = [checklist(b.find('table') if b.name == 'div' and b.find('table') else b,
                                   r['id'])
                         if (b.name == 'ul' and r['titre'].startswith('Avant'))
                         or (b.name == 'div' and b.find('table') and 'contrôle' in r['titre'])
                         else b for b in blocs]
            html = rendre(blocs, r['id'])
            rubs.append({'id': r['id'], 'titre': r['titre'], 'nouveau': r['nouveau'],
                         'etape': bool(re.match(r'Étape \d+', r['titre'])),
                         'html': html, 'texte': texte_brut(html)})

        intro_html = rendre(intro, aid)
        articles[aid] = {
            'id': aid,
            'titre': titre,
            'court': libelles_nav.get(aid, titre),
            'nouveau': nouveau,
            'eyebrow': eyebrow.get_text(' ', strip=True) if eyebrow else '',
            'chapeau': chapeau.decode_contents().strip() if chapeau else '',
            'chapeau_texte': texte_brut(str(chapeau)) if chapeau else '',
            'licences': licences,
            'intro': intro_html,
            'intro_texte': texte_brut(intro_html),
            'rubriques': rubs,
        }

    ordre = [a for _, _, _, ids in CATEGORIES for a in ids]
    manquants = set(articles) - set(ordre)
    assert not manquants, f'chapitres sans catégorie : {manquants}'

    donnees = {
        'meta': meta,
        'categories': [{'id': c, 'titre': t, 'sous': s, 'articles': ids}
                       for c, t, s, ids in CATEGORIES],
        'profils': [{'id': p, 'titre': t, 'sous': s, 'articles': ids}
                    for p, t, s, ids in PROFILS],
        'ordre': ordre,
        'articles': articles,
    }
    gabarit = (ICI / 'centre_aide.html').read_text(encoding='utf-8')
    json_donnees = json.dumps(donnees, ensure_ascii=False).replace('</', '<\\/')
    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(gabarit.replace('/*__DONNEES__*/null', json_donnees), encoding='utf-8')
    images = sorted(set(re.findall(r'captures/[\w.-]+\.webp', json_donnees)))
    (SORTIE.parent / 'fichiers.json').write_text(json.dumps(
        {**{i: f'docs/formation/{i}' for i in images},
         **{f'assets/font-{n}.woff2': f'docs/formation/assets/font-{n}.woff2' for n in range(5)}},
        indent=1), encoding='utf-8')
    print(f'  {SORTIE.relative_to(ICI.parent.parent)} — {len(articles)} articles, '
          f'{sum(len(a["rubriques"]) for a in articles.values())} rubriques, {len(images)} captures')


if __name__ == '__main__':
    main()
