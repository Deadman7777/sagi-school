/**
 * SAGI SCHOOL — Vérification de licence avec tolérance offline 30 jours
 */
const fs   = require('fs');
const path = require('path');
const os   = require('os');

const LICENCE_FILE    = path.join(os.homedir(), '.sagischool_licence');
const TOLERANCE_JOURS = 30;
const API_URL         = 'http://127.0.0.1:8765/api/licences/verifier/';

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
      derniere_verification: new Date().toISOString()
    }));
  } catch (e) { console.error('[Licence] Erreur sauvegarde:', e.message); }
}

function joursDepuisVerification(licence) {
  if (!licence?.derniere_verification) return 999;
  const diff = Date.now() - new Date(licence.derniere_verification).getTime();
  return Math.floor(diff / (1000 * 60 * 60 * 24));
}

async function verifierEnLigne(cle) {
  try {
    const http = require('http');
    return await new Promise((resolve, reject) => {
      const req = http.get(`${API_URL}?cle=${cle}`, res => {
        let data = '';
        res.on('data', d => data += d);
        res.on('end', () => {
          try { resolve(JSON.parse(data)); }
          catch { reject(new Error('JSON invalide')); }
        });
      });
      req.on('error', reject);
      req.setTimeout(5000, () => { req.destroy(); reject(new Error('Timeout')); });
    });
  } catch (e) {
    console.warn('[Licence] Vérification en ligne échouée:', e.message);
    return null;
  }
}

async function verifierLicence(cleLicence) {
  const locale = lireLicenceLocale();
  const jours  = joursDepuisVerification(locale);

  console.log(`[Licence] Dernière vérif: ${jours} jour(s)`);

  // Licence locale valide et dans la tolérance → on accepte sans vérifier en ligne
  // (Django n'est pas encore démarré au moment du check de licence)
  if (locale?.valide && jours <= TOLERANCE_JOURS) {
    console.log(`[Licence] ✅ Licence valide (offline — ${jours}j / ${TOLERANCE_JOURS}j)`);
    // Vérification en ligne en arrière-plan (non bloquante)
    verifierEnLigne(cleLicence || locale?.cle_licence).then(enligne => {
      if (enligne?.valide) {
        sauvegarderLicenceLocale({ ...enligne, cle_licence: cleLicence || locale?.cle_licence });
        console.log('[Licence] ✅ Vérification en ligne OK (arrière-plan)');
      }
    }).catch(() => {});
    return {
      valide:  true,
      mode:    'offline',
      jours:   jours,
      message: `Mode hors-ligne — ${TOLERANCE_JOURS - jours} jour(s) restant(s)`
    };
  }

  // Tolérance dépassée → tenter en ligne
  const enligne = await verifierEnLigne(cleLicence || locale?.cle_licence);
  if (enligne?.valide) {
    console.log('[Licence] ✅ Licence valide (en ligne)');
    sauvegarderLicenceLocale({ ...enligne, cle_licence: cleLicence || locale?.cle_licence });
    return { valide: true, mode: 'online', message: 'Licence active' };
  }

  if (locale && jours > TOLERANCE_JOURS) {
    console.warn(`[Licence] ❌ Tolérance offline dépassée (${jours} jours)`);
    return {
      valide:  false,
      mode:    'expired_offline',
      message: `Connexion requise — ${jours} jours sans vérification (max ${TOLERANCE_JOURS})`
    };
  }

  console.warn('[Licence] ❌ Aucune licence valide');
  return { valide: false, mode: 'invalid', message: 'Licence invalide ou absente' };
}

module.exports = { verifierLicence, lireLicenceLocale, sauvegarderLicenceLocale };
