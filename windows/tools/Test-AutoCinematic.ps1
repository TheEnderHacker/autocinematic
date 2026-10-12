<#
=====================================================================
 EnderNation AutoCinematic - Selbsttest unter Windows

 Prueft, was auf diesem Rechner WIRKLICH funktioniert, und schreibt ein
 Protokoll nach E:\AutoCinematic\logs\selftest-<Zeitstempel>.txt.
 Aendert nichts ausserhalb von E:\AutoCinematic.

 Tests:
   1. Umgebung: TEMP, Gradle, pip, npm usw. zeigen auf E:
   2. Werkzeuge: java, python, node, git, uv, ffmpeg (Version + Pfad)
   3. FFmpeg: 3-Sekunden-Testvideo 1080x1920 (9:16) und 1920x1080 nach render\previews
   4. Python-Analysekern: pytest (alle Unit-Tests)
   5. Pipeline-Demo: demo -> plan -> inject -> camera (Flashback-Editorzustand)
   6. Optional: echtes Replay (-Replay <zip>) -> info + camera --orbit-markers in Testordner
   7. C:-Belegung vorher/nachher (darf nicht nennenswert wachsen)

 Aufruf: tools\Test-AutoCinematic.cmd   oder
   powershell -ExecutionPolicy Bypass -File Test-AutoCinematic.ps1 [-Replay E:\...\replay.zip]
=====================================================================
#>
param([string]$Replay)

$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot
if (-not $Root) { $Root = 'E:\AutoCinematic' }
. (Join-Path $Root 'env\autocinematic-env.ps1') | Out-Null

$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$Log = Join-Path $Root "logs\selftest-$Stamp.txt"
$Work = Join-Path $Root "tmp\system\selftest-$Stamp"
New-Item -ItemType Directory -Path $Work -Force | Out-Null
$Pass = 0; $Fail = 0; $Warn = 0
$CFreeBefore = (Get-PSDrive C).Free

function W([string]$s, [string]$c = 'Gray') { Write-Host $s -ForegroundColor $c; Add-Content -LiteralPath $Log -Value $s -Encoding UTF8 }
function Check([string]$name, [bool]$ok, [string]$detail = '', [switch]$WarnOnly) {
    if ($ok) { $script:Pass++; W ("[PASS] {0} {1}" -f $name, $detail) 'Green' }
    elseif ($WarnOnly) { $script:Warn++; W ("[WARN] {0} {1}" -f $name, $detail) 'Yellow' }
    else { $script:Fail++; W ("[FAIL] {0} {1}" -f $name, $detail) 'Red' }
}
function Run([string]$exe, [string[]]$argv) {
    try {
        $out = & $exe @argv 2>&1 | Out-String
        return @{ code = $LASTEXITCODE; out = "$out".Trim() }
    } catch {
        return @{ code = -1; out = "$($_.Exception.Message)" }
    }
}

W "AutoCinematic Selbsttest $Stamp auf $env:COMPUTERNAME"
W ("C: frei: {0:N2} GB   E: frei: {1:N2} GB" -f ($CFreeBefore / 1GB), ((Get-PSDrive E).Free / 1GB))
W ''
W '== 1. Umgebung =='
foreach ($v in 'TEMP','TMP','GRADLE_USER_HOME','PIP_CACHE_DIR','UV_CACHE_DIR','npm_config_cache','HF_HOME','XDG_CACHE_HOME','PYTHONPYCACHEPREFIX') {
    $val = [Environment]::GetEnvironmentVariable($v)
    Check "env $v" ($val -like "$Root*") "= $val"
}
Check 'env JAVA_TOOL_OPTIONS (tmpdir+javacpp)' ($env:JAVA_TOOL_OPTIONS -like "*java.io.tmpdir=$Root*" -and $env:JAVA_TOOL_OPTIONS -like '*javacpp.cachedir*') $env:JAVA_TOOL_OPTIONS
Check 'env OLLAMA_MODELS unveraendert' ($env:OLLAMA_MODELS -ne $null) "= $env:OLLAMA_MODELS" -WarnOnly

W ''
W '== 2. Werkzeuge =='
$tools = [ordered]@{ java = @('-version'); python = @('--version'); node = @('--version'); npm = @('--version'); git = @('--version'); uv = @('--version'); ffmpeg = @('-hide_banner', '-version') }
foreach ($t in $tools.Keys) {
    $cmd = Get-Command $t -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $cmd) { Check "tool $t" $false 'nicht gefunden' -WarnOnly:($t -in 'npm'); continue }
    $r = Run $cmd.Source $tools[$t]
    $first = ($r.out -split "`r?`n" | Where-Object { $_ -notmatch 'JAVA_TOOL_OPTIONS' -and $_ -notmatch '^\s*-D' -and $_.Trim() } | Select-Object -First 1)
    Check "tool $t" ($r.code -eq 0) "$first  [$($cmd.Source)]"
}
$ff = Get-Command ffmpeg -ErrorAction SilentlyContinue
if ($ff) { Check 'ffmpeg liegt auf E:' ($ff.Source -like "$Root*") $ff.Source -WarnOnly }

W ''
W '== 3. FFmpeg-Testrender =='
if ($ff) {
    foreach ($fmt in @(@{n='9x16'; s='1080x1920'}, @{n='16x9'; s='1920x1080'})) {
        $outFile = Join-Path $Root "render\previews\selftest-$($fmt.n)-$Stamp.mp4"
        $r = Run $ff.Source @('-hide_banner','-loglevel','error','-y','-f','lavfi','-i',"testsrc2=size=$($fmt.s):rate=60:duration=3",
                              '-f','lavfi','-i','sine=frequency=440:duration=3','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',$outFile)
        $ok = ($r.code -eq 0) -and (Test-Path -LiteralPath $outFile)
        # Pruefung mit ffmpeg selbst (ffprobe.exe wird auf diesem PC von der Windows-Anwendungssteuerung blockiert)
        $info = ''
        if ($ok) {
            $p = Run $ff.Source @('-hide_banner', '-i', $outFile)
            $m = [regex]::Match($p.out, 'Video: h264.*?, (\d{3,4})x(\d{3,4}).*?, (\d+) fps')
            $info = if ($m.Success) { "$($m.Groups[1].Value)x$($m.Groups[2].Value) $($m.Groups[3].Value)fps" } else { 'Stream-Info nicht lesbar' }
            $ok = $m.Success -and ("$($m.Groups[1].Value)x$($m.Groups[2].Value)" -eq $fmt.s) -and ($m.Groups[3].Value -eq '60')
        }
        Check "ffmpeg $($fmt.s) 60fps" $ok "$info -> $outFile"
    }
} else { Check 'ffmpeg-Testrender' $false 'ffmpeg fehlt (tools\Install-AutoCinematicTools.cmd ausfuehren)' }

W ''
W '== 4./5. Python-Analysekern =='
$py = Join-Path $Root 'runtime\venvs\autocinematic\Scripts\python.exe'
$ac = Join-Path $Root 'runtime\venvs\autocinematic\Scripts\autocinematic.exe'
$pkg = Join-Path $Root 'repos\autocinematic\python'
if (Test-Path -LiteralPath $py) {
    Push-Location $pkg
    $r = Run $py @('-m','pytest','-q','-p','no:cacheprovider')
    Pop-Location
    $last = ($r.out -split "`r?`n" | Select-Object -Last 1)
    Check 'pytest' ($r.code -eq 0) $last
    if ($r.code -ne 0) { W $r.out }

    $d = Join-Path $Work 'demo'
    $steps = @(
        @('demo','-o',$d),
        @('plan','--replay',"$d\demo-replay.zip",'--events',"$d\demo-events.jsonl",'--format','short','-o',"$d\plan.json"),
        @('inject',"$d\demo-replay.zip",'--events',"$d\demo-events.jsonl",'--plan',"$d\plan.json",'-o',"$d\marked.zip"),
        @('camera','--replay',"$d\marked.zip",'--plan',"$d\plan.json",'--flashback-dir',"$d\flashback",'--report',"$d\camera-report.json")
    )
    foreach ($s in $steps) {
        $r = Run $ac $s
        Check "autocinematic $($s[0])" ($r.code -eq 0) (($r.out -split "`r?`n" | Select-Object -First 1))
    }
} else { Check 'Python-Umgebung' $false "fehlt: $py (Installer ausfuehren)" }

if ($Replay) {
    W ''
    W '== 6. Echtes Replay =='
    if ((Test-Path -LiteralPath $Replay) -and (Test-Path -LiteralPath $ac)) {
        $r = Run $ac @('info', $Replay)
        Check 'replay info' ($r.code -eq 0) ''
        W $r.out
        $r = Run $ac @('camera','--replay',$Replay,'--orbit-markers','--flashback-dir',"$Work\real-flashback")
        Check 'camera --orbit-markers (Testordner, nicht die Instanz)' ($r.code -eq 0) $r.out -WarnOnly
    } else { Check 'Replay vorhanden' $false $Replay }
}

W ''
W '== 7. Speicher =='
$grown = ($CFreeBefore - (Get-PSDrive C).Free) / 1MB
Check 'C: waehrend des Tests kaum gewachsen (<200 MB)' ($grown -lt 200) ("{0:N0} MB" -f $grown) -WarnOnly
W ''
W ("Ergebnis: {0} bestanden, {1} Warnungen, {2} fehlgeschlagen" -f $Pass, $Warn, $Fail) $(if ($Fail) { 'Red' } else { 'Green' })
W "Protokoll: $Log"
