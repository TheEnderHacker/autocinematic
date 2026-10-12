@echo off
rem Richtet uv, FFmpeg, Prism Launcher portable, die Minecraft-Instanz und die Python-Umgebung auf E: ein.
rem Erst pruefen ohne Download:  Install-AutoCinematicTools.cmd -DryRun
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-AutoCinematicTools.ps1" %*
echo.
pause
