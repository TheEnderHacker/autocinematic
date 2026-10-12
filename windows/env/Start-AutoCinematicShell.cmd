@echo off
rem Oeffnet eine PowerShell mit aktiver AutoCinematic-Umgebung in E:\AutoCinematic.
rem -ExecutionPolicy Bypass gilt nur fuer diesen einen Prozess (keine globale Aenderung).
where pwsh >nul 2>nul
if %ERRORLEVEL%==0 (
  start "AutoCinematic" pwsh -NoExit -ExecutionPolicy Bypass -Command ". '%~dp0autocinematic-env.ps1'; Set-Location '%~dp0..'"
) else (
  start "AutoCinematic" powershell -NoExit -ExecutionPolicy Bypass -Command ". '%~dp0autocinematic-env.ps1'; Set-Location '%~dp0..'"
)
