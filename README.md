# SAGI SCHOOL — ERP scolaire

Logiciel de gestion d'établissement scolaire édité par **HADY GESMAN**, destiné
aux écoles privées et aux daaras du Sénégal. Élèves, encaissements, comptabilité
SYSCOHADA Révisé, paie, notes et bulletins, mobilisation de ressources,
gouvernance par projet.

Deux modes de déploiement, le même code : **local** (application de bureau, sans
internet) et **cloud** (navigateur).

## Technologies

| | |
|---|---|
| Backend | Django 5.1 + Django REST Framework + PostgreSQL |
| Frontend | Angular 21 (standalone, signals) + PrimeNG 21 |
| Bureau | Electron |
| Comptabilité | SYSCOHADA Révisé (OHADA) |
| Cadre social et fiscal | Sénégal |

## Documentation

**Nouveau sur le projet ? Commencez par [`docs/dev/`](docs/dev/README.md).**
La documentation technique y couvre l'architecture, le montage d'un poste, le
modèle de données, le moteur comptable et le registre des pièges connus.

| | |
|---|---|
| [Documentation technique](docs/dev/README.md) | Pour les développeurs |
| [Guide utilisateur et support de formation](docs/guide-formation-sagi-school.pdf) | Pour les écoles et les formateurs |
| [Déploiement cloud](backend/deploy/DEPLOY.md) | Procédure serveur |

## Démarrage rapide

Version détaillée, avec les pièges : [`docs/dev/02-poste-de-developpement.md`](docs/dev/02-poste-de-developpement.md).

### Base de données

```bash
createdb hady_gesman          # PostgreSQL 14+
```

Il n'y a **pas** de schéma SQL à charger : le schéma vient des migrations Django.

### Backend

```bash
cd backend
python3 -m venv venv
./venv/bin/pip install -r requirements/local.txt
cp ../.env.example .env                    # ajustez les identifiants
./venv/bin/python manage.py migrate
./venv/bin/python manage.py createsuperuser
./venv/bin/python manage.py runserver 127.0.0.1:8765
```

Le port **8765** n'est pas modifiable en développement : le frontend et Electron
le codent en dur.

Un super-utilisateur n'a pas d'école rattachée, donc les écrans métier restent
vides. Créez un établissement de travail :

```bash
./venv/bin/python manage.py init_installation --payload install.json
./venv/bin/python manage.py init_plan_comptable --tous
./venv/bin/python manage.py init_parametres_fiscaux
```

Le contenu de `install.json` est donné dans la documentation technique.

### Frontend

```bash
cd frontend
npm install
npm start                     # http://localhost:4200
```

### Mode bureau (Electron)

```bash
cd frontend && ng build --configuration production
cd ../electron && npm install && npm start
```

## Multi-tenant — l'essentiel

Une installation cloud héberge toutes les écoles dans une seule base. La
séparation est logique : chaque modèle métier porte une clé `tenant`, et chaque
`queryset` doit filtrer dessus. **Aucun filtrage automatique n'existe.**

```python
from core.tenant import get_tenant
tenant = get_tenant(request)
```

> L'en-tête `X-Tenant-ID` **n'est pris en compte que pour un `SUPER_ADMIN`**. Pour
> tout autre utilisateur il est ignoré, et le tenant est celui de son compte —
> sans quoi n'importe qui lirait n'importe quelle école en falsifiant un en-tête.

Détails et règles complètes :
[`docs/dev/04-multi-tenant-et-roles.md`](docs/dev/04-multi-tenant-et-roles.md).

## Tests

```bash
cd backend && ./venv/bin/python manage.py test apps
```

Environ 590 tests. Deux erreurs de découverte sont attendues et préexistantes —
voir [`docs/dev/11-tests.md`](docs/dev/11-tests.md).

## Livrer une version

```bash
git tag v1.37.0 && git push origin v1.37.0
```

GitHub Actions compile et publie l'installateur Windows et les paquets Linux.
Voir [`docs/dev/10-build-et-deploiement.md`](docs/dev/10-build-et-deploiement.md).
