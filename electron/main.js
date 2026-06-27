const { app, BrowserWindow, dialog, ipcMain } = require('electron');
const { spawn } = require('child_process');
const path      = require('path');
const http      = require('http');
const fs        = require('fs');

let mainWindow;
let djangoProcess;
const isDev       = process.env.NODE_ENV === 'development';
const DJANGO_PORT = 8765;

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

function showSetupWindow() {
  return new Promise((resolve, reject) => {
    const win = new BrowserWindow({
      width: 500, height: 720,
      resizable: false,
      title: 'Configuration — SAGI SCHOOL',
      webPreferences: {
        preload: path.join(__dirname, 'setup-preload.js'),
        contextIsolation: true,
        nodeIntegration: false,
      }
    });
    win.setMenu(null);
    win.loadFile(path.join(__dirname, 'setup.html'));

    let settled = false;
    ipcMain.once('setup-submit', (event, payload) => {
      settled = true;
      resolve({ win, payload });
    });
    win.once('closed', () => {
      if (!settled) reject(new Error('Configuration annulée par l\'utilisateur'));
    });
  });
}

function runInitInstallation(backendDir, installData) {
  const tmpFile = path.join(app.getPath('userData'), `install-${Date.now()}.json`);
  fs.writeFileSync(tmpFile, JSON.stringify(installData), 'utf8');
  return runManageCommand(backendDir, ['init_installation', '--payload', tmpFile], 'init_installation')
    .finally(() => { try { fs.unlinkSync(tmpFile); } catch (_) {} });
}

function runManageCommand(backendDir, args, errorLabel) {
  return new Promise((resolve, reject) => {
    const python   = getPython();
    const managePy = path.join(backendDir, 'manage.py');
    const env = {
      ...process.env,
      DJANGO_SETTINGS_MODULE: 'config.settings.production',
      PYTHONUNBUFFERED: '1',
    };

    const proc = spawn(python, [managePy, ...args], { cwd: backendDir, env });

    let stderr = '';
    proc.stderr.on('data', d => { stderr += d.toString(); });
    proc.on('close', code => {
      if (code === 0) resolve();
      else reject(new Error(stderr.trim() || `${errorLabel} a échoué (code ${code})`));
    });
    proc.on('error', reject);
  });
}

function runCollectstatic(backendDir) {
  return runManageCommand(backendDir, ['collectstatic', '--noinput'], 'collectstatic');
}

function runMigrate(backendDir) {
  return runManageCommand(backendDir, ['migrate', '--noinput'], 'migrate');
}

// Tâches idempotentes à CHAQUE démarrage : applique les migrations en attente
// (essentiel après une mise à jour) et seed les données de référence du Coran.
// Non bloquant : un échec ne doit pas empêcher l'app de démarrer.
async function runMaintenance(backendDir) {
  try {
    await runMigrate(backendDir);
  } catch (e) {
    console.warn('[Maintenance] migrate:', e.message);
  }
  try {
    await runManageCommand(backendDir, ['init_coran'], 'init_coran');
  } catch (e) {
    console.warn('[Maintenance] init_coran:', e.message);
  }
}

function initParametresFiscaux(backendDir) {
  return new Promise(resolve => {
    const python   = getPython();
    const managePy = path.join(backendDir, 'manage.py');
    const env = {
      ...process.env,
      DJANGO_SETTINGS_MODULE: 'config.settings.production',
      PYTHONUNBUFFERED: '1',
    };
    const proc = spawn(python, [managePy, 'init_parametres_fiscaux'], { cwd: backendDir, env });
    proc.on('close', code => {
      console.log('[Setup] init_parametres_fiscaux code:', code);
      resolve(); // ne pas bloquer si déjà initialisé
    });
    proc.on('error', () => resolve());
  });
}

function getSetupLogPath() {
  const userData = app.getPath('userData');
  if (!fs.existsSync(userData)) fs.mkdirSync(userData, { recursive: true });
  return path.join(userData, 'setup.log');
}

function appendSetupLog(msg) {
  const line = `[${new Date().toISOString()}] ${msg}\n`;
  console.log(msg);
  try { fs.appendFileSync(getSetupLogPath(), line); } catch (_) {}
}

function runStep(label, python, args) {
  return new Promise(resolve => {
    appendSetupLog(`>> ${label}`);
    let out = '';
    const p = spawn(python, args, { env: { ...process.env, PYTHONUNBUFFERED: '1' } });
    p.stdout.on('data', d => { out += d.toString(); });
    p.stderr.on('data', d => { out += d.toString(); });
    p.on('close', code => {
      appendSetupLog(`<< ${label} exit=${code}\n${out.trim()}`);
      resolve(code);
    });
    p.on('error', err => {
      appendSetupLog(`<< ${label} ERROR: ${err.message}`);
      resolve(-1);
    });
  });
}

/**
 * Installe / met à jour les dépendances Python.
 * Séquence : ensurepip → force-reinstall setuptools → pip install requirements.
 */
async function ensurePythonPackages(backendDir) {
  const python  = getPython();
  const reqFile = path.join(backendDir, 'requirements', 'base.txt');
  appendSetupLog(`=== ensurePythonPackages python=${python} ===`);

  if (!fs.existsSync(reqFile)) {
    appendSetupLog('requirements/base.txt introuvable, skip');
    return;
  }

  await runStep('ensurepip', python, ['-m', 'ensurepip', '--upgrade']);
  await runStep('setuptools force-reinstall', python, [
    '-m', 'pip', 'install', '--force-reinstall', '--upgrade', 'setuptools',
    '--no-warn-script-location',
  ]);
  await runStep('pip install requirements', python, [
    '-m', 'pip', 'install', '-r', reqFile, '--no-warn-script-location',
  ]);
  appendSetupLog('=== ensurePythonPackages done ===');
}

/** Vérifie que pkg_resources est importable. Lève une erreur claire sinon. */
function checkPkgResources(python) {
  return new Promise((resolve, reject) => {
    const p = spawn(python, ['-c', 'import pkg_resources; print("OK")'], {
      env: { ...process.env, PYTHONUNBUFFERED: '1' },
    });
    let out = '';
    p.stdout.on('data', d => { out += d.toString(); });
    p.stderr.on('data', d => { out += d.toString(); });
    p.on('close', code => {
      if (code === 0 && out.includes('OK')) {
        appendSetupLog('pkg_resources OK');
        resolve();
      } else {
        const logPath = getSetupLogPath();
        appendSetupLog(`pkg_resources MANQUANT. Sortie: ${out.trim()}`);
        reject(new Error(
          `Le module Python "setuptools" (pkg_resources) n'est pas installé.\n\n` +
          `Ouvrez un terminal Windows et exécutez :\n` +
          `  python -m ensurepip --upgrade\n` +
          `  python -m pip install --force-reinstall setuptools\n\n` +
          `Log de diagnostic : ${logPath}`
        ));
      }
    });
    p.on('error', err => reject(new Error(`Python introuvable : ${err.message}`)));
  });
}

async function ensureProductionConfig() {
  const backendDir  = getBackendDir();
  const prodFile    = path.join(backendDir, 'config', 'settings', 'production.py');
  const exampleFile = path.join(backendDir, 'config', 'settings', 'production.example.py');

  if (fs.existsSync(prodFile)) return;

  const { win, payload } = await showSetupWindow();
  const { db: creds, install } = payload;

  // Échapper les apostrophes pour les chaînes Python single-quoted
  const esc = s => s.replace(/\\/g, '\\\\').replace(/'/g, "\\'");

  // Clé secrète unique par installation
  const crypto = require('crypto');
  const secretKey = crypto.randomBytes(48).toString('hex');

  let content = fs.readFileSync(exampleFile, 'utf8');
  content = content.replace(/SECRET_KEY\s*=\s*'[^']*'/, `SECRET_KEY = '${secretKey}'`);
  content = content.replace(/'PASSWORD': '[^']*'/, `'PASSWORD': '${esc(creds.password)}'`);
  content = content.replace(/'NAME': '[^']*'/,     `'NAME': '${esc(creds.name)}'`);
  content = content.replace(/'USER': '[^']*'/,     `'USER': '${esc(creds.user)}'`);
  content = content.replace(/'HOST': '[^']*'/,     `'HOST': '${esc(creds.host)}'`);
  content = content.replace(/'PORT': '[^']*'/,     `'PORT': '${esc(creds.port)}'`);
  fs.writeFileSync(prodFile, content, 'utf8');

  try {
    await runMigrate(backendDir);
  } catch (err) {
    if (fs.existsSync(prodFile)) fs.unlinkSync(prodFile);
    if (!win.isDestroyed()) win.close();
    throw new Error(`Erreur migrate : ${err.message}`);
  }

  // Initialiser les paramètres fiscaux RH (Sénégal) si pas encore fait
  await initParametresFiscaux(backendDir);

  // Créer école + licence essai + exercice + super_admin
  try {
    await runInitInstallation(backendDir, install);
  } catch (err) {
    if (fs.existsSync(prodFile)) fs.unlinkSync(prodFile);
    if (!win.isDestroyed()) win.close();
    throw new Error(`Erreur init_installation : ${err.message}`);
  }

  try {
    await runCollectstatic(backendDir);
  } catch (err) {
    if (fs.existsSync(prodFile)) fs.unlinkSync(prodFile);
    if (!win.isDestroyed()) win.close();
    throw new Error(`Erreur collectstatic : ${err.message}`);
  }

  if (!win.isDestroyed()) win.close();
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

    try {
      // En production Windows → waitress (WSGI stable).
      // En dev ou Linux → runserver Django.
      const cmd = (!isDev && process.platform === 'win32')
        ? ['-m', 'waitress',
           `--host=127.0.0.1`, `--port=${DJANGO_PORT}`,
           'config.wsgi:application']
        : [managePy, 'runserver', `127.0.0.1:${DJANGO_PORT}`, '--noreload'];

      console.log('[Electron] Commande Django:', python, cmd.join(' '));

      djangoProcess = spawn(python, cmd, { cwd: backendDir, env });

      djangoProcess.stdout.on('data', d => console.log('[Django]', d.toString().trim()));
      djangoProcess.stderr.on('data', d => console.error('[Django]', d.toString().trim()));
      djangoProcess.on('close',  code => console.log('[Django] Arrêté, code:', code));
      djangoProcess.on('error',  err  => console.error('[Django] Erreur:', err.message));
    } catch (err) {
      console.error('[Django] Impossible de démarrer:', err.message);
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

async function waitForDjango(retries = 40) {
  return new Promise(resolve => {
    const attempt = n => {
      http.get(`http://127.0.0.1:${DJANGO_PORT}/`, () => {
        console.log('[Electron] Django prêt !');
        setTimeout(resolve, 1500);
      }).on('error', () => {
        if (n <= 0) { resolve(); return; }
        console.log(`[Electron] Attente Django... (${n})`);
        setTimeout(() => attempt(n - 1), 1000);
      });
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

const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  console.log('[Electron] Instance déjà active');
  app.quit();
} else {
  app.whenReady().then(async () => {
    if (!isDev) {
      // ── 1. Paquets Python et config DB ───────────────────────
      await ensurePythonPackages(getBackendDir());

      try {
        await ensureProductionConfig();
      } catch (e) {
        dialog.showErrorBox('Erreur de configuration SAGI SCHOOL', e.message);
        app.quit();
        return;
      }

      // Migrations en attente (mises à jour) + seed Coran — idempotent, non bloquant
      await runMaintenance(getBackendDir());
    }

    // ── 2. Démarrer Django (nécessaire pour la vérif licence) ──
    createWindow();

    // ── 3. Vérification licence APRÈS démarrage Django ─────────
    if (!isDev) {
      try {
        // Attendre que Django soit prêt avant de vérifier
        await waitForDjango(20);
        const { verifierLicence } = require('./licence-check');
        const result = await verifierLicence();

        if (!result.valide) {
          dialog.showErrorBox(
            '⚠️ Licence SAGI SCHOOL',
            result.message + '\n\nContactez HADY GESMAN pour renouveler votre licence.'
          );
          // On ne quitte pas — on laisse l'utilisateur fermer manuellement
        } else if (result.mode !== 'online') {
          // Avertissement doux pour essai ou offline
          console.log('[Licence]', result.message);
        }
      } catch (e) {
        console.warn('[Licence] Vérification échouée (non bloquant):', e.message);
      }
    }
  });
}

app.on('window-all-closed', () => {
  if (djangoProcess) djangoProcess.kill();
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  if (djangoProcess) djangoProcess.kill();
});
