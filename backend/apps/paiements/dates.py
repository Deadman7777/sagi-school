"""Dates d'un règlement : jusqu'où accepter une avance, et à quel mois la rattacher.

Les familles paient avant la rentrée. Une école qui ouvre le 1er octobre
encaisse des inscriptions dès septembre, parfois plus tôt. Deux règles :

**On accepte l'avance.** Un règlement daté avant la rentrée est valable jusqu'à
`AVANCE_MAX_MOIS` mois avant elle ; au-delà, c'est une erreur de saisie (année
précédente, faute de frappe). Après la fin de l'exercice, jamais : la somme
n'appartient plus à cette année.

**On la rattache au premier mois de l'année.** Un encaissement de septembre ne
doit pas apparaître « en septembre » dans le suivi d'une année qui commence en
octobre : ce mois n'existe pas dans son calendrier, et la somme deviendrait
invisible. Il compte donc sur le premier mois facturé.
"""
import datetime

AVANCE_MAX_MOIS = 3


def plus_tot_accepte(exercice):
    """Date la plus ancienne acceptée pour un règlement de cet exercice."""
    debut = exercice.date_debut
    mois = debut.month - AVANCE_MAX_MOIS
    annee = debut.year
    while mois <= 0:
        mois += 12
        annee -= 1
    import calendar
    return datetime.date(annee, mois, min(debut.day, calendar.monthrange(annee, mois)[1]))


def mois_de_rattachement(exercice, jour):
    """(année, mois) où compter un encaissement daté `jour`.

    Avant la rentrée : le premier mois de l'année scolaire. Sinon : son mois.
    """
    if jour is None:
        return None
    if jour < exercice.date_debut:
        return (exercice.date_debut.year, exercice.date_debut.month)
    return (jour.year, jour.month)


def est_premier_mois(exercice, annee, mois):
    return (annee, mois) == (exercice.date_debut.year, exercice.date_debut.month)
