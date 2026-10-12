"""Ce que l'école doit à son personnel, et comment elle le règle.

Cas réel (suivi du 12/10/2026) : des parents d'élèves travaillent dans
l'établissement. L'école leur doit des salaires de l'année passée ; cette
année, ils règlent l'inscription et la scolarité de leurs enfants avec cette
créance plutôt qu'en espèces.

Trois sources de dette envers l'employé :

* le RELIQUAT d'un exercice antérieur (Employe.reliquat_anterieur), passé en
  à-nouveau 890 D / 422 C ;
* le reste de chaque BULLETIN validé : net à payer − part versée à la
  validation (BulletinPaie.montant_verse ; vide = net entier, l'usage de
  toujours) ;

et deux façons de la régler après coup, qui débitent toutes deux le 422 :

* un VERSEMENT (VersementPersonnel) : 422 D / trésorerie C ;
* une COMPENSATION : le reçu d'un enfant réglé en mode COMPENSATION,
  411 C / 422 D — aucun argent n'entre, aucun ne sort.

Comme pour les élèves, un règlement ne désigne pas de mois : il s'impute sur
la dette la plus ancienne (reliquat d'abord, puis les mois dans l'ordre). Un
seul calcul — `situation_personnel` — sert la fiche, le plafond des
compensations au guichet et celui des versements.
"""
import datetime
from decimal import Decimal


SOURCE_RELIQUAT = 'RELIQ_PERSO'
SOURCE_VERSEMENT = 'VERS_PERSO'
SOURCE_ANNUL_VERSEMENT = 'ANNUL_VERS_PERSO'
MODE_COMPENSATION = 'COMPENSATION'

MOIS_FR = ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet',
           'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']


def _r(v):
    return round(float(v or 0), 2)


def part_compensation(paiement):
    """Montant d'un reçu réglé par compensation (lignes COMPENSATION de sa
    ventilation, ou le reçu entier en mode simple)."""
    lignes = paiement.modes_reglement or []
    if lignes:
        return _r(sum(float((l or {}).get('montant') or 0)
                      for l in lignes if (l or {}).get('mode') == MODE_COMPENSATION))
    return _r(paiement.total) if paiement.mode_paiement == MODE_COMPENSATION else 0.0


def reste_bulletin(bulletin):
    """Ce qui reste dû sur un bulletin après la part versée à la validation."""
    net = _r(bulletin.net_a_payer)
    if bulletin.montant_verse is None:
        return 0.0
    return round(max(net - _r(bulletin.montant_verse), 0.0), 2)


def situation_personnel(employe, paiement_exclu=None, versement_exclu=None):
    """Situation de la dette de l'école envers un employé.

    `paiement_exclu` / `versement_exclu` : le règlement en cours de réécriture
    ne se compte pas lui-même (modification d'un reçu)."""
    from apps.paiements.models import Paiement
    from .models import BulletinPaie

    # ── Dettes, de la plus ancienne à la plus récente ──────────────────────
    dettes = []
    reliquat = _r(employe.reliquat_anterieur)
    if reliquat > 0:
        dettes.append({'type': 'RELIQUAT', 'mois': None, 'annee': None,
                       'libelle': employe.reliquat_note or 'Reliquat exercice antérieur',
                       'du': reliquat, 'verse': 0.0})
    bulletins = (BulletinPaie.objects
                 .filter(employe=employe, statut__in=('VALIDE', 'PAYE'))
                 .order_by('annee', 'mois'))
    for b in bulletins:
        net = _r(b.net_a_payer)
        verse = net if b.montant_verse is None else min(_r(b.montant_verse), net)
        dettes.append({'type': 'MOIS', 'mois': b.mois, 'annee': b.annee,
                       'bulletin': str(b.id),
                       'libelle': f"{MOIS_FR[b.mois]} {b.annee}",
                       'du': net, 'verse': round(verse, 2)})

    # ── Règlements après coup ──────────────────────────────────────────────
    versements = employe.versements.filter(statut='ACTIF')
    if versement_exclu is not None:
        versements = versements.exclude(id=versement_exclu.id)
    versements = list(versements.order_by('date_versement', 'no_piece'))

    compensations = (Paiement.objects.filter(employe_compense=employe, statut='ACTIF')
                     .select_related('eleve').order_by('date_paiement', 'no_piece'))
    if paiement_exclu is not None:
        compensations = compensations.exclude(id=paiement_exclu.id)
    compensations = [(p, part_compensation(p)) for p in compensations]

    total_versements = round(sum(_r(v.montant) for v in versements), 2)
    total_compense = round(sum(m for _, m in compensations), 2)

    # ── Imputation sur la dette la plus ancienne ───────────────────────────
    a_imputer = total_versements + total_compense
    for d in dettes:
        ouvert = round(d['du'] - d['verse'], 2)
        part = round(min(max(ouvert, 0.0), a_imputer), 2)
        d['regle_ensuite'] = part
        a_imputer = round(a_imputer - part, 2)
        d['reste'] = round(ouvert - part, 2)
        d['statut'] = ('SOLDE' if d['reste'] <= 0.009
                       else 'PARTIEL' if (d['verse'] + part) > 0 else 'IMPAYE')

    du_total = round(sum(d['du'] for d in dettes), 2)
    verse_validation = round(sum(d['verse'] for d in dettes), 2)
    reste_total = round(sum(d['reste'] for d in dettes), 2)

    enfants = []
    from apps.eleves.parcours import STATUTS_SORTIE
    for e in (employe.enfants.exclude(statut__in=STATUTS_SORTIE)
              .filter(exercice__cloture=False).select_related('section', 'classe')):
        enfants.append({'id': str(e.id), 'nom_complet': e.nom_complet,
                        'matricule': e.matricule,
                        'section': e.section.nom if e.section else '',
                        'classe': e.classe.nom if getattr(e, 'classe', None) else '',
                        'reste_a_payer': _r(e.reste_a_payer)})

    return {
        'employe': {'id': str(employe.id), 'nom_complet': employe.nom_complet,
                    'matricule': employe.matricule, 'poste': employe.poste},
        'lignes': dettes,
        'reliquat': {'du': reliquat, 'note': employe.reliquat_note},
        'versements': [{'id': str(v.id), 'date': v.date_versement, 'no_piece': v.no_piece,
                        'montant': _r(v.montant), 'mode_paiement': v.mode_paiement,
                        'observations': v.observations} for v in versements],
        'compensations': [{'paiement': str(p.id), 'date': p.date_paiement,
                           'no_piece': p.no_piece, 'eleve': p.eleve.nom_complet,
                           'eleve_id': str(p.eleve_id), 'montant': m}
                          for p, m in compensations],
        'enfants': enfants,
        'totaux': {
            'du': du_total,
            'verse_validation': verse_validation,
            'versements': total_versements,
            'compense': total_compense,
            'regle': round(verse_validation + total_versements + total_compense, 2),
            'reste': reste_total,
            # Réglé au-delà de ce qui était dû (ne devrait pas arriver : les
            # plafonds l'empêchent) — affiché plutôt que perdu.
            'excedent': round(max(a_imputer, 0.0), 2),
        },
    }


def reste_du_employe(employe, **exclus):
    return situation_personnel(employe, **exclus)['totaux']['reste']


def verifier_compensation(eleve, montant, paiement_exclu=None):
    """Rend (employe, None) si la compensation est possible, (None, message)
    sinon. Le plafond est ce que l'école doit encore au parent."""
    montant = _r(montant)
    if montant <= 0:
        return None, None
    employe = eleve.parent_employe
    if employe is None:
        return None, (f"{eleve.nom_complet} n'est relié à aucun membre du personnel : "
                      "la compensation n'est possible que pour l'enfant d'un employé.")
    reste = reste_du_employe(employe, paiement_exclu=paiement_exclu)
    if montant > reste + 0.01:
        return None, (f"Compensation de {montant:,.0f} FCFA supérieure à ce que l'école "
                      f"doit encore à {employe.nom_complet} ({reste:,.0f} FCFA).")
    return employe, None


# ── Écritures ────────────────────────────────────────────────────────────────

def _exercice_ouvert(tenant):
    from apps.paiements.models import Exercice
    return Exercice.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()


def comptabiliser_reliquat(employe):
    """(Re)passe l'à-nouveau du reliquat : 890 D / 422 C, sur l'exercice ouvert.

    Le reliquat est une donnée d'ouverture, saisie une fois et corrigeable :
    on remplace ses écritures plutôt que d'empiler des extournes — comme les
    à-nouveaux des élèves. Seules celles d'un exercice OUVERT sont réécrites ;
    un exercice clôturé ne se touche pas."""
    from apps.comptabilite.models import JournalEntry

    tenant = employe.tenant
    JournalEntry.objects.filter(tenant=tenant, source=SOURCE_RELIQUAT, source_id=employe.id,
                                exercice__cloture=False).delete()
    montant = Decimal(str(employe.reliquat_anterieur or 0))
    if montant <= 0:
        return
    exercice = _exercice_ouvert(tenant)
    if exercice is None:
        return
    ref = f"RLP-{employe.matricule or employe.id.hex[:6].upper()}"
    libelle = (f"Reliquat dû au personnel — {employe.nom_complet}"
               + (f" ({employe.reliquat_note})" if employe.reliquat_note else ''))
    commun = dict(tenant=tenant, exercice=exercice, no_piece=ref,
                  date_ecriture=exercice.date_debut, libelle=libelle,
                  source=SOURCE_RELIQUAT, source_id=employe.id)
    JournalEntry.objects.bulk_create([
        JournalEntry(no_compte='890', debit=montant, credit=0, ordre=1, **commun),
        JournalEntry(no_compte='422', debit=0, credit=montant, ordre=2, **commun),
    ])


def prochain_no_versement(tenant):
    import re
    from .models import VersementPersonnel
    nums = [int(m.group(1)) for p in VersementPersonnel.objects.filter(tenant=tenant)
            .values_list('no_piece', flat=True) if (m := re.search(r'(\d+)(?!.*\d)', p or ''))]
    return f"VRP-{max(nums, default=0) + 1:04d}"


def comptabiliser_versement(versement):
    """422 D / trésorerie C."""
    from apps.comptabilite.models import JournalEntry
    from .services import _compte_paiement

    exercice = _exercice_ouvert(versement.tenant)
    if exercice is None:
        raise ValueError("Aucun exercice ouvert pour enregistrer le versement.")
    montant = Decimal(str(versement.montant))
    libelle = f"Règlement dû au personnel — {versement.employe.nom_complet}"
    commun = dict(tenant=versement.tenant, exercice=exercice, no_piece=versement.no_piece,
                  date_ecriture=versement.date_versement, libelle=libelle,
                  source=SOURCE_VERSEMENT, source_id=versement.id)
    JournalEntry.objects.bulk_create([
        JournalEntry(no_compte='422', debit=montant, credit=0, ordre=1, **commun),
        JournalEntry(no_compte=_compte_paiement(versement.mode_paiement),
                     debit=0, credit=montant, ordre=2, **commun),
    ])


def annuler_versement(versement):
    """Extourne les écritures du versement et le marque annulé."""
    from apps.comptabilite.models import JournalEntry

    exercice = _exercice_ouvert(versement.tenant)
    origine = JournalEntry.objects.filter(tenant=versement.tenant, source=SOURCE_VERSEMENT,
                                          source_id=versement.id).order_by('ordre')
    if exercice is not None:
        date = min(datetime.date.today(), exercice.date_fin)
        JournalEntry.objects.bulk_create([
            JournalEntry(tenant=versement.tenant, exercice=exercice,
                         no_piece=f"ANN-{versement.no_piece}", date_ecriture=date,
                         no_compte=e.no_compte, libelle=f"ANNUL — {e.libelle}",
                         debit=e.credit, credit=e.debit,
                         source=SOURCE_ANNUL_VERSEMENT, source_id=versement.id, ordre=i)
            for i, e in enumerate(origine, start=1)])
    versement.statut = 'ANNULE'
    versement.save(update_fields=['statut'])
