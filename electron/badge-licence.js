/**
 * Badge de fin de licence sur l'icône de l'application.
 *
 * Angular calcule le badge (apps/licences/alertes.py : « 3 » à trois jours de
 * l'échéance, « ! » le jour J et après) et l'envoie ici :
 *   - Windows : pastille superposée à l'icône de la barre des tâches
 *     (setOverlayIcon), dessinée par la page — Windows n'a pas de compteur ;
 *   - macOS / Linux (Unity, GNOME avec extension) : compteur natif ;
 *   - expirée : la barre des tâches clignote une fois pour attirer l'œil.
 */
const { app, ipcMain, nativeImage } = require('electron');

function installerBadgeLicence(getWindow) {
  ipcMain.on('licence-badge', (_e, { nombre, image, texte, prioritaire } = {}) => {
    const win = getWindow();
    try {
      // `nombre` : jours restants, 0 pour un simple signal, null pour effacer.
      if (process.platform !== 'win32') {
        app.setBadgeCount(nombre === null || nombre === undefined ? 0 : Math.max(nombre, 1));
      }
      if (win && process.platform === 'win32') {
        const icone = image ? nativeImage.createFromDataURL(image) : null;
        win.setOverlayIcon(icone && !icone.isEmpty() ? icone : null, texte || '');
      }
      if (win && prioritaire && !win.isFocused()) win.flashFrame(true);
    } catch (err) {
      console.warn('[Electron] Badge licence :', err.message);
    }
  });
}

module.exports = { installerBadgeLicence };
