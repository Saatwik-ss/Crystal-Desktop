@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "ROOT_DIR=%SCRIPT_DIR%.."

rem Look for python in virtualenv or PATH
if exist "%ROOT_DIR%\venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT_DIR%\venv\Scripts\python.exe"
) else if exist "%LOCALAPPDATA%\Programs\Crystal\venv\Scripts\python.exe" (
    set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Crystal\venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" "%ROOT_DIR%\backend\cli.py" %*
endlocal
