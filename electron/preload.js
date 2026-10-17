const { contextBridge, ipcRenderer } = require('electron');

// Expose des APIs sécurisées à Angular
contextBridge.exposeInMainWorld('electronAPI', {
  getVersion:    ()    => ipcRenderer.invoke('get-version'),
  activerLicence: (cle) => ipcRenderer.invoke('activer-licence', cle),
  // Impression directe (voir impression.js)
  listerImprimantes:      ()          => ipcRenderer.invoke('imprimantes-lister'),
  reglagesImpression:     ()          => ipcRenderer.invoke('imprimantes-reglages'),
  enregistrerImpression:  (r)         => ipcRenderer.invoke('imprimantes-enregistrer', r),
  imprimerPdf:            (pdf, opts) => ipcRenderer.invoke('imprimer-pdf', pdf, opts),
  // Badge de fin de licence sur l'icône (voir badge-licence.js)
  badgeLicence:           (b)         => ipcRenderer.send('licence-badge', b),
  isDesktop:     true
});
