<#
=====================================================================
 EnderNation AutoCinematic - Speicher-Pruefung (NUR LESEN)

 Misst, wie viel Platz Claude, Minecraft, Java/Gradle, Python, Node,
 KI-Modelle und Temp-Ordner auf C: belegen, und zeigt, wohin die
 Werkzeuge aktuell schreiben. Es wird NICHTS geloescht oder geaendert.

 Aufruf (Doppelklick auf tools\Check-DiskUsage.cmd) oder:
   powershell -ExecutionPolicy Bypass -File E:\AutoCinematic\tools\Check-DiskUsage.ps1

 Ergebnis: E:\AutoCinematic\logs\disk-report-<Zeitstempel>.txt  (+ .csv)
 Dauer: je nach Dateianzahl 1-10 Minuten.
=====================================================================
#>
$ErrorActionPreference = 'SilentlyContinue'
$Root = Split-Path -Parent $PSScriptRoot
if (-not $Root) { $Root = 'E:\AutoCinematic' }
$LogDir = Join-Path $Root 'logs'
if (-not (Test-Path -LiteralPath $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$stamp  = Get-Date -Format 'yyyyMMdd-HHmmss'
$txt    = Join-Path $LogDir "disk-report-$stamp.txt"
$csv    = Join-Path $LogDir "disk-report-$stamp.csv"

$U  = $env:USERPROFILE
$AD = $env:APPDATA
$LA = $env:LOCALAPPDATA

function Get-DirSize([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $item = Get-Item -LiteralPath $Path -Force
    if (-not $item) { return $null }
    if (-not $item.PSIsContainer) { return [long]$item.Length }
    $total = [long]0
    $stack = New-Object 'System.Collections.Generic.Stack[System.IO.DirectoryInfo]'
    $stack.Push([System.IO.DirectoryInfo]::new($Path))
    while ($stack.Count -gt 0) {
        $d = $stack.Pop()
        try { foreach ($f in $d.EnumerateFiles()) { $total += $f.Length } } catch {}
        try {
            foreach ($s in $d.EnumerateDirectories()) {
                # Junctions/Symlinks nicht verfolgen (keine Doppelzaehlung, keine Schleifen)
                if (-not ($s.Attributes -band [IO.FileAttributes]::ReparsePoint)) { $stack.Push($s) }
            }
        } catch {}
    }
    return $total
}

function Fmt([object]$b) {
    if ($null -eq $b) { return '-' }
    if ($b -ge 1GB) { return '{0:N2} GB' -f ($b / 1GB) }
    if ($b -ge 1MB) { return '{0:N0} MB' -f ($b / 1MB) }
    return '{0:N0} KB' -f ($b / 1KB)
}

# Kategorie | Pfad (Wildcards erlaubt) | Hinweis | Aufschluesseln (Unterordner einzeln)
$Targets = @(
    ,@('Windows-Temp',  "$env:TEMP",                         'Benutzer-TEMP (aktueller Wert)', $false)
    ,@('Windows-Temp',  "$LA\Temp",                          'Standard-Benutzer-Temp', $false)
    ,@('Windows-Temp',  "C:\Windows\Temp",                   'System-Temp (evtl. kein Zugriff)', $false)

    ,@('Claude',        "$AD\Claude",                        'Claude Desktop-App (inkl. Arbeits-VM)', $true)
    ,@('Claude',        "$LA\AnthropicClaude",               'Claude Desktop-Installation', $true)
    ,@('Claude',        "$LA\Packages\Claude_*",             'Claude (MSIX/Store-Variante)', $true)
    ,@('Claude',        "$LA\Packages\AnthropicPBC*",        'Claude (MSIX/Store-Variante)', $true)
    ,@('Claude',        "$U\.claude",                        'Claude Code: Einstellungen, Verlaeufe', $true)
    ,@('Claude',        "$U\.claude.json",                   'Claude Code: Konfigurationsdatei', $false)
    ,@('Claude',        "$LA\claude-cli-nodejs",             'Claude Code: Cache/Logs', $true)

    ,@('Minecraft',     "$AD\.minecraft",                    'Offizieller Launcher: Spiel, Assets, Java-Runtime', $true)
    ,@('Minecraft',     "$LA\Packages\Microsoft.4297127D64EC6_*", 'Minecraft Launcher (Store)', $false)
    ,@('Minecraft',     "$AD\PrismLauncher",                 'Prism Launcher (nicht portabel)', $true)
    ,@('Minecraft',     "$AD\ModrinthApp",                   'Modrinth App', $true)
    ,@('Minecraft',     "$U\curseforge",                     'CurseForge', $true)
    ,@('Minecraft',     "$U\.universal-modder",              'Universal Modder', $false)

    ,@('Java/Gradle',   "$U\.gradle",                        'Gradle-Cache inkl. Fabric Loom', $true)
    ,@('Java/Gradle',   "$U\.m2",                            'Maven-Repository', $false)
    ,@('Java/Gradle',   "$U\.jdks",                          'JDKs (IntelliJ-Downloads)', $true)
    ,@('Java/Gradle',   "$U\.javacpp",                       'JavaCPP Native-Cache (z. B. FFmpeg/OpenCV)', $true)
    ,@('Java/Gradle',   "C:\Program Files\Java",             'Installierte JDKs', $true)
    ,@('Java/Gradle',   "C:\Program Files\Eclipse Adoptium",  'Installierte JDKs (Temurin)', $true)
    ,@('Java/Gradle',   "C:\Program Files\Microsoft\jdk-*",  'Installierte JDKs (Microsoft)', $false)

    ,@('Python',        "$LA\pip\Cache",                     'pip-Cache', $false)
    ,@('Python',        "$LA\Programs\Python",               'Python-Installationen', $true)
    ,@('Python',        "$LA\uv",                            'uv Cache/Pythons', $true)
    ,@('Python',        "$AD\uv",                            'uv Pythons/Tools', $true)
    ,@('Python',        "$U\.cache",                         'HuggingFace, Whisper, Torch u. a.', $true)

    ,@('Node/Remotion', "$LA\npm-cache",                     'npm-Cache', $false)
    ,@('Node/Remotion', "$AD\npm",                           'globale npm-Pakete', $false)
    ,@('Node/Remotion', "$LA\ms-playwright",                 'Playwright-Browser', $true)
    ,@('Node/Remotion', "$LA\pnpm",                          'pnpm', $false)
    ,@('Node/Remotion', "$LA\Yarn",                          'Yarn', $false)

    ,@('KI-Modelle',    "$U\.ollama",                        'Ollama-Modelle', $true)
    ,@('KI-Modelle',    "$U\.codex",                         'Codex CLI', $false)
    ,@('KI-Modelle',    "$U\.copilot",                       'Copilot CLI', $false)

    ,@('Video',         "$U\Videos",                         'Videos (OBS-Standardziel)', $true)
    ,@('Video',         "$AD\obs-studio",                    'OBS-Einstellungen/Logs', $false)

    ,@('Sonstiges',     "$U\Downloads",                      'Downloads', $false)
    ,@('Sonstiges',     "$U\.vscode",                        'VS Code Erweiterungen', $false)
    ,@('Sonstiges',     "$AD\Code",                          'VS Code Cache/Daten', $false)
    ,@('Sonstiges',     "$U\.dotnet",                        '.NET', $false)
    ,@('Sonstiges',     "$U\.sonar",                         'Sonar', $false)
    ,@('Sonstiges',     "$U\.sonarlint",                     'SonarLint', $false)
    ,@('Sonstiges',     "$U\cbmrserver-main",                'cbmrserver-main', $false)
    ,@('Sonstiges',     "C:\hiberfil.sys",                   'Ruhezustandsdatei', $false)
    ,@('Sonstiges',     "C:\pagefile.sys",                   'Auslagerungsdatei', $false)
)

$out = New-Object System.Collections.Generic.List[string]
$rows = New-Object System.Collections.Generic.List[object]
function Say([string]$s) { Write-Host $s; $out.Add($s) }

Say "EnderNation AutoCinematic - Speicherbericht  $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
Say "Rechner: $env:COMPUTERNAME   Benutzer: $env:USERNAME"
Say ''
Say '== Laufwerke =='
Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | ForEach-Object {
    Say ('  {0}  frei {1,10} von {2,10}' -f $_.DeviceID, (Fmt $_.FreeSpace), (Fmt $_.Size))
}
Say ''

Say '== Werkzeuge im PATH =='
foreach ($c in 'java','javac','gradle','python','py','pip','uv','node','npm','npx','pnpm','ffmpeg','ffprobe','git','gh','claude','ollama','obs64') {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue | Select-Object -First 1
    Say ('  {0,-8} {1}' -f $c, $(if ($cmd) { $cmd.Source } else { '-' }))
}
Say ''

Say '== Relevante Umgebungsvariablen (Prozess | Benutzer | System) =='
foreach ($v in 'TEMP','TMP','JAVA_HOME','JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','GRADLE_USER_HOME','PIP_CACHE_DIR','UV_CACHE_DIR','HF_HOME','TORCH_HOME','XDG_CACHE_HOME','OLLAMA_MODELS','npm_config_cache','npm_config_prefix','PLAYWRIGHT_BROWSERS_PATH','CLAUDE_CONFIG_DIR') {
    $p = [Environment]::GetEnvironmentVariable($v, 'Process')
    $u = [Environment]::GetEnvironmentVariable($v, 'User')
    $m = [Environment]::GetEnvironmentVariable($v, 'Machine')
    Say ('  {0,-26} {1} | {2} | {3}' -f $v, $(if($p){$p}else{'-'}), $(if($u){$u}else{'-'}), $(if($m){$m}else{'-'}))
}
Say ''

Say '== Belegung bekannter Speicherorte =='
$cat = ''
$seen = New-Object 'System.Collections.Generic.HashSet[string]'
foreach ($t in $Targets) {
    $paths = @(Resolve-Path -Path $t[1] -ErrorAction SilentlyContinue | ForEach-Object { $_.ProviderPath } |
               Where-Object { $seen.Add($_.TrimEnd('\','/').ToLowerInvariant()) })
    if (-not $paths) { continue }
    if ($t[0] -ne $cat) { $cat = $t[0]; Say ''; Say "[$cat]" }
    foreach ($p in $paths) {
        Write-Host "  ... messe $p" -ForegroundColor DarkGray
        $size = Get-DirSize $p
        Say ('  {0,12}  {1}   ({2})' -f (Fmt $size), $p, $t[2])
        $rows.Add([pscustomobject]@{ Kategorie = $t[0]; Pfad = $p; Bytes = $size; Hinweis = $t[2] })
        if ($t[3] -and (Test-Path -LiteralPath $p -PathType Container)) {
            $subs = Get-ChildItem -LiteralPath $p -Force -Directory | ForEach-Object {
                [pscustomobject]@{ P = $_.FullName; S = (Get-DirSize $_.FullName) }
            } | Sort-Object S -Descending | Select-Object -First 8
            foreach ($s in $subs) {
                if ($s.S -ge 50MB) {
                    Say ('  {0,12}    - {1}' -f (Fmt $s.S), $s.P)
                    $rows.Add([pscustomobject]@{ Kategorie = "$($t[0]) (Unterordner)"; Pfad = $s.P; Bytes = $s.S; Hinweis = '' })
                }
            }
        }
    }
}

Say ''
Say '== Groesste Posten auf C: =='
$rows | Where-Object { $_.Pfad -like 'C:*' -and $_.Kategorie -notlike '*(Unterordner)' -and $_.Bytes } |
    Sort-Object Bytes -Descending | Select-Object -First 15 | ForEach-Object {
        Say ('  {0,12}  {1}' -f (Fmt $_.Bytes), $_.Pfad)
    }

$out | Set-Content -LiteralPath $txt -Encoding UTF8
$rows | Export-Csv -LiteralPath $csv -NoTypeInformation -Encoding UTF8 -Delimiter ';'
Write-Host ''
Write-Host "Bericht gespeichert: $txt" -ForegroundColor Green
Write-Host "CSV:                 $csv" -ForegroundColor Green
