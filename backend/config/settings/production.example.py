from .base import *
import os

DEBUG         = False
SECRET_KEY    = 'changez-moi-absolument'
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '*']

INSTALLED_APPS = [a for a in INSTALLED_APPS if 'debug_toolbar' not in a]
MIDDLEWARE     = [m for m in MIDDLEWARE if 'debug_toolbar' not in m]

DATABASES = {
    'default': {
        'ENGINE':   'django.db.backends.postgresql',
        'NAME':     'hady_gesman',
        'USER':     'postgres',
        'PASSWORD': 'VOTRE_MOT_DE_PASSE_ICI',
        'HOST':     'localhost',
        'PORT':     '5432',
    }
}

MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
STATIC_ROOT      = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = []

import os as _os
_possible = [
    str(BASE_DIR.parent / 'frontend' / 'dist'),
    '/opt/SAGI SCHOOL/resources/frontend/dist',
]
FRONTEND_DIR = _possible[0]
for p in _possible:
    if _os.path.exists(_os.path.join(p, 'index.html')):
        FRONTEND_DIR = p
        break

WHITENOISE_ROOT = FRONTEND_DIR
