<#
=====================================================================
 EnderNation AutoCinematic - Werkzeuge auf E: einrichten

 Installiert NUR nach E:\AutoCinematic (keine Installer, keine Registry,
 keine globalen Einstellungen, kein Loeschen bestehender Dateien):

   runtime\bin\uv.exe            Python-Paket-/Umgebungsmanager (astral-sh/uv)
   runtime\ffmpeg\bin\ffmpeg.exe FFmpeg (BtbN-Build, GPL, Windows x64)
   minecraft\launcher\           Prism Launcher PORTABLE
   minecraft\launcher\instances\EnderNation-AutoCinematic\
                                 Fabric-Instanz (Minecraft 26.3 = Serverversion) mit Flashback,
                                 CineWolf AutoDirector und Fabric API (alles auf E:)
   runtime\venvs\autocinematic\  Python-Umgebung fuer repos\autocinematic

 Bestehende Programme (Java, Python, Node, Git auf C:) werden nur benutzt,
 nicht veraendert. Bereits vorhandene Komponenten auf E: werden uebersprungen.

 Aufruf (Doppelklick auf tools\Install-AutoCinematicTools.cmd) oder:
   powershell -ExecutionPolicy Bypass -File Install-AutoCinematicTools.ps1 [-DryRun]
     [-SkipFfmpeg] [-SkipUv] [-SkipPrism] [-SkipMinecraft] [-SkipPython]
     [-McVersion 26.3]

 -DryRun: nur pruefen, welche Versionen/Downloads verwendet wuerden.
 Protokoll: E:\AutoCinematic\logs\install-<Zeitstempel>.txt
=====================================================================
#>
param(
    [switch]$DryRun,
    [switch]$SkipFfmpeg,
    [switch]$SkipUv,
    [switch]$SkipPrism,
    [switch]$SkipMinecraft,
    [switch]$SkipPython,
    [string]$McVersion = '26.3',
    [string]$InstanceName = 'EnderNation-AutoCinematic',
    [int]$MaxMemoryMB = 6144
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # beschleunigt Invoke-WebRequest in Windows PowerShell 5.1 massiv
try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}

$Root = Split-Path -Parent $PSScriptRoot
if (-not $Root) { $Root = 'E:\AutoCinematic' }
. (Join-Path $Root 'env\autocinematic-env.ps1') | Out-Null

$Stamp    = Get-Date -Format 'yyyyMMdd-HHmmss'
$LogFile  = Join-Path $Root "logs\install-$Stamp.txt"
$DlDir    = Join-Path $Root 'downloads'
$TmpDir   = Join-Path $Root "tmp\system\install-$Stamp"
$Ua       = @{ 'User-Agent' = 'EnderNation-AutoCinematic-Installer' }
$Results  = New-Object System.Collections.Generic.List[string]
foreach ($d in $DlDir, $TmpDir, (Split-Path $LogFile)) { if (-not (Test-Path -LiteralPath $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null } }

function Log([string]$msg, [string]$color = 'Gray') {
    $line = "[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $msg
    Write-Host $line -ForegroundColor $color
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
}
function Result([string]$name, [string]$status, [string]$detail) {
    $r = '{0,-28} {1,-8} {2}' -f $name, $status, $detail
    $Results.Add($r)
    $c = switch ($status) { 'OK' { 'Green' } 'SKIP' { 'DarkGray' } 'DRYRUN' { 'Cyan' } default { 'Red' } }
    Log $r $c
}

function Get-GitHubRelease([string]$repo, [string]$tag = 'latest') {
    $url = if ($tag -eq 'latest') { "https://api.github.com/repos/$repo/releases/latest" } else { "https://api.github.com/repos/$repo/releases/tags/$tag" }
    return Invoke-RestMethod -Uri $url -Headers $Ua -UseBasicParsing
}

function Get-Download([string]$url, [string]$fileName, [string]$expectedHash, [string]$algo = 'SHA256') {
    $target = Join-Path $DlDir $fileName
    if ((Test-Path -LiteralPath $target) -and $expectedHash) {
        $h = (Get-FileHash -LiteralPath $target -Algorithm $algo).Hash
        if ($h -ieq $expectedHash) { Log "  bereits geladen: $fileName"; return $target }
    }
    Log "  lade $url"
    $part = "$target.part"
    Invoke-WebRequest -Uri $url -OutFile $part -Headers $Ua -UseBasicParsing
    if ($expectedHash) {
        $h = (Get-FileHash -LiteralPath $part -Algorithm $algo).Hash
        if ($h -ine $expectedHash) {
            Rename-Item -LiteralPath $part -NewName ("$fileName.BAD-$Stamp") -Force
            throw "Pruefsumme falsch fuer $fileName (erwartet $expectedHash, erhalten $h) - Datei als .BAD markiert"
        }
        Log "  $algo ok"
    } else {
        Log '  WARNUNG: keine Pruefsumme veroeffentlicht' 'Yellow'
    }
    Move-Item -LiteralPath $part -Destination $target -Force
    return $target
}

function Expand-Zip([string]$zip, [string]$dest) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($zip, $dest)
}

function Get-AssetDigest($asset) {
    if ($asset.PSObject.Properties.Name -contains 'digest' -and $asset.digest -like 'sha256:*') { return $asset.digest.Substring(7) }
    return $null
}

Log "AutoCinematic-Installer gestartet (DryRun=$DryRun) - Root $Root"
Log ("C: frei vorher: {0:N2} GB" -f ((Get-PSDrive C).Free / 1GB))

# ------------------------------------------------------------------ uv
if ($SkipUv) { Result 'uv' 'SKIP' 'per Parameter' }
elseif (Test-Path -LiteralPath "$Root\runtime\bin\uv.exe") { Result 'uv' 'SKIP' 'bereits vorhanden' }
else {
    try {
        $rel = Get-GitHubRelease 'astral-sh/uv'
        $asset = $rel.assets | Where-Object { $_.name -eq 'uv-x86_64-pc-windows-msvc.zip' } | Select-Object -First 1
        $shaAsset = $rel.assets | Where-Object { $_.name -eq 'uv-x86_64-pc-windows-msvc.zip.sha256' } | Select-Object -First 1
        if (-not $asset) { throw 'Windows-Asset nicht gefunden' }
        if ($DryRun) { Result 'uv' 'DRYRUN' "$($rel.tag_name) $($asset.browser_download_url)" }
        else {
            $hash = Get-AssetDigest $asset
            if (-not $hash -and $shaAsset) { $hash = ((Invoke-WebRequest -Uri $shaAsset.browser_download_url -Headers $Ua -UseBasicParsing).Content -split '\s+')[0] }
            $zip = Get-Download $asset.browser_download_url $asset.name $hash
            $x = Join-Path $TmpDir 'uv'; Expand-Zip $zip $x
            Get-ChildItem -LiteralPath $x -Recurse -Filter '*.exe' | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination "$Root\runtime\bin\" }
            Result 'uv' 'OK' "$($rel.tag_name) -> runtime\bin"
        }
    } catch { Result 'uv' 'FEHLER' $_.Exception.Message }
}

# -------------------------------------------------------------- FFmpeg
if ($SkipFfmpeg) { Result 'ffmpeg' 'SKIP' 'per Parameter' }
elseif (Test-Path -LiteralPath "$Root\runtime\ffmpeg\bin\ffmpeg.exe") { Result 'ffmpeg' 'SKIP' 'bereits vorhanden' }
else {
    try {
        $rel = Get-GitHubRelease 'BtbN/FFmpeg-Builds' 'latest'
        # Stabile Release-Linie bevorzugen (z. B. ffmpeg-n7.1-latest-win64-gpl-7.1.zip), sonst master
        $cands = $rel.assets | Where-Object { $_.name -match '^ffmpeg-n(\d+)\.(\d+)-latest-win64-gpl-\d+\.\d+\.zip$' } |
            Sort-Object { [int]([regex]::Match($_.name, 'n(\d+)\.(\d+)').Groups[1].Value) * 100 + [int]([regex]::Match($_.name, 'n(\d+)\.(\d+)').Groups[2].Value) } -Descending
        $asset = $cands | Select-Object -First 1
        if (-not $asset) { $asset = $rel.assets | Where-Object { $_.name -eq 'ffmpeg-master-latest-win64-gpl.zip' } | Select-Object -First 1 }
        if (-not $asset) { throw 'kein passendes Windows-Build gefunden' }
        if ($DryRun) { Result 'ffmpeg' 'DRYRUN' "$($asset.name) ($([math]::Round($asset.size/1MB)) MB)" }
        else {
            $hash = Get-AssetDigest $asset
            if (-not $hash) {
                $sumAsset = $rel.assets | Where-Object { $_.name -eq 'checksums.sha256' } | Select-Object -First 1
                if ($sumAsset) {
                    $sums = (Invoke-WebRequest -Uri $sumAsset.browser_download_url -Headers $Ua -UseBasicParsing).Content
                    $line = ($sums -split "`n") | Where-Object { $_ -match [regex]::Escape($asset.name) } | Select-Object -First 1
                    if ($line) { $hash = ($line.Trim() -split '\s+')[0] }
                }
            }
            $zip = Get-Download $asset.browser_download_url $asset.name $hash
            $x = Join-Path $TmpDir 'ffmpeg'; Expand-Zip $zip $x
            $top = Get-ChildItem -LiteralPath $x -Directory | Select-Object -First 1
            if (-not (Test-Path -LiteralPath "$($top.FullName)\bin\ffmpeg.exe")) { throw 'ffmpeg.exe nicht im Archiv gefunden' }
            foreach ($item in Get-ChildItem -LiteralPath $top.FullName) {
                $dest = Join-Path "$Root\runtime\ffmpeg" $item.Name
                if (-not (Test-Path -LiteralPath $dest)) { Move-Item -LiteralPath $item.FullName -Destination $dest }
            }
            Result 'ffmpeg' 'OK' "$($asset.name) -> runtime\ffmpeg"
        }
    } catch { Result 'ffmpeg' 'FEHLER' $_.Exception.Message }
}

# ------------------------------------------------------- Prism portable
$PrismDir = Join-Path $Root 'minecraft\launcher'
$PrismExe = Join-Path $PrismDir 'prismlauncher.exe'
if ($SkipPrism) { Result 'Prism Launcher' 'SKIP' 'per Parameter' }
elseif (Test-Path -LiteralPath $PrismExe) { Result 'Prism Launcher' 'SKIP' 'bereits vorhanden' }
else {
    try {
        $rel = Get-GitHubRelease 'PrismLauncher/PrismLauncher'
        $asset = $rel.assets | Where-Object { $_.name -match '^PrismLauncher-Windows-MSVC-Portable-[\d\.]+\.zip$' } | Select-Object -First 1
        if (-not $asset) { $asset = $rel.assets | Where-Object { $_.name -match 'Windows.*Portable.*\.zip$' -and $_.name -notmatch 'arm64' } | Select-Object -First 1 }
        if (-not $asset) { throw 'Portable-Archiv nicht gefunden' }
        if ($DryRun) { Result 'Prism Launcher' 'DRYRUN' "$($rel.tag_name) $($asset.name)" }
        else {
            $zip = Get-Download $asset.browser_download_url $asset.name (Get-AssetDigest $asset)
            $x = Join-Path $TmpDir 'prism'; Expand-Zip $zip $x
            $src = $x
            $exe = Get-ChildItem -LiteralPath $x -Recurse -Filter 'prismlauncher.exe' | Select-Object -First 1
            if (-not $exe) { throw 'prismlauncher.exe nicht im Archiv' }
            $src = $exe.DirectoryName
            foreach ($item in Get-ChildItem -LiteralPath $src -Force) {
                $dest = Join-Path $PrismDir $item.Name
                if (-not (Test-Path -LiteralPath $dest)) { Move-Item -LiteralPath $item.FullName -Destination $dest }
            }
            if (-not (Test-Path -LiteralPath "$PrismDir\portable.txt")) { Set-Content -LiteralPath "$PrismDir\portable.txt" -Value '' }
            Result 'Prism Launcher' 'OK' "$($rel.tag_name) portable -> minecraft\launcher"
        }
    } catch { Result 'Prism Launcher' 'FEHLER' $_.Exception.Message }
}

# ------------------------------------------------- Minecraft-Instanz
function Get-ModrinthVersion([string]$slug, [string]$mc) {
    $gv = [uri]::EscapeDataString("[`"$mc`"]")
    $ld = [uri]::EscapeDataString('["fabric"]')
    $list = Invoke-RestMethod -Uri "https://api.modrinth.com/v2/project/$slug/version?game_versions=$gv&loaders=$ld" -Headers $Ua -UseBasicParsing
    $v = @($list) | Where-Object { $_.version_type -eq 'release' } | Select-Object -First 1
    if (-not $v) { $v = @($list) | Select-Object -First 1 }
    return $v
}

$InstDir = Join-Path $PrismDir "instances\$InstanceName"
if ($SkipMinecraft) { Result 'Minecraft-Instanz' 'SKIP' 'per Parameter' }
elseif (Test-Path -LiteralPath "$InstDir\instance.cfg") { Result 'Minecraft-Instanz' 'SKIP' "bereits vorhanden ($InstDir) - wird nicht veraendert" }
else {
    try {
        $loaders = Invoke-RestMethod -Uri "https://meta.fabricmc.net/v2/versions/loader/$McVersion" -Headers $Ua -UseBasicParsing
        $loader = (@($loaders) | Select-Object -First 1).loader.version
        if (-not $loader) { throw "kein Fabric-Loader fuer Minecraft $McVersion gefunden" }
        $mods = [ordered]@{
            'fabric-api'            = $true
            'flashback'             = $true
            'cinewolf-autodirector' = $true
            'flashbatch'            = $false   # optional: Stapel-Export (bisher nur bis 26.2 verfuegbar)
            'modmenu'               = $false
        }
        $plan = @()
        foreach ($slug in $mods.Keys) {
            $v = $null
            try { $v = Get-ModrinthVersion $slug $McVersion } catch { $v = $null }
            if (-not $v) {
                if ($mods[$slug]) { throw "Pflicht-Mod '$slug' gibt es nicht fuer Minecraft $McVersion" }
                Log "  optional: $slug nicht fuer $McVersion verfuegbar - uebersprungen" 'Yellow'
                Result "Mod $slug" 'FEHLT' "nicht fuer $McVersion verfuegbar"
                continue
            }
            $file = @($v.files) | Where-Object { $_.primary } | Select-Object -First 1
            if (-not $file) { $file = @($v.files)[0] }
            $plan += [pscustomobject]@{ Slug = $slug; Version = $v.version_number; Url = $file.url; Name = $file.filename; Sha512 = $file.hashes.sha512; Size = $file.size }
        }
        if ($DryRun) {
            Result 'Minecraft-Instanz' 'DRYRUN' "MC $McVersion, Fabric-Loader $loader"
            foreach ($p in $plan) { Result "Mod $($p.Slug)" 'DRYRUN' "$($p.Version) ($([math]::Round($p.Size/1MB,1)) MB)" }
        } else {
            $mcDir = Join-Path $InstDir 'minecraft'
            New-Item -ItemType Directory -Path "$mcDir\mods" -Force | Out-Null
            foreach ($p in $plan) {
                $jar = Get-Download $p.Url $p.Name $p.Sha512 'SHA512'
                Copy-Item -LiteralPath $jar -Destination "$mcDir\mods\$($p.Name)"
                Result "Mod $($p.Slug)" 'OK' $p.Version
            }
            # Prism liest instance.cfg wie Qt-INI: Backslashes waeren Escape-Zeichen -> nur '/' verwenden
            $rootFwd = $Root.Replace('\', '/')
            $jvm = "-Djava.io.tmpdir=$rootFwd/tmp/java -Dorg.bytedeco.javacpp.cachedir=$rootFwd/cache/javacpp"
            @(
                '[General]'
                'ConfigVersion=1.2'
                'InstanceType=OneSix'
                "name=$InstanceName"
                'iconKey=default'
                'OverrideJavaArgs=true'
                "JvmArgs=$jvm"
                'OverrideMemory=true'
                'MinMemAlloc=2048'
                "MaxMemAlloc=$MaxMemoryMB"
                'notes=Von AutoCinematic angelegt. Replays: minecraft/flashback/replays'
            ) | Set-Content -LiteralPath "$InstDir\instance.cfg" -Encoding ASCII
            $pack = @{
                formatVersion = 1
                components = @(
                    @{ uid = 'net.minecraft'; version = $McVersion; important = $true },
                    @{ uid = 'net.fabricmc.fabric-loader'; version = $loader }
                )
            }
            $pack | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath "$InstDir\mmc-pack.json" -Encoding ASCII
            Result 'Minecraft-Instanz' 'OK' "MC $McVersion + Fabric $loader -> $InstDir"
        }
    } catch { Result 'Minecraft-Instanz' 'FEHLER' $_.Exception.Message }
}

# ---------------------------------------------------- Python-Umgebung
$Venv = Join-Path $Root 'runtime\venvs\autocinematic'
$Pkg  = Join-Path $Root 'repos\autocinematic\python'
if ($SkipPython) { Result 'Python-Umgebung' 'SKIP' 'per Parameter' }
elseif (-not (Test-Path -LiteralPath "$Pkg\pyproject.toml")) { Result 'Python-Umgebung' 'FEHLER' "Paket fehlt: $Pkg" }
elseif ($DryRun) { Result 'Python-Umgebung' 'DRYRUN' "uv venv $Venv --python 3.12; uv pip install -e $Pkg[test]" }
else {
    # Native Programme (uv, pip) schreiben Statusmeldungen nach stderr. In Windows PowerShell 5.1
    # wuerde das mit ErrorActionPreference=Stop als Fehler gelten -> hier nur den Exitcode pruefen.
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $uv = Join-Path $Root 'runtime\bin\uv.exe'
        function Invoke-Native([string]$exe, [string[]]$argv) {
            & $exe @argv 2>&1 | ForEach-Object { Log "  $_" }
            if ($LASTEXITCODE -ne 0) { throw "$(Split-Path $exe -Leaf) $($argv[0]) fehlgeschlagen (Exitcode $LASTEXITCODE)" }
        }
        # Pruefen, ob eine vorhandene Umgebung funktioniert (ein abgebrochener Lauf kann sie beschaedigt hinterlassen)
        $venvOk = $false
        if (Test-Path -LiteralPath "$Venv\Scripts\python.exe") {
            try { & "$Venv\Scripts\python.exe" -c "import sys" 2>&1 | Out-Null; $venvOk = ($LASTEXITCODE -eq 0) } catch { $venvOk = $false }
            if (-not $venvOk) { Log '  vorhandene Python-Umgebung ist beschaedigt - wird neu angelegt (nur dieser Ordner auf E:)' 'Yellow' }
        }
        if (Test-Path -LiteralPath $uv) {
            if (-not $venvOk) {
                $venvArgs = @('venv', $Venv, '--python', '3.12')
                if (Test-Path -LiteralPath $Venv) {
                    # Nur ersetzen, wenn der Ordner nachweislich von uv/venv stammt (Reste eines abgebrochenen Laufs)
                    $known = @('.gitignore', 'CACHEDIR.TAG', 'pyvenv.cfg', 'Scripts\python.exe', 'Scripts\pythonw.exe')
                    $files = @(Get-ChildItem -LiteralPath $Venv -Recurse -File -Force | ForEach-Object { $_.FullName.Substring($Venv.Length + 1).Replace([char]47, [char]92) })
                    $isVenv = Test-Path -LiteralPath "$Venv\pyvenv.cfg"
                    $onlySkeleton = @($files | Where-Object { $known -notcontains $_ }).Count -eq 0
                    if (-not ($isVenv -or $onlySkeleton)) { throw "$Venv enthaelt unbekannte Dateien - bitte pruefen, es wird nichts geloescht" }
                    $venvArgs += @('--clear', '--force')
                }
                Invoke-Native $uv $venvArgs
            }
            $env:VIRTUAL_ENV = $Venv
            Invoke-Native $uv @('pip', 'install', '-e', "$Pkg[test]")
            Remove-Item Env:VIRTUAL_ENV
        } else {
            if (-not $venvOk) { Invoke-Native 'py' @('-3.12', '-m', 'venv', '--clear', $Venv) }
            Invoke-Native "$Venv\Scripts\python.exe" @('-m', 'pip', 'install', '-e', "$Pkg[test]")
        }
        if (-not (Test-Path -LiteralPath "$Venv\Scripts\autocinematic.exe")) { throw 'Installation unvollstaendig (autocinematic.exe fehlt)' }
        Result 'Python-Umgebung' 'OK' $Venv
    } catch { Result 'Python-Umgebung' 'FEHLER' $_.Exception.Message }
    finally { $ErrorActionPreference = $prevEap }
}

# Nur eigene Entpack-Zwischenordner dieses Laufs aufraeumen (liegen in E:\AutoCinematic\tmp)
if (Test-Path -LiteralPath $TmpDir) { Remove-Item -LiteralPath $TmpDir -Recurse -Force -ErrorAction SilentlyContinue }

Log ("C: frei nachher: {0:N2} GB" -f ((Get-PSDrive C).Free / 1GB))
Log '================ Zusammenfassung ================' 'Cyan'
$Results | ForEach-Object { Log $_ }
Log "Protokoll: $LogFile" 'Cyan'
