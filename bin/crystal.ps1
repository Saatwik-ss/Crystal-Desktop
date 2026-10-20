<#
.SYNOPSIS
    Crystal AI Coding Assistant - PowerShell CLI Entry Point
.DESCRIPTION
    Launches the Crystal desktop harness, terminal chat agent, or server.
#>

param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

$RootDir = (Resolve-Path "$PSScriptRoot\..").Path

$PythonExe = "python"
if (Test-Path "$RootDir\venv\Scripts\python.exe") {
    $PythonExe = "$RootDir\venv\Scripts\python.exe"
} elseif (Test-Path "$env:LOCALAPPDATA\Programs\Crystal\venv\Scripts\python.exe") {
    $PythonExe = "$env:LOCALAPPDATA\Programs\Crystal\venv\Scripts\python.exe"
}

$CliPy = "$RootDir\backend\cli.py"
& $PythonExe $CliPy @Arguments
