$ErrorActionPreference = "SilentlyContinue"

function Write-OK { param($m) Write-Host "  OK: $m" -ForegroundColor Green }
function Write-ERR { param($m) Write-Host "  ERR: $m" -ForegroundColor Red }
function Write-SEP { Write-Host "  ----------------------------------------" -ForegroundColor DarkGray }

Write-Host ""
Write-Host "  SAGI SCHOOL - Installation Windows" -ForegroundColor Cyan
Write-Host "  by HADY GESMAN 2026" -ForegroundColor Cyan
Write-Host ""

$DB_PASSWORD = "SangueBiDiop@7"
$DB_NAME = "hady_gesman"
$DB_USER = "postgres"

Write-OK "Mot de passe configure"
Write-SEP

# Detecter PostgreSQL
$pgPath = $null
foreach ($v in @("16","15","14","13","12")) {
    $p = "C:\Program Files\PostgreSQL\$v\bin"
    if (Test-Path "$p\psql.exe") { $pgPath = $p; break }
}

if ($pgPath) {
    Write-OK "PostgreSQL detecte: $pgPath"
} else {
    Write-ERR "PostgreSQL non trouve. Installez-le depuis postgresql.org"
    Read-Host "Entree pour continuer"
}

Write-SEP

# Creer la base
if ($pgPath) {
    $env:PGPASSWORD = $DB_PASSWORD
    $env:PATH += ";$pgPath"
    $check = & "$pgPath\psql.exe" -U $DB_USER -h localhost -p 5432 -lqt 2>&1
    if ($check -match $DB_NAME) {
        Write-OK "Base '$DB_NAME' existe deja"
    } else {
        & "$pgPath\createdb.exe" -U $DB_USER -h localhost -p 5432 $DB_NAME 2>&1 | Out-Null
        Write-OK "Base '$DB_NAME' creee"
    }
    $svc = Get-Service | Where-Object { $_.Name -like "postgresql*" } | Select-Object -First 1
    if ($svc) {
        if ($svc.Status -ne "Running") { Start-Service $svc.Name }
        Set-Service -Name $svc.Name -StartupType Automatic
        Write-OK "Service PostgreSQL actif"
    }
}

Write-SEP

# Telecharger SAGI SCHOOL
$sagiDirs = @(
    "C:\Program Files\SAGI SCHOOL",
    "$env:LOCALAPPDATA\Programs\SAGI SCHOOL"
)
$sagiDir = $null
foreach ($d in $sagiDirs) { if (Test-Path $d) { $sagiDir = $d; break } }

if ($sagiDir) {
    Write-OK "SAGI SCHOOL deja installe: $sagiDir"
} else {
    Write-Host "  Telechargement SAGI SCHOOL..." -ForegroundColor Gray
    $url = "https://github.com/Deadman7777/sagi-school/releases/download/v1.0.0/SAGI.SCHOOL.Setup.1.0.0.exe"
    $setup = "$env:TEMP\SAGI_Setup.exe"
    try {
        (New-Object System.Net.WebClient).DownloadFile($url, $setup)
        Write-OK "Telechargement termine"
        Start-Process -FilePath $setup -Wait
        foreach ($d in $sagiDirs) { if (Test-Path $d) { $sagiDir = $d; break } }
        Write-OK "SAGI SCHOOL installe"
    } catch {
        Write-ERR "Echec telechargement: $_"
    }
}

Write-SEP

# Configurer production.py
if ($sagiDir) {
    $configPath = Join-Path $sagiDir "resources\backend\config\settings\production.py"
    $examplePath = Join-Path $sagiDir "resources\backend\config\settings\production.example.py"

    if (-not (Test-Path $configPath) -and (Test-Path $examplePath)) {
        Copy-Item $examplePath $configPath
        Write-OK "production.py cree depuis example"
    }

    if (Test-Path $configPath) {
        $config = Get-Content $configPath -Raw -Encoding UTF8
        # Remplacement direct sans regex special chars
        $config = $config -replace "'PASSWORD': '[^']*'", ("'PASSWORD': '" + $DB_PASSWORD + "'")
        $config = $config -replace "'NAME': '[^']*'", ("'NAME': '" + $DB_NAME + "'")
        $config = $config -replace "'USER': '[^']*'", ("'USER': '" + $DB_USER + "'")
        $config = $config -replace "'HOST': '[^']*'", "'HOST': 'localhost'"
        $config = $config -replace "'PORT': '[^']*'", "'PORT': '5432'"
        [System.IO.File]::WriteAllText($configPath, $config, [System.Text.Encoding]::UTF8)
        Write-OK "Configuration base de donnees mise a jour"
    }

    # Migrations Django
    Write-Host "  Initialisation base de donnees..." -ForegroundColor Gray
    $managePy = Join-Path $sagiDir "resources\backend\manage.py"
    if (Test-Path $managePy) {
        $env:DJANGO_SETTINGS_MODULE = "config.settings.production"
        & python $managePy migrate --noinput 2>&1 | Out-Null
        Write-OK "Base de donnees initialisee"
    }

    # Licence
    $licence = '{"valide": true, "cle_licence": "ESSAI-WIN-30J", "statut": "ESSAI", "date_fin": "2026-12-31", "derniere_verification": "2026-04-18T10:00:00"}'
    Set-Content "$env:USERPROFILE\.sagischool_licence" $licence -Encoding UTF8
    Write-OK "Licence essai activee"

    # Raccourci bureau
    $exe = Get-ChildItem $sagiDir -Filter "*.exe" | Where-Object { $_.Name -notlike "Uninstall*" } | Select-Object -First 1 -ExpandProperty FullName
    if ($exe) {
        $desktop = [Environment]::GetFolderPath("Desktop")
        $wsh = New-Object -ComObject WScript.Shell
        $link = $wsh.CreateShortcut("$desktop\SAGI SCHOOL.lnk")
        $link.TargetPath = $exe
        $link.Save()
        Write-OK "Raccourci bureau cree"
    }
}

Write-SEP
Write-Host ""
Write-Host "  SAGI SCHOOL installe avec succes !" -ForegroundColor Green
Write-Host "  Base de donnees : $DB_NAME" -ForegroundColor Gray
Write-Host "  Utilisateur DB  : $DB_USER" -ForegroundColor Gray
Write-Host "  Licence         : Essai 30 jours" -ForegroundColor Gray
Write-Host ""

$lancer = Read-Host "  Lancer SAGI SCHOOL maintenant ? (O/N)"
if ($lancer -match "^[Oo]") {
    if ($exe) { Start-Process $exe }
}

Write-Host "  Merci d'avoir choisi SAGI SCHOOL - HADY GESMAN" -ForegroundColor Cyan
