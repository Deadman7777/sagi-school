const { app, BrowserWindow, dialog } = require('electron');
const { spawn } = require('child_process');
const path      = require('path');
const http      = require('http');
const fs        = require('fs');

let mainWindow;
let djangoProcess;
const isDev       = process.env.NODE_ENV === 'development';
const DJANGO_PORT = 8765;

// ── Chemins selon environnement ──────────────────────────────
function getBackendDir() {
  return isDev
    ? path.join(__dirname, '..', 'backend')
    : path.join(process.resourcesPath, 'backend');
}

function getPython() {
  if (isDev) {
    return path.join(getBackendDir(), 'venv', 'bin', 'python');
  }
  // En prod — python3 système avec venv en PATH
  const venvPython = path.join(getBackendDir(), 'venv', 'bin', 'python3');
  if (fs.existsSync(venvPython)) return venvPython;
  return '/usr/bin/python3.10';
}

// ── Démarrer Django ──────────────────────────────────────────
function startDjango() {
  const backendDir = getBackendDir();
  const managePy   = path.join(backendDir, 'manage.py');
  const python     = getPython();

  console.log('[Electron] Python:', python);
  console.log('[Electron] manage.py:', managePy);

  // Vérifier si Django tourne déjà
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

    // En prod — ajouter venv au PATH si dispo
    if (!isDev) {
      const venvBin = path.join(backendDir, 'venv', 'bin');
      if (fs.existsSync(venvBin)) {
        env.PATH         = venvBin + ':' + process.env.PATH;
        env.VIRTUAL_ENV  = path.join(backendDir, 'venv');
      }
    }

    try {
      djangoProcess = spawn(python, [
        managePy, 'runserver', `127.0.0.1:${DJANGO_PORT}`, '--noreload'
      ], { cwd: backendDir, env });

      djangoProcess.stdout.on('data', d => console.log('[Django]', d.toString().trim()));
      djangoProcess.stderr.on('data', d => console.error('[Django]', d.toString().trim()));
      djangoProcess.on('close',  code => console.log('[Django] Arrêté, code:', code));
      djangoProcess.on('error',  err  => console.error('[Django] Erreur:', err.message));
    } catch (err) {
      console.error('[Django] Impossible de démarrer:', err.message);
    }
  });
}

// ── Attendre Angular (dev) ───────────────────────────────────
// Attendre que Django soit prêt en prod
async function waitForDjango(retries = 30) {
  return new Promise(resolve => {
    const attempt = n => {
      http.get(`http://127.0.0.1:${DJANGO_PORT}/`, () => {
        console.log('[Electron] Django prêt !');
        resolve();
      }).on('error', () => {
        if (n <= 0) { resolve(); return; }
        setTimeout(() => attempt(n - 1), 1000);
      });
    };
    attempt(retries);
  });
}

// ── Fenêtre principale ───────────────────────────────────────
async function createWindow() {
  const splash = new BrowserWindow({
    width: 400, height: 300,
    frame: false, alwaysOnTop: true,
    webPreferences: { nodeIntegration: false }
  });
  splash.loadFile(path.join(__dirname, 'splash.html'));

  startDjango();

  if (isDev) {
    await waitForAngular();
  } else {
    await waitForDjango();
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

  // En prod — Django sert le frontend via whitenoise
  const url = isDev
    ? 'http://localhost:4200'
    : `http://127.0.0.1:${DJANGO_PORT}`;

  console.log('[Electron] Chargement:', url);
  mainWindow.loadURL(url);

  mainWindow.once('ready-to-show', () => {
    splash.destroy();
    mainWindow.show();
    mainWindow.maximize();
  });

  mainWindow.on('closed', () => { mainWindow = null; });
}

// ── Instance unique ──────────────────────────────────────────
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  console.log('[Electron] Instance déjà active');
  app.quit();
} else {
  app.whenReady().then(async () => {
    // Vérification licence
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

// ── Nettoyage ────────────────────────────────────────────────
app.on('window-all-closed', () => {
  if (djangoProcess) djangoProcess.kill();
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  if (djangoProcess) djangoProcess.kill();
});
