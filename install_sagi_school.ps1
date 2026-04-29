# ============================================================
# SAGI SCHOOL — Installateur Automatique Windows
# HADY GESMAN © 2026
# ============================================================

$ErrorActionPreference = "SilentlyContinue"

function Write-Header {
    Clear-Host
    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "  ║          SAGI SCHOOL — Installation              ║" -ForegroundColor Cyan
    Write-Host "  ║           by HADY GESMAN © 2026                  ║" -ForegroundColor Cyan
    Write-Host "  ╚══════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

function Write-OK   { param($msg) Write-Host "  ✓ $msg" -ForegroundColor Green }
function Write-WARN { param($msg) Write-Host "  ⚠ $msg" -ForegroundColor Yellow }
function Write-ERR  { param($msg) Write-Host "  ✗ $msg" -ForegroundColor Red }
function Write-INFO { param($msg) Write-Host "    $msg"  -ForegroundColor Gray }
function Write-Sep  { Write-Host "  ────────────────────────────────────────────────────" -ForegroundColor DarkGray }

# ── Vérification Administrateur ──────────────────────────────
Write-Header
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-ERR "Ce script doit être lancé en tant qu'Administrateur."
    Write-INFO "Clic droit → Exécuter avec PowerShell en tant qu'administrateur"
    Read-Host "Appuyez sur Entrée pour fermer"
    exit 1
}
Write-OK "Droits administrateur OK"
Write-Sep

# ── Variables ────────────────────────────────────────────────
$SAGI_URL     = "https://github.com/Deadman7777/sagi-school/releases/download/v1.0.0/SAGI.SCHOOL.Setup.1.0.0.exe"
$PG_URL       = "https://get.enterprisedb.com/postgresql/postgresql-15.6-1-windows-x64.exe"
$SAGI_SETUP   = "$env:TEMP\SAGI_SCHOOL_Setup.exe"
$PG_SETUP     = "$env:TEMP\postgresql_setup.exe"
$DB_NAME      = "hady_gesman"
$DB_USER      = "postgres"
$DB_PASSWORD  = ""

# ── ÉTAPE 1 : Mot de passe ───────────────────────────────────
Write-Header
Write-Host "  ÉTAPE 1/4 — Mot de passe PostgreSQL" -ForegroundColor White
Write-Host ""

# Détecter si PostgreSQL est déjà installé
$pgPath = $null
$pgVersions = @("16","15","14","13","12")
foreach ($v in $pgVersions) {
    $p = "C:\Program Files\PostgreSQL\$v\bin"
    if (Test-Path "$p\psql.exe") {
        $pgPath = $p
        Write-OK "PostgreSQL $v détecté : $p"
        break
    }
}

if ($pgPath) {
    Write-Host ""
    Write-Host "  Entrez le mot de passe PostgreSQL existant :" -ForegroundColor Gray
    $pwd1 = Read-Host "  Mot de passe" -AsSecureString
    $DB_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($pwd1))
} else {
    Write-WARN "PostgreSQL non détecté — il sera installé"
    Write-Host ""
    do {
        $pwd1 = Read-Host "  Choisissez un mot de passe PostgreSQL (min. 8 caractères)" -AsSecureString
        $pwd2 = Read-Host "  Confirmez le mot de passe" -AsSecureString
        $p1 = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($pwd1))
        $p2 = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($pwd2))
        if ($p1.Length -lt 8) { Write-WARN "Trop court (min. 8 caractères)" }
        elseif ($p1 -ne $p2)  { Write-WARN "Les mots de passe ne correspondent pas" }
        else { $DB_PASSWORD = $p1; Write-OK "Mot de passe défini"; break }
    } while ($true)
}
Write-Sep

# ── ÉTAPE 2 : PostgreSQL ─────────────────────────────────────
Write-Header
Write-Host "  ÉTAPE 2/4 — PostgreSQL" -ForegroundColor White
Write-Host ""

if (-not $pgPath) {
    Write-Info "Téléchargement de PostgreSQL 15..."
    try {
        (New-Object System.Net.WebClient).DownloadFile($PG_URL, $PG_SETUP)
        Write-OK "Téléchargement terminé"
        Write-Info "Installation en cours (mode silencieux)..."
        Start-Process -FilePath $PG_SETUP -ArgumentList `
            "--mode","unattended",
            "--superpassword",$DB_PASSWORD,
            "--servicename","postgresql-x64-15",
            "--serverport","5432" `
            -Wait -NoNewWindow
        $pgPath = "C:\Program Files\PostgreSQL\15\bin"
        Write-OK "PostgreSQL 15 installé"
    } catch {
        Write-ERR "Échec installation PostgreSQL : $_"
        Write-WARN "Installez PostgreSQL manuellement depuis postgresql.org puis relancez ce script."
        Read-Host "Entrée pour fermer"
        exit 1
    }
} else {
    Write-OK "PostgreSQL déjà installé — étape ignorée"
}

# Démarrer le service
$pgSvc = Get-Service | Where-Object { $_.Name -like "postgresql*" } | Select-Object -First 1
if ($pgSvc) {
    if ($pgSvc.Status -ne "Running") { Start-Service $pgSvc.Name }
    Write-OK "Service PostgreSQL actif"
    Set-Service -Name $pgSvc.Name -StartupType Automatic
}

# Créer la base
$env:PGPASSWORD = $DB_PASSWORD
$env:PATH += ";$pgPath"

$check = & "$pgPath\psql.exe" -U $DB_USER -h localhost -p 5432 -lqt 2>&1
if ($check -match $DB_NAME) {
    Write-OK "Base '$DB_NAME' existe déjà"
} else {
    & "$pgPath\createdb.exe" -U $DB_USER -h localhost -p 5432 $DB_NAME 2>&1 | Out-Null
    Write-OK "Base '$DB_NAME' créée"
}
Write-Sep

# ── ÉTAPE 3 : SAGI SCHOOL ────────────────────────────────────
Write-Header
Write-Host "  ÉTAPE 3/4 — Téléchargement et installation de SAGI SCHOOL" -ForegroundColor White
Write-Host ""

# Chercher setup local d'abord
$scriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$localSetup = Join-Path $scriptDir "SAGI SCHOOL Setup 1.0.0.exe"

$sagiDirs = @(
    "C:\Program Files\SAGI SCHOOL",
    "C:\Program Files (x86)\SAGI SCHOOL",
    "$env:LOCALAPPDATA\Programs\SAGI SCHOOL"
)

$sagiDir = $null
foreach ($d in $sagiDirs) {
    if (Test-Path $d) { $sagiDir = $d; break }
}

if ($sagiDir) {
    Write-OK "SAGI SCHOOL déjà installé dans : $sagiDir"
} else {
    if (Test-Path $localSetup) {
        Write-OK "Setup trouvé localement"
        Start-Process -FilePath $localSetup -Wait
    } else {
        Write-Info "Téléchargement de SAGI SCHOOL depuis GitHub..."
        Write-Info "URL : $SAGI_URL"
        try {
            $wc = New-Object System.Net.WebClient
            $wc.DownloadFile($SAGI_URL, $SAGI_SETUP)
            Write-OK "Téléchargement terminé"
            Write-Info "Installation en cours..."
            Start-Process -FilePath $SAGI_SETUP -Wait
            Write-OK "SAGI SCHOOL installé"
        } catch {
            Write-ERR "Échec téléchargement : $_"
            Write-WARN "Téléchargez manuellement depuis :"
            Write-INFO "https://github.com/Deadman7777/sagi-school/releases"
            Read-Host "Entrée pour fermer"
            exit 1
        }
    }

    # Retrouver le dossier d'installation
    foreach ($d in $sagiDirs) {
        if (Test-Path $d) { $sagiDir = $d; break }
    }
}

Write-Sep

# ── ÉTAPE 4 : Configuration ──────────────────────────────────
Write-Header
Write-Host "  ÉTAPE 4/4 — Configuration finale" -ForegroundColor White
Write-Host ""

if ($sagiDir) {
    # Configurer production.py
    $configPath = Join-Path $sagiDir "resources\backend\config\settings\production.py"

    if (Test-Path $configPath) {
        $config = Get-Content $configPath -Raw
        $config = $config -replace "'PASSWORD': '[^']*'", "'PASSWORD': '$DB_PASSWORD'"
        $config = $config -replace "'NAME': '[^']*'",     "'NAME': '$DB_NAME'"
        $config = $config -replace "'USER': '[^']*'",     "'USER': '$DB_USER'"
        $config = $config -replace "'HOST': '[^']*'",     "'HOST': 'localhost'"
        $config = $config -replace "'PORT': '[^']*'",     "'PORT': '5432'"
        Set-Content $configPath $config -Encoding UTF8
        Write-OK "Configuration base de données mise à jour"
    } else {
        # Créer production.py si absent
        $configDir = Join-Path $sagiDir "resources\backend\config\settings"
        New-Item -ItemType Directory -Path $configDir -Force | Out-Null
        $prodConfig = @"
from .base import *
import os

DEBUG         = False
SECRET_KEY    = 'sagi-school-prod-2026-hady-gesman'
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '*']

INSTALLED_APPS = [a for a in INSTALLED_APPS if 'debug_toolbar' not in a]
MIDDLEWARE     = [m for m in MIDDLEWARE if 'debug_toolbar' not in m]

DATABASES = {
    'default': {
        'ENGINE':   'django.db.backends.postgresql',
        'NAME':     '$DB_NAME',
        'USER':     '$DB_USER',
        'PASSWORD': '$DB_PASSWORD',
        'HOST':     'localhost',
        'PORT':     '5432',
    }
}

MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
STATIC_ROOT      = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = []

import os as _os
FRONTEND_DIR = str(BASE_DIR.parent / 'frontend' / 'dist')
for p in [str(BASE_DIR.parent / 'frontend' / 'dist'), r'$sagiDir\resources\frontend\dist']:
    if _os.path.exists(_os.path.join(p, 'index.html')):
        FRONTEND_DIR = p
        break

WHITENOISE_ROOT = FRONTEND_DIR
"@
        Set-Content (Join-Path $configDir "production.py") $prodConfig -Encoding UTF8
        Write-OK "Fichier de configuration créé"
    }

    # Initialiser la base Django
    Write-Info "Initialisation de la base de données..."
    $pythonExe = "python"
    $managePy  = Join-Path $sagiDir "resources\backend\manage.py"

    if (Test-Path $managePy) {
        $env:DJANGO_SETTINGS_MODULE = "config.settings.production"
        $result = & $pythonExe $managePy migrate --noinput 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-OK "Base de données initialisée"
        } else {
            Write-WARN "Migration à faire manuellement (Python requis)"
        }
    }

    # Licence d'essai
    $licenceFile = Join-Path $env:USERPROFILE ".sagischool_licence"
    @{
        valide                = $true
        cle_licence           = "ESSAI-WINDOWS-30J"
        statut                = "ESSAI"
        date_fin              = (Get-Date).AddDays(30).ToString("yyyy-MM-dd")
        derniere_verification = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
    } | ConvertTo-Json | Set-Content $licenceFile
    Write-OK "Licence d'essai 30 jours activée"

    # Raccourci bureau
    $exe = Get-ChildItem $sagiDir -Filter "sagi-school.exe" -Recurse | Select-Object -First 1 -ExpandProperty FullName
    if (-not $exe) {
        $exe = Get-ChildItem $sagiDir -Filter "*.exe" | Select-Object -First 1 -ExpandProperty FullName
    }
    if ($exe) {
        $desktop  = [Environment]::GetFolderPath("Desktop")
        $wsh      = New-Object -ComObject WScript.Shell
        $link     = $wsh.CreateShortcut("$desktop\SAGI SCHOOL.lnk")
        $link.TargetPath  = $exe
        $link.Description = "SAGI SCHOOL — Gestion Scolaire by HADY GESMAN"
        $link.Save()
        Write-OK "Raccourci créé sur le bureau"
    }
}

Write-Sep

# ── RÉSUMÉ ────────────────────────────────────────────────────
Write-Header
Write-Host "  ╔══════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "  ║      SAGI SCHOOL installé avec succès ! ✓        ║" -ForegroundColor Green
Write-Host "  ╚══════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "  Base de données  : $DB_NAME (PostgreSQL)" -ForegroundColor Gray
Write-Host "  Utilisateur DB   : $DB_USER" -ForegroundColor Gray
Write-Host "  Mot de passe DB  : $DB_PASSWORD" -ForegroundColor Yellow
Write-Host "  Licence          : Essai 30 jours" -ForegroundColor Gray
Write-Host ""
Write-Host "  IMPORTANT : Notez votre mot de passe PostgreSQL !" -ForegroundColor Yellow
Write-Sep
Write-Host ""
Write-Host "  Pour démarrer SAGI SCHOOL :" -ForegroundColor White
Write-Host "  → Double-cliquez sur 'SAGI SCHOOL' sur votre bureau" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Identifiants par défaut :" -ForegroundColor White
Write-Host "  → Email    : admin@votreecole.sn" -ForegroundColor Cyan
Write-Host "  → Password : fourni par HADY GESMAN" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Support : contact@hadygesman.com" -ForegroundColor Gray
Write-Host ""

$lancer = Read-Host "  Lancer SAGI SCHOOL maintenant ? (O/N)"
if ($lancer -match "^[Oo]") {
    if ($exe) { Start-Process $exe }
    elseif ($sagiDir) {
        $anyExe = Get-ChildItem $sagiDir -Filter "*.exe" | Select-Object -First 1 -ExpandProperty FullName
        if ($anyExe) { Start-Process $anyExe }
    }
}

Write-Host ""
Write-Host "  Merci d'avoir choisi SAGI SCHOOL — HADY GESMAN" -ForegroundColor Cyan
Write-Host ""
