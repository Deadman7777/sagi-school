# SAGI SCHOOL — Déploiement cloud

Guide d'installation de SAGI SCHOOL en mode cloud (programme Taxawu Daara, ~100 tenants).

## Cible

- **Hébergeur** : OVHcloud
- **Offre** : VPS-2 (6 vCore, 12 GB RAM, 100 GB SSD NVMe, 1 Gbit/s) — ~8.49 €HT/mois
- **Datacenter** : GRA (Gravelines, France) — meilleure connectivité vers l'Afrique de l'Ouest
- **OS** : Ubuntu 22.04 LTS (ou plus récent)
- **Domaines** : `api.sagi-school.com` (Django) + `app.sagi-school.com` (Angular)

Architecture :
```
                ┌──────────────────────────┐
                │  app.sagi-school.com     │  ← Angular statique (nginx)
                │  api.sagi-school.com     │  ← Django (gunicorn + nginx)
                │  postgresql              │  ← local au serveur
                └──────────────────────────┘
                          │
                          ▼
            ┌──────────────────────────────┐
            │  Backup hors-site quotidien  │  ← Backblaze B2 / OVH Object Storage
            └──────────────────────────────┘
```

---

## 0. Provisionnement OVH & DNS

### 0.1 Commander le VPS
Sur le manager OVH → **Bare Metal Cloud > VPS > Commander un VPS** :
- Gamme : **VPS-2**
- Datacenter : **Gravelines (GRA)**
- OS : **Ubuntu 22.04 LTS Server**
- Authentification : **clé SSH** (coller `~/.ssh/id_ed25519.pub` de ta machine, pas de mot de passe root)
- Backups automatiques : **inclus** (rétention 7 jours, déjà activés par défaut)
- Anti-DDoS : **inclus** (rien à activer)

### 0.2 DNS (registrar du domaine)
Créer deux enregistrements **A** pointant vers l'IPv4 du VPS :
```
api.sagi-school.com    A    <IP_DU_VPS>    300
app.sagi-school.com    A    <IP_DU_VPS>    300
```
Et les **AAAA** correspondants si OVH attribue une IPv6.

Vérifier la propagation : `dig api.sagi-school.com +short`.

---

## 1. Hardening initial (avant tout le reste)

Connexion en root (clé SSH uniquement) :
```bash
ssh root@<IP_DU_VPS>
```

### 1.1 Mises à jour
```bash
apt update && apt upgrade -y
apt install -y unattended-upgrades
dpkg-reconfigure -plow unattended-upgrades   # activer les MAJ sécurité auto
```

### 1.2 Utilisateur applicatif
```bash
useradd -m -s /bin/bash sagi
usermod -aG sudo sagi
mkdir -p /home/sagi/.ssh
cp /root/.ssh/authorized_keys /home/sagi/.ssh/
chown -R sagi:sagi /home/sagi/.ssh
chmod 700 /home/sagi/.ssh && chmod 600 /home/sagi/.ssh/authorized_keys
```

### 1.3 SSH durci
Éditer `/etc/ssh/sshd_config` :
```
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
Port 22                # garder 22 ou changer, fail2ban gérera
```
```bash
systemctl restart ssh
```

**Tester depuis un autre terminal** que `ssh sagi@<IP>` fonctionne **avant** de fermer la session root.

### 1.4 Pare-feu UFW
```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
ufw status verbose
```

### 1.5 fail2ban
```bash
apt install -y fail2ban
cat > /etc/fail2ban/jail.local <<EOF
[DEFAULT]
bantime = 1h
findtime = 10m
maxretry = 5

[sshd]
enabled = true

[nginx-http-auth]
enabled = true

[nginx-limit-req]
enabled = true
EOF
systemctl enable --now fail2ban
fail2ban-client status sshd
```

### 1.6 Hostname & timezone
```bash
hostnamectl set-hostname sagi-prod-gra
timedatectl set-timezone Africa/Dakar
```

---

## 2. Logiciels système

```bash
apt install -y python3 python3-venv python3-pip postgresql postgresql-contrib \
               nginx certbot python3-certbot-nginx git rsync logrotate
```

Créer les dossiers applicatifs :
```bash
mkdir -p /opt/sagi-school /var/log/sagi-school /var/backups/sagi-school
chown -R sagi:sagi /opt/sagi-school /var/log/sagi-school /var/backups/sagi-school
```

---

## 3. PostgreSQL

### 3.1 Création base + utilisateur
```bash
sudo -u postgres psql <<EOF
CREATE DATABASE sagi_school_cloud;
CREATE USER sagi_cloud WITH ENCRYPTED PASSWORD 'CHANGE_ME';
GRANT ALL PRIVILEGES ON DATABASE sagi_school_cloud TO sagi_cloud;
ALTER DATABASE sagi_school_cloud OWNER TO sagi_cloud;
EOF
```

### 3.2 Tuning minimal pour VPS-2 (12 GB RAM)
Éditer `/etc/postgresql/14/main/postgresql.conf` (adapter le numéro de version) :
```conf
shared_buffers = 3GB
effective_cache_size = 8GB
work_mem = 32MB
maintenance_work_mem = 512MB
max_connections = 100
wal_buffers = 16MB
checkpoint_completion_target = 0.9
random_page_cost = 1.1   # SSD NVMe
```
```bash
systemctl restart postgresql
```

---

## 4. Code backend

```bash
sudo -iu sagi
cd /opt/sagi-school
git clone <ton-repo> .
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements/cloud.txt
```

---

## 5. Configuration

```bash
cp .env.cloud.example .env
nano .env   # SECRET_KEY, DB_PASSWORD, ALLOWED_HOSTS, etc.
chmod 600 .env
```

Générer une `SECRET_KEY` :
```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

---

## 6. Migrations + statics + super_admin

```bash
export DJANGO_SETTINGS_MODULE=config.settings.cloud
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser   # ← compte super_admin HADY GESMAN
```

---

## 7. Frontend (Angular)

Build depuis la machine de dev (pas sur le serveur) :
```bash
cd frontend
npm ci
npm run build:cloud
rsync -av dist/frontend/browser/ sagi@<IP>:/opt/sagi-school/frontend/dist/frontend/browser/
```

---

## 8. gunicorn (systemd)

```bash
sudo cp /opt/sagi-school/backend/deploy/gunicorn.service \
        /etc/systemd/system/sagi-school.service
sudo systemctl daemon-reload
sudo systemctl enable --now sagi-school
sudo systemctl status sagi-school
```

---

## 9. nginx + TLS

```bash
sudo cp /opt/sagi-school/backend/deploy/nginx.conf \
        /etc/nginx/sites-available/sagi-school
sudo ln -s /etc/nginx/sites-available/sagi-school /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t

# Certificats TLS (Let's Encrypt)
sudo certbot --nginx -d api.sagi-school.com -d app.sagi-school.com
# Renouvellement auto via timer systemd (vérifier : systemctl list-timers | grep certbot)

sudo systemctl reload nginx
```

---

## 10. Vérification

```bash
curl -I https://api.sagi-school.com/api/
# → 401 Unauthorized (normal : pas de token)

curl -I https://app.sagi-school.com/
# → 200 OK + index.html
```

Tests sécurité rapides :
```bash
curl -I https://api.sagi-school.com/   | grep -i strict-transport
# → strict-transport-security: max-age=31536000 ...

# SSL Labs : https://www.ssllabs.com/ssltest/analyze.html?d=api.sagi-school.com
# Cible : note A ou A+
```

Aller sur `https://app.sagi-school.com/login`, se connecter avec le super_admin.

---

## 11. Backups (local + hors-site chiffré)

**Règle 3-2-1** : 3 copies, 2 supports différents, 1 hors-site.

### 11.1 Dump quotidien local
Script `/usr/local/bin/sagi-backup.sh` :
```bash
#!/bin/bash
set -euo pipefail
DATE=$(date +%Y%m%d_%H%M)
DEST=/var/backups/sagi-school
mkdir -p "$DEST"

# Dump Postgres
sudo -u postgres pg_dump sagi_school_cloud | gzip > "$DEST/db_${DATE}.sql.gz"

# Backup média (uploads tenants, bulletins PDF générés, etc.)
tar -czf "$DEST/media_${DATE}.tar.gz" -C /opt/sagi-school/backend media/ 2>/dev/null || true

# Rotation locale : garder 7 jours
find "$DEST" -type f -mtime +7 -delete
```
```bash
chmod +x /usr/local/bin/sagi-backup.sh
```

### 11.2 Chiffrement + upload hors-site (Backblaze B2)
Backblaze B2 ~ 0.005 €/Go/mois — pour SAGI SCHOOL ça revient à quelques centimes/mois.

Installer `rclone` et `gpg` :
```bash
apt install -y rclone gnupg
```

Générer une clé GPG dédiée aux backups (sur ta machine de dev, pas sur le serveur) :
```bash
gpg --quick-generate-key "backup-sagi@sagi-school.com" rsa4096 default 0
gpg --export backup-sagi@sagi-school.com > backup-sagi.pub.asc
gpg --export-secret-key backup-sagi@sagi-school.com > backup-sagi.priv.asc
# La clé PRIVÉE reste sur ta machine + 1 copie offline (USB chiffrée). JAMAIS sur le serveur.
```
Importer la clé **publique** sur le serveur :
```bash
gpg --import backup-sagi.pub.asc
gpg --edit-key backup-sagi@sagi-school.com trust   # niveau 5 (ultimate)
```

Configurer rclone vers B2 :
```bash
rclone config   # nouveau remote "b2", type B2, app key id + key
```

Étendre le script `/usr/local/bin/sagi-backup.sh` :
```bash
# Chiffrement + upload
for f in "$DEST"/*_${DATE}*; do
    gpg --batch --yes --trust-model always \
        --encrypt --recipient backup-sagi@sagi-school.com \
        --output "${f}.gpg" "$f"
    rclone copy "${f}.gpg" b2:sagi-backups/$(date +%Y/%m)/
    rm "${f}.gpg"
done
```

Cron quotidien (en root, `crontab -e`) :
```cron
0 3 * * * /usr/local/bin/sagi-backup.sh >> /var/log/sagi-school/backup.log 2>&1
```

### 11.3 Vérification mensuelle
Une fois par mois, télécharger un backup B2, le déchiffrer sur une machine de test, restaurer dans une DB jetable. **Un backup non testé n'est pas un backup.**

---

## 12. Restauration (procédure)

À utiliser en cas de corruption DB, incident OVH, ou test mensuel.

```bash
# 1. Télécharger depuis B2
rclone copy b2:sagi-backups/2026/06/db_20260601_0300.sql.gz.gpg /tmp/

# 2. Déchiffrer (sur une machine avec la clé privée)
gpg --decrypt /tmp/db_20260601_0300.sql.gz.gpg > /tmp/db.sql.gz

# 3. Restaurer
sudo systemctl stop sagi-school
sudo -u postgres dropdb sagi_school_cloud
sudo -u postgres createdb sagi_school_cloud -O sagi_cloud
gunzip -c /tmp/db.sql.gz | sudo -u postgres psql sagi_school_cloud
sudo systemctl start sagi-school
```

---

## 13. Monitoring uptime externe

Indispensable : un VPS qui se croit en vie peut ne pas répondre côté réseau.

**UptimeRobot** (gratuit jusqu'à 50 monitors, check toutes les 5 min) :
- Monitor 1 : `https://api.sagi-school.com/api/health/` (à exposer côté Django, simple endpoint qui renvoie 200)
- Monitor 2 : `https://app.sagi-school.com/`
- Alerte : email + (optionnel) webhook Slack/Telegram

**Better Stack** (~10$/mois) si on veut des checks toutes les 30 s + status page publique.

---

## 14. Cloudflare (optionnel mais recommandé)

Cloudflare gratuit devant `app.sagi-school.com` :
- Cache edge des assets Angular → temps de chargement initial 2-3× plus rapide à Dakar (Cloudflare a un PoP à Dakar)
- WAF basique gratuit
- Mode "Proxy" (orange cloud) ON sur l'enregistrement A `app`
- Mode "DNS only" (grey cloud) sur `api` (cookies HttpOnly + sessions WS = on évite le proxy)

SSL mode : **Full (Strict)** pour préserver le certif Let's Encrypt en bout de chaîne.

---

## 15. Snapshot avant chaque mise à jour

Avant toute migration importante (Django) ou changement de schéma :
1. Manager OVH → VPS → **Snapshot** (1-clic, ~5 min)
2. Déployer
3. Si KO : restaurer le snapshot

Coût snapshot OVH : ~0.01 €/Go/mois, donc négligeable. Garder le dernier snapshot stable jusqu'au déploiement suivant validé.

---

## 16. Mises à jour applicatives

```bash
# 0. Snapshot OVH (cf. §15) + backup manuel
/usr/local/bin/sagi-backup.sh

# 1. Backend
sudo -iu sagi
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

# 2. Frontend (depuis la machine de dev)
cd frontend && npm run build:cloud
rsync -av dist/frontend/browser/ sagi@<IP>:/opt/sagi-school/frontend/dist/frontend/browser/

# 3. Vérification rapide
curl -I https://api.sagi-school.com/api/health/
curl -I https://app.sagi-school.com/
```

---

## 17. Logs & maintenance

### 17.1 Logs applicatifs
- gunicorn : `journalctl -u sagi-school -f`
- nginx : `/var/log/nginx/access.log`, `/var/log/nginx/error.log`
- backup : `/var/log/sagi-school/backup.log`

### 17.2 logrotate
Créer `/etc/logrotate.d/sagi-school` :
```
/var/log/sagi-school/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 640 sagi sagi
}
```

### 17.3 Espace disque
Surveiller : `df -h`, `du -sh /var/lib/postgresql /var/backups/sagi-school /opt/sagi-school`.
Alerte UptimeRobot configurable sur un endpoint Django qui expose `df`.

---

## 18. Plan de reprise — résumé

| Incident | Action |
|---|---|
| Corruption DB | Restaurer dernier backup local (§12) |
| VPS perdu (incendie, etc.) | Recommander VPS-2 GRA (ou autre DC OVH), redéployer depuis git + restaurer backup hors-site B2 |
| Compte OVH compromis | Backup B2 intact (clés API séparées) → recommander chez un autre hébergeur, restaurer |
| Clé GPG privée perdue | **Backups B2 illisibles**. → Sauvegarder la clé privée sur 2 USB chiffrées, dans 2 lieux physiques différents |

RTO cible (Recovery Time Objective) : ~2h.
RPO cible (Recovery Point Objective) : ≤ 24h (backup quotidien).
