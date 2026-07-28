"""Écritures SYSCOHADA d'un encaissement de scolarité.

Source unique partagée par la saisie et la modification d'un paiement, pour
qu'un reliquat soit traité identiquement des deux côtés.
"""
from apps.comptabilite.tresorerie import lignes_tresorerie


# Créances sur les organismes payeurs (État, ONG, fondation…), tenues à part
# des créances familles restées en 411. Un bailleur ou un contrôleur demande
# combien l'établissement attend de ses partenaires institutionnels : noyé
# dans le 411, le chiffre est introuvable.
COMPTE_CREANCE_ORGANISME = '4112'


def lignes_paiement(total, part_exercice, ventilation, libelle, organisme=False):
    """Rend les lignes d'écriture d'un règlement d'élève.

    `part_exercice` = frais de l'année en cours → constatation de la créance
    et du produit (411 D / 706 C).

    Le solde (`total − part_exercice`) est un reliquat d'exercice antérieur :
    sa créance a déjà été reconduite en à-nouveaux (411 D / 890 C au report),
    et son produit constaté l'année d'origine. On ne constate donc RIEN de
    plus — l'encaissement se contente de solder le 411. Repasser un 706 ici
    compterait le même produit deux fois.

    Dans les deux cas la trésorerie est débitée du montant réellement encaissé
    (`total`), ventilé par mode, et le 411 est soldé d'autant.

    `organisme=True` : le versement vient d'un tiers payeur. Sa créance a été
    constatée à l'attribution de la bourse (4112 D / 706 C, voir
    eleves.creances_organisme) — l'encaissement se contente donc de solder le
    4112, sans reconstater de produit. Le faire ici compterait la subvention
    deux fois, exactement comme pour un reliquat.
    """
    ecritures = []
    ordre = 1
    if part_exercice > 0 and not organisme:
        ecritures += [
            dict(ordre=1, no_compte='411', debit=part_exercice, credit=0,
                 libelle=f"Créance scolarité — {libelle}"),
            dict(ordre=2, no_compte='706', debit=0, credit=part_exercice,
                 libelle=f"Créance scolarité — {libelle}"),
        ]
        ordre = 3

    compte_creance = COMPTE_CREANCE_ORGANISME if organisme else '411'
    tresor = lignes_tresorerie(ventilation, 'debit', libelle, ordre_debut=ordre)
    ecritures += tresor
    ecritures.append(
        dict(ordre=ordre + len(tresor), no_compte=compte_creance,
             debit=0, credit=total,
             libelle=f"Règlement — {libelle}"))
    return ecritures


def verifier_reliquat(eleve, montant_reliquat, paiement_exclu=None):
    """Contrôle qu'on n'encaisse pas plus de reliquat que l'élève n'en doit.

    Rend un message d'erreur, ou None si tout va bien. `paiement_exclu` sert
    à la modification : le paiement en cours de réécriture ne doit pas être
    compté dans le déjà-réglé."""
    montant = float(montant_reliquat or 0)
    if montant <= 0:
        return None

    du = float(eleve.reliquat_anterieur or 0)
    if du <= 0:
        return ("Cet élève n'a aucun reliquat d'exercice antérieur "
                "à encaisser.")

    from django.db.models import Sum
    qs = eleve.paiements.filter(statut='ACTIF')
    if paiement_exclu is not None:
        qs = qs.exclude(id=paiement_exclu.id)
    deja = float(qs.aggregate(t=Sum('montant_reliquat'))['t'] or 0)
    ouvert = round(du - deja, 2)

    if montant > ouvert + 0.01:
        return (f"Reliquat encaissé ({montant:,.0f} FCFA) supérieur au reliquat "
                f"restant dû ({ouvert:,.0f} FCFA).")
    return None
