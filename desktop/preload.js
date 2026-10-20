const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  isDesktop: true,
  openFolderDialog: () => ipcRenderer.invoke('dialog:openFolder'),
  openExternal: (url) => ipcRenderer.invoke('shell:openExternal', url),
  restartBackend: () => ipcRenderer.invoke('backend:restart'),
  getBackendStatus: () => ipcRenderer.invoke('backend:status'),
  onOpenRepository: (callback) => {
    ipcRenderer.on('repo:open', (_event, path) => callback(path));
  },
  onBackendStatusChange: (callback) => {
    ipcRenderer.on('backend:statusChange', (_event, status) => callback(status));
  }
});
