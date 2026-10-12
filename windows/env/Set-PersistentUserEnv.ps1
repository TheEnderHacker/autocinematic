<#
=====================================================================
 EnderNation AutoCinematic - OPTIONAL: dauerhafte Benutzer-Variablen

 !!! Aendert Benutzer-Umgebungsvariablen (HKCU\Environment).
 !!! Nur nach Ruecksprache ausfuehren. Standard ist ein Trockenlauf.

 Zweck: Programme, die NICHT aus der AutoCinematic-Konsole gestartet
 werden (z. B. Ollama-Tray, IntelliJ, VS Code, Gradle aus der IDE),
 sollen ihre Caches ebenfalls auf E: ablegen.

 Aufrufe:
   Trockenlauf (zeigt nur an, aendert nichts):
     powershell -ExecutionPolicy Bypass -File Set-PersistentUserEnv.ps1
   Anwenden (sichert vorher die alten Werte nach logs\):
     powershell -ExecutionPolicy Bypass -File Set-PersistentUserEnv.ps1 -Apply
   Zusaetzlich TEMP/TMP des Benutzers auf E: legen (betrifft ALLE Programme):
     ... -Apply -IncludeTemp
   Rueckgaengig machen aus einer Sicherung:
     ... -Restore E:\AutoCinematic\logs\user-env-backup-YYYYMMDD-HHMMSS.json

 Keine Maschinen-Variablen, keine Admin-Rechte, nichts wird geloescht.
 Bestehende Caches auf C: (z. B. %USERPROFILE%\.gradle) bleiben liegen.
 OLLAMA_MODELS wird bewusst NICHT angefasst (bereits auf E:\EnderCoder\models).
=====================================================================
#>
param(
    [switch]$Apply,
    [switch]$IncludeTemp,
    [string]$Restore
)

$Root = Split-Path -Parent $PSScriptRoot
if (-not $Root) { $Root = 'E:\AutoCinematic' }
$LogDir = Join-Path $Root 'logs'
if (-not (Test-Path -LiteralPath $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

if ($Restore) {
    $data = Get-Content -LiteralPath $Restore -Raw | ConvertFrom-Json
    foreach ($p in $data.PSObject.Properties) {
        $val = $p.Value
        if ($null -eq $val -or $val -eq '') { $val = $null }
        [Environment]::SetEnvironmentVariable($p.Name, $val, 'User')
        Write-Host ("  wiederhergestellt: {0} = {1}" -f $p.Name, $(if ($val) { $val } else { '<entfernt>' }))
    }
    Write-Host 'Fertig. Neu gestartete Programme sehen die alten Werte.' -ForegroundColor Green
    return
}

$Vars = [ordered]@{
    AUTOCINEMATIC_ROOT       = $Root
    GRADLE_USER_HOME         = "$Root\cache\gradle"
    PIP_CACHE_DIR            = "$Root\cache\pip"
    UV_CACHE_DIR             = "$Root\cache\uv"
    UV_PYTHON_INSTALL_DIR    = "$Root\runtime\python"
    HF_HOME                  = "$Root\cache\huggingface"
    TORCH_HOME               = "$Root\cache\torch"
    npm_config_cache         = "$Root\cache\npm"
    PUPPETEER_CACHE_DIR      = "$Root\cache\puppeteer"
    PLAYWRIGHT_BROWSERS_PATH = "$Root\cache\playwright"
}
if ($IncludeTemp) {
    $Vars['TEMP'] = "$Root\tmp\system"
    $Vars['TMP']  = "$Root\tmp\system"
}

Write-Host ''
Write-Host ('{0,-26} {1,-45} -> {2}' -f 'Variable', 'aktuell (Benutzer)', 'neu') -ForegroundColor Cyan
$backup = [ordered]@{}
foreach ($k in $Vars.Keys) {
    $cur = [Environment]::GetEnvironmentVariable($k, 'User')
    $backup[$k] = $cur
    Write-Host ('{0,-26} {1,-45} -> {2}' -f $k, $(if ($cur) { $cur } else { '<nicht gesetzt>' }), $Vars[$k])
}

if (-not $Apply) {
    Write-Host ''
    Write-Host 'TROCKENLAUF - es wurde nichts geaendert. Zum Anwenden: -Apply' -ForegroundColor Yellow
    return
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$bfile = Join-Path $LogDir "user-env-backup-$stamp.json"
$backup | ConvertTo-Json | Set-Content -LiteralPath $bfile -Encoding UTF8
Write-Host "Sicherung der alten Werte: $bfile" -ForegroundColor DarkGray

foreach ($k in $Vars.Keys) {
    $dir = $Vars[$k]
    if ($dir -like "$Root*" -and -not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    [Environment]::SetEnvironmentVariable($k, $Vars[$k], 'User')
}
Write-Host 'Gesetzt. Wirkt fuer neu gestartete Programme (ggf. ab- und wieder anmelden).' -ForegroundColor Green
Write-Host "Rueckgaengig: -Restore `"$bfile`"" -ForegroundColor DarkGray
