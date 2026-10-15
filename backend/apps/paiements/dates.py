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

Une école dont l'année de facturation commence avant la rentrée
(`Exercice.mois_debut_annee`, crèche facturée dès septembre) : ce mois existe,
et c'est de lui que partent les deux règles (`Exercice.debut_facturation`).
"""
import datetime

AVANCE_MAX_MOIS = 3


def plus_tot_accepte(exercice):
    """Date la plus ancienne acceptée pour un règlement de cet exercice."""
    debut = exercice.debut_facturation
    mois = debut.month - AVANCE_MAX_MOIS
    annee = debut.year
    while mois <= 0:
        mois += 12
        annee -= 1
    import calendar
    return datetime.date(annee, mois, min(debut.day, calendar.monthrange(annee, mois)[1]))


def erreur_date_reglement(exercice, jour):
    """Message si `jour` ne peut pas dater un règlement de cet exercice, sinon
    None. Le même contrôle à l'encaissement et à la modification d'un reçu."""
    if jour > exercice.date_fin:
        return (f"Le {jour:%d/%m/%Y} est postérieur à la fin de l'exercice "
                f"{exercice.annee_scolaire} ({exercice.date_fin:%d/%m/%Y}).")
    if jour < plus_tot_accepte(exercice):
        return (f"Le {jour:%d/%m/%Y} précède de plus de {AVANCE_MAX_MOIS} mois la rentrée "
                f"({exercice.date_debut:%d/%m/%Y}) de l'exercice {exercice.annee_scolaire}.")
    return None


def mois_de_rattachement(exercice, jour):
    """(année, mois) où compter un encaissement daté `jour`.

    Avant la rentrée : le premier mois de l'année scolaire. Sinon : son mois.
    """
    if jour is None:
        return None
    debut = exercice.debut_facturation
    if jour < debut:
        return (debut.year, debut.month)
    return (jour.year, jour.month)


def est_premier_mois(exercice, annee, mois):
    debut = exercice.debut_facturation
    return (annee, mois) == (debut.year, debut.month)
