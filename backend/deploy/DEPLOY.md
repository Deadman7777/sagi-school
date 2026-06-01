# SAGI SCHOOL — Déploiement cloud

Ce guide installe SAGI SCHOOL en mode cloud sur un VPS Ubuntu 22.04+
(Hetzner / OVH / Scaleway). À adapter selon la distribution.

Architecture :
```
                ┌──────────────────────────┐
                │  app.sagi-school.com     │  ← Angular statique (nginx)
                │  api.sagi-school.com     │  ← Django (gunicorn + nginx)
                │  postgresql              │  ← local au serveur
                └──────────────────────────┘
```

## 1. Prérequis serveur

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip postgresql nginx \
                    certbot python3-certbot-nginx git
```

Créer l'utilisateur applicatif :
```bash
sudo useradd -m -s /bin/bash sagi
sudo mkdir -p /opt/sagi-school /var/log/sagi-school
sudo chown -R sagi:sagi /opt/sagi-school /var/log/sagi-school
```

## 2. PostgreSQL

```bash
sudo -u postgres psql <<EOF
CREATE DATABASE sagi_school_cloud;
CREATE USER sagi_cloud WITH ENCRYPTED PASSWORD 'CHANGE_ME';
GRANT ALL PRIVILEGES ON DATABASE sagi_school_cloud TO sagi_cloud;
ALTER DATABASE sagi_school_cloud OWNER TO sagi_cloud;
EOF
```

## 3. Code backend

```bash
sudo -u sagi -i
cd /opt/sagi-school
git clone <ton-repo> .
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements/cloud.txt
```

## 4. Configuration

```bash
cp .env.cloud.example .env
nano .env   # Remplir SECRET_KEY, DB_PASSWORD, etc.
```

Générer une SECRET_KEY :
```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

## 5. Migrations + statics + super_admin

```bash
export DJANGO_SETTINGS_MODULE=config.settings.cloud
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser   # ← ton compte super_admin HADY GESMAN
```

## 6. Frontend (Angular)

Build depuis ta machine de dev (pas sur le serveur, ou alors installer Node) :
```bash
cd frontend
npm ci
npm run build:cloud
# puis copier dist/frontend/browser/* vers /opt/sagi-school/frontend/dist/frontend/browser/ sur le serveur
rsync -av dist/frontend/browser/ user@serveur:/opt/sagi-school/frontend/dist/frontend/browser/
```

## 7. gunicorn (systemd)

```bash
sudo cp /opt/sagi-school/backend/deploy/gunicorn.service \
        /etc/systemd/system/sagi-school.service
sudo systemctl daemon-reload
sudo systemctl enable --now sagi-school
sudo systemctl status sagi-school
```

## 8. nginx + TLS

```bash
sudo cp /opt/sagi-school/backend/deploy/nginx.conf \
        /etc/nginx/sites-available/sagi-school
sudo ln -s /etc/nginx/sites-available/sagi-school /etc/nginx/sites-enabled/
sudo nginx -t

# Certificats TLS (Let's Encrypt)
sudo certbot --nginx -d api.sagi-school.com -d app.sagi-school.com
# certbot modifie les vhosts automatiquement pour brancher les certifs.

sudo systemctl reload nginx
```

## 9. Vérification

```bash
curl -I https://api.sagi-school.com/api/
# → 401 Unauthorized (normal : pas de token)

curl -I https://app.sagi-school.com/
# → 200 OK + index.html
```

Aller sur `https://app.sagi-school.com/login`, se connecter avec le super_admin.

## 10. Mises à jour

```bash
sudo -u sagi -i
cd /opt/sagi-school
git pull
cd backend
source venv/bin/activate
pip install -r requirements/cloud.txt
export DJANGO_SETTINGS_MODULE=config.settings.cloud
python manage.py migrate
python manage.py collectstatic --noinput
exit
sudo systemctl restart sagi-school

# Frontend : rebuild + rsync (depuis la machine de dev)
```

## Backups

À planifier en cron, ex. tous les jours à 3h :
```cron
0 3 * * * sudo -u postgres pg_dump sagi_school_cloud | gzip > /backups/sagi-$(date +\%Y\%m\%d).sql.gz
```

Penser à offload vers un stockage externe (S3, Backblaze) — un backup sur le même serveur ne protège de rien.
