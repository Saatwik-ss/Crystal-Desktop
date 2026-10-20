@echo off
cd /d "%~dp0"
echo Starting Crystal website preview server on http://localhost:8088...
start "" "http://localhost:8088"
python -m http.server 8088 --directory docs
pause
