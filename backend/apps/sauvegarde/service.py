"""Sauvegarde cloud des installations locales — service.

Réplication asynchrone par snapshots : `pg_dump -Fc` de la base locale,
rotation sur le poste, puis envoi HTTPS vers le serveur HADY GESMAN quand
l'ordinateur est connecté. L'authentification repose sur la clé de licence
de l'école (signature vérifiable côté serveur, voir Licence.generer_cle).

Le statut de la dernière sauvegarde est écrit dans backups/statut.json et
affiché dans Paramètres — c'est la réassurance visible du directeur.
"""
import base64
import glob
import hashlib
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from datetime import datetime

from django.conf import settings

DOSSIER_BACKUPS = settings.BASE_DIR / 'backups'
FICHIER_STATUT = DOSSIER_BACKUPS / 'statut.json'
RETENTION_LOCALE = 7
TIMEOUT_UPLOAD = 120


# ────────────────────────────── statut ──────────────────────────────── #
def lire_statut():
    try:
        with open(FICHIER_STATUT, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _ecrire_statut(**donnees):
    DOSSIER_BACKUPS.mkdir(exist_ok=True)
    donnees['date'] = datetime.now().isoformat(timespec='seconds')
    with open(FICHIER_STATUT, 'w', encoding='utf-8') as f:
        json.dump(donnees, f, ensure_ascii=False, indent=2)
    return donnees


def lister_dumps_locaux():
    return sorted(glob.glob(str(DOSSIER_BACKUPS / 'sagi_*.dump')))


# ────────────────────────────── pg_dump ─────────────────────────────── #
def _trouver_pg_dump():
    """SAGI_PG_DUMP (env) → PATH → installations Windows standards."""
    explicite = os.environ.get('SAGI_PG_DUMP')
    if explicite and os.path.exists(explicite):
        return explicite
    dans_path = shutil.which('pg_dump')
    if dans_path:
        return dans_path
    if os.name == 'nt':
        candidats = sorted(
            glob.glob(r'C:\Program Files\PostgreSQL\*\bin\pg_dump.exe') +
            glob.glob(r'C:\Program Files (x86)\PostgreSQL\*\bin\pg_dump.exe')
        )
        if candidats:
            return candidats[-1]        # version la plus récente
    return None


def creer_dump():
    """Rend le chemin du dump créé. Lève RuntimeError en cas d'échec."""
    pg_dump = _trouver_pg_dump()
    if not pg_dump:
        raise RuntimeError(
            "pg_dump introuvable sur ce poste (définir la variable "
            "d'environnement SAGI_PG_DUMP si PostgreSQL est installé "
            "dans un dossier non standard).")

    db = settings.DATABASES['default']
    DOSSIER_BACKUPS.mkdir(exist_ok=True)
    horodatage = datetime.now().strftime('%Y%m%d_%H%M%S')
    cible = DOSSIER_BACKUPS / f'sagi_{horodatage}.dump'

    env = {**os.environ, 'PGPASSWORD': db.get('PASSWORD', '')}
    cmd = [pg_dump, '-Fc',
           '-h', db.get('HOST') or 'localhost',
           '-p', str(db.get('PORT') or '5432'),
           '-U', db.get('USER') or 'postgres',
           '-d', db['NAME'],
           '-f', str(cible)]
    resultat = subprocess.run(cmd, env=env, capture_output=True, text=True,
                              timeout=600)
    if resultat.returncode != 0 or not cible.exists():
        try:
            cible.unlink(missing_ok=True)
        except OSError:
            pass
        raise RuntimeError(f"pg_dump a échoué : {resultat.stderr.strip()[:400]}")

    # Rotation locale
    dumps = lister_dumps_locaux()
    for ancien in dumps[:-RETENTION_LOCALE]:
        try:
            os.remove(ancien)
        except OSError:
            pass
    return cible


# ────────────────────────────── upload ──────────────────────────────── #
def _licence_locale():
    from apps.licences.models import Licence
    return Licence.objects.select_related('tenant').first()


def envoyer_dump(chemin):
    """Envoie le dump au serveur cloud. Rend la réponse JSON du serveur."""
    licence = _licence_locale()
    if licence is None:
        raise RuntimeError("Aucune licence locale — envoi cloud impossible.")

    url = settings.SAGI_CLOUD_URL.rstrip('/') + '/api/sauvegarde/recevoir/'
    with open(chemin, 'rb') as f:
        corps = f.read()

    ecole_b64 = base64.b64encode(
        (licence.tenant.nom or '')[:80].encode('utf-8')).decode('ascii')
    requete = urllib.request.Request(url, data=corps, method='POST', headers={
        'Content-Type': 'application/octet-stream',
        'X-Cle-Licence': licence.cle_licence,
        'X-Ecole-B64': ecole_b64,
        'X-Empreinte': hashlib.sha256(corps).hexdigest(),
        'X-Nom-Fichier': os.path.basename(chemin),
    })
    with urllib.request.urlopen(requete, timeout=TIMEOUT_UPLOAD) as reponse:
        return json.loads(reponse.read().decode('utf-8'))


# ─────────────────────────── orchestration ──────────────────────────── #
def executer_sauvegarde(envoyer=True):
    """Dump + rotation + envoi cloud, statut écrit quoi qu'il arrive.
    Rend le dict de statut."""
    try:
        chemin = creer_dump()
    except Exception as exc:
        return _ecrire_statut(statut='ERREUR', etape='dump', message=str(exc))

    taille = os.path.getsize(chemin)
    if not envoyer:
        return _ecrire_statut(statut='OK', etape='local',
                              fichier=os.path.basename(chemin), taille=taille,
                              message='Sauvegarde locale uniquement (envoi désactivé).')

    try:
        reponse = envoyer_dump(chemin)
        return _ecrire_statut(statut='OK', etape='cloud',
                              fichier=os.path.basename(chemin), taille=taille,
                              conservees=reponse.get('conservees'),
                              message='Sauvegarde envoyée sur le cloud HADY GESMAN.')
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', 'replace')[:200]
        return _ecrire_statut(statut='ERREUR', etape='envoi',
                              fichier=os.path.basename(chemin), taille=taille,
                              message=f'Serveur cloud : HTTP {exc.code} — {detail}')
    except Exception as exc:
        # Hors ligne, DNS, timeout… : le dump local existe, l'envoi
        # repartira à la prochaine exécution.
        return _ecrire_statut(statut='ERREUR', etape='envoi',
                              fichier=os.path.basename(chemin), taille=taille,
                              message=f'Envoi impossible (hors ligne ?) : {exc}')


def validation_cle(cle):
    """Vérifie la signature d'une clé de licence (format HG-…-SIGNATURE)
    sans accès base : les clés sont auto-signées, voir Licence.generer_cle."""
    if not cle or not cle.startswith('HG-') or '-' not in cle:
        return False
    payload, signature = cle.rsplit('-', 1)
    attendu = hashlib.sha256(payload.encode()).hexdigest()[:8].upper()
    return signature == attendu
