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
      width: 480, height: 510,
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
    ipcMain.once('setup-submit', (event, creds) => {
      settled = true;
      resolve({ win, creds });
    });
    win.once('closed', () => {
      if (!settled) reject(new Error('Configuration annulée par l\'utilisateur'));
    });
  });
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

/**
 * Installe / met à jour les dépendances Python depuis requirements/base.txt.
 * Ne bloque pas le démarrage si pip échoue (log uniquement).
 */
function ensurePythonPackages(backendDir) {
  return new Promise(resolve => {
    const python  = getPython();
    const reqFile = path.join(backendDir, 'requirements', 'base.txt');

    if (!fs.existsSync(reqFile)) {
      console.log('[Setup] requirements/base.txt introuvable, skip');
      return resolve();
    }

    console.log('[Setup] Vérification des paquets Python...');

    const pip = spawn(python, [
      '-m', 'pip', 'install', '-r', reqFile,
      '--quiet', '--no-warn-script-location',
    ], { cwd: backendDir, env: { ...process.env, PYTHONUNBUFFERED: '1' } });

    pip.stdout.on('data', d => console.log('[pip]', d.toString().trim()));
    pip.stderr.on('data', d => console.log('[pip]', d.toString().trim()));
    pip.on('close', code => {
      if (code === 0) console.log('[Setup] Paquets Python OK');
      else console.warn('[Setup] pip a retourné le code', code, '— démarrage quand même');
      resolve();
    });
    pip.on('error', err => {
      console.error('[Setup] pip inaccessible:', err.message);
      resolve(); // ne pas bloquer
    });
  });
}

async function ensureProductionConfig() {
  const backendDir  = getBackendDir();
  const prodFile    = path.join(backendDir, 'config', 'settings', 'production.py');
  const exampleFile = path.join(backendDir, 'config', 'settings', 'production.example.py');

  if (fs.existsSync(prodFile)) return;

  const { win, creds } = await showSetupWindow();

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
        resolve();
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

      // Installer/vérifier les paquets Python avant la config
      await ensurePythonPackages(getBackendDir());

      try {
        await ensureProductionConfig();
      } catch (e) {
        dialog.showErrorBox('Erreur de configuration SAGI SCHOOL', e.message);
        app.quit();
        return;
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
