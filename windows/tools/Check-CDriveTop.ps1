<#
=====================================================================
 EnderNation AutoCinematic - Wo liegt der Rest auf C:? (NUR LESEN)

 Der erste Bericht erklaerte nur ~27 GB von ~206 GB. Dieses Skript misst
 die obersten Ordnerebenen von C:\, des Benutzerprofils, AppData,
 Program Files und ProgramData. Es wird nichts geloescht oder veraendert.
 Ordner ohne Leserecht werden als "kein Zugriff" gezaehlt (ohne Admin normal).

 Aufruf: tools\Check-CDriveTop.cmd   (Dauer: einige Minuten)
 Ergebnis: E:\AutoCinematic\logs\c-top-<Zeitstempel>.txt
=====================================================================
#>
$ErrorActionPreference = 'SilentlyContinue'
$Root = Split-Path -Parent $PSScriptRoot
if (-not $Root) { $Root = 'E:\AutoCinematic' }
$Out = Join-Path $Root ("logs\c-top-{0}.txt" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
$lines = New-Object System.Collections.Generic.List[string]
function Say([string]$s) { Write-Host $s; $lines.Add($s) }

function Measure-Dir([string]$Path) {
    $total = [long]0; $denied = 0
    $stack = New-Object 'System.Collections.Generic.Stack[System.IO.DirectoryInfo]'
    $stack.Push([System.IO.DirectoryInfo]::new($Path))
    while ($stack.Count -gt 0) {
        $d = $stack.Pop()
        try { foreach ($f in $d.EnumerateFiles()) { $total += $f.Length } } catch { $denied++ }
        try { foreach ($s in $d.EnumerateDirectories()) { if (-not ($s.Attributes -band [IO.FileAttributes]::ReparsePoint)) { $stack.Push($s) } } } catch { $denied++ }
    }
    return [pscustomobject]@{ Bytes = $total; Denied = $denied }
}
function Fmt([long]$b) { if ($b -ge 1GB) { '{0,8:N1} GB' -f ($b / 1GB) } else { '{0,8:N0} MB' -f ($b / 1MB) } }

function Level([string]$Title, [string]$Path, [int]$Top = 15) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    Say ''
    Say "== $Title ($Path) =="
    $rows = foreach ($d in Get-ChildItem -LiteralPath $Path -Directory -Force) {
        if ($d.Attributes -band [IO.FileAttributes]::ReparsePoint) { continue }
        Write-Host "   ... $($d.FullName)" -ForegroundColor DarkGray
        $m = Measure-Dir $d.FullName
        [pscustomobject]@{ Name = $d.Name; Bytes = $m.Bytes; Denied = $m.Denied }
    }
    $rows | Sort-Object Bytes -Descending | Select-Object -First $Top | ForEach-Object {
        Say ("  {0}  {1}{2}" -f (Fmt $_.Bytes), $_.Name, $(if ($_.Denied) { "   (teilweise kein Zugriff: $($_.Denied))" } else { '' }))
    }
    $files = (Get-ChildItem -LiteralPath $Path -File -Force | Measure-Object Length -Sum).Sum
    if ($files) { Say ("  {0}  [Dateien direkt in diesem Ordner]" -f (Fmt $files)) }
}

$c = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
Say ("C: belegt {0:N1} GB von {1:N1} GB, frei {2:N1} GB" -f (($c.Size - $c.FreeSpace) / 1GB), ($c.Size / 1GB), ($c.FreeSpace / 1GB))
foreach ($sys in 'C:\pagefile.sys', 'C:\hiberfil.sys', 'C:\swapfile.sys') {
    $i = Get-ChildItem -LiteralPath (Split-Path $sys) -Force -Filter (Split-Path $sys -Leaf) | Select-Object -First 1
    if ($i) { Say ("  {0}  {1}" -f (Fmt $i.Length), $sys) }
}
Level 'Laufwerk C:' 'C:\' 20
Level 'Benutzerprofil' $env:USERPROFILE 20
Level 'AppData\Local' $env:LOCALAPPDATA 20
Level 'AppData\Roaming' $env:APPDATA 15
Level 'Program Files' 'C:\Program Files' 15
Level 'Program Files (x86)' 'C:\Program Files (x86)' 10
Level 'ProgramData' 'C:\ProgramData' 10
$lines | Set-Content -LiteralPath $Out -Encoding UTF8
Write-Host ''
Write-Host "Bericht: $Out" -ForegroundColor Green
