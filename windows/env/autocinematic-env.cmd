@echo off
rem =====================================================================
rem  EnderNation AutoCinematic - Sitzungs-Umgebung fuer cmd.exe
rem  Verwendung:  call E:\AutoCinematic\env\autocinematic-env.cmd
rem  Wirkt nur in diesem Konsolenfenster. Aendert nichts global.
rem =====================================================================

for %%I in ("%~dp0..") do set "AUTOCINEMATIC_ROOT=%%~fI"
set "AC=%AUTOCINEMATIC_ROOT%"

for %%D in (
  "tmp\system" "tmp\java" "tmp\ffmpeg"
  "cache\gradle" "cache\maven\repository" "cache\pip" "cache\pycache" "cache\uv"
  "cache\huggingface" "cache\torch" "cache\xdg" "cache\matplotlib" "cache\ollama\models" "cache\javacpp"
  "cache\npm" "cache\pnpm-store" "cache\yarn" "cache\puppeteer" "cache\playwright"
  "runtime\python" "runtime\uv-tools" "runtime\venvs" "runtime\npm-global" "runtime\bin"
) do if not exist "%AC%\%%~D" mkdir "%AC%\%%~D"

set "TEMP=%AC%\tmp\system"
set "TMP=%AC%\tmp\system"

set "GRADLE_USER_HOME=%AC%\cache\gradle"
set "JAVA_TOOL_OPTIONS=-Djava.io.tmpdir=%AC%\tmp\java -Dorg.bytedeco.javacpp.cachedir=%AC%\cache\javacpp"
set "MAVEN_OPTS=-Dmaven.repo.local=%AC%\cache\maven\repository -Djava.io.tmpdir=%AC%\tmp\java"

set "PIP_CACHE_DIR=%AC%\cache\pip"
set "PYTHONPYCACHEPREFIX=%AC%\cache\pycache"
set "UV_CACHE_DIR=%AC%\cache\uv"
set "UV_PYTHON_INSTALL_DIR=%AC%\runtime\python"
set "UV_TOOL_DIR=%AC%\runtime\uv-tools"
set "WORKON_HOME=%AC%\runtime\venvs"

set "HF_HOME=%AC%\cache\huggingface"
set "TORCH_HOME=%AC%\cache\torch"
set "XDG_CACHE_HOME=%AC%\cache\xdg"
set "MPLCONFIGDIR=%AC%\cache\matplotlib"
rem Ollama: vorhandene Einstellung nie ueberschreiben
if not defined OLLAMA_MODELS set "OLLAMA_MODELS=%AC%\cache\ollama\models"

set "npm_config_cache=%AC%\cache\npm"
set "npm_config_prefix=%AC%\runtime\npm-global"
set "npm_config_store_dir=%AC%\cache\pnpm-store"
set "YARN_CACHE_FOLDER=%AC%\cache\yarn"
set "PUPPETEER_CACHE_DIR=%AC%\cache\puppeteer"
set "PLAYWRIGHT_BROWSERS_PATH=%AC%\cache\playwright"

if exist "%AC%\runtime\jdk\bin\java.exe" (
  set "JAVA_HOME=%AC%\runtime\jdk"
  set "PATH=%AC%\runtime\jdk\bin;%PATH%"
)
if exist "%AC%\runtime\ffmpeg\bin" set "PATH=%AC%\runtime\ffmpeg\bin;%PATH%"
if exist "%AC%\runtime\node" set "PATH=%AC%\runtime\node;%PATH%"
set "PATH=%AC%\runtime\bin;%AC%\runtime\npm-global;%PATH%"

set "AC="
echo.
echo   EnderNation AutoCinematic - Umgebung aktiv
echo   Root : %AUTOCINEMATIC_ROOT%
echo   TEMP : %TEMP%
echo.
