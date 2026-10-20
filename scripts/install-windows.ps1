<#
.SYNOPSIS
    Crystal AI Coding Assistant - Automated Windows Installer
.DESCRIPTION
    Installs Crystal AI into %LOCALAPPDATA%\Programs\Crystal, sets up Python virtual environment,
    creates Desktop & Start Menu shortcuts, and registers 'crystal' into the user's PATH.
#>

[CmdletBinding()]
param(
    [switch]$SkipVenv,
    [string]$InstallDir = "$env:LOCALAPPDATA\Programs\Crystal"
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "     Crystal AI Coding Assistant - Windows Installer      " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check for Python
Write-Host "[1/6] Checking Python installation..." -ForegroundColor Yellow
$PythonCmd = Get-Command "python" -ErrorAction SilentlyContinue
if (-not $PythonCmd) {
    $PythonCmd = Get-Command "python3" -ErrorAction SilentlyContinue
}

if (-not $PythonCmd) {
    Write-Host "Python was not found on your system." -ForegroundColor Red
    Write-Host "Attempting to install Python 3.11 via winget..." -ForegroundColor Yellow
    $Winget = Get-Command "winget" -ErrorAction SilentlyContinue
    if ($Winget) {
        & winget install Python.Python.3.11 --silent --accept-package-agreements --accept-source-agreements
        $PythonCmd = Get-Command "python" -ErrorAction SilentlyContinue
    }
    
    if (-not $PythonCmd) {
        Write-Host "Please install Python 3.10+ from https://www.python.org/downloads/ and re-run this installer." -ForegroundColor Red
        exit 1
    }
}

$PyVer = & $PythonCmd.Source --version
Write-Host "      Detected: $PyVer" -ForegroundColor Green

# 2. Prepare Installation Directory
Write-Host "[2/6] Setting up installation directory at $InstallDir..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path "$InstallDir\bin" | Out-Null
New-Item -ItemType Directory -Force -Path "$InstallDir\backend" | Out-Null
New-Item -ItemType Directory -Force -Path "$InstallDir\frontend\dist" | Out-Null
New-Item -ItemType Directory -Force -Path "$InstallDir\desktop" | Out-Null

$RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path

# Copy backend files
Copy-Item -Path "$RepoRoot\backend\*" -Destination "$InstallDir\backend" -Recurse -Force -Exclude "__pycache__", ".pytest_cache"

# Copy frontend dist if exists, or build it
if (-not (Test-Path "$RepoRoot\frontend\dist\index.html")) {
    Write-Host "      Building frontend assets..." -ForegroundColor Yellow
    Push-Location "$RepoRoot\frontend"
    & npm run build
    Pop-Location
}
Copy-Item -Path "$RepoRoot\frontend\dist\*" -Destination "$InstallDir\frontend\dist" -Recurse -Force

# Copy desktop and bin files
Copy-Item -Path "$RepoRoot\bin\*" -Destination "$InstallDir\bin" -Recurse -Force
if (Test-Path "$RepoRoot\desktop") {
    Copy-Item -Path "$RepoRoot\desktop\*" -Destination "$InstallDir\desktop" -Recurse -Force -Exclude "node_modules", "dist-desktop"
}

# 3. Setup Python Virtual Environment
if (-not $SkipVenv) {
    Write-Host "[3/6] Configuring Python virtual environment..." -ForegroundColor Yellow
    $VenvPath = "$InstallDir\venv"
    if (-not (Test-Path "$VenvPath\Scripts\python.exe")) {
        & $PythonCmd.Source -m venv "$VenvPath"
    }

    $VenvPython = "$VenvPath\Scripts\python.exe"
    Write-Host "      Installing required Python packages..." -ForegroundColor Yellow
    & $VenvPython -m pip install --upgrade pip --quiet
    & $VenvPython -m pip install -r "$InstallDir\backend\requirements.txt" --quiet
} else {
    Write-Host "[3/6] Skipping Python virtual environment (-SkipVenv specified)." -ForegroundColor Gray
}

# 4. Register in User PATH
Write-Host "[4/6] Registering 'crystal' CLI in user PATH..." -ForegroundColor Yellow
$BinDir = "$InstallDir\bin"
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($UserPath -notlike "*$BinDir*") {
    $NewPath = if ($UserPath.EndsWith(";")) { "$UserPath$BinDir;" } else { "$UserPath;$BinDir;" }
    [Environment]::SetEnvironmentVariable("Path", $NewPath, "User")
    $env:Path = "$env:Path;$BinDir"
    Write-Host "      Added $BinDir to PATH." -ForegroundColor Green
} else {
    Write-Host "      $BinDir is already in PATH." -ForegroundColor Green
}

# 5. Create Desktop and Start Menu Shortcuts
Write-Host "[5/6] Creating Desktop & Start Menu shortcuts..." -ForegroundColor Yellow
$WshShell = New-Object -ComObject WScript.Shell

# Desktop shortcut
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$Shortcut = $WshShell.CreateShortcut("$DesktopPath\Crystal AI.lnk")
$Shortcut.TargetPath = "$InstallDir\bin\crystal.cmd"
$Shortcut.Arguments = "open ."
$Shortcut.WorkingDirectory = [Environment]::GetFolderPath("UserProfile")
$Shortcut.Description = "Crystal AI Coding Assistant"
$Shortcut.Save()

# Start Menu shortcut
$StartMenuPath = [Environment]::GetFolderPath("StartMenu") + "\Programs"
$StartShortcut = $WshShell.CreateShortcut("$StartMenuPath\Crystal AI.lnk")
$StartShortcut.TargetPath = "$InstallDir\bin\crystal.cmd"
$StartShortcut.Arguments = "open ."
$StartShortcut.WorkingDirectory = [Environment]::GetFolderPath("UserProfile")
$StartShortcut.Description = "Crystal AI Coding Assistant"
$StartShortcut.Save()

Write-Host "      Created Desktop and Start Menu shortcuts." -ForegroundColor Green

# 6. Verification
Write-Host "[6/6] Verifying Crystal CLI status..." -ForegroundColor Yellow
Write-Host ""
& "$InstallDir\bin\crystal.cmd" status

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "       Crystal AI installed successfully on Windows!      " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host ""
Write-Host "You can now use Crystal anywhere in PowerShell or CMD:" -ForegroundColor Cyan
Write-Host "  crystal .                       # Open current directory in Crystal" -ForegroundColor White
Write-Host "  crystal chat 'how does it work' # Ask questions in terminal" -ForegroundColor White
Write-Host "  crystal serve                   # Start backend server" -ForegroundColor White
Write-Host "  crystal config --set-gemini-key # Configure your API key" -ForegroundColor White
Write-Host "  crystal status                  # Check server and system status" -ForegroundColor White
Write-Host ""
