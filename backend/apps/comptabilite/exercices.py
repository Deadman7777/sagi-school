"""Plusieurs exercices, régularisation d'un exercice antérieur, continuité.

Une école peut arriver sur SAGI SCHOOL alors que son exercice précédent n'est
pas régularisé et que ses ETAFI ne sont pas produits. Elle doit pouvoir
travailler sur l'année en cours ET terminer l'année d'avant, puis enchaîner
les deux proprement. Trois outils, une règle de continuité.

1. Écritures diverses (OD) — saisie libre et équilibrée, dans l'exercice
   choisi (courant ou antérieur encore ouvert), pour régulariser.

2. Import de balance — la balance d'un expert-comptable ou d'un ancien
   logiciel : d'OUVERTURE (soldes au premier jour) ou de CLÔTURE (tous les
   comptes de l'année, classes 6 et 7 comprises, quand le détail des
   opérations n'existe pas). Une pièce, remplacée à chaque réimport.

3. À-nouveaux — le bilan de clôture d'un exercice devient le bilan
   d'ouverture du suivant. Générés à la demande, REGÉNÉRABLES tant que
   l'exercice source reste ouvert : régulariser l'année antérieure puis
   régénérer suffit à mettre l'année courante à jour.

La trésorerie d'ouverture garde son mécanisme historique : les soldes
initiaux de l'exercice (`Exercice.solde_initial_*`), lus par le tableau de
bord, le point de trésorerie, les canaux… Les à-nouveaux posent donc ces
soldes et reportent TOUS les autres comptes de bilan (classes 1 à 5) en une
pièce équilibrée :

    comptes de bilan hors trésorerie   à leur solde de clôture
    890 D  trésorerie d'ouverture + impayés déjà reportés (contrepartie)
    121 C  capitaux reportés (129 D s'ils sont négatifs)

Le 890 est le compte d'à-nouveaux de l'application (voir report_reliquats) :
la pièce le débite de la trésorerie d'ouverture, que l'exercice porte en
soldes initiaux ; les impayés reportés (411 D / 890 C, source
REPORT_RELIQUAT) ne sont pas reportés une seconde fois. Le bilan présente le
890 net avec les capitaux d'ouverture (voir BilanView) : rien n'est compté
deux fois et le bilan d'ouverture du nouvel exercice égale le bilan de
clôture de l'ancien, au franc près.
"""
import re
from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone

from apps.paiements.models import Exercice

from .models import JournalEntry

SOURCE_AN = 'AN'
SOURCE_OD = 'OD'
SOURCE_ANNUL_OD = 'ANNUL_OD'
SOURCE_BALANCE = 'BALANCE_IMPORT'
COMPTE_A_NOUVEAUX = '890'
COMPTE_REPORT_CREDITEUR = '121'
COMPTE_REPORT_DEBITEUR = '129'

# Trésorerie portée par les soldes initiaux (même découpage que
# tresorerie.POSTES_TRESORERIE).
PREFIXES_TRESO = {'caisse': ('571',), 'banque': ('521',), 'mobile': ('5521', '5522', '5523')}
TOUS_PREFIXES_TRESO = tuple(p for ps in PREFIXES_TRESO.values() for p in ps)

ZERO = Decimal('0')


def _d(x):
    return Decimal(str(x or 0)).quantize(Decimal('0.01'))


def est_tresorerie(no_compte):
    return no_compte.startswith(TOUS_PREFIXES_TRESO)


def est_compte_bilan(no_compte):
    return bool(no_compte) and no_compte[0] in '12345'


def exercice_suivant(exercice):
    return (Exercice.objects.filter(tenant=exercice.tenant, date_debut__gt=exercice.date_debut)
            .order_by('date_debut').first())


def exercice_precedent(exercice):
    return (Exercice.objects.filter(tenant=exercice.tenant, date_debut__lt=exercice.date_debut)
            .order_by('-date_debut').first())


def soldes_comptes(exercice, exclure_sources=()):
    """{compte: solde débiteur (D − C)} de l'exercice, soldes initiaux de
    trésorerie compris (571 caisse, 521 banque, 5521 mobile — porté par Wave,
    comme au tableau de bord)."""
    qs = JournalEntry.objects.filter(tenant=exercice.tenant, exercice=exercice)
    if exclure_sources:
        qs = qs.exclude(source__in=exclure_sources)
    soldes = defaultdict(lambda: ZERO)
    for r in qs.values('no_compte').annotate(d=Sum('debit'), c=Sum('credit')):
        soldes[r['no_compte']] += _d(r['d']) - _d(r['c'])
    for compte, champ in (('571', 'solde_initial_caisse'), ('521', 'solde_initial_banque'),
                          ('5521', 'solde_initial_mobile')):
        if getattr(exercice, champ):
            soldes[compte] += _d(getattr(exercice, champ))
    return {c: s for c, s in soldes.items() if s != 0}


def _libelles(tenant):
    from .views import get_plan_dict
    return get_plan_dict(tenant)


def calculer_a_nouveaux(source, cible):
    """Les à-nouveaux de `source` vers `cible`, sans rien écrire.

    Rend {'lignes': [{no_compte, debit, credit, libelle}], 'tresorerie':
    {caisse, banque, mobile}, 'capitaux': Decimal, 'reliquats_reportes':
    Decimal}.
    """
    from apps.paiements.report_reliquats import SOURCE_REPORT

    soldes = soldes_comptes(source)
    plan = _libelles(source.tenant)

    treso = {poste: ZERO for poste in PREFIXES_TRESO}
    for compte, solde in soldes.items():
        for poste, prefixes in PREFIXES_TRESO.items():
            if compte.startswith(prefixes):
                treso[poste] += solde

    # Impayés déjà reportés dans la cible (411 D / 890 C) : ne pas les
    # reporter une seconde fois.
    deja = defaultdict(lambda: ZERO)
    for r in (JournalEntry.objects.filter(tenant=cible.tenant, exercice=cible, source=SOURCE_REPORT)
              .exclude(no_compte=COMPTE_A_NOUVEAUX)
              .values('no_compte').annotate(d=Sum('debit'), c=Sum('credit'))):
        deja[r['no_compte']] += _d(r['d']) - _d(r['c'])
    reliquats = sum(deja.values(), ZERO)

    lignes = []
    capitaux = ZERO
    for compte in sorted(soldes):
        solde = soldes[compte]
        if not est_compte_bilan(compte):
            continue
        capitaux += solde                      # actif net de clôture
        if est_tresorerie(compte):
            continue
        reste = solde - deja.get(compte, ZERO)
        if reste == 0:
            continue
        lib = f"À-nouveau {source.annee_scolaire} — {plan.get(compte, compte)}"
        lignes.append({'no_compte': compte, 'debit': reste if reste > 0 else ZERO,
                       'credit': -reste if reste < 0 else ZERO, 'libelle': lib})
    # Comptes de bilan créditeurs reportés au passif : `capitaux` est déjà
    # l'actif net (D − C) de tous les comptes 1 à 5 — le résultat de l'année
    # y est inclus, puisqu'il n'a pas été viré au 13.
    contrepartie = sum(treso.values(), ZERO) + reliquats
    if contrepartie:
        lignes.append({'no_compte': COMPTE_A_NOUVEAUX,
                       'debit': contrepartie if contrepartie > 0 else ZERO,
                       'credit': -contrepartie if contrepartie < 0 else ZERO,
                       'libelle': f"À-nouveaux {source.annee_scolaire} — trésorerie d'ouverture"
                                  f" et impayés reportés"})
    # Capitaux propres reportés : les comptes 10-14 sont déjà dans `lignes` ;
    # le solde (résultat non affecté + capitaux d'ouverture implicites) va
    # au report à nouveau.
    report = ZERO
    for l in lignes:
        report += l['debit'] - l['credit']
    if report > 0:
        lignes.append({'no_compte': COMPTE_REPORT_CREDITEUR, 'debit': ZERO, 'credit': report,
                       'libelle': f"Report à nouveau {source.annee_scolaire} (créditeur)"})
    elif report < 0:
        lignes.append({'no_compte': COMPTE_REPORT_DEBITEUR, 'debit': -report, 'credit': ZERO,
                       'libelle': f"Report à nouveau {source.annee_scolaire} (débiteur)"})
    return {'lignes': lignes, 'tresorerie': treso, 'capitaux': capitaux,
            'report': report, 'reliquats_reportes': reliquats}


def a_nouveaux_existants(cible):
    return JournalEntry.objects.filter(tenant=cible.tenant, exercice=cible, source=SOURCE_AN)


@transaction.atomic
def generer_a_nouveaux(source, cible=None):
    """Écrit (ou réécrit) les à-nouveaux de `source` dans `cible` (par défaut
    l'exercice qui suit). Idempotent : les anciens à-nouveaux de la cible sont
    remplacés. Refusé si la cible est clôturée."""
    cible = cible or exercice_suivant(source)
    if cible is None:
        raise ValueError("Aucun exercice après celui-ci : créez d'abord l'exercice suivant.")
    if cible.date_debut <= source.date_debut:
        raise ValueError("L'exercice cible doit suivre l'exercice source.")
    if cible.cloture:
        raise ValueError(f"L'exercice {cible.annee_scolaire} est clôturé : ses à-nouveaux sont figés.")
    calcul = calculer_a_nouveaux(source, cible)
    a_nouveaux_existants(cible).delete()
    no_piece = f"AN-{source.annee_scolaire}"[:30]
    for i, l in enumerate(calcul['lignes'], start=1):
        JournalEntry.objects.create(
            tenant=cible.tenant, exercice=cible, no_piece=no_piece, date_ecriture=cible.date_debut,
            source=SOURCE_AN, source_id=source.id, ordre=i, **l)
    t = calcul['tresorerie']
    cible.solde_initial_caisse = t['caisse']
    cible.solde_initial_banque = t['banque']
    cible.solde_initial_mobile = t['mobile']
    cible.an_source = source
    cible.an_genere_le = timezone.now()
    cible.save(update_fields=['solde_initial_caisse', 'solde_initial_banque',
                              'solde_initial_mobile', 'an_source', 'an_genere_le'])
    return {'source': source.annee_scolaire, 'cible': cible.annee_scolaire,
            'nb_lignes': len(calcul['lignes']),
            'tresorerie': {k: float(v) for k, v in t.items()},
            'report': float(calcul['report']), 'no_piece': no_piece,
            'provisoire': not source.cloture}


def controle_continuite(source, cible):
    """Les à-nouveaux de `cible` reflètent-ils encore la clôture de `source` ?

    Écart non nul : l'exercice source a été modifié (régularisation) depuis
    la génération — il faut régénérer.
    """
    attendu = defaultdict(lambda: ZERO)
    for l in calculer_a_nouveaux(source, cible)['lignes']:
        attendu[l['no_compte']] += l['debit'] - l['credit']
    present = defaultdict(lambda: ZERO)
    for r in a_nouveaux_existants(cible).values('no_compte').annotate(d=Sum('debit'), c=Sum('credit')):
        present[r['no_compte']] += _d(r['d']) - _d(r['c'])
    ecarts = []
    for compte in sorted(set(attendu) | set(present)):
        e = attendu[compte] - present[compte]
        if e != 0:
            ecarts.append({'compte': compte, 'attendu': float(attendu[compte]),
                           'present': float(present[compte]), 'ecart': float(e)})
    t = calculer_a_nouveaux(source, cible)['tresorerie']
    for poste, champ in (('caisse', 'solde_initial_caisse'), ('banque', 'solde_initial_banque'),
                         ('mobile', 'solde_initial_mobile')):
        if _d(getattr(cible, champ)) != t[poste]:
            ecarts.append({'compte': f'solde initial {poste}', 'attendu': float(t[poste]),
                           'present': float(getattr(cible, champ)),
                           'ecart': float(t[poste] - _d(getattr(cible, champ)))})
    return ecarts


def situation_exercices(tenant):
    """Tous les exercices, du plus ancien au plus récent, avec leur état
    comptable et la continuité de l'un à l'autre."""
    exercices = list(Exercice.objects.filter(tenant=tenant).order_by('date_debut'))
    courant = (Exercice.objects.filter(tenant=tenant, cloture=False)
               .order_by('-date_debut').first())
    sortie = []
    for i, ex in enumerate(exercices):
        j = JournalEntry.objects.filter(tenant=tenant, exercice=ex)
        agg = j.aggregate(d=Sum('debit'), c=Sum('credit'))
        precedent = exercices[i - 1] if i > 0 else None
        an = a_nouveaux_existants(ex).exists()
        continuite = None
        if precedent is not None and an:
            continuite = controle_continuite(precedent, ex)
        from .models import EtafiArchive
        sortie.append({
            'id': str(ex.id), 'annee_scolaire': ex.annee_scolaire,
            'date_debut': str(ex.date_debut), 'date_fin': str(ex.date_fin),
            'cloture': ex.cloture, 'date_cloture': str(ex.date_cloture) if ex.date_cloture else None,
            'courant': courant is not None and ex.id == courant.id,
            'anterieur_ouvert': not ex.cloture and courant is not None and ex.id != courant.id,
            'nb_ecritures': j.count(),
            'equilibre': abs(_d(agg['d']) - _d(agg['c'])) < 1,
            'ecart_journal': float(_d(agg['d']) - _d(agg['c'])),
            'a_nouveaux': an,
            'an_genere_le': str(ex.an_genere_le) if ex.an_genere_le else None,
            'an_depuis': ex.an_source.annee_scolaire if ex.an_source_id else None,
            'continuite_ok': None if continuite is None else not continuite,
            'ecarts_continuite': continuite or [],
            'balance_importee': j.filter(source=SOURCE_BALANCE).exists(),
            'nb_etafi': EtafiArchive.objects.filter(tenant=tenant, exercice=ex).count(),
        })
    return sortie


# ── Écritures diverses ────────────────────────────────────────────────────────
def _prochain_no(tenant, prefixe, sources):
    dernier = (JournalEntry.objects.filter(tenant=tenant, source__in=sources,
                                           no_piece__startswith=prefixe)
               .aggregate(m=Max('no_piece'))['m'])
    nums = re.findall(r'\d+', dernier or '')
    return f"{prefixe}{int(nums[-1]) + 1 if nums else 1:04d}"


def verifier_lignes(lignes, plan=None):
    """Lignes [{no_compte, debit, credit, libelle?}] → lignes nettoyées.
    ValueError si une ligne est invalide ou si la pièce n'est pas équilibrée."""
    propres = []
    total_d = total_c = ZERO
    for i, l in enumerate(lignes or [], start=1):
        compte = str(l.get('no_compte') or '').strip()
        if not re.fullmatch(r'[1-9][0-9.]{1,19}', compte):
            raise ValueError(f"Ligne {i} : numéro de compte invalide « {compte} ».")
        d, c = _d(l.get('debit')), _d(l.get('credit'))
        if d < 0 or c < 0 or (d and c) or not (d or c):
            raise ValueError(f"Ligne {i} : un montant au débit OU au crédit, positif.")
        propres.append({'no_compte': compte, 'debit': d, 'credit': c,
                        'libelle': str(l.get('libelle') or '').strip(),
                        'activite_id': l.get('activite_id') or None})
        total_d += d
        total_c += c
    if len(propres) < 2:
        raise ValueError('Une écriture compte au moins deux lignes.')
    if total_d != total_c:
        raise ValueError(f"Écriture déséquilibrée : débit {total_d:,.0f} ≠ crédit {total_c:,.0f}.")
    return propres


@transaction.atomic
def saisir_ecriture_diverse(tenant, exercice, date, libelle, lignes):
    from .activites import resoudre_activite
    if exercice.cloture:
        raise ValueError(f"L'exercice {exercice.annee_scolaire} est clôturé.")
    lignes = verifier_lignes(lignes)
    no_piece = _prochain_no(tenant, 'OD-', (SOURCE_OD,))
    for i, l in enumerate(lignes, start=1):
        activite = resoudre_activite(tenant, l.pop('activite_id'))
        JournalEntry.objects.create(
            tenant=tenant, exercice=exercice, no_piece=no_piece, date_ecriture=date,
            source=SOURCE_OD, ordre=i, activite=activite,
            no_compte=l['no_compte'], debit=l['debit'], credit=l['credit'],
            libelle=l['libelle'] or libelle)
    return no_piece


@transaction.atomic
def extourner_ecriture_diverse(tenant, no_piece):
    origine = list(JournalEntry.objects.filter(tenant=tenant, source=SOURCE_OD, no_piece=no_piece))
    if not origine:
        raise ValueError('Écriture introuvable.')
    exercice = origine[0].exercice
    if exercice.cloture:
        raise ValueError(f"L'exercice {exercice.annee_scolaire} est clôturé.")
    if JournalEntry.objects.filter(tenant=tenant, source=SOURCE_ANNUL_OD,
                                   no_piece=f"X{no_piece}").exists():
        raise ValueError('Écriture déjà extournée.')
    for e in origine:
        JournalEntry.objects.create(
            tenant=tenant, exercice=exercice, no_piece=f"X{no_piece}",
            date_ecriture=timezone.localdate() if timezone.localdate() <= exercice.date_fin
            else exercice.date_fin,
            source=SOURCE_ANNUL_OD, source_id=e.id, ordre=e.ordre, no_compte=e.no_compte,
            debit=e.credit, credit=e.debit, libelle=f"EXTOURNE — {e.libelle}",
            activite=e.activite)
    return f"X{no_piece}"


# ── Import de balance ─────────────────────────────────────────────────────────
def lire_balance(fichier):
    """Lit un .xlsx ou un .csv : colonnes « compte », « libellé » (facultatif),
    « débit » et « crédit » (ou « solde »). Rend [{no_compte, libelle, debit, credit}]."""
    import csv
    import io
    nom = getattr(fichier, 'name', '').lower()
    if nom.endswith('.csv'):
        texte = fichier.read().decode('utf-8-sig', errors='replace')
        dialecte = csv.Sniffer().sniff(texte[:2048], delimiters=';,\t')
        lignes = list(csv.reader(io.StringIO(texte), dialecte))
    else:
        import openpyxl
        feuille = openpyxl.load_workbook(fichier, data_only=True, read_only=True).active
        lignes = [list(r) for r in feuille.iter_rows(values_only=True)]

    def norm(v):
        import unicodedata
        v = unicodedata.normalize('NFD', str(v or '')).encode('ascii', 'ignore').decode().lower()
        return v.strip()

    entete = None
    for i, l in enumerate(lignes[:15]):
        n = [norm(c) for c in l]
        if any('compte' in c for c in n) and any(c.startswith(('debit', 'credit', 'solde')) for c in n):
            entete = (i, n)
            break
    if entete is None:
        raise ValueError("En-tête introuvable : il faut des colonnes « Compte », « Débit » et "
                         "« Crédit » (ou « Solde »).")
    debut, n = entete

    def col(*mots):
        for j, c in enumerate(n):
            if any(c.startswith(m) or m in c for m in mots):
                return j
        return None

    c_cpt, c_lib = col('compte', 'n° compte'), col('libelle', 'intitule')
    c_d, c_c, c_s = col('debit'), col('credit'), col('solde')

    def nombre(v):
        if v in (None, ''):
            return ZERO
        if isinstance(v, (int, float, Decimal)):
            return _d(v)
        s = str(v).replace(' ', '').replace('\xa0', '').replace(' ', '').replace(',', '.')
        try:
            return _d(s)
        except Exception:
            raise ValueError(f"Montant illisible : « {v} ».")

    resultat = []
    for l in lignes[debut + 1:]:
        if c_cpt is None or c_cpt >= len(l) or l[c_cpt] in (None, ''):
            continue
        compte = str(l[c_cpt]).strip().split('.')[0] if isinstance(l[c_cpt], float) else str(l[c_cpt]).strip()
        if not re.fullmatch(r'[1-9][0-9.]*', compte):
            continue                       # ligne de total, de classe…
        if c_s is not None and c_d is None:
            s = nombre(l[c_s])
            d, c = (s, ZERO) if s > 0 else (ZERO, -s)
        else:
            d = nombre(l[c_d]) if c_d is not None and c_d < len(l) else ZERO
            c = nombre(l[c_c]) if c_c is not None and c_c < len(l) else ZERO
            net = d - c                    # une balance « mouvements » donne les deux colonnes
            d, c = (net, ZERO) if net > 0 else (ZERO, -net)
        if d == 0 and c == 0:
            continue
        resultat.append({'no_compte': compte,
                         'libelle': str(l[c_lib]).strip() if c_lib is not None and c_lib < len(l) and l[c_lib] else '',
                         'debit': d, 'credit': c})
    return resultat


@transaction.atomic
def importer_balance(exercice, lignes, nature='CLOTURE'):
    """Importe une balance dans l'exercice (remplace l'import précédent).

    OUVERTURE : soldes au premier jour. La trésorerie (571/521/552x) va aux
    soldes initiaux de l'exercice, comme pour les à-nouveaux ; la pièce garde
    les autres comptes + 890 en contrepartie.
    CLOTURE : tous les comptes de l'année (classes 1 à 8) — l'exercice dont
    on n'a que la balance finale. Trésorerie comprise, en écritures : les
    soldes initiaux de l'exercice sont remis à zéro pour ne pas la compter
    deux fois.
    """
    if exercice.cloture:
        raise ValueError(f"L'exercice {exercice.annee_scolaire} est clôturé.")
    if nature not in ('OUVERTURE', 'CLOTURE'):
        raise ValueError('Nature de balance inconnue.')
    lignes = verifier_lignes(lignes)
    if nature == 'OUVERTURE':
        hors_bilan = [l['no_compte'] for l in lignes if not est_compte_bilan(l['no_compte'])]
        if hors_bilan:
            raise ValueError("Une balance d'ouverture ne contient que des comptes de bilan "
                             f"(classes 1 à 5) : {', '.join(hors_bilan[:5])}…")

    JournalEntry.objects.filter(tenant=exercice.tenant, exercice=exercice, source=SOURCE_BALANCE).delete()
    treso = {poste: ZERO for poste in PREFIXES_TRESO}
    a_ecrire = []
    for l in lignes:
        poste = next((p for p, pref in PREFIXES_TRESO.items() if l['no_compte'].startswith(pref)), None)
        if nature == 'OUVERTURE' and poste:
            treso[poste] += l['debit'] - l['credit']
        else:
            a_ecrire.append(l)
    contrepartie = sum(treso.values(), ZERO)
    if contrepartie:
        a_ecrire.append({'no_compte': COMPTE_A_NOUVEAUX,
                         'debit': contrepartie if contrepartie > 0 else ZERO,
                         'credit': -contrepartie if contrepartie < 0 else ZERO,
                         'libelle': "Balance d'ouverture — trésorerie (soldes initiaux)"})
    date = exercice.date_debut if nature == 'OUVERTURE' else exercice.date_fin
    no_piece = f"BAL-{'OUV' if nature == 'OUVERTURE' else 'CLO'}-{exercice.annee_scolaire}"[:30]
    plan = _libelles(exercice.tenant)
    for i, l in enumerate(a_ecrire, start=1):
        JournalEntry.objects.create(
            tenant=exercice.tenant, exercice=exercice, no_piece=no_piece, date_ecriture=date,
            source=SOURCE_BALANCE, ordre=i, no_compte=l['no_compte'], debit=l['debit'],
            credit=l['credit'],
            libelle=l.get('libelle') or f"Balance {nature.lower()} — {plan.get(l['no_compte'], l['no_compte'])}")
    if nature == 'OUVERTURE':
        exercice.solde_initial_caisse = treso['caisse']
        exercice.solde_initial_banque = treso['banque']
        exercice.solde_initial_mobile = treso['mobile']
    else:
        exercice.solde_initial_caisse = exercice.solde_initial_banque = exercice.solde_initial_mobile = ZERO
    exercice.save(update_fields=['solde_initial_caisse', 'solde_initial_banque', 'solde_initial_mobile'])
    return {'no_piece': no_piece, 'nb_lignes': len(a_ecrire), 'nature': nature,
            'tresorerie': {k: float(v) for k, v in treso.items()},
            'total': float(sum((l['debit'] for l in lignes), ZERO))}
