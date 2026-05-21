/**
 * SAGI SCHOOL — Vérification de licence
 * - Vérifie auprès du serveur Django local (après son démarrage)
 * - Fallback offline 30 jours
 * - Première installation : période d'essai automatique de 30 jours
 */
const fs   = require('fs');
const path = require('path');
const os   = require('os');
const http = require('http');

const LICENCE_FILE    = path.join(os.homedir(), '.sagischool_licence');
const TOLERANCE_JOURS = 30;
const ESSAI_JOURS     = 30;
const API_BASE        = 'http://127.0.0.1:8765/api';

function lireLicenceLocale() {
  try {
    if (!fs.existsSync(LICENCE_FILE)) return null;
    return JSON.parse(fs.readFileSync(LICENCE_FILE, 'utf8'));
  } catch { return null; }
}

function sauvegarderLicenceLocale(data) {
  try {
    fs.writeFileSync(LICENCE_FILE, JSON.stringify({
      ...data,
      derniere_verification: new Date().toISOString(),
    }));
  } catch (e) { console.error('[Licence] Erreur sauvegarde:', e.message); }
}

function joursDepuis(isoDate) {
  if (!isoDate) return 9999;
  return Math.floor((Date.now() - new Date(isoDate).getTime()) / 86400000);
}

/** POST JSON vers l'API Django locale */
function postJson(path, body) {
  return new Promise((resolve, reject) => {
    const payload = JSON.stringify(body);
    const req = http.request({
      hostname: '127.0.0.1',
      port:     8765,
      path:     path,
      method:   'POST',
      headers:  { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) },
    }, res => {
      let data = '';
      res.on('data', d => data += d);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); }
        catch { reject(new Error('Réponse non-JSON')); }
      });
    });
    req.on('error', reject);
    req.setTimeout(5000, () => { req.destroy(); reject(new Error('Timeout')); });
    req.write(payload);
    req.end();
  });
}

async function verifierEnLigne(cle) {
  if (!cle) return null;
  try {
    const res = await postJson('/api/licences/verifier/', { cle_licence: cle });
    return res;
  } catch (e) {
    console.warn('[Licence] Vérif en ligne échouée:', e.message);
    return null;
  }
}

async function verifierLicence(cleLicence) {
  const locale = lireLicenceLocale();
  const jours  = joursDepuis(locale?.derniere_verification);

  console.log('[Licence] Fichier local:', locale ? `ok (${jours}j)` : 'absent');

  // ── 1. Vérification en ligne (POST correct) ──────────────────
  const cle = cleLicence || locale?.cle_licence;
  const enligne = await verifierEnLigne(cle);

  if (enligne?.valide) {
    console.log('[Licence] ✅ En ligne — valide');
    sauvegarderLicenceLocale({ valide: true, cle_licence: cle, ...enligne });
    return { valide: true, mode: 'online', message: 'Licence active' };
  }

  // ── 2. Fallback offline (cache local < 30 j) ─────────────────
  if (locale?.valide && jours <= TOLERANCE_JOURS) {
    const restant = TOLERANCE_JOURS - jours;
    console.log(`[Licence] ✅ Offline — ${restant} jour(s) restant(s)`);
    return {
      valide:  true,
      mode:    'offline',
      message: `Mode hors-ligne — ${restant} jour(s) avant reconnexion requise`,
    };
  }

  // ── 3. Première installation : période d'essai automatique ───
  if (!locale) {
    console.log('[Licence] 🆕 Première installation — démarrage essai 30 jours');
    sauvegarderLicenceLocale({
      valide:   true,
      mode:     'essai',
      essai:    true,
      debut_essai: new Date().toISOString(),
    });
    return {
      valide:  true,
      mode:    'essai',
      message: `Période d'essai — ${ESSAI_JOURS} jours. Configurez votre licence dans les paramètres.`,
    };
  }

  // ── 4. Essai expiré ───────────────────────────────────────────
  if (locale?.essai) {
    const joursEssai = joursDepuis(locale.debut_essai);
    if (joursEssai <= ESSAI_JOURS) {
      const restant = ESSAI_JOURS - joursEssai;
      return { valide: true, mode: 'essai', message: `Essai — ${restant} jour(s) restant(s)` };
    }
    return {
      valide:  false,
      mode:    'essai_expire',
      message: `Période d'essai expirée (${joursEssai} jours). Contactez HADY GESMAN pour une licence.`,
    };
  }

  // ── 5. Tolérance offline dépassée ────────────────────────────
  if (locale?.valide && jours > TOLERANCE_JOURS) {
    return {
      valide:  false,
      mode:    'offline_expire',
      message: `Reconnexion requise — ${jours} jours sans vérification (max ${TOLERANCE_JOURS}).`,
    };
  }

  return { valide: false, mode: 'invalid', message: 'Licence invalide. Contactez HADY GESMAN.' };
}

module.exports = { verifierLicence, lireLicenceLocale, sauvegarderLicenceLocale };
