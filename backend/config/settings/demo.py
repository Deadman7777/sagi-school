"""Instance de démonstration — celle qui sert à filmer et à photographier.

**SQLite, et non PostgreSQL.** Aucune partie du code n'utilise de
fonctionnalité propre à Postgres : une base fichier suffit, ne demande aucun
mot de passe d'administration, et se jette d'un `rm`. On peut donc la
reconstruire à volonté sans jamais approcher les données réelles.

**C'est une école inventée de bout en bout.** Les captures qui illustrent
SAGI SCHOOL — site vitrine, guide de formation, vidéo de démonstration — ne
doivent jamais montrer un élève, un parent ou un montant appartenant à une
école cliente. Le seul moyen sûr de le garantir est de ne pas avoir ces
données sous la main : cette base ne contient que ce que `scripts/seed_demo.py`
y met.

Reconstruire la démonstration :

    rm -f demo.sqlite3
    python manage.py migrate --settings=config.settings.demo
    python scripts/seed_demo.py
    python manage.py runserver 8765 --settings=config.settings.demo
"""
from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ['*']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'demo.sqlite3',  # noqa: F405
    }
}

# Le frontend de développement tourne sur 4200 et une capture peut être servie
# depuis n'importe quel port local : on n'ajoute pas de friction sur une base
# jetable qui ne contient aucune donnée réelle.
CORS_ALLOW_ALL_ORIGINS = True

# Ni courriels ni SMS ne doivent partir d'une démonstration : la boîte de
# réception est en mémoire, et les rappels ne quittent pas le processus.
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
EMAIL_HOST = ''

# L'assistant reste éteint : une capture ne doit rien coûter en jetons.
ANTHROPIC_API_KEY = ''
