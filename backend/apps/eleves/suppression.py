"""Suppression d'un élève saisi par erreur.

Demandé le 08/10/2026 : « supprimer les élèves saisis par erreur », depuis la
liste des élèves et depuis les anciens. Une suppression efface la fiche, ses
abonnements, ses notes et ses reçus ANNULÉS ; elle ne doit jamais faire
disparaître de l'argent ni une créance de la comptabilité. Elle est donc
refusée, avec la marche à suivre, dès que la fiche porte :

- un reçu actif : l'encaissement est dans le journal (annuler le reçu d'abord) ;
- une bourse ou prise en charge d'un organisme : créance 4112 écrite ;
- un reste des années antérieures : à-nouveau 411/890 écrit ;
- une fiche sur l'année suivante (réinscription) qui pointe vers elle ;
- un exercice clôturé : les comptes de cette année sont arrêtés.

Un reçu annulé a déjà son écriture et son extourne, qui se compensent : il
part avec la fiche, son numéro est conservé dans le journal d'audit.

Un enfant qui a réellement fréquenté l'école ne se supprime pas : il sort
(Changer statut), et reste dans la base des anciens.
"""
from .parcours import grouper_par_eleve


class SuppressionRefusee(Exception):
    def __init__(self, motifs):
        super().__init__('; '.join(motifs))
        self.motifs = motifs


def _fmt(montant):
    return f"{float(montant):,.0f}".replace(',', ' ')


def obstacles(fiche, fiches_supprimees=()):
    """Les raisons qui interdisent de supprimer `fiche` (liste vide = permis).

    `fiches_supprimees` : les autres fiches supprimées en même temps (tout le
    parcours d'un ancien) ; une réinscription qui en fait partie n'est pas un
    obstacle."""
    annee = fiche.exercice.annee_scolaire if fiche.exercice_id else ''
    motifs = []
    if fiche.exercice_id and fiche.exercice.cloture:
        motifs.append(f"L'exercice {annee} est clôturé : ses comptes sont arrêtés.")
    actifs = list(fiche.paiements.filter(statut='ACTIF').values_list('no_piece', flat=True))
    if actifs:
        motifs.append(f"{len(actifs)} reçu(s) actif(s) en {annee} ({', '.join(actifs[:5])}"
                      f"{'…' if len(actifs) > 5 else ''}) : annulez-les d'abord dans Paiements.")
    if fiche.prises_en_charge_organisme.exists():
        motifs.append(f"Une bourse / prise en charge d'organisme est enregistrée en {annee} : "
                      "retirez-la d'abord.")
    if float(fiche.reliquat_anterieur or 0) != 0:
        motifs.append(f"La fiche {annee} porte un reste des années antérieures "
                      f"({_fmt(fiche.reliquat_anterieur)} F) inscrit en comptabilité.")
    ids = {f.id for f in fiches_supprimees}
    suivantes = [f for f in fiche.reinscriptions.all() if f.id not in ids]
    if suivantes:
        motifs.append(f"L'élève est réinscrit en {suivantes[0].exercice.annee_scolaire} : "
                      "supprimez d'abord cette fiche-là.")
    return motifs


def fiches_du_parcours(fiche):
    """Toutes les fiches du même enfant (mêmes règles que la base des anciens)."""
    from .models import Eleve
    toutes = list(Eleve.objects.filter(tenant_id=fiche.tenant_id).select_related('exercice'))
    for groupe in grouper_par_eleve(toutes):
        if any(f.id == fiche.id for f in groupe):
            return groupe
    return [fiche]


def supprimer(fiche, tout_le_parcours=False):
    """Supprime la fiche (ou tout le parcours) ; rend un résumé pour l'audit.
    Lève SuppressionRefusee sans rien toucher si un obstacle existe."""
    from django.db import transaction

    fiches = fiches_du_parcours(fiche) if tout_le_parcours else [fiche]
    motifs = []
    for f in fiches:
        motifs += obstacles(f, fiches)
    if motifs:
        raise SuppressionRefusee(motifs)

    annules = []
    for f in fiches:
        annules += list(f.paiements.values_list('no_piece', flat=True))
    resume = {
        'nom_complet': fiche.nom_complet,
        'matricule':   fiche.matricule or '',
        'annees':      sorted(f.exercice.annee_scolaire for f in fiches if f.exercice_id),
        'nb_fiches':   len(fiches),
        'recus_annules': annules,
    }
    with transaction.atomic():
        # Les plus récentes d'abord : une réinscription pointe vers la fiche
        # d'avant (SET_NULL, mais autant ne pas réécrire ce qu'on efface).
        for f in sorted(fiches, key=lambda x: x.exercice.date_debut, reverse=True):
            f.delete()
    return resume
