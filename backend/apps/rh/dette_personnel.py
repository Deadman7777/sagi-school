"""Ce que l'école doit à son personnel, et comment elle le règle.

Cas réel (suivi du 12/10/2026) : des parents d'élèves travaillent dans
l'établissement. L'école leur doit des salaires de l'année passée ; cette
année, ils règlent l'inscription et la scolarité de leurs enfants avec cette
créance plutôt qu'en espèces.

Trois sources de dette envers l'employé :

* le RELIQUAT d'un exercice antérieur (Employe.reliquat_anterieur), passé en
  à-nouveau 890 D / 422 C ;
* chaque MOIS DE PAIE de l'exercice (calendrier des mensualités : octobre →
  juin pour 9 mois), bulletin établi ou non : le net du bulletin validé, sinon
  le salaire convenu ; la part versée à la validation d'un bulletin
  (BulletinPaie.montant_verse ; vide = net entier) le règle d'autant ;

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


def aujourdhui():
    """Date du jour (isolée pour les tests)."""
    return datetime.date.today()


def exercice_courant(tenant):
    """L'exercice suivi pour le personnel : le dernier ouvert."""
    from apps.paiements.models import Exercice
    return (Exercice.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()
            or Exercice.objects.filter(tenant=tenant).order_by('-date_debut').first())


def mois_de_paie(exercice):
    """[(annee, mois)] des mois payés de l'année : les `nb_mensualites`
    premiers mois de l'exercice — le même calendrier que la scolarité
    (octobre → juin pour 9 mensualités)."""
    a, m = exercice.date_debut.year, exercice.date_debut.month
    sortie = []
    for _ in range(max(int(exercice.nb_mensualites or 0), 0)):
        sortie.append((a, m))
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return sortie


def _present(employe, annee, mois):
    """L'employé est-il dans l'école ce mois-là (embauche, départ) ?"""
    if employe.date_embauche and (annee, mois) < (employe.date_embauche.year, employe.date_embauche.month):
        return False
    if employe.date_depart and (annee, mois) > (employe.date_depart.year, employe.date_depart.month):
        return False
    return True


def situation_personnel(employe, paiement_exclu=None, versement_exclu=None,
                        exercice=None, today=None):
    """Situation de la dette de l'école envers un employé.

    Le dû de l'année se lit sur le CALENDRIER de l'exercice : un mois de paie
    est dû dès qu'il appartient à l'année, bulletin établi ou non. Son montant
    est le net du bulletin validé du mois s'il existe, sinon le salaire
    convenu (salaire de base de la fiche). S'y ajoute l'antérieur : le
    reliquat saisi et le reste des bulletins d'avant l'exercice.

    `paiement_exclu` / `versement_exclu` : le règlement en cours de réécriture
    ne se compte pas lui-même (modification d'un reçu)."""
    from apps.paiements.models import Paiement
    from .models import BulletinPaie

    today = today or aujourdhui()
    exercice = exercice or exercice_courant(employe.tenant)
    calendrier = mois_de_paie(exercice) if exercice else []
    salaire = _r(employe.salaire_base)

    bulletins = {(b.annee, b.mois): b for b in
                 BulletinPaie.objects.filter(employe=employe, statut__in=('VALIDE', 'PAYE'))}

    def ligne_bulletin(b, type_):
        net = _r(b.net_a_payer)
        verse = net if b.montant_verse is None else min(_r(b.montant_verse), net)
        return {'type': type_, 'mois': b.mois, 'annee': b.annee, 'bulletin': str(b.id),
                'source': 'BULLETIN', 'libelle': f"{MOIS_FR[b.mois]} {b.annee}",
                'du': net, 'verse': round(verse, 2), 'echu': True}

    # ── Antérieur : reliquat saisi + bulletins d'avant l'exercice non soldés ─
    dettes = []
    reliquat = _r(employe.reliquat_anterieur)
    if reliquat > 0:
        dettes.append({'type': 'RELIQUAT', 'mois': None, 'annee': None, 'source': 'RELIQUAT',
                       'libelle': employe.reliquat_note or 'Reliquat exercice antérieur',
                       'du': reliquat, 'verse': 0.0, 'echu': True})
    debut = calendrier[0] if calendrier else None
    for cle in sorted(bulletins):
        if debut and cle < debut:
            l = ligne_bulletin(bulletins[cle], 'ANTERIEUR')
            if l['du'] - l['verse'] > 0.009:
                dettes.append(l)

    # ── Année : chaque mois du calendrier où l'employé est présent ─────────
    courant = (today.year, today.month)
    for (a, m) in calendrier:
        b = bulletins.get((a, m))
        if b is not None:
            l = ligne_bulletin(b, 'MOIS')
        elif _present(employe, a, m):
            l = {'type': 'MOIS', 'mois': m, 'annee': a, 'bulletin': None, 'source': 'SALAIRE',
                 'libelle': f"{MOIS_FR[m]} {a}", 'du': salaire, 'verse': 0.0}
        else:
            continue
        l['echu'] = (a, m) <= courant
        dettes.append(l)
    # Bulletin d'un mois hors calendrier (après la dernière mensualité) : il
    # est dû aussi, à sa place dans l'ordre.
    fin = calendrier[-1] if calendrier else None
    for cle in sorted(bulletins):
        if fin and cle > fin:
            l = ligne_bulletin(bulletins[cle], 'MOIS')
            l['echu'] = cle <= courant
            dettes.append(l)

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
        d['regle'] = round(d['verse'] + part, 2)
        d['reste'] = round(ouvert - part, 2)
        d['statut'] = ('SOLDE' if d['reste'] <= 0.009
                       else 'PARTIEL' if d['regle'] > 0 else 'IMPAYE')

    def somme(cle, filtre=lambda d: True):
        return round(sum(d[cle] for d in dettes if filtre(d)), 2)

    anterieur = lambda d: d['type'] in ('RELIQUAT', 'ANTERIEUR')
    annee = lambda d: d['type'] == 'MOIS'
    echu = lambda d: d['echu']

    from apps.eleves.parcours import STATUTS_SORTIE
    enfants = []
    for e in (employe.enfants.exclude(statut__in=STATUTS_SORTIE)
              .filter(exercice__cloture=False).select_related('section', 'classe')):
        enfants.append({'id': str(e.id), 'nom_complet': e.nom_complet,
                        'matricule': e.matricule,
                        'section': e.section.nom if e.section else '',
                        'classe': e.classe.nom if getattr(e, 'classe', None) else '',
                        'reste_a_payer': _r(e.reste_a_payer)})

    return {
        'employe': {'id': str(employe.id), 'nom_complet': employe.nom_complet,
                    'matricule': employe.matricule, 'poste': employe.poste,
                    'salaire_mensuel': salaire},
        'exercice': {'annee_scolaire': exercice.annee_scolaire if exercice else '',
                     'nb_mois': len(calendrier),
                     'premier_mois': f"{MOIS_FR[calendrier[0][1]]} {calendrier[0][0]}" if calendrier else '',
                     'dernier_mois': f"{MOIS_FR[calendrier[-1][1]]} {calendrier[-1][0]}" if calendrier else ''},
        'lignes': dettes,
        'reliquat': {'du': reliquat, 'note': employe.reliquat_note},
        'versements': [{'id': str(v.id), 'date': v.date_versement, 'no_piece': v.no_piece,
                        'montant': _r(v.montant), 'mode_paiement': v.mode_paiement,
                        'mode_libelle': v.get_mode_paiement_display(),
                        'observations': v.observations} for v in versements],
        'compensations': [{'paiement': str(p.id), 'date': p.date_paiement,
                           'no_piece': p.no_piece, 'eleve': p.eleve.nom_complet,
                           'eleve_id': str(p.eleve_id), 'montant': m,
                           'objet': _objet_paiement(p)}
                          for p, m in compensations],
        'enfants': enfants,
        'totaux': {
            'du_anterieur': somme('du', anterieur),
            'du_annee': somme('du', annee),
            'du': somme('du'),
            'du_echu': somme('du', echu),
            'verse_validation': somme('verse'),
            'versements': total_versements,
            'compense': total_compense,
            'regle': round(somme('verse') + total_versements + total_compense, 2),
            'reste_anterieur': somme('reste', anterieur),
            'reste_annee': somme('reste', annee),
            'reste': somme('reste'),
            # Exigible aujourd'hui : l'antérieur et les mois déjà commencés.
            'reste_echu': somme('reste', echu),
            'reste_a_venir': somme('reste', lambda d: not d['echu']),
            # Réglé au-delà de tout le dû de l'année (les plafonds l'empêchent)
            # — affiché plutôt que perdu.
            'excedent': round(max(a_imputer, 0.0), 2),
        },
    }


def _objet_paiement(p):
    """« Inscription + Mensualité » : ce que la compensation a réglé."""
    parts = []
    if p.montant_inscription:
        parts.append('Inscription')
    if p.montant_mensualite:
        parts.append('Scolarité')
    if p.montant_uniforme or p.montant_fournitures:
        parts.append('Fournitures')
    if p.montant_cantine or p.montant_divers:
        parts.append('Services')
    if p.montant_reliquat:
        parts.append('Reliquat')
    return ' + '.join(parts)


def reste_du_employe(employe, **exclus):
    """Plafond d'un versement ou d'une compensation : ce que l'école doit À CE
    JOUR (antérieur + mois commencés), pas les salaires des mois à venir —
    les régler d'avance serait une avance sur salaire, pas un règlement."""
    return situation_personnel(employe, **exclus)['totaux']['reste_echu']


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
                      f"doit à ce jour à {employe.nom_complet} ({reste:,.0f} FCFA : "
                      "antérieur et mois commencés).")
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
