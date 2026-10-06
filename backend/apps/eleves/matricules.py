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


def exercices_de(tenant_id):
    """Les exercices d'une école, lus une fois pour toute une série d'élèves."""
    from apps.paiements.models import Exercice
    return list(Exercice.objects.filter(tenant_id=tenant_id).order_by('date_debut'))


def _promo(exercice, date_entree, exercices=None):
    """(année de promo, exercice de cette promo ou None).

    Règle (décision de l'école L'Éveil, octobre 2026) : la promo est l'ANNÉE
    SCOLAIRE de l'école, lue dans ses exercices — pas l'année civile de la
    date d'inscription. Toute la promo 2026-2027 porte 2026-…, qu'on se soit
    inscrit en juin 2026 (anticipé), en septembre ou en janvier 2027.

      1. Pas de date : l'exercice de la fiche.
      2. Date dans un exercice de l'école : cet exercice.
      3. Date dans les 12 mois qui précèdent la rentrée, sans exercice qui la
         couvre : inscription anticipée, l'exercice de la fiche.
      4. Date plus ancienne (migration : enfant entré en 2021, versé dans
         l'exercice courant) : l'année de sa vraie entrée, avec bascule au mois
         de rentrée. Sans ça le numéro annoncerait l'année où l'école a saisi
         la donnée au lieu de sa promo.

    Toujours lue sur `date_debut`, jamais sur `annee_scolaire` (saisie libre).
    """
    if date_entree is None:
        return exercice.date_debut.year, exercice
    if exercice.date_debut <= date_entree <= exercice.date_fin:
        return exercice.date_debut.year, exercice
    if exercices is None:
        exercices = exercices_de(exercice.tenant_id)
    couvrant = [e for e in exercices if e.date_debut <= date_entree <= e.date_fin]
    if couvrant:
        e = max(couvrant, key=lambda x: x.date_debut)
        return e.date_debut.year, e
    debut = exercice.date_debut
    un_an_avant = debut.replace(year=debut.year - 1) if not (debut.month == 2 and debut.day == 29) \
        else debut.replace(year=debut.year - 1, day=28)
    if un_an_avant <= date_entree < debut:
        return debut.year, exercice
    mois_bascule = debut.month
    annee = (date_entree.year if date_entree.month >= mois_bascule
             else date_entree.year - 1)
    return annee, None


def annee_promo(exercice, date_entree=None, exercices=None):
    """Année de début de la promo (voir `_promo`)."""
    return _promo(exercice, date_entree, exercices)[0]


def libelle_promo(exercice, date_entree=None, exercices=None):
    """Libellé de la promo pour l'affichage : celui de l'exercice de la promo
    quand l'école l'a dans ses exercices (« 2026-2027 »), sinon reconstruit."""
    annee, ex_promo = _promo(exercice, date_entree, exercices)
    ref = ex_promo or exercice
    libelle = (ref.annee_scolaire or '').strip()
    if ex_promo is not None and libelle.startswith(str(annee)):
        return libelle
    # École qui compte en année civile (exercice « 2026 ») : garder ce format
    # pour les promos antérieures aussi, sinon on inventerait un « 2021-2022 »
    # qui ne correspond à aucun exercice de cette école.
    if libelle == str(ref.date_debut.year):
        return str(annee)
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
        self._exercices = exercices_de(tenant.id)
        self.code     = code_etablissement(tenant)
        self._numero  = (Eleve.objects.filter(tenant=tenant)
                                      .aggregate(m=Max('numero'))['m'] or 0)
        # Un rang par promo, pas un seul : un import de migration peut couvrir
        # plusieurs années d'entrée d'un coup. Rempli à la demande — une requête
        # par promo rencontrée, pas une par élève.
        self._rangs   = {}
        # Matricules fournis par l'école (colonne Excel remplie) : ils peuvent
        # entrer en collision avec ceux qu'on génère, on les garde en vue.
        self._pris    = set()

    def _matricule_libre(self, annee):
        if annee not in self._rangs:
            self._rangs[annee] = dernier_rang(self.tenant, annee)
        while True:
            self._rangs[annee] += 1
            matricule = f"{annee}-{self.code}-{self._rangs[annee]:04d}"
            if matricule not in self._pris:
                return matricule

    def suivant(self, *, matricule=None, date_entree=None):
        """Champs d'identité du prochain entrant : {numero, matricule,
        annee_entree, date_entree}, à passer tel quel à la création.

        `matricule` fourni est respecté — l'école garde la main sur sa propre
        numérotation quand elle en a déjà une.
        """
        self._numero += 1
        # La promo se lit sur la date d'entrée réelle quand on l'a : un élève
        # migré entré en 2021 appartient à la promo 2021, même si sa fiche est
        # créée dans l'exercice 2026.
        annee = annee_promo(self.exercice, date_entree, self._exercices)
        if matricule:
            self._pris.add(matricule)
        else:
            matricule = self._matricule_libre(annee)
            self._pris.add(matricule)
        return {
            'numero':       self._numero,
            'matricule':    matricule,
            'annee_entree': libelle_promo(self.exercice, date_entree, self._exercices),
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
