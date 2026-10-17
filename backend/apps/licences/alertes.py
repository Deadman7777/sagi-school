"""Alertes de fin de licence dans l'application de l'école.

Demande de la direction (17/10/2026, licence des Petits Érudits qui expire le
lendemain) : un badge sur l'icône de l'application, un rappel à chaque
connexion avec la date d'expiration et un bouton « Renouveler maintenant »
qui mène au paiement, une alerte prioritaire une fois la licence expirée — et
le statut qui se met à jour dès que le renouvellement est confirmé.

**Un seul calcul.** `etat()` dit, pour une licence et un jour, dans quelle
phase on est, quel palier, quel message, quel badge. Le badge de la barre du
haut, le badge de l'icône, le rappel de connexion, le bandeau prioritaire et
l'écran « Ma licence » lisent tous ce dictionnaire : aucun ne recalcule de
son côté (voir la règle « un seul calcul par grandeur »).

**Phases.**
  NORMAL   : plus loin que le premier palier — rien à signaler ;
  ECHEANCE : entre le premier palier (J-7 par défaut) et le jour J ;
  EXPIREE  : date de fin dépassée, pendant les jours de grâce ;
  COUPEE   : grâce épuisée ou licence suspendue — modules coupés.

**Réglable par HADY GESMAN** (écran Facturation → Paramètres) : les paliers
(7,3,1,0 par défaut, les mêmes que les relances e-mail), l'interrupteur des
alertes, le lien de paiement en ligne et les coordonnées de paiement.

**Installations locales.** Ces réglages vivent sur le cloud ; le poste de
l'école les y lit (`etat-distant`, authentifié par la clé de licence), avec la
date de fin que le cloud connaît. Un renouvellement confirmé sur le cloud
prolonge donc la licence locale à la consultation suivante, sans intervention
sur place. Hors connexion : les réglages par défaut, et la licence locale
telle qu'elle est.
"""
import json
import logging
import urllib.error
import urllib.request
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from . import catalogue
from .models import Licence

logger = logging.getLogger(__name__)

PALIERS_DEFAUT = (7, 3, 1, 0)
TIMEOUT_DISTANT = 6
CACHE_DISTANT = 15 * 60          # un renouvellement confirmé se voit sous 15 min (ou tout de suite par « Actualiser »)
CACHE_ECHEC = 5 * 60

# Formules proposées au renouvellement : (mois, libellé, clé dans catalogue.formules).
FORMULES = ((1, '1 mois', 'mensuelle'), (6, '6 mois', 'semestrielle'), (12, '12 mois', 'annuelle'))


def lire_paliers(texte):
    """« 7, 3,1,0 » → (7, 3, 1, 0). Décroissant, sans doublon, de 0 à 60 jours."""
    vus = set()
    for morceau in str(texte or '').replace(';', ',').split(','):
        morceau = morceau.strip().upper().lstrip('J').lstrip('-').strip()
        if morceau.isdigit() and 0 <= int(morceau) <= 60:
            vus.add(int(morceau))
    return tuple(sorted(vus, reverse=True)) or PALIERS_DEFAUT


def palier_courant(jours, paliers=PALIERS_DEFAUT):
    """Le palier dont relève une licence à `jours` de son échéance, ou None.

    Paliers 7,3,1,0 : 7 → 7 ; 5 → 7 ; 2 → 3 ; 0 → 0 ; 8 ou -1 → None.
    """
    if jours is None or jours < 0 or not paliers or jours > max(paliers):
        return None
    return min(p for p in paliers if p >= jours)


# ── Réglages ────────────────────────────────────────────────────────────

def _config_locale():
    from apps.prospects.models import ParametresFacturation
    p = ParametresFacturation.actuels()
    return {
        'actif': p.alertes_ecoles,
        'paliers': list(lire_paliers(p.paliers_alerte)),
        'lien_paiement': p.lien_paiement,
        'coordonnees_paiement': p.coordonnees_paiement,
        'telephone': p.telephone or getattr(settings, 'EDITEUR_TELEPHONE', ''),
        'email': p.email or getattr(settings, 'LICENCE_SUPPORT_EMAIL', ''),
    }


def config_publique():
    """Ce que le cloud communique aux installations locales."""
    return _config_locale()


def _distant(licence, forcer=False):
    """Installation locale : {'licence': {...}|None, 'config': {...}} lus sur le cloud, ou None."""
    cle_cache = f'licence-distant:{licence.cle_licence}'
    if not forcer:
        en_cache = cache.get(cle_cache)
        if en_cache is not None:
            return en_cache or None
    url = settings.SAGI_CLOUD_URL.rstrip('/') + '/api/licences/etat-distant/'
    requete = urllib.request.Request(url, data=b'{}', method='POST', headers={
        'Content-Type': 'application/json',
        # Sans User-Agent explicite, Cloudflare bloque « Python-urllib ».
        'User-Agent': 'SAGI-SCHOOL-Licence/1.0 (+https://sagi-school.com)',
        'X-Cle-Licence': licence.cle_licence,
    })
    try:
        with urllib.request.urlopen(requete, timeout=TIMEOUT_DISTANT) as reponse:
            data = json.loads(reponse.read().decode('utf-8') or '{}')
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.info('Licence %s : cloud injoignable (%s)', licence.cle_licence, exc)
        cache.set(cle_cache, {}, CACHE_ECHEC)
        return None
    cache.set(cle_cache, data, CACHE_DISTANT)
    return data


def synchroniser(licence, distant):
    """Aligne la licence locale sur le cloud — seulement pour la PROLONGER.

    Une copie cloud en retard (école renouvelée sur place) ne doit jamais
    raccourcir la licence locale ni couper l'accès. Rend True si modifiée.
    """
    import datetime
    l = (distant or {}).get('licence') or {}
    try:
        date_fin = datetime.date.fromisoformat(str(l.get('date_fin') or ''))
    except ValueError:
        return False
    if date_fin <= licence.date_fin:
        return False
    licence.date_fin = date_fin
    if l.get('type') in dict(Licence.TYPE_CHOICES):
        licence.type = l['type']
    if licence.statut != 'SUSPENDUE':
        licence.statut = 'ACTIVE' if licence.type != 'ESSAI' else licence.statut
    licence.save(update_fields=['date_fin', 'type', 'statut', 'updated_at'])
    # La demande faite depuis ce poste est honorée : elle ne reste pas « en attente ».
    licence.demandes_renouvellement.filter(traitee=False).update(
        traitee=True, confirmee=True, traitee_le=timezone.now())
    logger.info('Licence %s prolongée depuis le cloud jusqu\'au %s', licence.cle_licence, date_fin)
    return True


def config(licence=None, forcer=False):
    """Réglages des alertes. En local, ceux du cloud quand il répond (et la
    licence est alors synchronisée au passage)."""
    if getattr(settings, 'SAGI_EST_CLOUD', False) or licence is None:
        return _config_locale()
    distant = _distant(licence, forcer=forcer)
    if distant:
        synchroniser(licence, distant)
        cfg = distant.get('config') or {}
        base = _config_locale()
        base.update({k: v for k, v in cfg.items() if k in base and v not in (None, '')})
        base['paliers'] = list(lire_paliers(','.join(map(str, base['paliers']))))
        return base
    return _config_locale()


# ── Offre de renouvellement ─────────────────────────────────────────────

def offres(licence):
    """Les formules chiffrées proposées par « Renouveler maintenant ».

    Licence payante : son type, en 1, 6 ou 12 mois. Essai : chaque licence
    payante, l'école choisit.
    """
    from apps.prospects.proposition import libelle_licence
    types = ([licence.type] if licence.type != 'ESSAI'
             else [c for c, _ in Licence.TYPE_CHOICES if catalogue.tarif_mensuel(c)])
    resultat = []
    for code in types:
        prix = catalogue.tarif_mensuel(code)
        if not prix:
            continue
        ch = catalogue.formules(prix, catalogue.remise_semestrielle(),
                                catalogue.remise_annuelle(), 0, 0)
        resultat.append({'type': code, 'libelle': libelle_licence(code), 'formules': [{
            'mois': mois, 'libelle': libelle, 'montant': ch[cle]['net'],
            'remise': ch[cle]['remise'],
        } for mois, libelle, cle in FORMULES]})
    return resultat


def montant(type_licence, mois):
    """Le montant d'une formule, recalculé par le serveur (jamais celui du client)."""
    lic = Licence(type=type_licence)
    for o in offres(lic):
        for f in o['formules']:
            if o['type'] == type_licence and f['mois'] == mois:
                return f['montant']
    return None


# ── L'état d'alerte ─────────────────────────────────────────────────────

def _date(d):
    from apps.prospects.proposition import date_longue
    return date_longue(d)


def etat(licence, aujourdhui=None, cfg=None):
    """Tout ce qu'il faut à l'écran pour alerter l'école. Voir le docstring du module."""
    aujourdhui = aujourdhui or timezone.localdate()
    cfg = cfg or _config_locale()
    paliers = tuple(cfg['paliers']) or PALIERS_DEFAUT
    jours = (licence.date_fin - aujourdhui).days
    # Premier jour sans les modules (acces_expire : aujourd'hui > fin + grâce).
    coupure = licence.date_fin + timedelta(days=Licence.GRACE_JOURS + 1)
    essai = licence.type == 'ESSAI'
    quoi = "Votre période d'essai" if essai else 'Votre licence SAGI SCHOOL'
    fin, coupe_le = _date(licence.date_fin), _date(coupure)
    palier = palier_courant(jours, paliers)

    if licence.acces_expire:
        phase, niveau = 'COUPEE', 'expiree'
        if licence.statut == 'SUSPENDUE':
            titre = 'Licence suspendue'
            texte = ("L'accès aux modules est suspendu. Contactez HADY GESMAN pour le "
                     "rétablir.")
        else:
            titre = 'Licence expirée — accès limité'
            texte = (f"{quoi} a expiré le {fin}. Depuis le {coupe_le}, seuls « Ma licence » "
                     f"et « Paramètres » sont accessibles. Vos données sont conservées : "
                     f"renouvelez pour retrouver tous les modules.")
    elif jours < 0:
        phase, niveau = 'EXPIREE', 'expiree'
        reste = (coupure - aujourdhui).days
        titre = f'Licence expirée le {fin}'
        texte = (f"{quoi} a expiré le {fin}. Sans renouvellement, l'accès aux modules sera "
                 f"limité à « Ma licence » et « Paramètres » "
                 + ("dès demain." if reste == 1 else f"à partir du {coupe_le} (dans {reste} jours)."))
    elif palier is not None:
        phase = 'ECHEANCE'
        niveau = 'critique' if jours <= 1 else 'urgent' if jours <= 3 else 'attention'
        quand = ("expire aujourd'hui" if jours == 0 else 'expire demain' if jours == 1
                 else f'expire dans {jours} jours')
        titre = f"{quoi} {quand}"
        texte = (f"Échéance le {fin}. Renouvelez dès maintenant pour éviter toute "
                 f"interruption : après {Licence.GRACE_JOURS} jours de grâce, l'accès aux "
                 f"modules serait limité (à partir du {coupe_le}).")
    else:
        phase, niveau, titre, texte = 'NORMAL', 'ok', '', ''

    actif = bool(cfg.get('actif', True))
    alerte = actif and phase != 'NORMAL'
    if not alerte:
        badge = None
    elif phase == 'ECHEANCE' and jours > 0:
        badge = jours                      # « 3 » sur l'icône : 3 jours
    else:
        badge = '!'                        # jour J et après : un signal, pas un nombre
    return {
        'licence': str(licence.id), 'type': licence.type, 'statut': licence.statut,
        'date_fin': licence.date_fin, 'date_fin_longue': fin,
        'date_coupure': coupure, 'jours': jours, 'grace_jours': Licence.GRACE_JOURS,
        'phase': phase, 'niveau': niveau,
        'palier': palier if phase == 'ECHEANCE' else ('EXP' if phase != 'NORMAL' else None),
        'paliers': list(paliers),
        'alerte': alerte,
        'prioritaire': alerte and phase in ('EXPIREE', 'COUPEE'),
        # Le rappel de connexion ne revient qu'une fois par palier et par session.
        'cle_rappel': f'{licence.date_fin}:{palier if phase == "ECHEANCE" else phase}',
        'badge': badge,
        'titre': titre, 'texte': texte,
        'acces_expire': licence.acces_expire, 'modules': licence.modules,
        'offres': offres(licence),
        'paiement': {
            'lien': cfg.get('lien_paiement') or '',
            'coordonnees': cfg.get('coordonnees_paiement') or '',
            'moyens': list(catalogue.MOYENS_PAIEMENT),
            'telephone': cfg.get('telephone') or '',
            'email': cfg.get('email') or '',
        },
        'demande_en_attente': _demande_en_attente(licence),
    }


def _demande_en_attente(licence):
    d = licence.demandes_renouvellement.filter(traitee=False).order_by('-created_at').first()
    if d is None:
        return None
    return {'id': str(d.id), 'le': d.created_at, 'mois': d.mois, 'montant': d.montant,
            'type': d.type_demande or d.type_licence,
            'reference_paiement': d.reference_paiement}
