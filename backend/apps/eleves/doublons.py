"""Garde-fou contre la double inscription d'un même élève.

Constat à une installation (08/10/2026) : un élève saisi une seconde fois par
erreur ouvre une seconde fiche, avec son propre dû. La famille est réclamée
deux fois, les effectifs sont faux, et personne ne sait laquelle des deux
fiches fait foi.

Avant de créer une fiche, on cherche dans l'école :

  · CERTAIN  — même nom (accents, casse, espaces et ordre des mots ignorés)
               et même date de naissance ;
  · PROBABLE — même nom, l'une des deux dates manquante ; ou même nom, date
               différente (faute de frappe) mais un téléphone de parent commun.

Deux homonymes nés à des dates différentes, sans parent commun, ne sont pas un
doublon. Des jumeaux (même date, même téléphone) n'ont pas le même nom : ils
ne sont pas signalés non plus.

Seule une fiche du MÊME exercice bloque la création — l'utilisateur peut
alors confirmer (vrai homonyme). Une fiche d'un autre exercice est signalée
sans bloquer : c'est le plus souvent un ancien élève, à réinscrire.
"""
import unicodedata

from django.utils import timezone


class DoublonEleve(Exception):
    """La fiche existe déjà. `corps` décrit la ou les fiches trouvées ; la vue
    le renvoie tel quel en 409 (une APIException en ferait des chaînes)."""
    def __init__(self, corps):
        super().__init__(corps.get('error', ''))
        self.corps = corps


def cle_nom(nom):
    """« Awa  NDIAYE », « ndiaye awa », « Àwa Ndiaye » → même clé."""
    s = unicodedata.normalize('NFKD', str(nom or ''))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = ''.join(c if c.isalnum() else ' ' for c in s.lower())
    return ' '.join(sorted(s.split()))


def _chiffres(tel):
    """Les 9 derniers chiffres : +221 77 123 45 67 et 771234567 se valent."""
    chiffres = ''.join(c for c in str(tel or '') if c.isdigit())
    return chiffres[-9:] if len(chiffres) >= 7 else ''


def _telephones(obj):
    get = obj.get if isinstance(obj, dict) else (lambda k: getattr(obj, k, ''))
    return {t for t in (_chiffres(get('telephone_pere')), _chiffres(get('telephone_mere')),
                        _chiffres(get('telephone_tuteur'))) if t}


def chercher_doublons(tenant, donnees, exercice=None, exclure=None):
    """Fiches de l'école qui ressemblent à `donnees` (nom_complet,
    date_naissance, téléphones des parents). Les plus sûres d'abord."""
    from .models import Eleve

    cle = cle_nom(donnees.get('nom_complet'))
    if not cle:
        return []
    naissance = donnees.get('date_naissance')
    if isinstance(naissance, str):
        from django.utils.dateparse import parse_date
        naissance = parse_date(naissance[:10]) if naissance else None
    tels = _telephones(donnees)

    # Rapprochement sur les seuls noms (requête légère), puis lecture des
    # fiches retenues. Pas d'`unaccent` : l'extension PostgreSQL n'est pas
    # garantie sur les postes Windows.
    # Les fiches de créance (dettes d'années passées) ne sont pas des inscriptions.
    noms = Eleve.objects.filter(tenant=tenant, fiche_creance=False)
    if exclure:
        noms = noms.exclude(pk=exclure)
    ids = [pk for pk, nom in noms.values_list('pk', 'nom_complet') if cle_nom(nom) == cle]
    qs = Eleve.objects.filter(pk__in=ids).select_related('exercice', 'section', 'classe')

    trouves = []
    for e in qs:
        if naissance and e.date_naissance:
            if naissance == e.date_naissance:
                certitude = 'CERTAIN'
            elif tels & _telephones(e):
                certitude = 'PROBABLE'
            else:
                continue
        else:
            certitude = 'PROBABLE'
        trouves.append(_decrire(e, certitude, exercice))
    trouves.sort(key=lambda d: (not d['meme_exercice'], d['certitude'] != 'CERTAIN',
                                d['cree_le'] or ''))
    return trouves


def bloquants(doublons):
    """Ceux qui empêchent la création sans confirmation : même exercice."""
    return [d for d in doublons if d['meme_exercice']]


def message(doublons):
    """« Awa NDIAYE est déjà enregistrée : … le 08/10/2026 à 10:42 par … »."""
    d = doublons[0]
    quand = f" le {d['cree_le_texte']}" if d['cree_le_texte'] else ''
    par = f" par {d['cree_par']}" if d['cree_par'] else ''
    ou = ', '.join(x for x in (d['matricule'], d['section'], d['classe']) if x)
    autres = f" (et {len(doublons) - 1} autre(s) fiche(s) semblable(s))" if len(doublons) > 1 else ''
    return (f"{d['nom_complet']} est déjà enregistré(e) dans le système{quand}{par}"
            f"{' — ' + ou if ou else ''}{autres}.")


def _decrire(e, certitude, exercice):
    cree = timezone.localtime(e.created_at) if e.created_at else None
    return {
        'id':             str(e.id),
        'nom_complet':    e.nom_complet,
        'matricule':      e.matricule or '',
        'date_naissance': e.date_naissance.isoformat() if e.date_naissance else None,
        'section':        e.section.nom if e.section_id else '',
        'classe':         e.classe.nom if e.classe_id else '',
        'statut':         e.statut,
        'exercice':       e.exercice.annee_scolaire if e.exercice_id else '',
        'meme_exercice':  bool(exercice and e.exercice_id == exercice.id),
        'certitude':      certitude,
        'cree_le':        cree.isoformat() if cree else None,
        'cree_le_texte':  cree.strftime('%d/%m/%Y à %H:%M') if cree else '',
        'cree_par':       e.cree_par or '',
    }

