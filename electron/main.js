const { app, BrowserWindow, dialog } = require('electron');
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

function getServePy() {
  return isDev
    ? path.join(__dirname, 'serve.py')
    : path.join(process.resourcesPath, 'serve.py');
}

function getPython() {
  if (isDev) {
    return path.join(getBackendDir(), 'venv', 'bin', 'python');
  }
  if (process.platform === 'win32') {
    // Prefer a venv bundled with the app (Scripts\ on Windows)
    const venvPython = path.join(getBackendDir(), 'venv', 'Scripts', 'python.exe');
    if (fs.existsSync(venvPython)) return venvPython;
    // Fixed LOCALAPPDATA install paths
    const candidates = [
      path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Python', 'Python313', 'python.exe'),
      path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Python', 'Python312', 'python.exe'),
      path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Python', 'Python311', 'python.exe'),
      path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Python', 'Python310', 'python.exe'),
    ];
    for (const p of candidates) {
      if (fs.existsSync(p)) return p;
    }
    // py launcher is the most reliable Windows fallback
    return 'py';
  }
  const venvPython = path.join(getBackendDir(), 'venv', 'bin', 'python3');
  if (fs.existsSync(venvPython)) return venvPython;
  return '/usr/bin/python3.10';
}

function startDjango() {
  return new Promise((resolve) => {
    const backendDir = getBackendDir();
    const python     = getPython();

    console.log('[Electron] Python:', python);
    console.log('[Electron] BackendDir:', backendDir);

    http.get(`http://127.0.0.1:${DJANGO_PORT}/`, () => {
      console.log('[Electron] Django déjà actif');
      resolve();
    }).on('error', () => {

      const env = {
        ...process.env,
        DJANGO_SETTINGS_MODULE: isDev ? 'config.settings.local' : 'config.settings.production',
        PYTHONUNBUFFERED: '1',
        PYTHONPATH: backendDir,
      };

      if (!isDev && process.platform !== 'win32') {
        const venvBin = path.join(backendDir, 'venv', 'bin');
        if (fs.existsSync(venvBin)) {
          env.PATH        = venvBin + ':' + process.env.PATH;
          env.VIRTUAL_ENV = path.join(backendDir, 'venv');
        }
      }

      // On Windows production use serve.py (a real file on disk, not inside asar)
      // so Python can import it. python -m waitress requires a global waitress install.
      const spawnArgs = (process.platform === 'win32' && !isDev)
        ? [getServePy(), String(DJANGO_PORT)]
        : [path.join(backendDir, 'manage.py'), 'runserver', `127.0.0.1:${DJANGO_PORT}`, '--noreload'];

      try {
        djangoProcess = spawn(python, spawnArgs, { cwd: backendDir, env, windowsHide: true });
        djangoProcess.stdout.on('data', d => console.log('[Django]', d.toString().trim()));
        djangoProcess.stderr.on('data', d => console.error('[Django]', d.toString().trim()));
        djangoProcess.on('close',  code => console.log('[Django] Arrêté, code:', code));
        djangoProcess.on('error',  err  => console.error('[Django] Erreur:', err.message));
      } catch (err) {
        console.error('[Django] Impossible de démarrer:', err.message);
      }
      resolve();
    });
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
        setTimeout(() => attempt(n - 1), 1000);
      });
    };
    attempt(retries);
  });
}

async function waitForDjango(retries = 60) {
  return new Promise((resolve, reject) => {
    const attempt = n => {
      http.get(`http://127.0.0.1:${DJANGO_PORT}/`, () => {
        console.log('[Electron] Django prêt !');
        resolve();
      }).on('error', () => {
        if (n <= 0) {
          reject(new Error(`Django n'a pas répondu après ${retries} secondes.`));
          return;
        }
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

  await startDjango();

  if (isDev) {
    await waitForAngular();
  } else {
    try {
      await waitForDjango();
    } catch (err) {
      splash.destroy();
      dialog.showErrorBox(
        'Erreur de démarrage',
        `Le serveur Django n'a pas démarré.\n\nVérifiez que Python et waitress sont installés.\n\n${err.message}`
      );
      app.quit();
      return;
    }
    await new Promise(resolve => setTimeout(resolve, 2000));
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

  const url = isDev ? 'http://localhost:4200' : `http://127.0.0.1:${DJANGO_PORT}`;
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
