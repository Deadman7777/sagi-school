"""Ordre des élèves dans les listes exportées.

Une liste d'école se lit dans un ordre précis, et cet ordre n'est pas le même
d'un établissement à l'autre : un complexe qui a un internat Tahfiiz, une
demi-pension et un externat veut voir ses groupes dans SON ordre, pas dans
l'ordre alphabétique. Le choix appartient donc à l'école (`Section.ordre`,
`Classe.ordre`), et l'export se contente de l'appliquer.

À l'intérieur d'un groupe, deux ordres possibles :

- **alphabétique** (par défaut) : NOM DE FAMILLE, puis prénoms. Les écoles
  écrivent « Prénom NOM » (« Moustapha GUEYE ») : trier le texte tel quel
  rangeait les élèves par PRÉNOM, et une liste de classe paraissait mélangée.
  Le nom de famille est la suite de mots en MAJUSCULES qui termine le nom ; à
  défaut, le dernier mot. Accents et casse ne comptent pas (« Ndèye » = « NDEYE »).
- **ancienneté** : le MATRICULE croissant, du plus ancien au plus récent — le
  matricule promo (`AAAA-CODE-NNNN`) porte l'année d'entrée puis le rang.

Un module à part parce que les deux exports (financier et nominatif) doivent
trier de la même façon : deux tris séparés finiraient par diverger, et les
deux documents cesseraient d'être comparables ligne à ligne.
"""
import re
import unicodedata

# Regroupements proposés. `ecole` = pas de regroupement : toute l'école dans une
# seule liste. `matricule` (ancienne valeur) = toute l'école, par ancienneté.
GROUPES = ('section', 'classe', 'ecole', 'matricule')
ORDRES = ('alpha', 'matricule')


def _sans_accents(texte):
    decompose = unicodedata.normalize('NFKD', texte or '')
    return ''.join(c for c in decompose if not unicodedata.combining(c)).upper().strip()


def _en_majuscules(mot):
    lettres = [c for c in mot if c.isalpha()]
    # Deux lettres au moins : une initiale (« Mame A. DIOP ») n'est pas un nom.
    return len(lettres) >= 2 and all(c.isupper() for c in lettres)


def cle_nom(nom_complet):
    """(nom de famille, prénoms, nom complet) sans accents ni casse.

    « Mame Diarra BA » → ('BA', 'MAME DIARRA', …) ; « moussa diop » → ('DIOP',
    'MOUSSA', …) ; « AWA NDIAYE », tout en majuscules → dernier mot.
    """
    mots = (nom_complet or '').split()
    if not mots:
        return ('', '', '')
    debut = len(mots)
    while debut > 0 and _en_majuscules(mots[debut - 1]):
        debut -= 1
    if debut == 0 or debut == len(mots):
        famille, prenoms = mots[-1:], mots[:-1]
    else:
        famille, prenoms = mots[debut:], mots[:debut]
    return (_sans_accents(' '.join(famille)), _sans_accents(' '.join(prenoms)),
            _sans_accents(nom_complet))


def libelle_tri(nom_complet):
    """« GUEYE Moustapha » : la clé alphabétique, lisible, pour l'écran."""
    famille, prenoms, _ = cle_nom(nom_complet)
    return f'{famille} {prenoms}'.strip()


def _naturel(texte):
    """Découpe un texte en blocs comparables, chiffres lus comme des nombres.

    Sans cela « A-9 » passerait après « A-12 » : un tri de chaînes compare
    caractère à caractère, et « 1 » précède « 9 ». Les écoles qui ont leur
    propre numérotation en font largement les frais.
    """
    parties = []
    for bloc in re.findall(r'\d+|\D+', texte):
        if bloc.isdigit():
            # Le rang du tuple sépare nombres et lettres : à position égale,
            # un nombre passe toujours avant du texte, de façon déterministe.
            parties.append((0, int(bloc), ''))
        else:
            parties.append((1, 0, bloc.upper()))
    return parties


def cle_matricule(eleve):
    """Clé d'ancienneté : matricule croissant, sans matricule à la fin.

    Une fiche sans matricule ne doit ni faire échouer le tri ni se glisser au
    milieu : elle se range à la fin, où elle se voit et se corrige. À défaut
    de matricule on départage sur le nom, pour que deux éditions successives
    de la même liste sortent dans le même ordre.
    """
    matricule = (eleve.matricule or '').strip()
    nom = (eleve.nom_complet or '').upper()
    if not matricule:
        return (1, [], nom)
    return (0, _naturel(matricule), nom)


def cle_groupe(eleve, groupe):
    """Rang du groupe de l'élève, dans l'ordre choisi par l'école.

    Les élèves sans section (ou sans classe) ferment la marche : les noyer
    dans le premier groupe reviendrait à les y attribuer.
    """
    if groupe == 'classe':
        objet = eleve.classe
    elif groupe == 'section':
        objet = eleve.section
    else:
        return ()
    if objet is None:
        return (1, 0, '')
    return (0, objet.ordre or 0, (objet.nom or '').upper())


def trier(eleves, groupe='section', ordre='alpha'):
    """Ordonne des élèves pour un export : groupe de l'école, puis ordre choisi.

    `groupe` : 'section', 'classe' ou 'ecole' (aucun regroupement) ;
    `ordre` : 'alpha' (nom de famille, prénoms) ou 'matricule' (ancienneté).
    L'ancienne valeur `groupe='matricule'` vaut « toute l'école, par
    ancienneté ». Une valeur inconnue prend le défaut plutôt que de refuser
    l'export : un paramètre fautif ne doit pas priver l'école de sa liste.
    """
    if groupe == 'matricule':
        groupe, ordre = 'ecole', 'matricule'
    if groupe not in GROUPES:
        groupe = 'ecole'
    if ordre not in ORDRES:
        ordre = 'alpha'
    if ordre == 'alpha':
        return sorted(eleves, key=lambda e: (cle_groupe(e, groupe), cle_nom(e.nom_complet),
                                             cle_matricule(e)))
    return sorted(eleves, key=lambda e: (cle_groupe(e, groupe), cle_matricule(e)))
