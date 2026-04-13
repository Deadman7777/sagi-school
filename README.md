# HADY GESMAN — ERP Scolaire

## Stack
- **Backend** : Django 5 + DRF + PostgreSQL
- **Frontend** : Angular 17 + PrimeNG
- **Desktop**  : Electron

## Démarrage rapide

### 1. Base de données
```bash
createdb hady_gesman
psql -d hady_gesman -f backend/db/schema.sql
```

### 2. Backend Django
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements/local.txt
cp .env.example .env       # remplissez vos infos
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 8765
```

### 3. Frontend Angular
```bash
cd frontend
npm install
ng serve                   # http://localhost:4200
```

### 4. Mode desktop (Electron)
```bash
cd electron
npm install
NODE_ENV=development npm start
```

## Architecture multi-tenant
Chaque requête doit inclure le header `X-Tenant-ID: <uuid>`.
Le middleware Django injecte automatiquement `request.tenant`.
