from .base import *
import os

DEBUG         = False
SECRET_KEY    = 'sagi-school-prod-2025-hady-gesman-secret'
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '*']

INSTALLED_APPS = [a for a in INSTALLED_APPS if 'debug_toolbar' not in a]
MIDDLEWARE     = [m for m in MIDDLEWARE if 'debug_toolbar' not in m]

MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
STATIC_ROOT        = BASE_DIR / 'staticfiles'
STATICFILES_DIRS   = []

# Chemin correct — détection automatique
_possible_paths = [
    BASE_DIR.parent / 'frontend' / 'dist',                          # dev
    BASE_DIR.parent.parent / 'frontend' / 'dist',                   # /opt
    '/opt/SAGI SCHOOL/resources/frontend/dist',                      # absolu
]

FRONTEND_DIR = str(BASE_DIR.parent / 'frontend' / 'dist')
for p in _possible_paths:
    if os.path.exists(os.path.join(str(p), 'index.html')):
        FRONTEND_DIR = str(p)
        break

WHITENOISE_ROOT = FRONTEND_DIR
