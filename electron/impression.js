// Impression directe des documents (reçus, tickets…) sur les imprimantes du poste.
//
// Le navigateur ne peut ni lister les imprimantes ni imprimer sans fenêtre :
// seul Electron le peut. Angular envoie le PDF, on l'écrit dans un fichier
// temporaire et on le confie à l'imprimante :
//   - Windows : SumatraPDF (embarqué par pdf-to-printer). L'impression PDF
//     intégrée à Electron sort des pages blanches.
//   - Linux   : `lp` (CUPS).
// Les imprimantes choisies (documents A4, tickets) sont propres au POSTE : elles
// sont rangées dans le dossier utilisateur d'Electron, pas en base.
const { app, ipcMain } = require('electron');
const { execFile }     = require('child_process');
const path             = require('path');
const fs               = require('fs');
const os               = require('os');

const FICHIER_REGLAGES = () => path.join(app.getPath('userData'), 'impression.json');

function lireReglages() {
  try {
    return JSON.parse(fs.readFileSync(FICHIER_REGLAGES(), 'utf8'));
  } catch {
    return { document: '', ticket: '' };
  }
}

function enregistrerReglages(r) {
  const propre = { document: String(r?.document || ''), ticket: String(r?.ticket || '') };
  fs.writeFileSync(FICHIER_REGLAGES(), JSON.stringify(propre, null, 2));
  return propre;
}

// SumatraPDF ne peut pas s'exécuter depuis l'archive asar : l'installateur
// Windows le copie à part (build.win.extraResources → resources/impression/).
function cheminSumatra() {
  if (app.isPackaged) return path.join(process.resourcesPath, 'impression', 'SumatraPDF.exe');
  return path.join(path.dirname(require.resolve('pdf-to-printer')), 'SumatraPDF-3.4.6-32.exe');
}

function imprimerFichier(fichier, { imprimante, copies, ticket }) {
  if (process.platform === 'win32') {
    const { print } = require('pdf-to-printer');
    return print(fichier, {
      printer: imprimante || undefined,           // vide → imprimante par défaut de Windows
      copies:  copies > 1 ? copies : undefined,
      // Ticket : la page fait déjà la largeur du rouleau, ne pas la toucher.
      // Document : réduit seulement s'il dépasse le papier (un reçu A5 sur
      // une imprimante A4 reste en A5, il n'est pas agrandi).
      scale:   ticket ? 'noscale' : 'shrink',
      sumatraPdfPath: cheminSumatra(),
    });
  }
  const args = [];
  if (imprimante) args.push('-d', imprimante);
  if (copies > 1) args.push('-n', String(copies));
  args.push(fichier);
  return new Promise((resolve, reject) =>
    execFile('lp', args, (err, _out, stderr) => err ? reject(new Error(stderr || err.message)) : resolve()));
}

function installerImpression(getFenetre) {
  ipcMain.handle('imprimantes-lister', async () => {
    const win = getFenetre();
    const liste = win ? await win.webContents.getPrintersAsync() : [];
    return liste.map(p => ({ nom: p.name, libelle: p.displayName || p.name, parDefaut: !!p.isDefault }));
  });

  ipcMain.handle('imprimantes-reglages', () => lireReglages());
  ipcMain.handle('imprimantes-enregistrer', (_e, r) => enregistrerReglages(r));

  // donnees : ArrayBuffer du PDF ; options : { type: 'document'|'ticket', imprimante?, copies? }
  ipcMain.handle('imprimer-pdf', async (_e, donnees, options = {}) => {
    const ticket     = options.type === 'ticket';
    const reglages   = lireReglages();
    const imprimante = options.imprimante || (ticket ? reglages.ticket : reglages.document) || '';
    const fichier    = path.join(os.tmpdir(), `sagi_impression_${Date.now()}.pdf`);
    fs.writeFileSync(fichier, Buffer.from(donnees));
    try {
      await imprimerFichier(fichier, { imprimante, copies: Number(options.copies) || 1, ticket });
      return { ok: true, imprimante: imprimante || 'imprimante par défaut' };
    } catch (e) {
      return { ok: false, erreur: String(e?.message || e) };
    } finally {
      // SumatraPDF/lp ont fini de lire (Sumatra rend la main après le spool ;
      // lp copie le fichier dans la file CUPS) : on peut le supprimer.
      setTimeout(() => fs.rm(fichier, { force: true }, () => {}), 30000);
    }
  });
}

module.exports = { installerImpression };
