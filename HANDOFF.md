# HANDOFF – EnderNation AutoCinematic

Diese Datei wird laufend fortgeschrieben. Hier steht nur, was wirklich getestet ist.

## Stand 2026-10-12

| | |
|---|---|
| Phase | A (Bestand und Machbarkeit) abgeschlossen; B (erster echter Kameratest) bereit zum Test unter Windows |
| Repository | GitHub: `TheEnderHacker/autocinematic` (angelegt). Push ist noch blockiert, weil die Claude-GitHub-App fehlt. Lokal: `E:\AutoCinematic\repos\autocinematic` und `repos\autocinematic-git.bundle` |
| Branch / Commits | `dev`: `e8bb191` Phase A: Analysekern, Flashback-Keyframe-Export, Machbarkeitsbericht · danach: HANDOFF |
| Analysierte Repos | SwornGuns-V1 `master` de3eb7f / `endernation` 048760a / `ai-dev` 29d37ad · server-enderguns 5954f0c · EnderGuns-API c7182d7 · endernation 6474f3c · Flashback (GitHub, 0.43.6) |

## Tests

| Test | Ergebnis | Wo |
|---|---|---|
| Python-Unit-Tests (57) | **bestanden** unter Python 3.11.x, 3.12.3, 3.13.x | Linux-Cloud-Container |
| ruff (E, F, W, B) | sauber | Linux-Cloud-Container |
| PowerShell-Skripte: Syntax | alle 6 fehlerfrei geparst (PowerShell 7.4.6) | Linux |
| Installer: Auswahl-Logik | mit echten Asset-Namen geprüft (uv, FFmpeg n9.0, Prism 11.1.1 MSVC Portable) und mit simulierten Modrinth- und Fabric-Antworten (Instanz-Dateien, SHA-512-Prüfung, fehlende optionale Mod) | Linux, simuliert |
| Speicherbericht (Check-DiskUsage) | **unter Windows gelaufen** (logs\disk-report-20261012-141345.txt) | Windows |
| Installer, Selbsttest, C:-Analyse, FFmpeg-Render, Flashback-Laden, MP4-Export | **noch nicht unter Windows gelaufen** | – |

## Offene Aufgaben (nächste zuerst)

1. **Windows:** `tools\Install-AutoCinematicTools.cmd -DryRun`, danach ohne `-DryRun`. Anschließend `tools\Test-AutoCinematic.cmd`. Die Logs aus `logs\` gehen an Claude.
2. **Phase B:** Singleplayer-Aufnahme mit Positionsmarker, dann `autocinematic camera --orbit-markers`. Danach in Flashback öffnen, exportieren und die MP4 mit ffprobe prüfen.
3. ~~B2~~ geklärt: live laufen 26.3 und `ai-dev`. B4: Die Claude-GitHub-App muss für `TheEnderHacker/autocinematic` installiert werden.
4. Phase C: Paper-Plugin „AutoCinematic Recorder“ (MONITOR-Listener, Flugbahn pro Tick, JSONL, Aufbewahrung, Zugriffsschutz) und Client-Addon (Plugin-Message → Flashback-Marker). Die Java-Builds laufen auf deinem PC.
5. CineWolf-JAR untersuchen: Quellen und Erweiterungspunkte (A-7).
6. `tools\Check-CDriveTop.cmd`: klären, wo die übrigen ca. 180 GB auf C: liegen.

## Bekannte Grenzen

- Kamerapositionen werden nicht gegen Blöcke geprüft. Jede Einstellung ist deshalb als `verified: false` markiert und trägt eine Warnung.
- Die Projektilkamera bleibt deaktiviert, bis Server-Flugbahndaten vorliegen. Das ist ausdrücklich gemeldet und wird nicht erfunden.
- Das `editor_states`-Format ist aus Flashback 0.43.6 (MC 26.3) abgeleitet; der Nachweis im Spiel steht noch aus.
- Client-Instanz: MC 26.3 (wie der Server). Flashbatch ist für 26.3 noch nicht verfügbar.
