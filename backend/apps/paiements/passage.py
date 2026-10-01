"""Passage de fin d'année — passe, redouble ou sort, sans ressaisir les élèves.

La clôture crée l'exercice suivant mais ne recopiait que les élèves endettés
(report_reliquats), dans leur MÊME section. Une école de 900 élèves aurait dû
réinscrire tous les autres à la main.

Règles (validées le 01/10/2026) :
  · par défaut, tout le monde PASSE dans la section suivante ; la direction
    coche les redoublants et les sorties (diplômé, transféré, abandon) ;
  · la section suivante est celle qui vient juste après dans l'ordre configuré
    (CI → CP → CE1…, 6ème → 5ème…, 2nde → 1ère → TL) ;
  · dans une école qui range ses sections par NIVEAU scolaire, une section
    sans niveau (garderie, internat) est une formule, pas une classe : l'élève
    y est reconduit. Une école qui n'utilise pas les niveaux fait progresser
    toutes ses sections selon leur ordre ;
  · ordre jamais réglé (tout à 0) : signalé, et la section d'arrivée est à
    choisir — un clic par section dans l'assistant ;
  · on ne change de niveau que vers le niveau qui suit naturellement
    (préscolaire → élémentaire → collège → lycée) : sans collège, le CM2
    termine son cycle. La dernière section d'un cycle propose « diplômé » ;
  · deux sections au même rang suivant (1ère L / 1ère S) : on prend celle de
    la même série si le nom le dit (1ère L → TL), sinon la direction choisit.

Les fiches du nouvel exercice reprennent l'identité de l'élève (matricule,
famille, parents, santé, prise en charge : CHAMPS_IDENTITE de report_reliquats).
Le passage est rejouable : une fiche déjà présente sur l'exercice cible (créée
par le report des impayés ou par un passage précédent) est mise à jour, jamais
dupliquée.
"""
import re

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.eleves.models import Eleve, Section

from .models import Exercice
from .report_reliquats import CHAMPS_IDENTITE, STATUTS_SORTIE, _fiche_cible

DECISIONS = ('PASSE', 'REDOUBLE', 'SORT', 'IGNORER')
# Le niveau où l'on continue après le dernier de celui-ci ; rien après le
# lycée (le supérieur est un autre établissement, ou une inscription neuve).
NIVEAU_SUIVANT = {'PRESCOLAIRE': 'ELEMENTAIRE', 'ELEMENTAIRE': 'COLLEGE', 'COLLEGE': 'LYCEE'}
MOTIFS_SORTIE = ('DIPLOME', 'TRANSFERE', 'ABANDONNE')


# ── Exercices concernés ───────────────────────────────────────────────────
def exercice_suivant(exercice):
    """L'exercice qui suit `exercice` (ouvert), ou None."""
    return (Exercice.objects
            .filter(tenant=exercice.tenant, date_debut__gt=exercice.date_debut, cloture=False)
            .order_by('date_debut').first())


def exercice_source_par_defaut(tenant):
    """Le dernier exercice clôturé qui a un successeur ouvert."""
    for ex in Exercice.objects.filter(tenant=tenant, cloture=True).order_by('-date_debut'):
        if exercice_suivant(ex):
            return ex
    return None


# ── Section suivante ──────────────────────────────────────────────────────
def _serie(nom):
    """La série portée par le nom : « 1ère L » → « L » ; rien pour « CP »."""
    mots = nom.upper().split()
    return mots[-1] if len(mots) > 1 and len(mots[-1]) <= 3 else ''


def _sans_espaces(nom):
    return re.sub(r'\s+', '', nom.upper())


def plan_sections(tenant):
    """{section_id: {section, progression, suivante, derniere}} et un drapeau
    « ordre à configurer » quand les sections qui progressent ont toutes le
    même rang (cas de toute école qui n'a jamais réglé l'ordre)."""
    sections = list(Section.objects.filter(tenant=tenant).select_related('niveau')
                    .order_by('ordre', 'nom'))
    # Une école qui range ses sections par niveau : celles qui n'en ont pas
    # sont des formules (garderie, internat), pas des classes. Une école qui
    # n'utilise pas les niveaux : toutes ses sections sont des classes.
    utilise_niveaux = any(x.niveau_id for x in sections)
    progressives = [x for x in sections if x.niveau_id or not utilise_niveaux]
    ordre_a_configurer = len(progressives) > 1 and len({x.ordre for x in progressives}) == 1

    def meme_cycle(depuis, vers):
        if not (depuis.niveau_id and vers.niveau_id):
            return True
        code = depuis.niveau.code
        return vers.niveau.code in (code, NIVEAU_SUIVANT.get(code))

    plan = {}
    for s in sections:
        if s not in progressives:
            plan[s.id] = {'section': s, 'progression': False, 'suivante': s, 'derniere': False}
            continue
        if ordre_a_configurer:
            plan[s.id] = {'section': s, 'progression': True, 'suivante': None, 'derniere': False}
            continue
        plus_haut = [x for x in progressives if x.ordre > s.ordre and meme_cycle(s, x)]
        if not plus_haut:
            plan[s.id] = {'section': s, 'progression': True, 'suivante': None, 'derniere': True}
            continue
        rang = min(x.ordre for x in plus_haut)
        candidates = [x for x in plus_haut if x.ordre == rang]
        suivante = candidates[0] if len(candidates) == 1 else None
        if suivante is None and (serie := _serie(s.nom)):
            meme = [x for x in candidates if _sans_espaces(x.nom).endswith(serie)]
            suivante = meme[0] if len(meme) == 1 else None
        plan[s.id] = {'section': s, 'progression': True, 'suivante': suivante, 'derniere': False}
    return plan, ordre_a_configurer


def proposition(eleve, plan):
    """La décision proposée pour un élève : passe, ou diplômé en fin de cycle."""
    if eleve.regime == 'PASSAGER':
        # Durée de séjour convenue : on ne devine pas les mois restants.
        return {'decision': 'IGNORER', 'section_id': None, 'motif': ''}
    p = plan.get(eleve.section_id)
    if p is None:
        return {'decision': 'PASSE', 'section_id': None, 'motif': ''}
    if p['derniere']:
        return {'decision': 'SORT', 'section_id': None, 'motif': 'DIPLOME'}
    return {'decision': 'PASSE',
            'section_id': str(p['suivante'].id) if p['suivante'] else None, 'motif': ''}


# ── Lecture : l'écran de l'assistant ──────────────────────────────────────
def eleves_concernes(source):
    """Les élèves présents de l'exercice source."""
    return (Eleve.objects
            .filter(tenant=source.tenant, exercice=source, fiche_creance=False)
            .exclude(statut__in=STATUTS_SORTIE)
            .select_related('section', 'classe'))


def apercu(source, cible):
    plan, ordre_a_configurer = plan_sections(source.tenant)
    fiches_cible = {}
    for f in (Eleve.objects.filter(tenant=source.tenant, exercice=cible)
              .select_related('section')):
        if f.eleve_precedent_id:
            fiches_cible[('id', f.eleve_precedent_id)] = f
        if f.matricule:
            fiches_cible.setdefault(('mat', f.matricule), f)

    eleves = []
    for e in eleves_concernes(source).order_by('section__ordre', 'section__nom', 'nom_complet'):
        deja = fiches_cible.get(('id', e.id)) or (
            fiches_cible.get(('mat', e.matricule)) if e.matricule else None)
        eleves.append({
            'id':          str(e.id),
            'matricule':   e.matricule or '',
            'nom_complet': e.nom_complet,
            'section_id':  str(e.section_id) if e.section_id else None,
            'section':     e.section.nom if e.section_id else '',
            'classe':      e.classe.nom if e.classe_id else '',
            'regime':      e.regime,
            'proposition': proposition(e, plan),
            'deja': {
                'fiche_id':   str(deja.id),
                'section_id': str(deja.section_id) if deja.section_id else None,
                'section':    deja.section.nom if deja.section_id else '',
                'redoublant': deja.redoublant,
                # Décision déjà prise par l'assistant (sinon : simple report
                # des impayés dans la même section, rien n'est encore décidé).
                'passe':      deja.passage_le is not None,
                'creance':    deja.fiche_creance,
                'reliquat':   float(deja.reliquat_anterieur or 0),
            } if deja else None,
        })

    return {
        'source': {'id': str(source.id), 'annee': source.annee_scolaire, 'cloture': source.cloture},
        'cible':  {'id': str(cible.id), 'annee': cible.annee_scolaire},
        'ordre_a_configurer': ordre_a_configurer,
        'sections': [{
            'id':          str(p['section'].id),
            'nom':         p['section'].nom,
            'ordre':       p['section'].ordre,
            'progression': p['progression'],
            'derniere':    p['derniere'],
            'suivante_id': str(p['suivante'].id) if p['suivante'] else None,
            'suivante':    p['suivante'].nom if p['suivante'] else '',
        } for p in sorted(plan.values(), key=lambda p: (p['section'].ordre, p['section'].nom))],
        'eleves': eleves,
    }


# ── Écriture : appliquer les décisions ────────────────────────────────────
def _classe_unique(section):
    """La classe de la section quand elle n'en a qu'une (sinon l'école répartit)."""
    classes = list(section.classes.all()[:2]) if section else []
    return classes[0] if len(classes) == 1 else None


def _ouvrir_fiche(eleve, cible, section, redoublant):
    valeurs = {champ: getattr(eleve, champ) for champ in CHAMPS_IDENTITE}
    valeurs.update(section=section, statut='INSCRIT')
    return Eleve.objects.create(
        tenant=eleve.tenant, exercice=cible, eleve_precedent=eleve,
        date_inscription=cible.date_debut, date_inscription_jour_estime=False,
        regime='EXERCICE', nb_mois_passager=None, fiche_creance=False,
        redoublant=redoublant, passage_le=timezone.now(),
        classe=eleve.classe if redoublant else _classe_unique(section),
        **valeurs)


def _sortir(eleve, motif, source, utilisateur):
    """Pose la sortie sur la fiche de l'année qui se termine, tracée comme
    toute sortie (et donc annulable si elle était une erreur)."""
    from apps.eleves.reintegration import tracer_sortie
    statut_avant = eleve.statut
    eleve.statut = motif
    eleve.date_sortie = eleve.date_sortie or source.date_fin
    eleve.save(update_fields=['statut', 'date_sortie'])
    tracer_sortie(eleve, statut_avant, motif=f"Passage de fin d'année {source.annee_scolaire}",
                  utilisateur=utilisateur)


def appliquer(source, cible, decisions, utilisateur=''):
    """Applique [{eleve_id, decision, section_id?, motif?}] ; rend un rapport.

    Chaque élève est traité dans sa propre transaction : une erreur sur une
    fiche (numéro déjà pris…) est rapportée sans bloquer les autres.
    """
    if cible.cloture:
        raise ValueError(f"L'exercice {cible.annee_scolaire} est clôturé.")
    if cible.tenant_id != source.tenant_id or cible.id == source.id:
        raise ValueError("Exercice cible invalide.")

    eleves = {str(e.id): e for e in eleves_concernes(source)}
    deja_sortis = {str(i) for i in Eleve.objects.filter(
        tenant=source.tenant, exercice=source, fiche_creance=False,
        statut__in=STATUTS_SORTIE).values_list('id', flat=True)}
    sections = {str(s.id): s for s in Section.objects.filter(tenant=source.tenant)}
    rapport = {'passes': 0, 'redoublants': 0, 'sortis': 0, 'ignores': 0, 'deja_sortis': 0,
               'creees': 0, 'mises_a_jour': 0, 'erreurs': []}

    for d in decisions:
        eleve = eleves.get(str(d.get('eleve_id')))
        decision = d.get('decision')
        if eleve is None and str(d.get('eleve_id')) in deja_sortis:
            # Rejeu : sorti au passage précédent. Le faire revenir passe par
            # « annuler la sortie » (onglet Anciens), pas par ici.
            if decision in ('SORT', 'IGNORER'):
                rapport['deja_sortis'] += 1
            else:
                rapport['erreurs'].append({'eleve_id': d.get('eleve_id'),
                                           'erreur': "Déjà sorti : annulez d'abord sa sortie (Élèves → Anciens)."})
            continue
        if eleve is None or decision not in DECISIONS:
            rapport['erreurs'].append({'eleve_id': d.get('eleve_id'),
                                       'erreur': 'Élève ou décision inconnu(e).'})
            continue
        if decision == 'IGNORER':
            rapport['ignores'] += 1
            continue
        try:
            with transaction.atomic():
                _appliquer_un(eleve, decision, d, source, cible, sections, utilisateur, rapport)
        except (ValueError, IntegrityError) as exc:
            rapport['erreurs'].append({'eleve_id': str(eleve.id), 'nom_complet': eleve.nom_complet,
                                       'erreur': str(exc) if isinstance(exc, ValueError)
                                       else "Fiche en conflit sur l'exercice cible (matricule ou numéro déjà pris)."})
    rapport['nb_erreurs'] = len(rapport['erreurs'])
    return rapport


def _appliquer_un(eleve, decision, d, source, cible, sections, utilisateur, rapport):
    fiche = _fiche_cible(eleve, cible)

    if decision == 'SORT':
        motif = d.get('motif') or 'DIPLOME'
        if motif not in MOTIFS_SORTIE:
            raise ValueError(f"Motif de sortie inconnu : {motif}.")
        _sortir(eleve, motif, source, utilisateur)
        if fiche:
            # Il ne revient pas, mais sa dette reportée le suit : la fiche
            # reste une créance, hors des listes et des effectifs.
            fiche.statut, fiche.fiche_creance = motif, True
            fiche.save(update_fields=['statut', 'fiche_creance'])
        rapport['sortis'] += 1
        return

    redoublant = decision == 'REDOUBLE'
    if redoublant:
        section = eleve.section
    else:
        section = sections.get(str(d.get('section_id') or ''))
        if section is None:
            raise ValueError("Section d'arrivée à choisir.")

    if fiche is None:
        _ouvrir_fiche(eleve, cible, section, redoublant)
        rapport['creees'] += 1
    else:
        fiche.section, fiche.redoublant = section, redoublant
        fiche.statut, fiche.fiche_creance = 'INSCRIT', False
        fiche.passage_le = timezone.now()
        if not fiche.eleve_precedent_id:
            fiche.eleve_precedent = eleve
        fiche.save(update_fields=['section', 'redoublant', 'statut', 'fiche_creance',
                                  'eleve_precedent', 'passage_le'])
        rapport['mises_a_jour'] += 1
    rapport['redoublants' if redoublant else 'passes'] += 1
