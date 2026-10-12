# HANDOFF – EnderNation AutoCinematic

Diese Datei wird laufend fortgeschrieben. Hier steht nur, was wirklich getestet ist.

## Stand 2026-10-12

| | |
|---|---|
| Phase | A abgeschlossen. **B: erster echter Kameratest bestanden (2026-10-12)** |
| Repository | GitHub: `TheEnderHacker/autocinematic` (angelegt). Push funktioniert. Lokal: `E:\AutoCinematic\repos\autocinematic` und `repos\autocinematic-git.bundle` |
| Branch / Commits | `dev` auf GitHub (TheEnderHacker/autocinematic) |
| Analysierte Repos | SwornGuns-V1 `master` de3eb7f / `endernation` 048760a / `ai-dev` 29d37ad · server-enderguns 5954f0c · EnderGuns-API c7182d7 · endernation 6474f3c · Flashback (GitHub, 0.43.6) |

## Tests

| Test | Ergebnis | Wo |
|---|---|---|
| Python-Unit-Tests (62) | **bestanden** unter Python 3.11.x, 3.12.3, 3.13.x | Linux-Cloud-Container |
| ruff (E, F, W, B) | sauber | Linux-Cloud-Container |
| PowerShell-Skripte: Syntax | alle 6 fehlerfrei geparst (PowerShell 7.4.6) | Linux |
| Installer: Auswahl-Logik | mit echten Asset-Namen geprüft (uv, FFmpeg n9.0, Prism 11.1.1 MSVC Portable) und mit simulierten Modrinth- und Fabric-Antworten (Instanz-Dateien, SHA-512-Prüfung, fehlende optionale Mod) | Linux, simuliert |
| Speicherbericht (Check-DiskUsage) | **unter Windows gelaufen** (logs\disk-report-20261012-141345.txt) | Windows |
| Installer (uv 0.13.0, FFmpeg n9.0, Prism 11.1.1, Instanz MC 26.3 mit Fabric 0.19.5, Fabric API 0.162.0, Flashback 0.43.6, CineWolf 2.0.33, Python-venv) | **unter Windows erfolgreich** (logs\install-20261012-151634.txt). Zwei Fehler gefunden und behoben: stderr-Behandlung in PowerShell 5.1, beschädigte venv | Windows |
| Selbsttest 20261012-152206 | **25 bestanden, 2 fehlgeschlagen.** Die MP4s (1080×1920 und 1920×1080, 60 fps) wurden gerendert; nur die Prüfung schlug fehl, weil die Windows-Anwendungssteuerung `ffprobe.exe` blockiert. Die Prüfung läuft jetzt über `ffmpeg -i`; der Nachweis steht noch aus. | Windows |
| pytest unter Windows (Python 3.12.10) | **bestanden** | Windows |
| **Phase B – echter Kameratest** | **bestanden.** Replay `2026-10-12T15_50_48.zip` (EnderNation-Server, Map new-dust2, 859 Ticks, Marker bei Tick 437 mit Position). `autocinematic camera --orbit-markers` → `editor_states/90d6287a-….json`. Flashback 0.43.6 hat die Szene „AC Orbit 1“ mit Spur und Exportbereich 377–497 geladen (Screenshot vom Nutzer). Export → `render\flashback-exports\phase-b-orbit.mp4`: **H.264, 1920×1080, 60 fps, 360 Frames, 6,0 s** (ffprobe). Einzelbilder: `docs/evidence/phase-b-orbit-frames.jpg` | Windows + Minecraft |
| **Verfolgerkamera aus echtem Laufweg** | **bestanden.** Replay `2026-10-12T15_47_54.zip` (Lobby): Spielerweg aus `move_entities` (936 Positionen, 388 Blöcke), automatisch gewählter bewegtester Abschnitt Tick 71–231. Export `phase-b-follow.mp4`: H.264, 1920×1080, 60 fps, 480 Frames, 8,0 s. Spieler ist in allen geprüften Bildern im Bild; im letzten Abschnitt ragt Fels ins Bild (keine Kollisionsprüfung). `docs/evidence/phase-b-follow-frames.jpg` | Windows + Minecraft |
| Echtzeit-Uhr aus Replay | rekonstruiert, 0 Ticks Abweichung an beiden echten Aufnahmen | Linux, echte Daten |

## Offene Aufgaben (nächste zuerst)

1. ~~Installation~~ erledigt. Den Selbsttest mit der neuen Video-Prüfung erneut laufen lassen.
2. ~~Phase B~~ bestanden, Verfolgerkamera bestanden. Als Nächstes: Kollisionsprüfung/Sichtlinie (Weltdaten aus `level_chunk_caches` oder Client-Addon), Export ohne manuellen Klick.
3. ~~B2~~ geklärt: live laufen 26.3 und `ai-dev`. B4 erledigt (GitHub-App installiert).
4. Phase C: Paper-Plugin „AutoCinematic Recorder“ (MONITOR-Listener, Flugbahn pro Tick, JSONL, Aufbewahrung, Zugriffsschutz) und Client-Addon (Plugin-Message → Flashback-Marker). Die Java-Builds laufen auf deinem PC.
5. CineWolf-JAR untersuchen: Quellen und Erweiterungspunkte (A-7).
6. `tools\Check-CDriveTop.cmd`: klären, wo die übrigen ca. 180 GB auf C: liegen.

## Bekannte Grenzen

- Kamerapositionen werden nicht gegen Blöcke geprüft. Jede Einstellung ist deshalb als `verified: false` markiert und trägt eine Warnung.
- Die Projektilkamera bleibt deaktiviert, bis Server-Flugbahndaten vorliegen. Das ist ausdrücklich gemeldet und wird nicht erfunden.
- Das `editor_states`-Format ist in Flashback 0.43.6 nachgewiesen (Phase B).
- Flashback-Marker-Tasten sind ab Werk nicht belegt (Optionen → Steuerung → Flashback → „Create Marker #1“).
- Prism liest `\` in instance.cfg als Escape-Zeichen; JVM-Argumente müssen `/` verwenden (behoben).
- Client-Instanz: MC 26.3 (wie der Server). Flashbatch ist für 26.3 noch nicht verfügbar.

- Windows-Anwendungssteuerung (Smart App Control o. ä.) blockiert `ffprobe.exe`. Deshalb wird kein ffprobe benutzt; an der Windows-Einstellung wurde nichts geändert.
- `windows/` im Repository spiegelt die Skripte aus `E:\AutoCinematic\tools` und `env`.
