"""Recalage des reliquats déjà reportés pour des élèves SORTIS.

Jusqu'à la décision de septembre 2026, le report des impayés reconduisait pour
un élève parti le reste de TOUTE son année — mois postérieurs au départ
compris. Les à-nouveaux 411/890 déjà passés gonflent donc les créances.

Ce module recalcule, pour chaque fiche portant un tel reliquat, ce qui était
réellement dû au départ (le calendrier s'arrête désormais à la sortie, voir
`echeancier.mois_factures`) et ramène l'impayé antérieur à ce montant par
l'outil existant `definir_impaye_anterieur` — qui réécrit l'à-nouveaux et
refuse de descendre sous ce qui a déjà été encaissé.

Rien n'est modifié sans `appliquer=True`. Les exercices clôturés ne sont pas
touchés.
"""
from apps.eleves.models import Eleve
from apps.eleves.parcours import STATUTS_SORTIE

from .reliquat_migration import definir_impaye_anterieur
from .report_reliquats import _eleves_annotes

SEUIL = 1.0


def _fiche_source(fiche):
    origine = fiche.reliquat_exercice_origine
    if fiche.eleve_precedent_id and fiche.eleve_precedent.exercice_id == origine.id:
        return fiche.eleve_precedent
    if fiche.matricule:
        return Eleve.objects.filter(tenant=fiche.tenant, exercice=origine,
                                    matricule=fiche.matricule).first()
    return None


def recaler_reliquats_sortants(tenant, appliquer=False):
    lignes = []
    fiches = (Eleve.objects.filter(tenant=tenant, reliquat_exercice_origine__isnull=False,
                                   reliquat_anterieur__gt=0, exercice__cloture=False)
              .select_related('exercice', 'reliquat_exercice_origine', 'eleve_precedent__exercice'))
    for fiche in fiches:
        source = _fiche_source(fiche)
        if source is None or source.statut not in STATUTS_SORTIE or not source.date_sortie:
            continue
        annotee = _eleves_annotes(source.exercice).filter(id=source.id).first()
        annotee._total_paye_cache = annotee.total_paye_sql
        du_au_depart = round(max(annotee.reste_a_payer_global, 0.0), 2)
        avant = round(float(fiche.reliquat_anterieur), 2)
        if avant - du_au_depart < SEUIL:
            continue
        deja_paye = fiche.reliquat_paye
        apres = round(max(du_au_depart, deja_paye), 2)
        ligne = {
            'eleve_id':     str(fiche.id),
            'nom_complet':  fiche.nom_complet,
            'matricule':    fiche.matricule or '',
            'exercice':     fiche.exercice.annee_scolaire,
            'sortie':       source.date_sortie,
            'avant':        avant,
            'du_au_depart': du_au_depart,
            'deja_paye':    deja_paye,
            'apres':        apres,
            # Déjà encaissé au-delà du dû au départ : on s'arrête à l'encaissé,
            # le trop-perçu éventuel se traite à la main avec la famille.
            'plafonne_a_l_encaisse': apres > du_au_depart,
        }
        if appliquer:
            definir_impaye_anterieur(fiche, apres)
        lignes.append(ligne)
    return {
        'appliquer': appliquer,
        'lignes':    lignes,
        'nb':        len(lignes),
        'total_avant': round(sum(l['avant'] for l in lignes), 2),
        'total_apres': round(sum(l['apres'] for l in lignes), 2),
        'reduction':   round(sum(l['avant'] - l['apres'] for l in lignes), 2),
    }
