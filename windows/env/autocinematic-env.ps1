# =====================================================================
#  EnderNation AutoCinematic - Sitzungs-Umgebung
#  Leitet Temp-, Cache- und Build-Verzeichnisse auf E:\AutoCinematic um.
#
#  Verwendung (in PowerShell, mit Punkt am Anfang = "dot-sourcing"):
#     . E:\AutoCinematic\env\autocinematic-env.ps1
#  oder einfach env\Start-AutoCinematicShell.cmd doppelklicken.
#
#  Wirkt NUR in der aktuellen Konsole und in Programmen, die daraus
#  gestartet werden. Es werden KEINE globalen Windows-Einstellungen,
#  keine Registry-Werte und keine Dateien veraendert oder geloescht.
# =====================================================================

$AcRoot = Split-Path -Parent $PSScriptRoot
if (-not $AcRoot) { $AcRoot = 'E:\AutoCinematic' }

$AcVars = [ordered]@{
    AUTOCINEMATIC_ROOT        = $AcRoot

    # --- Allgemeines Temp (Python tempfile, Node os.tmpdir(), Remotion, FFmpeg, Git ...)
    TEMP                      = "$AcRoot\tmp\system"
    TMP                       = "$AcRoot\tmp\system"

    # --- Java / Gradle / Fabric Loom / Maven
    GRADLE_USER_HOME          = "$AcRoot\cache\gradle"
    # java.io.tmpdir + JavaCPP-Cache (FFmpeg-Bibliotheken von Flashback/JavaCV, sonst %USERPROFILE%\.javacpp)
    JAVA_TOOL_OPTIONS         = "-Djava.io.tmpdir=$AcRoot\tmp\java -Dorg.bytedeco.javacpp.cachedir=$AcRoot\cache\javacpp"
    MAVEN_OPTS                = "-Dmaven.repo.local=$AcRoot\cache\maven\repository -Djava.io.tmpdir=$AcRoot\tmp\java"

    # --- Python / pip / uv
    PIP_CACHE_DIR             = "$AcRoot\cache\pip"
    PYTHONPYCACHEPREFIX       = "$AcRoot\cache\pycache"
    UV_CACHE_DIR              = "$AcRoot\cache\uv"
    UV_PYTHON_INSTALL_DIR     = "$AcRoot\runtime\python"
    UV_TOOL_DIR               = "$AcRoot\runtime\uv-tools"
    WORKON_HOME               = "$AcRoot\runtime\venvs"

    # --- Lokale KI-/Analysemodelle (Whisper, Beat-Detection, Torch, HuggingFace, Ollama)
    HF_HOME                   = "$AcRoot\cache\huggingface"
    TORCH_HOME                = "$AcRoot\cache\torch"
    XDG_CACHE_HOME            = "$AcRoot\cache\xdg"
    MPLCONFIGDIR              = "$AcRoot\cache\matplotlib"

    # --- Node / npm / Remotion
    npm_config_cache          = "$AcRoot\cache\npm"
    npm_config_prefix         = "$AcRoot\runtime\npm-global"
    npm_config_store_dir      = "$AcRoot\cache\pnpm-store"
    YARN_CACHE_FOLDER         = "$AcRoot\cache\yarn"
    PUPPETEER_CACHE_DIR       = "$AcRoot\cache\puppeteer"
    PLAYWRIGHT_BROWSERS_PATH  = "$AcRoot\cache\playwright"
}

# Verzeichnisse anlegen, falls sie fehlen (nur Erstellen, nie Loeschen)
$AcDirs = @(
    "$AcRoot\tmp\system", "$AcRoot\tmp\java", "$AcRoot\tmp\ffmpeg",
    "$AcRoot\cache\gradle", "$AcRoot\cache\maven\repository", "$AcRoot\cache\pip",
    "$AcRoot\cache\pycache", "$AcRoot\cache\uv", "$AcRoot\cache\huggingface",
    "$AcRoot\cache\torch", "$AcRoot\cache\xdg", "$AcRoot\cache\matplotlib",
    "$AcRoot\cache\ollama\models", "$AcRoot\cache\javacpp", "$AcRoot\cache\npm", "$AcRoot\cache\pnpm-store",
    "$AcRoot\cache\yarn", "$AcRoot\cache\puppeteer", "$AcRoot\cache\playwright",
    "$AcRoot\runtime\python", "$AcRoot\runtime\uv-tools", "$AcRoot\runtime\venvs",
    "$AcRoot\runtime\npm-global", "$AcRoot\runtime\bin"
)
foreach ($d in $AcDirs) {
    if (-not (Test-Path -LiteralPath $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}

foreach ($k in $AcVars.Keys) { Set-Item -Path "Env:$k" -Value $AcVars[$k] }

# Ollama: vorhandene Einstellung (z. B. E:\EnderCoder\models) NIE ueberschreiben
if (-not $env:OLLAMA_MODELS) { $env:OLLAMA_MODELS = "$AcRoot\cache\ollama\models" }

# Portable Werkzeuge auf E: bevorzugen (nur Ordner, die existieren)
$AcPath = @(
    "$AcRoot\runtime\bin",
    "$AcRoot\runtime\ffmpeg\bin",
    "$AcRoot\runtime\node",
    "$AcRoot\runtime\npm-global",
    "$AcRoot\runtime\jdk\bin"
) | Where-Object { Test-Path -LiteralPath $_ }
if ($AcPath) { $env:PATH = (($AcPath -join ';') + ';' + $env:PATH) }

if (Test-Path -LiteralPath "$AcRoot\runtime\jdk\bin\java.exe") {
    $env:JAVA_HOME = "$AcRoot\runtime\jdk"
}

Write-Host ''
Write-Host '  EnderNation AutoCinematic - Umgebung aktiv' -ForegroundColor Cyan
Write-Host "  Root : $AcRoot"
Write-Host "  TEMP : $env:TEMP"
Write-Host "  Gradle-Home : $env:GRADLE_USER_HOME"
if ($env:JAVA_HOME) { Write-Host "  JAVA_HOME : $env:JAVA_HOME" }
Write-Host '  (Gilt nur fuer diese Konsole und daraus gestartete Programme.)' -ForegroundColor DarkGray
Write-Host ''
