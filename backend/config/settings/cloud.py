"""
Settings pour le déploiement cloud (api.sagi-school.com).

Toutes les valeurs sensibles viennent de variables d'environnement
(fichier .env à la racine backend, jamais commité).

Différences vs production.py (Electron) :
- Tout est piloté par env vars (secret key, DB, hosts)
- HTTPS strict (cookies secure, HSTS, SSL redirect)
- CORS limité à app.sagi-school.com
- WhiteNoise sert uniquement /static/ (Django admin), PAS le frontend
- Logging vers fichier rotatif
"""
from .base import *
from decouple import config, Csv

DEBUG      = config('DEBUG', default=False, cast=bool)
SECRET_KEY = config('SECRET_KEY')  # obligatoire — pas de défaut

ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    default='api.sagi-school.com',
    cast=Csv()
)

# ─── Base de données ───────────────────────────────────────────────
DATABASES = {
    'default': {
        'ENGINE':   'django.db.backends.postgresql',
        'NAME':     config('DB_NAME'),
        'USER':     config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST':     config('DB_HOST', default='localhost'),
        'PORT':     config('DB_PORT', default='5432'),
        'CONN_MAX_AGE': config('DB_CONN_MAX_AGE', default=60, cast=int),
    }
}

# ─── Pas de debug toolbar en cloud ─────────────────────────────────
INSTALLED_APPS = [a for a in INSTALLED_APPS if 'debug_toolbar' not in a]
MIDDLEWARE     = [m for m in MIDDLEWARE if 'debug_toolbar' not in m]

# ─── Static (Django admin + DRF browsable API uniquement) ──────────
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
STATIC_ROOT      = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = []
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ─── CORS ──────────────────────────────────────────────────────────
# Deux origines, et deux seulement : l'application cloud, et le site
# vitrine — qui appelle /api/public/ (demande de démo, compteurs) et
# /api/assistant/ (SAMA). Sans le site vitrine ici, le navigateur bloque
# ces appels avant même qu'ils n'atteignent le serveur, et l'assistant
# reste muet sans qu'aucun journal côté serveur ne le montre.
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='https://app.sagi-school.com,https://sagi-school.com,https://www.sagi-school.com',
    cast=Csv()
)
# (on garde CORS_ALLOW_CREDENTIALS et CORS_ALLOW_HEADERS hérités de base.py)

# ─── Sécurité HTTPS ────────────────────────────────────────────────
# nginx termine TLS et forward X-Forwarded-Proto=https
SECURE_PROXY_SSL_HEADER  = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT      = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
SESSION_COOKIE_SECURE    = True
CSRF_COOKIE_SECURE       = True
SECURE_HSTS_SECONDS      = config('SECURE_HSTS_SECONDS', default=31536000, cast=int)  # 1 an
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD      = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY   = 'same-origin'
X_FRAME_OPTIONS          = 'DENY'

CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='https://app.sagi-school.com,https://api.sagi-school.com',
    cast=Csv()
)

# ─── Logging : fichier rotatif + console ───────────────────────────
import os
LOG_DIR = config('LOG_DIR', default=str(BASE_DIR / 'logs'))
os.makedirs(LOG_DIR, exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name} — {message}',
            'style':  '{',
        },
    },
    'handlers': {
        'console': {
            'class':     'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class':       'logging.handlers.RotatingFileHandler',
            'filename':    os.path.join(LOG_DIR, 'django.log'),
            'maxBytes':    10 * 1024 * 1024,   # 10 MB
            'backupCount': 5,
            'formatter':   'verbose',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level':    config('LOG_LEVEL', default='INFO'),
    },
    'loggers': {
        'django.security': {
            'handlers': ['console', 'file'],
            'level':    'WARNING',
            'propagate': False,
        },
    },
}

# ─── Email (pour reset password plus tard) ─────────────────────────
EMAIL_BACKEND      = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST         = config('EMAIL_HOST',         default='')
EMAIL_PORT         = config('EMAIL_PORT',         default=587, cast=int)
EMAIL_HOST_USER    = config('EMAIL_HOST_USER',    default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS      = config('EMAIL_USE_TLS',      default=True, cast=bool)
EMAIL_TIMEOUT      = config('EMAIL_TIMEOUT',      default=10, cast=int)
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='no-reply@sagi-school.com')

# Destinataire des demandes de renouvellement de licence (Ma Licence)
LICENCE_SUPPORT_EMAIL = config('LICENCE_SUPPORT_EMAIL', default='hadygesman@gmail.com')

# Réception des sauvegardes des installations locales
SAGI_BACKUPS_DIR = config('SAGI_BACKUPS_DIR',
                          default='/var/backups/sagi-school/clients')
