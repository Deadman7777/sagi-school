const { app, BrowserWindow, dialog, ipcMain, shell } = require('electron');
const { spawn } = require('child_process');
const path      = require('path');
const http      = require('http');
const fs        = require('fs');
const os        = require('os');

let mainWindow;
let djangoProcess;              // processus unique (poste isolé) ou 1er du groupe
let djangoWorkers   = [];       // processus de travail en mode réseau
let lanProxy        = null;     // répartiteur devant les processus de travail
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

// ─── Config applicative persistante (userData, survit aux mises à jour) ──────
// Contient notamment { lanServer: bool } : ce poste écoute-t-il sur le réseau ?
function getAppConfigPath() {
  return path.join(app.getPath('userData'), 'app-config.json');
}

function readAppConfig() {
  try {
    return JSON.parse(fs.readFileSync(getAppConfigPath(), 'utf8')) || {};
  } catch (_) {
    return {};
  }
}

function writeAppConfig(patch) {
  const cfg = { ...readAppConfig(), ...patch };
  try {
    fs.writeFileSync(getAppConfigPath(), JSON.stringify(cfg, null, 2), 'utf8');
  } catch (err) {
    console.error('[Electron] Écriture app-config échouée:', err.message);
  }
  return cfg;
}

// Adresses IPv4 non-loopback de ce poste. Une machine a souvent plusieurs
// interfaces (Ethernet + Wi-Fi + adaptateurs virtuels VirtualBox, VPN…) : on
// les rend TOUTES plutôt que de deviner. Un secrétariat qui reçoit la mauvaise
// adresse ne peut pas se connecter et le diagnostic prend une heure.
function getLanIps() {
  const ifaces = os.networkInterfaces();
  const adresses = [];
  for (const nom of Object.keys(ifaces)) {
    for (const iface of ifaces[nom] || []) {
      if (iface.family === 'IPv4' && !iface.internal) {
        adresses.push({ nom, adresse: iface.address });
      }
    }
  }
  return adresses;
}

/** Texte d'aide listant les adresses à ouvrir sur les postes clients. */
function texteAdressesLan() {
  const ips = getLanIps();
  if (!ips.length) {
    return `Aucune adresse réseau détectée sur ce poste.\n\n`
      + `Vérifiez qu'il est bien raccordé au réseau de l'établissement, `
      + `puis relancez SAGI SCHOOL.`;
  }
  const liste = ips
    .map(({ nom, adresse }) => `    http://${adresse}:${DJANGO_PORT}      (${nom})`)
    .join('\n');
  return `Sur les autres postes (comptabilité, secrétariat, scolarité…), `
    + `ouvrez cette adresse dans Chrome ou Edge :\n\n${liste}\n\n`
    + (ips.length > 1
        ? `Plusieurs interfaces réseau sont actives : essayez-les dans l'ordre, `
          + `la bonne est celle du réseau de l'établissement.\n\n`
        : '')
    + `À vérifier une fois pour toutes :\n`
    + `  • ce poste doit garder la MÊME adresse IP (réservation sur la box ou le routeur) ;\n`
    + `  • le pare-feu Windows doit autoriser le port ${DJANGO_PORT} en entrée.\n\n`
    + `Commande pare-feu, à lancer une seule fois dans une invite de commandes `
    + `ouverte en tant qu'administrateur :\n\n`
    + `    netsh advfirewall firewall add rule name="SAGI SCHOOL" `
    + `dir=in action=allow protocol=TCP localport=${DJANGO_PORT}`;
}

/** Fenêtre « où se connecter » — accessible à tout moment par le menu Réseau. */
function afficherAdresseServeur() {
  const actif = !!readAppConfig().lanServer;
  if (!actif) {
    dialog.showMessageBox(mainWindow, {
      type: 'info',
      title: 'Partage réseau',
      message: 'Ce poste ne partage pas sa base avec le réseau.',
      detail: 'Activez « Partager avec les autres postes » dans le menu Réseau, '
        + 'puis redémarrez SAGI SCHOOL.',
    });
    return;
  }
  dialog.showMessageBox(mainWindow, {
    type: 'info',
    title: 'Adresse du poste serveur',
    message: 'Ce poste partage sa base avec le réseau local.',
    detail: texteAdressesLan(),
  });
}

/**
 * Menu natif de l'application. Il porte le réglage du partage réseau, seul
 * endroit où l'on peut l'activer APRÈS l'installation : le réglage n'était
 * demandé qu'une fois, dans l'assistant, et une école déjà installée n'avait
 * plus aucun moyen de passer en multiposte sans réinstaller.
 */
function installerMenu() {
  const { Menu } = require('electron');
  const lanActif = !!readAppConfig().lanServer;

  const modele = [
    {
      label: 'Réseau',
      submenu: [
        {
          label: 'Partager avec les autres postes du réseau',
          type: 'checkbox',
          checked: lanActif,
          click: (item) => basculerPartageReseau(item.checked),
        },
        { type: 'separator' },
        {
          label: "Adresse du poste serveur…",
          click: () => afficherAdresseServeur(),
        },
      ],
    },
    {
      label: 'Aide',
      submenu: [
        {
          label: 'Journal d\'installation…',
          click: () => shell.showItemInFolder(getSetupLogPath()),
        },
        {
          label: 'À propos de SAGI SCHOOL',
          click: () => dialog.showMessageBox(mainWindow, {
            type: 'info',
            title: 'À propos',
            message: `SAGI SCHOOL ${app.getVersion()}`,
            detail: 'Système de gestion scolaire édité par HADY GESMAN.\n'
              + 'Comptabilité conforme au SYSCOHADA Révisé.\n\n'
              + 'Support : +221 70 328 61 51 · +221 78 429 78 30',
          }),
        },
      ],
    },
  ];

  Menu.setApplicationMenu(Menu.buildFromTemplate(modele));
}

/** Active ou coupe le partage réseau, puis propose le redémarrage. */
async function basculerPartageReseau(actif) {
  writeAppConfig({ lanServer: actif });
  installerMenu();   // reconstruit le menu pour refléter le nouvel état

  const detail = actif
    ? `Le partage sera effectif au prochain démarrage.\n\n${texteAdressesLan()}`
    : 'Ce poste redeviendra accessible depuis lui seul au prochain démarrage.';

  const { response } = await dialog.showMessageBox(mainWindow, {
    type: 'question',
    buttons: ['Redémarrer maintenant', 'Plus tard'],
    defaultId: 0,
    cancelId: 1,
    title: actif ? 'Partage réseau activé' : 'Partage réseau désactivé',
    message: actif
      ? 'Ce poste va partager sa base avec le réseau local.'
      : 'Le partage réseau est désactivé.',
    detail,
  });

  if (response === 0) {
    arreterServeurs();
    app.relaunch();
    app.exit(0);
  }
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
  demarrerSauvegardeCloud(backendDir);
}

// Sauvegarde cloud : pg_dump + envoi au serveur HADY GESMAN au démarrage
// puis toutes les 24 h. Non bloquant — hors ligne, le dump reste local et
// l'envoi repart à la prochaine exécution.
const SAUVEGARDE_INTERVALLE_MS = 24 * 60 * 60 * 1000;

function demarrerSauvegardeCloud(backendDir) {
  const lancer = () => {
    runManageCommand(backendDir, ['sauvegarde_cloud'], 'sauvegarde_cloud')
      .then(() => console.log('[Sauvegarde] OK'))
      .catch(e => console.warn('[Sauvegarde]', e.message));
  };
  lancer();
  setInterval(lancer, SAUVEGARDE_INTERVALLE_MS);
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
  const lanServer = !!payload.lan_server;

  // Mémoriser si ce poste doit être accessible depuis le réseau (lu à chaque
  // démarrage par startDjango). Persiste dans userData, indépendant de production.py.
  writeAppConfig({ lanServer });

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

  // Poste serveur : rappeler l'adresse que les autres postes devront ouvrir.
  // La même information reste accessible à tout moment par le menu Réseau.
  if (lanServer) {
    dialog.showMessageBox({
      type: 'info',
      title: 'Mode serveur réseau activé',
      message: 'Ce poste partage désormais sa base avec le réseau local.',
      detail: texteAdressesLan()
        + `\n\nCette adresse reste consultable à tout moment : menu Réseau, `
        + `« Adresse du poste serveur ».`,
    });
  }
}

/** Environnement d'exécution commun aux processus Django. */
function envDjango(backendDir) {
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
  return env;
}

/** Lance un processus Django sur un port et une interface donnés. */
function lancerProcessusDjango(backendDir, python, hote, port, etiquette) {
  const managePy = path.join(backendDir, 'manage.py');
  // waitress en production (WSGI stable) ; runserver en développement.
  const cmd = isDev
    ? [managePy, 'runserver', `${hote}:${port}`, '--noreload']
    : ['-m', 'waitress', `--host=${hote}`, `--port=${port}`, 'config.wsgi:application'];

  console.log(`[Django${etiquette}] ${python} ${cmd.join(' ')}`);
  const proc = spawn(python, cmd, { cwd: backendDir, env: envDjango(backendDir) });
  proc.stdout.on('data', d => console.log(`[Django${etiquette}]`, d.toString().trim()));
  proc.stderr.on('data', d => console.error(`[Django${etiquette}]`, d.toString().trim()));
  proc.on('close', code => console.log(`[Django${etiquette}] arrêté, code ${code}`));
  proc.on('error', err => console.error(`[Django${etiquette}] erreur :`, err.message));
  return proc;
}

/**
 * Démarre le serveur applicatif.
 *
 * Poste isolé : UN processus Django sur la boucle locale — comportement
 * historique, inchangé.
 *
 * Mode réseau : PLUSIEURS processus sur des ports internes, derrière un
 * répartiteur qui occupe seul le port public. Un serveur mono-processus
 * s'effondre dès qu'une dizaine de postes travaillent en même temps sur un
 * gros effectif, non pas à cause de la base mais du GIL de Python — voir
 * l'en-tête de lan-proxy.js pour les mesures.
 */
function startDjango() {
  const backendDir = getBackendDir();
  const python     = getPython();
  const lan        = !!readAppConfig().lanServer;

  http.get(`http://127.0.0.1:${DJANGO_PORT}/`, () => {
    console.log('[Electron] Serveur déjà actif');
  }).on('error', async () => {
    if (!lan) {
      djangoProcess = lancerProcessusDjango(
        backendDir, python, '127.0.0.1', DJANGO_PORT, '');
      return;
    }

    try {
      const { demarrerRepartiteur, portInterne, nombreDeProcessus, attendrePort } =
        require('./lan-proxy');
      const nb = nombreDeProcessus();

      djangoWorkers = [];
      for (let i = 0; i < nb; i++) {
        // Les processus de travail n'écoutent QUE la boucle locale : seul le
        // répartiteur est exposé au réseau de l'établissement.
        djangoWorkers.push(lancerProcessusDjango(
          backendDir, python, '127.0.0.1', portInterne(DJANGO_PORT, i), `-${i + 1}`));
      }
      djangoProcess = djangoWorkers[0];   // compatibilité avec l'arrêt existant

      const prets = await Promise.all(
        djangoWorkers.map((_, i) => attendrePort(portInterne(DJANGO_PORT, i))));
      const nbPrets = prets.filter(Boolean).length;
      if (nbPrets === 0) {
        throw new Error("aucun processus Django n'a démarré");
      }
      if (nbPrets < nb) {
        console.warn(`[Electron] ${nbPrets}/${nb} processus prêts — on continue`);
      }

      lanProxy = await demarrerRepartiteur({
        portPublic: DJANGO_PORT,
        hote: '0.0.0.0',
        nbProcessus: nb,
      });
    } catch (err) {
      console.error('[Electron] Mode réseau indisponible :', err.message);
      dialog.showErrorBox(
        'Partage réseau indisponible',
        `SAGI SCHOOL n'a pas pu démarrer en mode réseau :\n\n${err.message}\n\n`
        + `L'application va démarrer pour ce poste seulement. `
        + `Les autres postes ne pourront pas s'y connecter.`);
      arreterServeurs();
      djangoProcess = lancerProcessusDjango(
        backendDir, python, '127.0.0.1', DJANGO_PORT, '');
    }
  });
}

/** Arrête le répartiteur et tous les processus Django. */
function arreterServeurs() {
  if (lanProxy) { try { lanProxy.close(); } catch (_) {} lanProxy = null; }
  for (const p of djangoWorkers) { try { p.kill(); } catch (_) {} }
  djangoWorkers = [];
  if (djangoProcess) { try { djangoProcess.kill(); } catch (_) {} djangoProcess = null; }
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

  installerMenu();

  const url = isDev
    ? 'http://localhost:4200'
    : `http://127.0.0.1:${DJANGO_PORT}`;

  console.log('[Electron] Chargement:', url);
  mainWindow.loadURL(url);

  // mailto:/tel: (demande de renouvellement, contact support) → application
  // par défaut de l'OS au lieu d'une navigation dans la fenêtre
  mainWindow.webContents.on('will-navigate', (e, navUrl) => {
    if (navUrl.startsWith('mailto:') || navUrl.startsWith('tel:')) {
      e.preventDefault();
      shell.openExternal(navUrl);
    }
  });

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
  arreterServeurs();
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  arreterServeurs();
});
