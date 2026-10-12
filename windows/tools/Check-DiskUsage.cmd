@echo off
rem Startet die Speicher-Pruefung (nur lesen). Bericht landet in E:\AutoCinematic\logs.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Check-DiskUsage.ps1"
echo.
pause
