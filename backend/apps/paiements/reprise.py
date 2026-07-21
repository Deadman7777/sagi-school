"""Paiement de reprise — migration d'une école avec un historique.

Quand une école bascule sur SAGI SCHOOL en cours d'année, ses élèves ont
déjà réglé une partie des frais dans l'ancien système. On enregistre ces
montants comme un Paiement en mode REPRISE afin que le reste à payer,
le suivi mensuel et les alertes repartent d'un état juste — mais le
règlement est comptabilisé au compte 890 (bilan d'ouverture SYSCOHADA),
PAS en trésorerie : l'argent est déjà compris dans les soldes initiaux
de l'exercice, les canaux (caisse, banque, mobile money) ne bougent pas.

Écritures générées (source PAIEMENT → l'annulation standard fonctionne) :
  1. 411 D / 706 C — créance et produit scolarité (résultat de l'exercice)
  2. 890 D / 411 C — règlement par bilan d'ouverture
"""
import re
from django.db.models import Max

from .models import Paiement


def _prochain_no_piece(tenant):
    """REP-NNNN sur la même séquence numérique que les REC-NNNN du tenant."""
    last = Paiement.objects.filter(tenant=tenant).aggregate(Max('no_piece'))['no_piece__max']
    if last:
        nums = re.findall(r'\d+', last)
        suivant = int(nums[-1]) + 1 if nums else 1
    else:
        suivant = 1
    return f"REP-{suivant:04d}"


def _mois_reprise(exercice, nb):
    """Les nb premiers mois calendaires de l'année scolaire (mêmes numéros
    que mois_regles : ex. exercice débutant en octobre, nb=3 → [10, 11, 12])."""
    mois, m = [], exercice.date_debut.month
    for _ in range(nb):
        mois.append(m)
        m = 1 if m == 12 else m + 1
    return mois


def creer_paiement_reprise(tenant, exercice, eleve, user=None, *,
                           inscription=False, nb_mensualites=0,
                           uniforme=False, fournitures=False, montants=None):
    """Crée le paiement de reprise et ses écritures. Rend le Paiement,
    ou None si tous les montants sont nuls.

    Deux modes :
      - `montants` fourni (dict montant_inscription/mensualite/uniforme/
        fournitures) → montants explicites, ex. reconstruits depuis « À jour »
        ou « Dette actuelle » à l'import ;
      - sinon → calcul depuis les frais de la section et les drapeaux
        inscription/nb_mensualites/uniforme/fournitures.
    """
    section = eleve.section
    if not section:
        return None

    if montants is None:
        nb = min(int(nb_mensualites or 0), exercice.nb_mensualites)
        montants = {
            'montant_inscription': section.frais_inscription if inscription else 0,
            'montant_mensualite':  section.frais_mensualite * nb,
            'montant_uniforme':    section.frais_uniforme if uniforme else 0,
            'montant_fournitures': section.frais_fournitures if fournitures else 0,
        }
    total = sum(montants.values())
    if total <= 0:
        return None

    # Mois réglés = mensualités entières couvertes par le montant mensualité,
    # pour que le suivi mensuel marque les bons mois.
    frais_m = float(section.frais_mensualite) or 0
    nb = (min(int(round(float(montants.get('montant_mensualite', 0)) / frais_m)),
              exercice.nb_mensualites) if frais_m else 0)

    paiement = Paiement.objects.create(
        tenant=tenant, exercice=exercice, eleve=eleve,
        no_piece=_prochain_no_piece(tenant),
        mode_paiement='REPRISE',
        mois_regles=_mois_reprise(exercice, nb),
        observations="Reprise de soldes — montants réglés avant la migration vers SAGI SCHOOL",
        saisi_par=user,
        **montants,
    )

    from apps.comptabilite.models import JournalEntry
    montant = float(paiement.total)
    libelle = f"{eleve.nom_complet} - {paiement.no_piece}"
    ecritures = [
        dict(ordre=1, no_compte='411', debit=montant, credit=0,
             libelle=f"Créance scolarité (reprise) — {libelle}"),
        dict(ordre=2, no_compte='706', debit=0, credit=montant,
             libelle=f"Créance scolarité (reprise) — {libelle}"),
        dict(ordre=3, no_compte='890', debit=montant, credit=0,
             libelle=f"Règlement bilan d'ouverture — {libelle}"),
        dict(ordre=4, no_compte='411', debit=0, credit=montant,
             libelle=f"Règlement bilan d'ouverture — {libelle}"),
    ]
    for e in ecritures:
        JournalEntry.objects.create(
            tenant=tenant, exercice=exercice,
            no_piece=paiement.no_piece,
            date_ecriture=paiement.date_paiement or exercice.date_debut,
            source='PAIEMENT', source_id=paiement.id,
            **e,
        )
    return paiement
