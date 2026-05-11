const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('setupAPI', {
  submit: (creds) => ipcRenderer.send('setup-submit', creds),
});
