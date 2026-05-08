import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

import django
django.setup()

from waitress import serve
from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()

port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
print(f'Starting on port {port}')
serve(application, host='127.0.0.1', port=port)
