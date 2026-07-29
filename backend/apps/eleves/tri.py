"""Ordre des élèves dans les listes exportées.

Une liste d'école se lit dans un ordre précis, et cet ordre n'est pas le même
d'un établissement à l'autre : un complexe qui a un internat Tahfiiz, une
demi-pension et un externat veut voir ses groupes dans SON ordre, pas dans
l'ordre alphabétique. Le choix appartient donc à l'école (`Section.ordre`,
`Classe.ordre`), et l'export se contente de l'appliquer.

À l'intérieur d'un groupe, une seule règle : le MATRICULE croissant, du plus
ancien au plus récent. C'est l'ordre d'ancienneté — le matricule promo
(`AAAA-CODE-NNNN`) porte l'année d'entrée puis le rang — et c'est celui dans
lequel une école cherche un élève sur une feuille.

Un module à part parce que les deux exports (financier et nominatif) doivent
trier de la même façon : deux tris séparés finiraient par diverger, et les
deux documents cesseraient d'être comparables ligne à ligne.
"""
import re

# Regroupements proposés. `matricule` = pas de regroupement du tout : toute
# l'école dans un seul fil d'ancienneté.
GROUPES = ('section', 'classe', 'matricule')


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


def trier(eleves, groupe='section'):
    """Ordonne des élèves pour un export : groupe de l'école, puis ancienneté.

    `groupe` vaut 'section', 'classe' ou 'matricule' (aucun regroupement).
    Une valeur inconnue est traitée comme 'matricule' plutôt que de refuser
    l'export : un paramètre fautif ne doit pas priver l'école de sa liste.
    """
    if groupe not in GROUPES:
        groupe = 'matricule'
    return sorted(eleves, key=lambda e: (cle_groupe(e, groupe), cle_matricule(e)))
