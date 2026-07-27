"""Report des reliquats — reconduction du reste dû d'un exercice à l'autre.

Un élève peut terminer l'année avec un impayé. Ce reste dû est une créance
(411) née de l'exercice écoulé : le produit correspondant (706) y a déjà été
constaté. Le reconduire ne crée donc AUCUN produit nouveau — c'est un
à-nouveaux de bilan, passé dans le NOUVEL exercice à sa date d'ouverture :

    411 D / 890 C     (créance reportée / bilan d'ouverture)

L'exercice source n'est jamais touché : une année clôturée reste en lecture
seule, et le report peut donc être joué après coup sur un exercice déjà
clôturé (c'est même le cas courant).

Plus tard, l'encaissement du reliquat soldera cette créance —
trésorerie D / 411 C, toujours sans 706 (voir Paiement.montant_reliquat).

Le report est IDEMPOTENT : le rejouer ne duplique ni les fiches, ni les
écritures. Il peut donc servir de rattrapage autant de fois que nécessaire.
"""
import re

from django.db import transaction
from django.db.models import DecimalField, Max, Q, Sum, Value
from django.db.models.functions import Coalesce

from apps.eleves.models import Eleve
from apps.eleves.parcours import STATUTS_SORTIE
from .models import Exercice

SOURCE_REPORT = 'REPORT_RELIQUAT'

# Champs d'identité recopiés sur la fiche de réinscription. Volontairement
# ABSENTS de cette liste :
#   - classe        : l'élève change de niveau, l'école l'affecte à la main ;
#   - abonnements   : les services optionnels se resouscrivent chaque année,
#                     les recopier gonflerait le dû de la famille en silence ;
#   - date_inscription : repositionnée au début du nouvel exercice.
CHAMPS_IDENTITE = (
    'section', 'numero', 'matricule', 'nom_complet', 'genre',
    # Entrée dans l'établissement : figée à vie, sinon la promo et la date
    # d'arrivée se perdent dès la 2e année (date_inscription, elle, est
    # repositionnée plus bas au début du nouvel exercice pour le prorata).
    'matricule_ancien', 'annee_entree', 'date_entree',
    'date_naissance', 'lieu_naissance',
    'nom_pere', 'telephone_pere', 'nom_mere', 'telephone_mere',
    'nom_tuteur', 'telephone_tuteur', 'lien_tuteur',
    'etat_sante', 'observations_sante',
    'statut',
    'prise_en_charge', 'obs_prise_en_charge',
    'pec_inscription', 'pec_mensualite',
    'type_pec', 'taux_pec_inscription', 'taux_pec_mensualite',
    'taux_prise_en_charge',
)


def _eleves_annotes(exercice):
    """Élèves d'un exercice, avec payé et reliquat déjà réglé annotés.

    Seuls les paiements ACTIFs comptent : un paiement annulé ne solde rien,
    sinon un impayé disparaîtrait du report."""
    actif = Q(paiements__statut='ACTIF')

    def zero(expr):
        return Coalesce(expr, Value(0), output_field=DecimalField())

    return Eleve.objects.filter(
        tenant=exercice.tenant, exercice=exercice
    ).select_related('section', 'exercice', 'reliquat_exercice_origine').prefetch_related(
        'abonnements__service'
    ).annotate(
        total_paye_sql=zero(
            Sum('paiements__montant_inscription', filter=actif) +
            Sum('paiements__montant_mensualite',  filter=actif) +
            Sum('paiements__montant_uniforme',    filter=actif) +
            Sum('paiements__montant_fournitures', filter=actif) +
            Sum('paiements__montant_cantine',     filter=actif) +
            Sum('paiements__montant_divers',      filter=actif)
        ),
        reliquat_paye_sql=zero(Sum('paiements__montant_reliquat', filter=actif)),
    )


def calculer_reliquats(exercice_source):
    """Rend [(eleve, montant_du)] pour les élèves qui terminent l'exercice
    source avec un impayé, du plus gros au plus petit.

    Le montant retenu est le dû GLOBAL (reste de l'année + reliquat encore
    ouvert hérité de l'année d'avant) : une dette non réglée traverse autant
    d'exercices qu'il le faut, elle ne s'évapore pas au deuxième report."""
    lignes = []
    for eleve in _eleves_annotes(exercice_source):
        # total_paye lit l'annotation via _total_paye_cache (property Eleve)
        eleve._total_paye_cache = eleve.total_paye_sql
        du = eleve.reste_a_payer_global
        if du > 0:
            lignes.append((eleve, round(du, 2)))
    lignes.sort(key=lambda l: l[1], reverse=True)
    return lignes


def _prochain_no_piece(tenant):
    """RAN-NNNN — séquence propre à l'école (jamais globale : deux écoles
    doivent pouvoir avoir chacune leur RAN-0001)."""
    from apps.comptabilite.models import JournalEntry
    last = JournalEntry.objects.filter(
        tenant=tenant, no_piece__startswith='RAN-'
    ).aggregate(m=Max('no_piece'))['m']
    suivant = 1
    if last and (nums := re.findall(r'\d+', last)):
        suivant = int(nums[-1]) + 1
    return f"RAN-{suivant:04d}"


def _fiche_cible(eleve, exercice_cible):
    """Fiche de l'élève déjà présente sur l'exercice cible, s'il y en a une.

    On la reconnaît par le lien de réinscription, sinon par le matricule
    (fiche créée à la main ou importée avant le report)."""
    base = Eleve.objects.filter(tenant=eleve.tenant, exercice=exercice_cible)
    if fiche := base.filter(eleve_precedent=eleve).first():
        return fiche
    if eleve.matricule:
        return base.filter(matricule=eleve.matricule).first()
    return None


def _ecrire_a_nouveaux(fiche, montant, exercice_cible, exercice_source):
    """Passe l'à-nouveaux 411 D / 890 C dans l'exercice cible."""
    from apps.comptabilite.models import JournalEntry
    no_piece = _prochain_no_piece(fiche.tenant)
    libelle = (f"Reliquat {exercice_source.annee_scolaire} — "
               f"{fiche.nom_complet} ({no_piece})")
    for ordre, (compte, debit, credit) in enumerate((
        ('411', montant, 0),
        ('890', 0, montant),
    ), start=1):
        JournalEntry.objects.create(
            tenant=fiche.tenant, exercice=exercice_cible,
            no_piece=no_piece, date_ecriture=exercice_cible.date_debut,
            no_compte=compte, debit=debit, credit=credit, libelle=libelle,
            source=SOURCE_REPORT, source_id=fiche.id, ordre=ordre,
        )
    return no_piece


def _creer_fiche(eleve, exercice_cible):
    """Ouvre la fiche de l'élève sur l'exercice cible : même identité
    (matricule, numéro et entrée conservés — c'est le même enfant).

    Pour un élève SORTI (diplômé, transféré, abandon), ce n'est pas une
    réinscription : il ne revient pas, mais sa dette le suit. La fiche est
    alors marquée `fiche_creance` — elle porte l'à-nouveaux 411/890, sans
    quoi la créance disparaîtrait du bilan du nouvel exercice, tout en
    restant hors de la liste des élèves et des effectifs.
    """
    valeurs = {champ: getattr(eleve, champ) for champ in CHAMPS_IDENTITE}
    return Eleve.objects.create(
        tenant=eleve.tenant,
        exercice=exercice_cible,
        eleve_precedent=eleve,
        date_inscription=exercice_cible.date_debut,
        date_inscription_jour_estime=False,
        regime='EXERCICE',
        nb_mois_passager=None,
        fiche_creance=eleve.statut in STATUTS_SORTIE,
        **valeurs,
    )


def _deja_reporte(fiche, exercice_source):
    """Vrai si cette fiche porte déjà le reliquat de l'exercice source."""
    return (fiche.reliquat_exercice_origine_id == exercice_source.id
            and float(fiche.reliquat_anterieur or 0) > 0)


def reporter_reliquats(exercice_source, exercice_cible, *, creer_fiches=True,
                       dry_run=False):
    """Reconduit les impayés de `exercice_source` sur `exercice_cible`.

    - `creer_fiches` : réinscrit les élèves absents de l'exercice cible.
      À False, seuls les élèves déjà réinscrits reçoivent leur reliquat.
    - `dry_run` : calcule et rend le même rapport sans rien écrire.

    Rend un rapport {reportes, ignores, a_verifier, nb_*, montant_total}.
    Rejouable sans risque : une fiche qui porte déjà le reliquat est ignorée.
    """
    if exercice_source.tenant_id != exercice_cible.tenant_id:
        raise ValueError("Les deux exercices doivent appartenir à la même école.")
    if exercice_source.id == exercice_cible.id:
        raise ValueError("L'exercice source et l'exercice cible sont identiques.")
    if exercice_cible.cloture:
        raise ValueError(
            f"L'exercice cible {exercice_cible.annee_scolaire} est clôturé : "
            "on ne peut pas y passer les à-nouveaux.")

    reportes, ignores, a_verifier = [], [], []

    for eleve, montant in calculer_reliquats(exercice_source):
        ligne = {
            'eleve_id':    str(eleve.id),
            'matricule':   eleve.matricule or '',
            'nom_complet': eleve.nom_complet,
            'section':     eleve.section.nom if eleve.section else '',
            'montant':     montant,
        }
        fiche = _fiche_cible(eleve, exercice_cible)

        if fiche and _deja_reporte(fiche, exercice_source):
            ignores.append({**ligne, 'motif': 'deja_reporte'})
            continue

        # Un ndongo passager a une durée de séjour convenue : on ne peut pas
        # deviner les mois restants à sa place. Sa dette est bien réelle, mais
        # la réinscription doit être faite à la main (avec les bons mois) —
        # ensuite un simple rejeu du report y accrochera le reliquat.
        if not fiche and eleve.regime == 'PASSAGER':
            a_verifier.append({**ligne, 'motif': 'passager_a_reinscrire'})
            continue

        if not fiche and not creer_fiches:
            ignores.append({**ligne, 'motif': 'non_reinscrit'})
            continue

        if dry_run:
            reportes.append({**ligne, 'fiche': 'existante' if fiche else 'creee',
                             'no_piece': ''})
            continue

        with transaction.atomic():
            if fiche is None:
                fiche = _creer_fiche(eleve, exercice_cible)
                creee = True
            else:
                creee = False
                if not fiche.eleve_precedent_id:
                    fiche.eleve_precedent = eleve
            fiche.reliquat_anterieur = montant
            fiche.reliquat_exercice_origine = exercice_source
            fiche.save(update_fields=['reliquat_anterieur',
                                      'reliquat_exercice_origine',
                                      'eleve_precedent'])
            no_piece = _ecrire_a_nouveaux(fiche, montant, exercice_cible,
                                          exercice_source)

        reportes.append({**ligne, 'fiche': 'creee' if creee else 'existante',
                         'no_piece': no_piece,
                         'eleve_cible_id': str(fiche.id)})

    return {
        'exercice_source':  exercice_source.annee_scolaire,
        'exercice_cible':   exercice_cible.annee_scolaire,
        'dry_run':          dry_run,
        'reportes':         reportes,
        'ignores':          ignores,
        'a_verifier':       a_verifier,
        'nb_reportes':      len(reportes),
        'nb_ignores':       len(ignores),
        'nb_a_verifier':    len(a_verifier),
        'montant_total':    round(sum(l['montant'] for l in reportes), 2),
        'montant_a_verifier': round(sum(l['montant'] for l in a_verifier), 2),
    }


def exercice_source_par_defaut(tenant, exercice_cible):
    """Exercice précédant immédiatement la cible (le plus récent qui commence
    avant elle) — celui dont on reconduit naturellement les impayés."""
    return Exercice.objects.filter(
        tenant=tenant, date_debut__lt=exercice_cible.date_debut
    ).exclude(id=exercice_cible.id).order_by('-date_debut').first()
