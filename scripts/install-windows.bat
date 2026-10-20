@echo off
title Crystal AI Assistant - Windows Installer
echo Starting Crystal AI Windows Installation...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-windows.ps1"
echo.
pause
