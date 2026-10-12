@echo off
rem Misst die groessten Ordner auf C: (nur lesen). Bericht in E:\AutoCinematic\logs.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Check-CDriveTop.ps1"
echo.
pause
