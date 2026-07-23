from pathlib import Path
from decouple import Config, RepositoryEnv, RepositoryEmpty

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _build_config():
    """Lecture tolérante du fichier .env.

    Sous Windows, un .env créé/édité dans Notepad est souvent enregistré en
    ANSI (cp1252). python-decouple le lit en UTF-8 strict et plante alors avec
    « 'utf8' codec can't decode byte 0xe9 ». On tente UTF-8 puis cp1252, et on
    se limite à backend/.env (pas de remontée vers un .env parasite ailleurs
    sur le disque). En l'absence de fichier, on part sur les valeurs par défaut.
    """
    env_path = BASE_DIR / '.env'
    if env_path.is_file():
        for enc in ('utf-8-sig', 'utf-8', 'cp1252'):
            try:
                return Config(RepositoryEnv(str(env_path), encoding=enc))
            except UnicodeDecodeError:
                continue
    return Config(RepositoryEmpty())


config = _build_config()

SECRET_KEY = config('SECRET_KEY', default='changeme-in-production')
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='*').split(',')

DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
]

LOCAL_APPS = [
    'apps.tenants',
    'apps.licences',
    'apps.users',
    'apps.eleves',
    'apps.paiements',
    'apps.comptabilite',
    'apps.fiscal',
    'apps.dashboard',
    'apps.rh',
    'apps.academique',
    'apps.daara',
    'apps.gmrf',
    'apps.gouvernance',
    'apps.sauvegarde',
]

# Sauvegarde cloud des installations locales (apps.sauvegarde)
# NB : c'est le host du BACKEND (api.), pas celui du SPA (app.). envoyer_dump
# y ajoute /api/sauvegarde/recevoir/ ; app.sagi-school.com ne sert que le
# frontend statique et renverrait un 405 nginx sur ce POST.
SAGI_CLOUD_URL = config('SAGI_CLOUD_URL', default='https://api.sagi-school.com')
SAGI_BACKUPS_DIR = config('SAGI_BACKUPS_DIR', default=str(BASE_DIR / 'backups_clients'))

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.TenantMiddleware',  # notre middleware multi-tenant
]

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
AUTH_USER_MODEL = 'users.User'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'Africa/Dakar'
USE_I18N = True
USE_TZ = True
STATIC_URL = '/static/'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 500,
}


# CORS
CORS_ALLOWED_ORIGINS = [
    'http://localhost:4200',
    'http://127.0.0.1:4200',
    'http://localhost:8080',   # Electron
]
CORS_ALLOW_CREDENTIALS = True

CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'x-tenant-id',        # ← c'est ça qui manquait
]
# JWT
from datetime import timedelta

def _check_user_actif(user):
    return user is not None and getattr(user, 'actif', True)

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME':       timedelta(hours=8),
    'REFRESH_TOKEN_LIFETIME':      timedelta(days=7),
    'AUTH_HEADER_TYPES':           ('Bearer',),
    'USER_AUTHENTICATION_RULE':    _check_user_actif,
}

# Cache en mémoire — accélère le dashboard
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'TIMEOUT': 300,  # 5 minutes
    }
}