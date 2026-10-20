const { app, BrowserWindow, Menu, Tray, dialog, ipcMain, shell } = require('electron');
const path = require('path');
const fs = require('fs');
const http = require('http');
const { spawn } = require('child_process');

let mainWindow = null;
let tray = null;
let backendProcess = null;
let isQuitting = false;

const BACKEND_PORT = 8000;
const BACKEND_HOST = '127.0.0.1';
const HEALTH_URL = `http://${BACKEND_HOST}:${BACKEND_PORT}/health`;

// Resolve project directories
const ROOT_DIR = path.resolve(__dirname, '..');
const BACKEND_DIR = path.join(ROOT_DIR, 'backend');
const DATA_DIR = process.env.APPDATA
  ? path.join(process.env.APPDATA, 'Crystal')
  : path.join(process.env.HOME || '', '.crystal');
const LOGS_DIR = path.join(DATA_DIR, 'logs');

// Ensure data and logs directories exist
fs.mkdirSync(LOGS_DIR, { recursive: true });
const backendLogStream = fs.createWriteStream(path.join(LOGS_DIR, 'backend.log'), { flags: 'a' });

// Set dedicated userData path for Electron to isolate Chromium caches and locks
const ELECTRON_USER_DATA = path.join(DATA_DIR, 'electron_user_data');
fs.mkdirSync(ELECTRON_USER_DATA, { recursive: true });
app.setPath('userData', ELECTRON_USER_DATA);

// Synchronous file logging for Electron process
const ELECTRON_LOG_PATH = path.join(LOGS_DIR, 'electron.log');
function elog(...args) {
  try {
    fs.appendFileSync(ELECTRON_LOG_PATH, `[${new Date().toISOString()}] ${args.join(' ')}\n`);
  } catch (_) {}
}
elog('=== Crystal Desktop Process Started === PID:', process.pid, 'isPackaged:', app.isPackaged, 'Argv:', JSON.stringify(process.argv));

process.on('uncaughtException', (err) => elog('UncaughtException:', err.stack || err));
process.on('unhandledRejection', (reason) => elog('UnhandledRejection:', reason));

// Single instance handling: focus existing instance and cleanly quit duplicate
try {
  const gotTheLock = app.requestSingleInstanceLock();
  elog('SingleInstance lock check result:', gotTheLock);
  if (!gotTheLock) {
    elog('SingleInstance: another instance is already running. Quitting duplicate.');
    app.quit();
  } else {
    app.on('second-instance', (_event, commandLine) => {
      if (mainWindow) {
        if (mainWindow.isMinimized()) mainWindow.restore();
        mainWindow.show();
        mainWindow.focus();

        const lastArg = commandLine[commandLine.length - 1];
        if (lastArg && fs.existsSync(lastArg) && fs.statSync(lastArg).isDirectory()) {
          mainWindow.webContents.send('repo:open', path.resolve(lastArg));
        }
      }
    });
  }
} catch (e) {
  elog('SingleInstance lock check error:', e);
}

function checkServerHealth() {
  return new Promise((resolve) => {
    const req = http.get(HEALTH_URL, { timeout: 1500 }, (res) => {
      resolve(res.statusCode === 200);
    });
    req.on('error', () => resolve(false));
    req.on('timeout', () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function waitForServer(maxAttempts = 30, intervalMs = 500) {
  for (let i = 0; i < maxAttempts; i++) {
    const healthy = await checkServerHealth();
    if (healthy) return true;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return false;
}

function resolveBackendDir() {
  const localAppData = process.env.LOCALAPPDATA || '';
  const candidates = [
    app.isPackaged ? path.join(process.resourcesPath, 'backend') : null,
    path.join(path.resolve(__dirname, '..'), 'backend'),
    path.join(localAppData, 'Programs', 'Crystal', 'backend'),
    path.join(localAppData, 'Programs', 'Crystal', 'app', 'resources', 'backend')
  ].filter(Boolean);

  for (const c of candidates) {
    if (fs.existsSync(c)) return c;
  }
  return path.join(ROOT_DIR, 'backend');
}

function resolvePythonExecutable() {
  const localAppData = process.env.LOCALAPPDATA || '';
  const userProfile = process.env.USERPROFILE || '';
  const candidates = [
    path.join(localAppData, 'Programs', 'Crystal', 'venv', 'Scripts', 'python.exe'),
    path.join(ROOT_DIR, 'venv', 'Scripts', 'python.exe'),
    path.join(userProfile, 'Downloads', 'Crystal-Desktop', 'venv', 'Scripts', 'python.exe'),
    path.join(ROOT_DIR, '.venv', 'Scripts', 'python.exe'),
    path.join(userProfile, '.venv', 'Scripts', 'python.exe')
  ];

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  return 'python';
}

async function startBackend() {
  const isRunning = await checkServerHealth();
  if (isRunning) {
    console.log('[Crystal Desktop] Backend server already running.');
    return;
  }

  const pythonExe = resolvePythonExecutable();
  const backendDir = resolveBackendDir();
  console.log(`[Crystal Desktop] Launching backend with: ${pythonExe} in ${backendDir}`);

  const env = {
    ...process.env,
    PYTHONUNBUFFERED: '1',
    CRYSTAL_DATA_DIR: DATA_DIR
  };

  backendProcess = spawn(
    pythonExe,
    ['-m', 'uvicorn', 'main:app', `--host=${BACKEND_HOST}`, `--port=${BACKEND_PORT}`],
    {
      cwd: backendDir,
      env: env,
      stdio: ['ignore', 'pipe', 'pipe']
    }
  );

  backendProcess.stdout.pipe(backendLogStream);
  backendProcess.stderr.pipe(backendLogStream);

  backendProcess.on('exit', (code) => {
    console.log(`[Crystal Desktop] Backend exited with code ${code}`);
    backendProcess = null;
  });

  const healthy = await waitForServer(120, 500);
  if (!healthy) {
    dialog.showErrorBox(
      'Crystal Backend Error',
      'Failed to start the Crystal backend server within 60 seconds. Check logs at:\n' +
        path.join(LOGS_DIR, 'backend.log')
    );
  }
}

function stopBackend() {
  if (backendProcess) {
    console.log('[Crystal Desktop] Stopping backend process...');
    try {
      if (process.platform === 'win32') {
        const { spawnSync } = require('child_process');
        spawnSync('taskkill', ['/pid', backendProcess.pid.toString(), '/f', '/t']);
      } else {
        backendProcess.kill('SIGTERM');
      }
    } catch (e) {
      console.error('Error stopping backend:', e);
    }
    backendProcess = null;
  }
}

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 960,
    minHeight: 600,
    show: true,
    backgroundColor: '#111827',
    title: 'Crystal AI Coding Assistant',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true
    }
  });

  const loadingHtml = `
  <!DOCTYPE html>
  <html>
    <head>
      <meta charset="utf-8" />
      <title>Crystal AI Coding Assistant</title>
      <style>
        body {
          margin: 0;
          background: #111827;
          color: #f3f4f6;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          height: 100vh;
          user-select: none;
        }
        .spinner {
          width: 48px;
          height: 48px;
          border: 4px solid #374151;
          border-top: 4px solid #6366f1;
          border-radius: 50%;
          animation: spin 1s linear infinite;
          margin-bottom: 24px;
        }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        h1 { margin: 0 0 8px 0; font-size: 26px; font-weight: 700; color: #818cf8; }
        p { margin: 0; color: #9ca3af; font-size: 14px; }
      </style>
    </head>
    <body>
      <div class="spinner"></div>
      <h1>Crystal AI</h1>
      <p id="msg">Starting local AI backend and workspace services...</p>
    </body>
  </html>
  `;
  mainWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(loadingHtml)}`);

  mainWindow.on('close', (event) => {
    if (!isQuitting) {
      // Clean quit
      isQuitting = true;
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  setupMenu();
  setupTray();
}

function setupMenu() {
  const template = [
    {
      label: 'File',
      submenu: [
        {
          label: 'Open Local Folder...',
          accelerator: 'CmdOrCtrl+O',
          click: async () => {
            const result = await dialog.showOpenDialog(mainWindow, {
              properties: ['openDirectory'],
              title: 'Select Repository Folder'
            });
            if (!result.canceled && result.filePaths.length > 0) {
              mainWindow.webContents.send('repo:open', result.filePaths[0]);
            }
          }
        },
        { type: 'separator' },
        {
          label: 'View Logs',
          click: () => shell.openPath(LOGS_DIR)
        },
        { type: 'separator' },
        {
          label: 'Exit',
          accelerator: 'CmdOrCtrl+Q',
          click: () => {
            isQuitting = true;
            app.quit();
          }
        }
      ]
    },
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' },
        { role: 'redo' },
        { type: 'separator' },
        { role: 'cut' },
        { role: 'copy' },
        { role: 'paste' },
        { role: 'selectAll' }
      ]
    },
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'forceReload' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' }
      ]
    },
    {
      label: 'Help',
      submenu: [
        {
          label: 'Documentation & GitHub',
          click: () => shell.openExternal('https://github.com/Saatwik-ss/Crystal')
        },
        {
          label: 'About Crystal',
          click: () => {
            dialog.showMessageBox(mainWindow, {
              type: 'info',
              title: 'About Crystal',
              message: 'Crystal AI Coding Assistant',
              detail: 'Full-stack AI pair programmer with deep repository intelligence.\nVersion 0.1.0'
            });
          }
        }
      ]
    }
  ];

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);
}

function setupTray() {
  // Graceful tray setup
  try {
    const iconPath = path.join(__dirname, 'assets', 'icon.png');
    if (fs.existsSync(iconPath)) {
      tray = new Tray(iconPath);
      const contextMenu = Menu.buildFromTemplate([
        {
          label: 'Open Crystal',
          click: () => {
            if (mainWindow) {
              mainWindow.show();
              mainWindow.focus();
            }
          }
        },
        {
          label: 'Restart Backend',
          click: async () => {
            stopBackend();
            await startBackend();
            if (mainWindow) mainWindow.reload();
          }
        },
        { type: 'separator' },
        {
          label: 'Quit',
          click: () => {
            isQuitting = true;
            app.quit();
          }
        }
      ]);
      tray.setToolTip('Crystal AI Assistant');
      tray.setContextMenu(contextMenu);
      tray.on('double-click', () => {
        if (mainWindow) {
          mainWindow.show();
          mainWindow.focus();
        }
      });
    }
  } catch (err) {
    console.log('Tray setup skipped:', err);
  }
}

// IPC Handlers
ipcMain.handle('dialog:openFolder', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory'],
    title: 'Open Repository Folder'
  });
  if (result.canceled || result.filePaths.length === 0) {
    return null;
  }
  return result.filePaths[0];
});

ipcMain.handle('shell:openExternal', async (_event, url) => {
  await shell.openExternal(url);
});

ipcMain.handle('backend:restart', async () => {
  stopBackend();
  await startBackend();
  return true;
});

ipcMain.handle('backend:status', async () => {
  const running = await checkServerHealth();
  return { running, port: BACKEND_PORT };
});

app.whenReady().then(async () => {
  elog('app.whenReady entered');
  createMainWindow();
  await startBackend();
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.loadURL(`http://${BACKEND_HOST}:${BACKEND_PORT}`);
    mainWindow.show();
    mainWindow.focus();

    const targetArg = process.argv.slice(1).find(arg => !arg.startsWith('-') && fs.existsSync(arg) && fs.statSync(arg).isDirectory());
    if (targetArg) {
      mainWindow.webContents.once('did-finish-load', () => {
        mainWindow.webContents.send('repo:open', path.resolve(targetArg));
      });
    }
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createMainWindow();
    }
  });
});

app.on('before-quit', () => {
  elog('before-quit event received');
  isQuitting = true;
  stopBackend();
});

app.on('window-all-closed', () => {
  elog('window-all-closed event received');
  if (process.platform !== 'darwin') {
    isQuitting = true;
    stopBackend();
    app.quit();
  }
});
