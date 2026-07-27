"""Attribution du matricule — ancré sur l'entrée dans l'établissement.

Format : ``AAAA-CODE-NNNN`` — par exemple ``2025-SHE-0042``.

  * ``AAAA`` = année de début de l'exercice où l'élève est entré (sa promo) ;
  * ``CODE`` = code de l'établissement ;
  * ``NNNN`` = rang dans la promo, par ordre d'entrée.

Le matricule se lit donc tout seul : « 42ᵉ élève entré en 2025-2026 ». C'est
ce qui donne une base ordonnée des premiers aux derniers inscrits, promo par
promo, et qui reste vraie année après année — le matricule est attribué UNE
fois et suit l'enfant jusqu'à sa sortie (la réinscription le recopie).

L'ancien format prenait l'année CIVILE du jour de la saisie et un compteur
global à l'école : deux élèves d'une même promo saisis en septembre puis en
janvier portaient deux années différentes, et le numéro ne disait rien de la
cohorte. Voir la commande ``rebaser_matricules`` pour reprendre l'existant.

Le rang suit l'ordre de création dans le système, que le rebasage réaligne
sur l'ordre chronologique réel. Un élève saisi après coup avec une date
d'entrée ancienne prend donc le rang suivant, pas sa place chronologique :
un matricule déjà attribué ne se renumérote pas dans le dos de l'école.
"""
import re

from django.db.models import Max

LONGUEUR_CODE = 8   # garde le matricule sous les 20 caractères du champ


def code_etablissement(tenant):
    """Code court de l'école, en majuscules. 'ETB' par défaut."""
    code = (getattr(tenant, 'code_etablissement', '') or 'ETB').upper()
    return re.sub(r'[^A-Z0-9]', '', code)[:LONGUEUR_CODE] or 'ETB'


def annee_promo(exercice):
    """Année de début de l'exercice — la promo. Toujours lue sur date_debut :
    annee_scolaire est une saisie libre et peut être n'importe quoi."""
    return exercice.date_debut.year


def libelle_promo(exercice):
    """Libellé de la promo pour l'affichage (« 2025-2026 »)."""
    annee = annee_promo(exercice)
    libelle = (exercice.annee_scolaire or '').strip()
    # On ne garde le libellé de l'école que s'il commence bien par l'année
    # calculée, sinon il induirait en erreur à côté du matricule.
    if libelle.startswith(str(annee)):
        return libelle
    return f"{annee}-{annee + 1}"


def dernier_rang(tenant, annee):
    """Plus haut rang déjà attribué dans la promo `annee` pour cette école.

    Lu sur les matricules existants plutôt que sur un compteur stocké : c'est
    auto-réparateur (une fiche supprimée ne trouera pas la suite, un rebasage
    n'a rien à resynchroniser) et ça reste juste quand le même enfant porte
    plusieurs fiches, une par exercice.
    """
    from .models import Eleve

    rang = 0
    for m in (Eleve.objects.filter(tenant=tenant, matricule__startswith=f"{annee}-")
                           .values_list('matricule', flat=True)):
        if nums := re.findall(r'\d+', m or ''):
            rang = max(rang, int(nums[-1]))
    return rang


class Attributeur:
    """Attribue numéros et matricules à une série de nouveaux entrants.

    L'état (dernier numéro, dernier rang de promo) est lu UNE fois puis tenu
    en mémoire : un import de 2000 élèves ne doit pas relire toute la table à
    chaque ligne. À usage unique, dans une transaction.
    """

    def __init__(self, tenant, exercice):
        from .models import Eleve

        self.tenant   = tenant
        self.exercice = exercice
        self.annee    = annee_promo(exercice)
        self.promo    = libelle_promo(exercice)
        self.code     = code_etablissement(tenant)
        self._numero  = (Eleve.objects.filter(tenant=tenant)
                                      .aggregate(m=Max('numero'))['m'] or 0)
        self._rang    = dernier_rang(tenant, self.annee)
        # Matricules fournis par l'école (colonne Excel remplie) : ils peuvent
        # entrer en collision avec ceux qu'on génère, on les garde en vue.
        self._pris    = set()

    def _matricule_libre(self):
        while True:
            self._rang += 1
            matricule = f"{self.annee}-{self.code}-{self._rang:04d}"
            if matricule not in self._pris:
                return matricule

    def suivant(self, *, matricule=None, date_entree=None):
        """Champs d'identité du prochain entrant : {numero, matricule,
        annee_entree, date_entree}, à passer tel quel à la création.

        `matricule` fourni est respecté — l'école garde la main sur sa propre
        numérotation quand elle en a déjà une.
        """
        self._numero += 1
        if matricule:
            self._pris.add(matricule)
        else:
            matricule = self._matricule_libre()
            self._pris.add(matricule)
        return {
            'numero':       self._numero,
            'matricule':    matricule,
            'annee_entree': self.promo,
            'date_entree':  date_entree or self.exercice.date_debut,
        }


def identite_nouvel_eleve(tenant, exercice, *, matricule=None, date_entree=None):
    """Raccourci pour une création isolée (fiche saisie à la main)."""
    return Attributeur(tenant, exercice).suivant(matricule=matricule,
                                                 date_entree=date_entree)


def resoudre_entree(eleve):
    """Remonte la chaîne des réinscriptions et rend (exercice, date) d'entrée.

    Une fiche par exercice, chaînée par `eleve_precedent` : la fiche la plus
    ancienne porte la vraie entrée. Sa `date_inscription` est fiable car elle
    n'a jamais été repositionnée — c'est aux fiches SUIVANTES que le report
    écrase la date pour le prorata.
    """
    vus = set()
    fiche = eleve
    while fiche.eleve_precedent_id and fiche.eleve_precedent_id not in vus:
        vus.add(fiche.id)
        fiche = fiche.eleve_precedent
    return fiche.exercice, (fiche.date_inscription or fiche.exercice.date_debut)
