const { app, BrowserWindow, dialog } = require('electron');
const { spawn } = require('child_process');
const path      = require('path');
const http      = require('http');
const fs        = require('fs');

let mainWindow;
let djangoProcess;
const isDev       = process.env.NODE_ENV === 'development';
const DJANGO_PORT = 8765;

/**
 * Génère production.py avec les chemins corrects avant de démarrer Django.
 * Lit les credentials DB depuis le fichier existant pour les préserver.
 */
function ensureProductionConfig() {
  if (isDev) return;

  const backendDir  = getBackendDir();
  const configPath  = path.join(backendDir, 'config', 'settings', 'production.py');
  const frontendDir = path.join(process.resourcesPath, 'frontend', 'dist').replace(/\\/g, '/');
  const staticRoot  = path.join(backendDir, 'staticfiles').replace(/\\/g, '/');

  // Lire les credentials depuis le fichier existant, ou utiliser les defaults
  let dbName     = 'hady_gesman';
  let dbUser     = 'postgres';
  let dbPassword = 'postgres';
  let dbHost     = 'localhost';
  let dbPort     = '5432';
  let secretKey  = 'sagi-school-prod-2025-hady-gesman-secret';

  if (fs.existsSync(configPath)) {
    const existing = fs.readFileSync(configPath, 'utf8');
    const m = (re) => { const r = existing.match(re); return r ? r[1] : null; };
    dbName     = m(/'NAME':\s*'([^']+)'/)     || dbName;
    dbUser     = m(/'USER':\s*'([^']+)'/)     || dbUser;
    dbPassword = m(/'PASSWORD':\s*'([^']+)'/) || dbPassword;
    dbHost     = m(/'HOST':\s*'([^']+)'/)     || dbHost;
    dbPort     = m(/'PORT':\s*'([^']+)'/)     || dbPort;
    secretKey  = m(/SECRET_KEY\s*=\s*['"]([^'"]+)['"]/) || secretKey;
  }

  const content = `from .base import *

DEBUG = False
SECRET_KEY = '${secretKey}'
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '*']

INSTALLED_APPS = [a for a in INSTALLED_APPS if 'debug_toolbar' not in a]
MIDDLEWARE     = [m for m in MIDDLEWARE if 'debug_toolbar' not in m]

DATABASES = {
    'default': {
        'ENGINE':   'django.db.backends.postgresql',
        'NAME':     '${dbName}',
        'USER':     '${dbUser}',
        'PASSWORD': '${dbPassword}',
        'HOST':     '${dbHost}',
        'PORT':     '${dbPort}',
        'OPTIONS':  {'connect_timeout': 5},
        'CONN_MAX_AGE': 0,
    }
}

STATIC_ROOT      = '${staticRoot}'
STATICFILES_DIRS = []
FRONTEND_DIR     = '${frontendDir}'

CORS_ALLOW_ALL_ORIGINS = True
`;

  try {
    fs.writeFileSync(configPath, content, 'utf8');
    console.log('[Config] production.py OK :', configPath);
    console.log('[Config] FRONTEND_DIR     :', frontendDir);
  } catch (err) {
    console.error('[Config] Erreur écriture production.py :', err.message);
  }
}

function getBackendDir() {
  return isDev
    ? path.join(__dirname, '..', 'backend')
    : path.join(process.resourcesPath, 'backend');
}

function getPython() {
  if (isDev) {
    return path.join(getBackendDir(), 'venv', 'bin', 'python');
  }
  // Windows — chercher python dans plusieurs endroits
  if (process.platform === 'win32') {
    const candidates = [
      'python',
      path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Python', 'Python310', 'python.exe'),
      path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Python', 'Python311', 'python.exe'),
      path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Python', 'Python312', 'python.exe'),
      'C:\\Python310\\python.exe',
      'C:\\Python311\\python.exe',
      'C:\\Python312\\python.exe',
    ];
    for (const p of candidates) {
      if (p === 'python') return p; // dans le PATH
      if (fs.existsSync(p)) return p;
    }
    return 'python';
  }
  // Linux/Mac
  const venvPython = path.join(getBackendDir(), 'venv', 'bin', 'python3');
  if (fs.existsSync(venvPython)) return venvPython;
  return '/usr/bin/python3.10';
}

function spawnDjango(python, args, opts) {
  try {
    djangoProcess = spawn(python, args, opts);
    djangoProcess.stdout.on('data', d => console.log('[Django]', d.toString().trim()));
    djangoProcess.stderr.on('data', d => console.error('[Django]', d.toString().trim()));
    djangoProcess.on('close',  code => console.log('[Django] Arrêté, code:', code));
    djangoProcess.on('error',  err  => console.error('[Django] Erreur:', err.message));
  } catch (err) {
    console.error('[Django] Impossible de démarrer:', err.message);
  }
}

function startDjango() {
  const backendDir = getBackendDir();
  const managePy   = path.join(backendDir, 'manage.py');
  const python     = getPython();

  console.log('[Electron] Python:', python);
  console.log('[Electron] manage.py:', managePy);

  http.get(`http://127.0.0.1:${DJANGO_PORT}/`, () => {
    console.log('[Electron] Django déjà actif');
  }).on('error', () => {
    const env = {
      ...process.env,
      DJANGO_SETTINGS_MODULE: isDev
        ? 'config.settings.local'
        : 'config.settings.production',
      PYTHONUNBUFFERED: '1',
    };

    if (!isDev && process.platform !== 'win32') {
      const venvBin = path.join(backendDir, 'venv', 'bin');
      if (fs.existsSync(venvBin)) {
        env.PATH        = venvBin + ':' + process.env.PATH;
        env.VIRTUAL_ENV = path.join(backendDir, 'venv');
      }
    }

    const spawnOpts = { cwd: backendDir, env };

    // Sur Windows, waitress est plus fiable que runserver pour les requêtes concurrentes
    if (!isDev && process.platform === 'win32') {
      const checkWaitress = spawn(python, ['-c', 'import waitress'], spawnOpts);
      checkWaitress.on('close', code => {
        if (code === 0) {
          console.log('[Django] Démarrage avec waitress');
          spawnDjango(python, [
            '-m', 'waitress',
            `--host=127.0.0.1`,
            `--port=${DJANGO_PORT}`,
            'config.wsgi:application'
          ], spawnOpts);
        } else {
          console.log('[Django] Démarrage avec runserver (waitress absent)');
          spawnDjango(python, [managePy, 'runserver', `127.0.0.1:${DJANGO_PORT}`, '--noreload'], spawnOpts);
        }
      });
    } else {
      spawnDjango(python, [managePy, 'runserver', `127.0.0.1:${DJANGO_PORT}`, '--noreload'], spawnOpts);
    }
  });
}

function waitForAngular(retries = 30) {
  return new Promise(resolve => {
    const attempt = n => {
      http.get('http://localhost:4200', () => {
        console.log('[Electron] Angular prêt !');
        resolve();
      }).on('error', () => {
        if (n <= 0) { resolve(); return; }
        console.log(`[Electron] Attente Angular... (${n})`);
        setTimeout(() => attempt(n - 1), 1000);
      });
    };
    attempt(retries);
  });
}

async function waitForDjango(retries = 120) {
  return new Promise(resolve => {
    const attempt = n => {
      const req = http.get(`http://127.0.0.1:${DJANGO_PORT}/api/auth/login/`, res => {
        console.log('[Electron] Django prêt ! (statut:', res.statusCode, ')');
        resolve(true);
      });
      req.on('error', () => {
        if (n <= 0) {
          console.error('[Electron] Django n\'a pas démarré après 2 minutes.');
          resolve(false);
          return;
        }
        if ((retries - n) % 10 === 0) {
          console.log(`[Electron] Attente Django... (${retries - n}s)`);
        }
        setTimeout(() => attempt(n - 1), 1000);
      });
      req.setTimeout(2000, () => { req.destroy(); });
    };
    attempt(retries);
  });
}

async function createWindow() {
  const splash = new BrowserWindow({
    width: 400, height: 300,
    frame: false, alwaysOnTop: true,
    webPreferences: { nodeIntegration: false }
  });
  splash.loadFile(path.join(__dirname, 'splash.html'));

  ensureProductionConfig();
  startDjango();

  let djangoReady = true;
  if (isDev) {
    await waitForAngular();
  } else {
    djangoReady = await waitForDjango();
  }

  splash.destroy();

  if (!djangoReady) {
    dialog.showErrorBox(
      'SAGI SCHOOL — Erreur de démarrage',
      'Le serveur n\'a pas pu démarrer après 2 minutes.\n\n' +
      'Vérifiez que :\n' +
      '• PostgreSQL est démarré (services Windows)\n' +
      '• install_win.ps1 a bien été exécuté\n\n' +
      'Relancez l\'application.'
    );
    app.quit();
    return;
  }

  mainWindow = new BrowserWindow({
    width: 1400, height: 900,
    minWidth: 1024, minHeight: 700,
    show: false,
    title: 'SAGI SCHOOL',
    webPreferences: {
      preload:          path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration:  false,
      webSecurity:      false,
    }
  });

  const url = isDev
    ? 'http://localhost:4200'
    : `http://127.0.0.1:${DJANGO_PORT}`;

  console.log('[Electron] Chargement:', url);
  mainWindow.loadURL(url);

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    mainWindow.maximize();
  });

  mainWindow.on('closed', () => { mainWindow = null; });
}

const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  console.log('[Electron] Instance déjà active');
  app.quit();
} else {
  app.whenReady().then(async () => {
    if (!isDev) {
      try {
        const { verifierLicence } = require('./licence-check');
        const result = await verifierLicence();
        if (!result.valide) {
          dialog.showErrorBox('Licence SAGI SCHOOL', result.message);
          app.quit();
          return;
        }
        if (result.mode === 'offline') {
          console.warn('[Electron] Mode offline:', result.message);
        }
      } catch (e) {
        console.warn('[Electron] Vérification licence échouée:', e.message);
      }
    }
    createWindow();
  });
}

app.on('window-all-closed', () => {
  if (djangoProcess) djangoProcess.kill();
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  if (djangoProcess) djangoProcess.kill();
});
