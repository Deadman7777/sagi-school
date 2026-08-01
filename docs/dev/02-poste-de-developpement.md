# 2 — Monter un poste de développement

Objectif : partir d'une machine vierge et arriver à une application qui tourne,
avec des données dedans, en une heure.

## Ce qu'il faut installer

| | Version | Pourquoi cette version |
|---|---|---|
| Python | **3.10 à 3.12** | 3.10 est celle du poste de référence et des builds Windows |
| Node.js | **20 ou plus** | Ce qu'utilise la chaîne de compilation (`.github/workflows/build.yml`) |
| PostgreSQL | **14 ou plus** | La base de production, en local comme en cloud |
| Git | — | — |

Le projet **n'utilise aucune extension PostgreSQL ni aucun champ spécifique à
PostgreSQL** — pas de `ArrayField`, pas de `django.contrib.postgres`. C'est ce
qui permet de faire tourner les tests et une instance jetable sur SQLite (voir
plus bas), sans installer de serveur de base de données.

## Backend

```bash
cd backend
python3 -m venv venv
./venv/bin/pip install -r requirements/local.txt
```

`requirements/` est découpé : `base.txt` (le socle, celui qu'installe
l'application chez le client), `local.txt` (base + debug-toolbar + ipython),
`cloud.txt` et `production.txt`.

### La base de données

`manage.py` utilise `config.settings.local` par défaut. Ce fichier lit
`backend/.env`, avec ces valeurs par défaut :

```
DB_NAME=hady_gesman   DB_USER=postgres   DB_PASSWORD=   DB_HOST=localhost   DB_PORT=5432
```

Copiez `.env.example` à la racine du dépôt vers `backend/.env` et ajustez, puis :

```bash
sudo -u postgres psql -c "CREATE ROLE $USER LOGIN SUPERUSER CREATEDB;"
createdb hady_gesman

cd backend
./venv/bin/python manage.py migrate
./venv/bin/python manage.py createsuperuser        # crée un SUPER_ADMIN
./venv/bin/python manage.py runserver 127.0.0.1:8765
```

> **Le port 8765 n'est pas négociable en développement.**
> `frontend/src/environments/environment.ts` pointe en dur sur
> `http://127.0.0.1:8765/api`, et c'est aussi le port qu'Electron utilise.
> Servir sur 8000 vous donnera un frontend qui ne trouve rien.

### Créer une école pour travailler

Un super-utilisateur seul ne suffit pas : il n'a pas de tenant, donc la plupart
des écrans sont vides. Il faut une **école**, une **licence**, un **exercice** et
un **administrateur d'école**. La commande `init_installation` fait les quatre :

```bash
cat > /tmp/install.json <<'EOF'
{
  "ecole_nom": "École de test", "ecole_code": "TEST", "ecole_ville": "Dakar",
  "admin_email": "dir@test.sn", "admin_password": "Test2026!", "admin_nom": "TEST",
  "annee_scolaire": "2025-2026", "date_debut": "2025-10-01", "date_fin": "2026-07-31"
}
EOF
./venv/bin/python manage.py init_installation --payload /tmp/install.json
./venv/bin/python manage.py init_plan_comptable --tous
./venv/bin/python manage.py init_parametres_fiscaux
```

`init_installation` est **idempotente et ne fait rien si une école existe
déjà** — c'est voulu : elle tourne à chaque démarrage d'Electron.

La licence créée est un essai de 30 jours, qui n'ouvre pas tous les modules.
Pour travailler sur RH, Académique, Fiscal, GMRF ou Gouvernance, passez-la en
`AVANCE` :

```bash
./venv/bin/python manage.py shell -c "
from apps.licences.models import Licence
from datetime import date
l = Licence.objects.first()
l.type, l.statut = 'AVANCE', 'ACTIVE'
l.date_fin = date.today().replace(year=date.today().year + 1)
l.save()
print(l, l.modules)"
```

## Frontend

```bash
cd frontend
npm install
npm start          # ng serve, sur http://127.0.0.1:4200
```

Le backend doit tourner en parallèle sur 8765. CORS autorise déjà
`localhost:4200` et `127.0.0.1:4200` (`backend/config/settings/base.py`).

## Application de bureau (Electron)

Utile seulement pour travailler sur l'assistant d'installation ou le démarrage :

```bash
cd frontend && ng build --configuration production   # Electron sert le build, pas ng serve
cd ../electron && npm install && npm start
```

## Une instance jetable sur SQLite

Pour peupler une base de démonstration, produire des captures, ou reproduire un
bug sans toucher à votre base de travail. C'est la méthode utilisée pour
fabriquer le guide utilisateur.

Créez un fichier de réglages **hors du dépôt**, par exemple
`/tmp/demo/demo_settings.py` :

```python
import os
from config.settings.base import *

DEBUG = True
ALLOWED_HOSTS = ['*']
DATABASES = {'default': {
    'ENGINE': 'django.db.backends.sqlite3',
    'NAME': '/tmp/demo/demo.sqlite3',
}}
CORS_ALLOW_ALL_ORIGINS = True
```

Puis :

```bash
cd backend
export PYTHONPATH=/tmp/demo:$PWD
export DJANGO_SETTINGS_MODULE=demo_settings
./venv/bin/python manage.py migrate
./venv/bin/python manage.py runserver 127.0.0.1:8765 --noreload
```

`base.py` n'ajoute pas la debug-toolbar — c'est `local.py` qui le fait. Une
instance de démonstration en est donc dépourvue, ce qui est préférable pour des
captures d'écran.

### Peupler par l'API, pas par l'ORM

Pour créer des données de test réalistes, **passez par l'API**, jamais par
`Model.objects.create()` directement. Les écritures comptables sont produites
par les vues : contourner la vue donne une base sans comptabilité, donc des
états financiers vides et des tableaux de bord faux.

```python
import django
django.setup()
from rest_framework.test import APIClient
from apps.users.models import User

c = APIClient()
c.force_authenticate(user=User.objects.get(email='dir@test.sn'))
c.post('/api/eleves/liste/', {...}, format='json')
c.post('/api/paiements/paiements/', {...}, format='json')
```

> **Piège** : `Paiement.date_paiement` est en `auto_now_add`. Tous vos
> règlements porteront la date du jour de l'injection. Pour étaler un historique,
> corrigez ensuite le paiement **et** ses écritures :
> ```python
> Paiement.objects.filter(id=pid).update(date_paiement=d)
> JournalEntry.objects.filter(source='PAIEMENT', source_id=pid).update(date_ecriture=d)
> ```

## Cas particuliers Windows

Trois pièges qui ont chacun coûté une journée. Détail dans le document 12.

**Toujours préciser les réglages.** `manage.py` prend `config.settings.local`
par défaut, qui charge la debug-toolbar — absente chez un client. Sur un poste
Windows en production :

```
python manage.py <commande> --settings=config.settings.production
```

**`pkg_resources` peut manquer** même après un `pip install`. Un shim minimal
est embarqué dans `backend/pkg_resources/__init__.py`, trouvé en premier dans
`sys.path` quand `manage.py` s'exécute depuis `backend/`. Ne le supprimez pas.

**L'application ne crée pas la base PostgreSQL.** Seul le script
`install_win.ps1` le fait. Un `UnicodeDecodeError` sur l'octet `0xe9` au
démarrage est en réalité un message d'erreur PostgreSQL en français
(`lc_messages` en WIN1252) qui masque un « la base n'existe pas ».

## Vérifier que tout marche

```bash
cd backend && ./venv/bin/python manage.py test apps
```

Environ 590 tests, une centaine de secondes. Deux erreurs de **découverte** sont
attendues et préexistantes (`eleves.tests` et `gmrf.tests` chargés comme modules
de premier niveau) — elles ne signalent pas un problème dans votre installation.
Voir le document 11.
