@echo off
rem Selbsttest (nur lesen + Testdateien unter E:\AutoCinematic). Optional: Test-AutoCinematic.cmd -Replay E:\pfad\replay.zip
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Test-AutoCinematic.ps1" %*
echo.
pause
