<#
=====================================================================
 EnderNation AutoCinematic - Recorder-Plugin bauen (nur E:)

 Quelle:    E:\AutoCinematic\repos\autocinematic\recorder
 Ergebnis:  E:\AutoCinematic\build\AutoCinematicRecorder-<Version>.jar
 Protokoll: E:\AutoCinematic\logs\build-recorder.txt

 Braucht ein JDK 17-24 (mit javac). Gefunden wird zuerst JAVA_HOME, sonst
 E:\AutoCinematic\runtime\jdk\temurin-21. Fehlt beides, wird Eclipse Temurin 21
 (ZIP, ca. 190 MB, SHA-256 geprueft) nach E:\AutoCinematic\runtime\jdk entpackt.
 Kein Installer, keine Registry, nichts auf C:. Gradle-Cache: cache\gradle.
=====================================================================
#>
param([switch]$NoJdkDownload)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}

$Root = Split-Path -Parent $PSScriptRoot
. (Join-Path $Root 'env\autocinematic-env.ps1') | Out-Null
$Src     = Join-Path $Root 'repos\autocinematic\recorder'
$Log     = Join-Path $Root 'logs\build-recorder.txt'
$OutDir  = Join-Path $Root 'build'
$JdkDir  = Join-Path $Root 'runtime\jdk\temurin-21'
$DlDir   = Join-Path $Root 'downloads'
foreach ($d in $OutDir, $DlDir, (Split-Path $Log), (Split-Path $JdkDir)) { if (-not (Test-Path -LiteralPath $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null } }
Set-Content -LiteralPath $Log -Value "Build $(Get-Date -Format s)" -Encoding UTF8

function Log([string]$msg, [string]$color = 'Gray') {
    Write-Host $msg -ForegroundColor $color
    Add-Content -LiteralPath $Log -Value $msg -Encoding UTF8
}

function Get-JdkMajor([string]$home_) {
    $javac = Join-Path $home_ 'bin\javac.exe'
    if (-not (Test-Path -LiteralPath $javac)) { return 0 }
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    try { $v = (& $javac -version 2>&1 | Out-String) } catch { $v = '' } finally { $ErrorActionPreference = $old }
    if ($v -match 'javac (\d+)') { return [int]$Matches[1] }
    return 0
}

try {
    if (-not (Test-Path -LiteralPath (Join-Path $Src 'gradlew.bat'))) { throw "Quellcode fehlt: $Src" }

    # ---------------------------------------------------------------- JDK waehlen
    $jdk = $null
    foreach ($cand in @($env:JAVA_HOME, $JdkDir)) {
        if (-not $cand) { continue }
        $m = Get-JdkMajor $cand
        if ($m -ge 17 -and $m -le 24) { $jdk = $cand; Log "JDK $m gefunden: $cand" 'Green'; break }
        elseif ($m -gt 0) { Log "JDK $m in $cand passt nicht (Gradle 8.14 braucht 17-24) - wird nicht benutzt" 'Yellow' }
    }
    if (-not $jdk) {
        if ($NoJdkDownload) { throw 'Kein passendes JDK gefunden (17-24)' }
        if (Test-Path -LiteralPath $JdkDir) { throw "$JdkDir existiert, enthaelt aber kein brauchbares JDK - bitte pruefen, es wird nichts geloescht" }
        Log 'Kein JDK 17-24 gefunden - lade Eclipse Temurin 21 nach E:\AutoCinematic\runtime\jdk ...' 'Cyan'
        $api = 'https://api.adoptium.net/v3/assets/latest/21/hotspot?architecture=x64&image_type=jdk&os=windows&vendor=eclipse'
        $rel = @(Invoke-RestMethod -Uri $api -UseBasicParsing)[0]
        $pkg = $rel.binary.package
        if (-not $pkg -or $pkg.name -notlike '*.zip') { throw 'Adoptium-API lieferte kein ZIP-Paket' }
        $zip = Join-Path $DlDir $pkg.name
        $ok = (Test-Path -LiteralPath $zip) -and ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash -ieq $pkg.checksum)
        if (-not $ok) {
            Log "  lade $($pkg.link) ($([math]::Round($pkg.size / 1MB)) MB)"
            Invoke-WebRequest -Uri $pkg.link -OutFile "$zip.part" -UseBasicParsing
            $h = (Get-FileHash -LiteralPath "$zip.part" -Algorithm SHA256).Hash
            if ($h -ine $pkg.checksum) { throw "SHA-256 stimmt nicht: $h (erwartet $($pkg.checksum))" }
            Move-Item -LiteralPath "$zip.part" -Destination $zip -Force
        }
        Log '  SHA-256 ok, entpacke ...'
        $tmp = Join-Path $Root ("tmp\system\jdk-" + (Get-Date -Format 'yyyyMMddHHmmss'))
        New-Item -ItemType Directory -Path $tmp -Force | Out-Null
        if (Get-Command tar.exe -ErrorAction SilentlyContinue) { & tar.exe -xf $zip -C $tmp; if ($LASTEXITCODE -ne 0) { throw 'Entpacken fehlgeschlagen' } }
        else { Expand-Archive -LiteralPath $zip -DestinationPath $tmp }
        $inner = @(Get-ChildItem -LiteralPath $tmp -Directory)[0]
        Move-Item -LiteralPath $inner.FullName -Destination $JdkDir
        Remove-Item -LiteralPath $tmp -Force   # nur der jetzt leere, eigene Temp-Ordner
        $m = Get-JdkMajor $JdkDir
        if ($m -lt 17) { throw "Entpacktes JDK startet nicht (javac.exe). Evtl. blockiert die Windows-Anwendungssteuerung $JdkDir\bin\javac.exe" }
        Log "  Temurin $($rel.release_name) bereit: $JdkDir" 'Green'
        $jdk = $JdkDir
    }
    $env:JAVA_HOME = $jdk
    $env:PATH = "$jdk\bin;$env:PATH"

    # ---------------------------------------------------------------- Bauen
    Log "Baue $Src (erster Lauf laedt Gradle 8.14.3 + Paper-API nach $env:GRADLE_USER_HOME) ..." 'Cyan'
    Push-Location -LiteralPath $Src
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    try {
        & cmd.exe /c "gradlew.bat build --no-daemon --console=plain 2>&1" | ForEach-Object { Add-Content -LiteralPath $Log -Value "$_" -Encoding UTF8; Write-Host "  $_" -ForegroundColor DarkGray }
        $rc = $LASTEXITCODE
    } finally { $ErrorActionPreference = $old; Pop-Location }
    if ($rc -ne 0) { throw "Gradle-Build fehlgeschlagen (Exitcode $rc)" }

    $jars = @(Get-ChildItem -LiteralPath (Join-Path $Src 'build\libs') -Filter 'AutoCinematicRecorder-*.jar')
    if (-not $jars) { throw 'Build meldet Erfolg, aber keine JAR gefunden' }
    foreach ($j in $jars) {
        Copy-Item -LiteralPath $j.FullName -Destination $OutDir -Force
        $h = (Get-FileHash -LiteralPath $j.FullName -Algorithm SHA256).Hash
        Log ("FERTIG: {0}\{1}  ({2} KB, SHA-256 {3})" -f $OutDir, $j.Name, [math]::Round($j.Length / 1KB), $h) 'Green'
    }
    exit 0
} catch {
    Log "FEHLER: $($_.Exception.Message)" 'Red'
    Log "Protokoll: $Log" 'Red'
    exit 1
}
