"""Rebasage des matricules sur le format promo — reprise de l'existant.

Les écoles déjà installées portent des matricules ``AAAA-CODE-NNNNNN`` où
``AAAA`` est l'année CIVILE du jour de la saisie et ``NNNNNN`` un compteur
global : deux élèves d'une même promo saisis en septembre puis en janvier
portent deux années différentes, et le numéro ne dit rien de la cohorte.

Ce module renumérote la base au format ``AAAA-CODE-NNNN`` (voir matricules.py),
par ordre chronologique d'entrée, et conserve l'ancien matricule dans
``matricule_ancien`` — les carnets papier et les anciens reçus de l'école
restent exploitables.

Trois précautions :

  * un même enfant possède une fiche PAR exercice ; toutes les fiches d'un
    même enfant reçoivent le même matricule, sinon on casserait justement le
    suivi année après année qu'on cherche à établir ;
  * les fiches sont regroupées par chaîne de réinscription ET par matricule
    identique — le report lie normalement les fiches, mais une fiche créée à
    la main ou importée avant le report peut ne pas l'être ;
  * l'écriture se fait en deux passes (matricules parqués sur une valeur
    temporaire, puis valeur finale) : sans cela, réattribuer un matricule
    déjà porté par un autre élève violerait la contrainte d'unicité en cours
    de route.

Rejouable : un second passage recalcule exactement les mêmes matricules et
ne touche plus rien.
"""
from django.db import transaction

from .matricules import annee_promo, code_etablissement, libelle_promo
from .models import Eleve
# Le regroupement des fiches par enfant réel est partagé avec le parcours :
# une seule définition de « c'est le même enfant » dans toute l'application.
from .parcours import grouper_par_eleve


def _entree(groupe):
    """(exercice, date) d'entrée d'un enfant : sa fiche la plus ancienne.

    La `date_inscription` de cette fiche-là est fiable — c'est aux fiches
    SUIVANTES que le report l'écrase avec le début d'exercice pour le prorata.
    """
    premiere = min(groupe, key=lambda f: (f.exercice.date_debut, f.created_at))
    return premiere.exercice, (premiere.date_inscription or premiere.exercice.date_debut)


def calculer_rebasage(tenant):
    """Calcule la renumérotation sans rien écrire.

    Rend {'lignes': [...], 'nb_eleves', 'nb_changements'} ; chaque ligne :
    {groupe, nom_complet, ancien, nouveau, promo, date_entree, nb_fiches}.
    """
    fiches = list(Eleve.objects.filter(tenant=tenant)
                               .select_related('exercice')
                               .order_by('created_at'))
    code = code_etablissement(tenant)

    enfants = []
    for groupe in grouper_par_eleve(fiches):
        exercice, date_entree = _entree(groupe)
        enfants.append({
            'groupe':      groupe,
            'exercice':    exercice,
            'date_entree': date_entree,
            'nom_complet': groupe[0].nom_complet,
        })

    # Ordre chronologique réel : promo, puis date d'entrée, puis ordre de
    # création (départage stable des élèves entrés le même jour).
    # La promo se lit sur la DATE D'ENTRÉE réelle, pas sur l'exercice de la
    # fiche : une migration verse tous les élèves dans l'exercice courant, et
    # sans ça un enfant entré en 2021 serait rebasé en promo 2026.
    enfants.sort(key=lambda e: (annee_promo(e['exercice'], e['date_entree']),
                                e['date_entree'],
                                min(f.created_at for f in e['groupe'])))

    rangs = {}
    lignes = []
    for enfant in enfants:
        annee = annee_promo(enfant['exercice'], enfant['date_entree'])
        rangs[annee] = rangs.get(annee, 0) + 1
        nouveau = f"{annee}-{code}-{rangs[annee]:04d}"
        ancien = next((f.matricule for f in enfant['groupe'] if f.matricule), '')
        lignes.append({
            **enfant,
            'promo':     libelle_promo(enfant['exercice'], enfant['date_entree']),
            'ancien':    ancien or '',
            'nouveau':   nouveau,
            'nb_fiches': len(enfant['groupe']),
            'change':    any(f.matricule != nouveau for f in enfant['groupe']),
        })

    return {
        'lignes':         lignes,
        'nb_eleves':      len(lignes),
        'nb_fiches':      len(fiches),
        'nb_changements': sum(1 for l in lignes if l['change']),
    }


def appliquer_rebasage(tenant):
    """Écrit la renumérotation. Rend le même rapport, augmenté de
    'nb_fiches_ecrites'.

    Les fiches sont d'abord parquées sur un matricule temporaire pour que la
    contrainte d'unicité (tenant, exercice, matricule) ne saute pas quand un
    matricule cible est encore porté par un autre élève.
    """
    rapport = calculer_rebasage(tenant)
    a_changer = [l for l in rapport['lignes'] if l['change']]
    ecrites = 0

    with transaction.atomic():
        for i, ligne in enumerate(a_changer):
            for j, fiche in enumerate(ligne['groupe']):
                Eleve.objects.filter(id=fiche.id).update(
                    matricule=f"TMP-{i:05d}-{j:03d}")

        for ligne in a_changer:
            for fiche in ligne['groupe']:
                # matricule_ancien n'est renseigné qu'une fois : un second
                # rebasage ne doit pas écraser le matricule d'origine de
                # l'école par un intermédiaire que nous avons nous-mêmes créé.
                ancien = fiche.matricule_ancien or ligne['ancien'] or ''
                Eleve.objects.filter(id=fiche.id).update(
                    matricule=ligne['nouveau'],
                    matricule_ancien=ancien if ancien != ligne['nouveau'] else '',
                    annee_entree=ligne['promo'],
                    date_entree=ligne['date_entree'],
                )
                ecrites += 1

        # Les élèves déjà au bon matricule peuvent quand même manquer de
        # promo / date d'entrée (base d'avant le lot 2).
        for ligne in rapport['lignes']:
            if ligne['change']:
                continue
            for fiche in ligne['groupe']:
                if (fiche.annee_entree == ligne['promo']
                        and fiche.date_entree == ligne['date_entree']):
                    continue
                Eleve.objects.filter(id=fiche.id).update(
                    annee_entree=ligne['promo'], date_entree=ligne['date_entree'])
                ecrites += 1

    rapport['nb_fiches_ecrites'] = ecrites
    return rapport
