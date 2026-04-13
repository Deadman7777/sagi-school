const { contextBridge, ipcRenderer } = require('electron');

// Expose des APIs sécurisées à Angular
contextBridge.exposeInMainWorld('electronAPI', {
  getVersion:    ()    => ipcRenderer.invoke('get-version'),
  activerLicence: (cle) => ipcRenderer.invoke('activer-licence', cle),
  isDesktop:     true
});
