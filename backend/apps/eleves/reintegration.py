"""Réintégration d'un élève sorti — l'enfant qui revient après un abandon.

Demande de la directrice de Shoumoul (septembre 2026) : un élève abandonne,
revient quelques mois plus tard, et le système ne savait pas le reprendre.

RÈGLES — chacune est testée (tests_reintegration.py) :

  1. Seul un élève ABANDONNÉ ou TRANSFÉRÉ se réintègre. Un diplômé qui revient
     pour un autre cycle est une nouvelle inscription, pas un retour.
  2. On réintègre l'enfant, pas une fiche : la demande porte sur sa DERNIÈRE
     fiche. S'il a déjà été réinscrit ailleurs, c'est refusé.
  3. La date de retour est obligatoire, postérieure à la sortie, pas dans le
     futur, et tombe dans un exercice OUVERT.
  4. Le motif est obligatoire : c'est la trace qu'on relira à la demande
     suivante.
  5. La dette laissée au départ n'est jamais effacée. Si elle existe, le
     retour exige qu'elle soit explicitement RECONNUE (l'école en a parlé avec
     la famille) — sans quoi on refuse, montant à l'appui.
  6. Retour dans le MÊME exercice : la fiche redevient présente ; les mois
     entièrement compris dans l'absence ne sont plus facturés. Un mois déjà
     (même partiellement) payé n'est jamais retiré. Le mois du retour est dû —
     l'école peut l'ajuster via le montant du mois.
  7. Retour sur un exercice SUIVANT : la fiche de l'exercice ouvert est créée
     (ou reprise si le report des impayés l'a déjà ouverte comme fiche de
     créance), l'identité et le matricule sont conservés, la dette suit en
     reliquat (411 D / 890 C) si elle n'y est pas déjà, et la facturation
     démarre à la date de retour.
  8. Chaque sortie et chaque retour laissent un MouvementEleve.

Aucune écriture de produit n'est passée ici : le 706 naît des paiements. Seul
le report d'une dette sur un nouvel exercice écrit, et c'est l'à-nouveaux
existant (apps.paiements.report_reliquats).
"""
import calendar
import datetime

from django.db import transaction

from .echeancier import SEUIL_ALERTE, _annee_du_mois, construire_echeancier, mois_factures
from .models import Eleve, MouvementEleve
from .parcours import fiches_du_meme_eleve

STATUTS_REINTEGRABLES = ('ABANDONNE', 'TRANSFERE')


class ReintegrationRefusee(Exception):
    def __init__(self, message, code='REFUS', **extra):
        super().__init__(message)
        self.message = message
        self.code = code
        self.extra = extra


def _fiche_source(eleve):
    """La fiche qui porte la sortie : la dernière vraie fiche de l'enfant.

    L'écran « Anciens élèves » peut désigner une fiche de créance (ouverte par
    le report des impayés) : on remonte alors à la fiche réelle qu'elle suit.
    """
    fiches = fiches_du_meme_eleve(eleve) or [eleve]
    reelles = [f for f in fiches if not f.fiche_creance]
    if not reelles:
        raise ReintegrationRefusee("Aucune fiche d'élève réelle n'a été trouvée.")
    derniere = reelles[-1]
    return derniere, fiches


def _exercice_ouvert_couvrant(tenant, jour):
    from apps.paiements.models import Exercice
    return (Exercice.objects.filter(tenant=tenant, cloture=False,
                                    date_debut__lte=jour, date_fin__gte=jour)
            .order_by('-date_debut').first())


def _dette_au_depart(fiche, today):
    """Ce que la famille devait le jour du départ, ardoise antérieure comprise.

    L'échéancier d'un sortant arrête son horloge à la date de sortie : ses
    « retards » sont exactement la scolarité exigible avant le départ.
    """
    synth = construire_echeancier(fiche, today=today)['synthese']
    return round(synth['total_anterieurs'], 2)


def _mois_d_absence(fiche, date_sortie, date_retour, today):
    """Mois facturés entièrement compris entre la sortie et le retour, et non payés."""
    if not date_sortie:
        return []
    payes = {l['mois']: l['paye'] for l in construire_echeancier(fiche, today=today)['lignes']}
    # L'échéancier d'un sortant s'arrête au départ : un mois prépayé APRÈS la
    # sortie n'y figure plus. On relit donc les mois désignés par les paiements
    # et par la répartition manuelle — un mois réglé n'est jamais retiré.
    for p in fiche.paiements.filter(statut='ACTIF').only('mois_regles'):
        for m in (p.mois_regles or []):
            payes[int(m)] = max(payes.get(int(m), 0), SEUIL_ALERTE)
    for m, v in (fiche.imputation_mois or {}).items():
        if float(v or 0) >= SEUIL_ALERTE:
            payes[int(m)] = max(payes.get(int(m), 0), float(v))
    retires = []
    for m in mois_factures(fiche, jusqu_a_la_sortie=False):
        annee = _annee_du_mois(fiche.exercice, m)
        premier = datetime.date(annee, m, 1)
        dernier = datetime.date(annee, m, calendar.monthrange(annee, m)[1])
        if premier > date_sortie and dernier < date_retour and payes.get(m, 0) < SEUIL_ALERTE:
            retires.append(m)
    return retires


def analyser(eleve, date_retour, today=None):
    """Tout ce que l'écran doit montrer AVANT de confirmer. Lève ReintegrationRefusee."""
    from apps.eleves.echeancier import NOMS_MOIS

    today = today or datetime.date.today()
    source, _ = _fiche_source(eleve)

    if source.statut not in STATUTS_REINTEGRABLES:
        if source.statut == 'DIPLOME':
            raise ReintegrationRefusee(
                "Un élève diplômé ne se réintègre pas : enregistrez une nouvelle inscription.",
                code='DIPLOME')
        raise ReintegrationRefusee(f"{source.nom_complet} est déjà présent dans l'établissement.",
                                   code='DEJA_PRESENT')
    if not date_retour:
        raise ReintegrationRefusee('La date de retour est obligatoire.', code='DATE')
    if date_retour > today:
        raise ReintegrationRefusee('La date de retour ne peut pas être dans le futur.', code='DATE')
    if source.date_sortie and date_retour <= source.date_sortie:
        raise ReintegrationRefusee(
            f"Le retour doit être postérieur à la sortie du {source.date_sortie:%d/%m/%Y}.",
            code='DATE')

    cible = _exercice_ouvert_couvrant(source.tenant, date_retour)
    if cible is None:
        raise ReintegrationRefusee(
            f"Aucun exercice ouvert ne couvre le {date_retour:%d/%m/%Y}. "
            "Ouvrez l'exercice concerné avant de réintégrer l'élève.", code='EXERCICE')
    if cible.date_debut < source.exercice.date_debut:
        raise ReintegrationRefusee("Le retour ne peut pas précéder l'exercice de la sortie.",
                                   code='EXERCICE')

    meme_exercice = cible.id == source.exercice_id
    fiche_cible = None
    if not meme_exercice:
        from apps.paiements.report_reliquats import _fiche_cible
        fiche_cible = _fiche_cible(source, cible)
        if fiche_cible and not fiche_cible.fiche_creance:
            raise ReintegrationRefusee(
                f"{source.nom_complet} a déjà une fiche d'élève sur {cible.annee_scolaire}.",
                code='DEJA_REINSCRIT')

    dette = _dette_au_depart(source, today)
    if fiche_cible is not None and float(fiche_cible.reliquat_anterieur or 0) > 0:
        # Le report l'a déjà reconduite : c'est le montant inscrit au bilan.
        dette = round(fiche_cible.reliquat_restant, 2)

    retires = (_mois_d_absence(source, source.date_sortie, date_retour, today)
               if meme_exercice else [])
    return {
        'fiche_source_id':  str(source.id),
        'nom_complet':      source.nom_complet,
        'statut':           source.statut,
        'date_sortie':      source.date_sortie,
        'cas':              'MEME_EXERCICE' if meme_exercice else 'NOUVEL_EXERCICE',
        'exercice_cible':   cible.annee_scolaire,
        'exercice_cible_id': str(cible.id),
        'fiche_cible_id':   str(fiche_cible.id) if fiche_cible else None,
        'dette':            dette,
        'dette_a_reconnaitre': dette >= SEUIL_ALERTE,
        'mois_retires':     retires,
        'mois_retires_noms': [NOMS_MOIS.get(m, str(m)) for m in retires],
        '_source':          source,
        '_cible':           cible,
        '_fiche_cible':     fiche_cible,
    }


def reintegrer(eleve, date_retour, motif, *, dette_reconnue=False, utilisateur='',
               section=None, classe=None, today=None):
    """Réintègre l'élève et rend la fiche désormais présente."""
    today = today or datetime.date.today()
    motif = (motif or '').strip()
    a = analyser(eleve, date_retour, today)
    if not motif:
        raise ReintegrationRefusee('Le motif de la réintégration est obligatoire.', code='MOTIF')
    if a['dette_a_reconnaitre'] and not dette_reconnue:
        raise ReintegrationRefusee(
            f"{a['nom_complet']} a laissé {a['dette']:,.0f} FCFA d'impayés au départ. "
            "Cette dette reste due : confirmez qu'elle a été reconnue avec la famille.",
            code='DETTE_A_RECONNAITRE', dette=a['dette'])

    source, cible = a['_source'], a['_cible']
    statut_avant = source.statut

    with transaction.atomic():
        if a['cas'] == 'MEME_EXERCICE':
            fiche = source
            if a['mois_retires']:
                fiche.mois_dus = [m for m in mois_factures(fiche, jusqu_a_la_sortie=False)
                                  if m not in a['mois_retires']]
            fiche.statut = 'INSCRIT'
            fiche.date_sortie = None
        else:
            from apps.paiements.report_reliquats import (
                _creer_fiche, _deja_reporte, _ecrire_a_nouveaux)
            fiche = a['_fiche_cible'] or _creer_fiche(source, cible)
            if not fiche.eleve_precedent_id:
                fiche.eleve_precedent = source
            if a['dette'] >= SEUIL_ALERTE and not _deja_reporte(fiche, source.exercice):
                fiche.reliquat_anterieur = a['dette']
                fiche.reliquat_exercice_origine = source.exercice
                fiche.save(update_fields=['reliquat_anterieur', 'reliquat_exercice_origine',
                                          'eleve_precedent'])
                _ecrire_a_nouveaux(fiche, a['dette'], cible, source.exercice)
            fiche.fiche_creance = False
            fiche.statut = 'INSCRIT'
            fiche.date_sortie = None
            # La facturation repart du retour : le prorata d'entrée s'applique.
            fiche.date_inscription = date_retour
            fiche.date_inscription_jour_estime = False
            fiche.mois_dus = []
        if section is not None:
            fiche.section = section
        if classe is not None:
            fiche.classe = classe
        fiche.save()

        MouvementEleve.objects.create(
            tenant=fiche.tenant, eleve=fiche, type_mouvement='REINTEGRATION',
            date_mouvement=date_retour, statut_avant=statut_avant, statut_apres='INSCRIT',
            motif=motif, mois_retires=a['mois_retires'],
            dette_reconnue=a['dette'] if a['dette_a_reconnaitre'] else 0,
            fiche_origine=source if fiche.id != source.id else None,
            utilisateur=utilisateur,
        )
    return fiche, a


def tracer_sortie(eleve, statut_avant, motif='', utilisateur=''):
    """Trace une sortie (appelée quand le statut bascule vers un statut de sortie)."""
    return MouvementEleve.objects.create(
        tenant=eleve.tenant, eleve=eleve, type_mouvement='SORTIE',
        date_mouvement=eleve.date_sortie or datetime.date.today(),
        statut_avant=statut_avant, statut_apres=eleve.statut,
        motif=motif, utilisateur=utilisateur)


def historique(eleve):
    """Les mouvements de toutes les fiches de l'enfant, du plus récent au plus ancien."""
    ids = [f.id for f in (fiches_du_meme_eleve(eleve) or [eleve])]
    return [{
        'id':           str(m.id),
        'type':         m.type_mouvement,
        'libelle':      m.get_type_mouvement_display(),
        'date':         m.date_mouvement,
        'statut_avant': m.statut_avant,
        'statut_apres': m.statut_apres,
        'motif':        m.motif,
        'mois_retires': m.mois_retires,
        'dette_reconnue': float(m.dette_reconnue),
        'exercice':     m.eleve.exercice.annee_scolaire if m.eleve.exercice_id else '',
        'utilisateur':  m.utilisateur,
    } for m in MouvementEleve.objects.filter(eleve_id__in=ids).select_related('eleve__exercice')]
