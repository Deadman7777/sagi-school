import os
import sys

def create_production_if_needed():
    if sys.platform != 'win32':
        return
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    prod_file = os.path.join(base, 'config', 'settings', 'production.py')
    if not os.path.exists(prod_file):
        content = """from .base import *
import os
DEBUG = False
SECRET_KEY = 'sagi-school-prod-2025-hady-gesman'
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '*']
INSTALLED_APPS = [a for a in INSTALLED_APPS if 'debug_toolbar' not in a]
MIDDLEWARE = [m for m in MIDDLEWARE if 'debug_toolbar' not in m]
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'hady_gesman',
        'USER': 'postgres',
        'PASSWORD': 'SangueBiDiop@7',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
STATIC_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'staticfiles')
_base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
FRONTEND_DIR = os.path.join(_base, 'frontend', 'dist')
if os.path.exists(os.path.join(FRONTEND_DIR, 'index.html')):
    WHITENOISE_ROOT = FRONTEND_DIR
"""
        with open(prod_file, 'w') as f:
            f.write(content)

create_production_if_needed()

if sys.platform == 'win32':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
else:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
