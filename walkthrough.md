# Transfer of Windows Desktop Application to Downloads & Repository Cleanup

All Windows desktop application files, CLI tooling, harnesses, and installers have been transferred away from the GitHub/web repository to a standalone folder in `Downloads`. The GitHub repository has been restored and pushed to GitHub.

---

## 1. Standalone Desktop Location

The complete standalone desktop package is located at:
📁 **`C:\Users\saatw\Downloads\Crystal-Desktop`**

### Package Contents:
- **`desktop/`**:
  - `main.js`: Electron process supervisor, health monitoring, single-instance lock, and system tray.
  - `preload.js`: Context isolation bridge for native folder dialogs and workspace switching.
  - `package.json` & `electron-builder.yml`: Ready to build NSIS executable installer or portable archive.
  - `assets/icon.svg`: Application logo.
- **`bin/`**:
  - `crystal.cmd` & `crystal.ps1`: Windows Command Prompt and PowerShell CLI wrappers.
- **`scripts/`**:
  - `install-windows.ps1` & `install-windows.bat`: One-click Windows installer (sets up venv, registers `crystal` in PATH, creates Start Menu & Desktop shortcuts).
  - `build-windows.ps1`: Builds frontend and packages desktop installer.
- **`backend/`**:
  - Includes `cli.py` (`crystal chat`, `crystal index`, `crystal serve`, `crystal config`, etc.), FastAPI app, and all services.
- **`frontend/`**:
  - Includes precompiled production assets in `frontend/dist/`.

---

## 2. GitHub Web Repository Status

📁 **`c:\Users\saatw\Documents\GitHub\Crystal`**

- **Clean Web State**: Reverted back to the original web/server state without desktop-specific files.
- **Git Commits**:
  - `a8a7f92`: Reverted desktop harness commit (`f3270e1`), removing `desktop/`, `bin/`, `scripts/`, and restoring `README.md` and `backend/`.
  - `333788c`: Ignored `node_modules/` in `.gitignore`.
- **Remote Sync**: Pushed to `origin/main` (https://github.com/Saatwik-ss/Crystal.git). Working tree is completely clean.

---

## 3. How to Run & Install the Desktop App from Downloads

In PowerShell or CMD:
```powershell
# Navigate to the standalone desktop folder
cd "C:\Users\saatw\Downloads\Crystal-Desktop"

# Option A: Run the one-click installer
.\scripts\install-windows.bat

# Option B: Run CLI directly
python backend\cli.py status
python backend\cli.py .
```
