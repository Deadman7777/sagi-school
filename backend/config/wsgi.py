import os, sys

def ensure_production_settings():
    if sys.platform != 'win32':
        return
    # config/wsgi.py -> config -> backend -> resources
    base          = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # backend
    prod          = os.path.join(base, 'config', 'settings', 'production.py')
    if os.path.exists(prod):
        return
    resources_dir = os.path.dirname(base)  # resources
    frontend_dir  = os.path.join(resources_dir, 'frontend', 'dist')
    static_root   = os.path.join(base, 'staticfiles')
    content = f"""from .base import *
import os
DEBUG = False
SECRET_KEY = 'sagi-school-prod-2025-hady-gesman'
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '*']
INSTALLED_APPS = [a for a in INSTALLED_APPS if 'debug_toolbar' not in a]
MIDDLEWARE = [m for m in MIDDLEWARE if 'debug_toolbar' not in m]
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
DATABASES = {{'default': {{'ENGINE': 'django.db.backends.postgresql','NAME': 'hady_gesman','USER': 'postgres','PASSWORD': 'SangueBiDiop@7','HOST': 'localhost','PORT': '5432'}}}}
FRONTEND_DIR = r'{frontend_dir}'
STATIC_ROOT  = r'{static_root}'
STATICFILES_DIRS = []
if os.path.exists(os.path.join(FRONTEND_DIR, 'index.html')):
    WHITENOISE_ROOT = FRONTEND_DIR
"""
    with open(prod, 'w', encoding='utf-8') as f:
        f.write(content)

ensure_production_settings()

if sys.platform == 'win32':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
else:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
