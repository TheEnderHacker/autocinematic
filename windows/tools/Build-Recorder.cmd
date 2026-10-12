@echo off
rem Baut das AutoCinematic-Recorder-Plugin (nur auf E:). Ergebnis: E:\AutoCinematic\build\AutoCinematicRecorder-*.jar
rem Protokoll: E:\AutoCinematic\logs\build-recorder.txt
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Build-Recorder.ps1" %*
echo.
pause
