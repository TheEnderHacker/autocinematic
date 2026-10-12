# Phase A – Bestand und Machbarkeit

Stand: 2026-10-12 · Grundlage: realer Quellcode und Modrinth-Daten, keine Annahmen aus früheren Analysen ungeprüft übernommen.

## 1. Ergebnis in Kürze

- **Machbar ist es**, mit klarer Arbeitsteilung:
  - Die Server-Ereignisse aus SwornGuns liefern die Antwort auf die Frage **was wann** passiert ist.
  - Flashback liefert die **Bilder**. Das Render-Ziel ist dabei Flashbacks eigene Keyframe-Datei (`editor_states`).
  - FFmpeg und Remotion übernehmen den **Schnitt**.
- **Projektil-Kamera:** Eine echte Sniper-Projektilkamera braucht eine serverseitig aufgezeichnete Flugbahn. Im Replay selbst ist die Flugbahn nur die Vorhersage des Clients (siehe §7).
- **Der kleinste Kameratest (Phase B)** braucht keinen Server und keine eigene Mod. Es reichen eine Singleplayer-Aufnahme, ein Marker mit Position und unsere erzeugte `editor_states`-Datei. Dann ein Export-Klick in Flashback.
- **Client-Version:** Für die Aufnahme- und Render-Instanz habe ich **Minecraft 26.2** festgelegt (Begründung in §6).

## 2. Repositories (geprüft)

| Repository | Branch @ Commit | Relevanter Inhalt |
|---|---|---|
| EnderNationTeam/minecraft-SwornGuns-V1 | `master` @ de3eb7f | Original-Fork: `SwornGunFireEvent`, `Bullet`, `EntityListener` (Kopfschuss), Waffen-YAMLs |
| | `endernation` @ 048760a | `paper-api 1.21.11-R0.1-SNAPSHOT`, Java 24, EnderCore 4.0.0. Eine Commit-Nachricht erwähnt „EnderNation 26.3“; das muss geklärt werden. |
| | `ai-dev` @ 29d37ad | zusätzlich `CombatDebug`, `SwornGunShotEvent(player, weaponId, shotId)`, `shotId`/`pelletIndex` im `Bullet`, `HitFeedback` sowie Tests (`CombatDebugJsonlTest` …) |
| EnderNationTeam/minecraft-server-enderguns | `master` @ 5954f0c | EnderGuns-Spielmodus (Folia-API 1.21.11, JDK 25): Kampf-, Tod- und Kit-Logik. `AttackListener` (deprecated) erkennt Treffer über Schneeball-Damager. |
| EnderNationTeam/EnderGuns-API | `master` @ c7182d7 | nur Manager-Interfaces (`ICombatManager` …), keine Ereignisse |
| EnderNationTeam/minecraft-endernation | `master` @ 6474f3c | Monorepo-Gerüst (commons/server/proxy). Die Unterprojekte enthalten keine Java-Quellen im Checkout. |

Replay- oder Kamera-Komponenten gibt es in keinem dieser Repositories.

### Verfügbare Kampfereignisse

| Ereignis | Quelle | Verfügbar in | Daten |
|---|---|---|---|
| Schuss | `SwornGunFireEvent` (cancellable) | allen Branches | Spieler, `Gun` (Name, `maxDistance`, `bulletSpeed`, `canHeadshot` …) |
| Schuss mit ID | `SwornGunShotEvent` | nur `ai-dev` | Spieler, `weaponId`, fortlaufende `shotId` |
| Projektil | `Bullet`: Snowball-Entity. Die Geschwindigkeit wird **jeden Tick** neu gesetzt (`projectile.setVelocity`). | alle | Start-Position, Ticks, Schütze. `shotId` und `pelletIndex` nur in `ai-dev`. |
| Treffer | `EntityDamageByEntityEvent` mit Projektil → `plugin.getBullet(proj)` | alle | Schaden. Kopfschuss, wenn \|Projektil-Y − Augen-Y\| ≤ 0,26 (Faktor 1,5). |
| Eliminierung | `PlayerDeathEvent` | Bukkit | Opfer, Killer |
| CombatDebug | `ai-dev`: Sitzungen von 10–900 s, JSONL (`fired`, `actualSpawn`, `collision`, `shotSummary`, `death` …) mit `serverTick` und `sessionId` | nur `ai-dev` | Debug-Werkzeug mit begrenzter Laufzeit, **kein** Produktions-Recorder |

**Antwort auf die Kernfrage (Szenen erkennen, ohne das Gameplay zu ändern):** Ein eigenes, optionales Plugin „AutoCinematic Recorder“ übernimmt das.
- Es registriert ausschließlich `EventPriority.MONITOR`-Listener mit `ignoreCancelled = true`.
- Projektilpositionen liest es nur, über den Entity-Scheduler (Folia-tauglich).
- An SwornGuns ändert sich **nichts**.
- Schuss und Projektil ordnet es so zu: gleicher Tick, gleicher Schütze und `ProjectileLaunchEvent`. Sobald `ai-dev` gemergt ist, nimmt es direkt die `shotId`.

## 3. Flashback (Quelltext 0.43.6 gelesen)

- **Lizenz:** „All Rights Reserved – Do not redistribute“, Fremdbeiträge werden nicht angenommen. Das heißt für uns: **kein Fork und kein Patch.** Erlaubt ist, eigene Dateien zu erzeugen und ein separates Addon zu bauen, das Flashback nicht mitliefert (so arbeiten MultiView und Flashbatch auch).
- **Versionen:** MC 26.2 → 0.43.4 · MC 26.3 → 0.43.6 · MC 1.21.11 → 0.39.9 (die letzte für 1.21.11)
- **Replay-Datei:** ein ZIP mit folgendem Inhalt:
  - `metadata.json` mit `uuid`, `name`, `version_string`, `world_name`, `total_ticks`, `markers`, `chunks`, `mod_versions`
  - `cN.flashback` mit Aktionen: Game-Packets, MoveEntities, NextTick …
  - `level_chunk_caches/`
  - `icon.png`
- **Zeit:** 20 Ticks pro Sekunde. Marker: `markers{"<tick>": {colour, position{position:[x,y,z], dimension}, description}}`, **höchstens ein Marker pro Tick**.
- **Keyframes:** `<spielordner>/flashback/editor_states/<replay-uuid>.json` (Gson).
  - Ein Editorzustand enthält mehrere Szenen. Jede Szene hat Spuren und einen Exportbereich (`exportStartTicks`/`exportEndTicks`).
  - Spurtypen: `CAMERA`, `CAMERA_ORBIT`, `TRACK_ENTITY` (UUID, Körperteil HEAD/BODY/ROOT, Offsets), `FOV`, `SPEED` (Tickrate), `CAMERA_SHAKE`, `TIME_OF_DAY`, `FREEZE`, `TIMELAPSE`, `BLOCK_OVERRIDE`, `AUDIO`.
  - Interpolation: SMOOTH, LINEAR, EASE_IN/OUT/IN_OUT, HOLD, HERMITE.
- **Rendern:** `ExportSettings` (Auflösung, Start/End-Tick, FPS, Codec, Ausgabe) landet in der `ExportJobQueue`. Es gibt **keine öffentliche API und kein CLI**.
- **Automatisierung, Stufe 1 (jetzt):** Wir schreiben die `editor_states`-Datei. Du öffnest das Replay; mit Flashbatch reicht dann *ein* Klick für alle Szenen.
- **Automatisierung, Stufe 2 (später):** Ein eigenes Client-Addon stößt die interne Export-Queue an. Das ist versionsspezifisch, greift auf Flashback-Interna zu und muss je Version getestet werden.

## 4. CineWolf AutoDirector

- MPL-2.0, Fabric, nur Client. Versionen: MC 26.2 (2.0.30) und 26.3 (2.0.34). Benötigt Flashback ≥ 0.41.1.
- **Kein öffentlich verlinktes Quellcode-Repository**, keine dokumentierte API für eigene Event-Detektoren.
- Funktionen:
  - Montage (In/Out, Preset, Analyse, editierbare Shot-Liste)
  - Einzel-Shots (Reveal, Crane, Spiral, Tracking, Chase, Close Detail)
  - Glättung und Prüfung lokaler Block-Kollisionen
  - schreibt **native Flashback-Keyframes**
- **Entscheidung:**
  - CineWolf bleibt das Werkzeug für die Feinarbeit im Editor (Kollisionen, Glättung).
  - Unsere Pipeline erzeugt ihre Kameras in **eigenen, getrennten Flashback-Szenen** („AC n: …“). Sie überschreibt nie CineWolf- oder Handarbeit.
  - Die Shot-Typen unseres Plans sind bewusst nach CineWolf benannt.
  - Ob das JAR Quellen oder Erweiterungspunkte enthält, prüfe ich unter Windows (offene Aufgabe A-7). Ein MPL-Fork ist rechtlich möglich, ergibt aber nur mit Quellcode Sinn.

## 5. Flashback-Addons (Modrinth)

| Addon | Lizenz | Versionen | Nutzen für uns |
|---|---|---|---|
| **Flashbatch** | MIT, Quellcode auf GitHub | 26.1–26.2 | stellt alle Szenen per Klick in die Export-Queue → **Stapel-Export unserer AC-Szenen** |
| MultiView | MIT | 26.1.2–26.3 | führt mehrere Aufnahmen derselben Sitzung zusammen. Sinnvoll, sobald mehrere Spieler aufnehmen (z. B. Schütze und Ziel). |
| Flashback Extras | ARR | 26.1.2–26.3 | Editor-Komfort, optional |
| Flashback Turbo | ARR | 26.1.2–26.3 | schnellere Exporte (Herstellerangabe, ungeprüft) |
| Flashback Settings | PolyForm-Noncommercial, Telemetrie (Opt-out) | 26.1.2–26.3 | **nicht empfohlen** (nicht-kommerzielle Lizenz für ein Werbeprojekt) |

## 6. Versionen – Entscheidung

- **Server:** Die `endernation`-Branch kompiliert gegen `paper-api 1.21.11`. Ob live schon 26.3 läuft, ist **offen (B2)**.
- **Client = Minecraft 26.2.** Das ist die einzige Version, für die Flashback (0.43.4), CineWolf (2.0.30), Flashbatch, MultiView **und** ViaFabricPlus (5.0.2) gleichzeitig verfügbar sind.
  - Die Verbindung zu einem 1.21.11-Server läuft clientseitig über ViaFabricPlus oder serverseitig über ViaVersion. Das muss getestet werden.
  - Mit 1.21.11 als Client wäre nur Flashback 0.39.9 möglich, **ohne** CineWolf.

## 7. Sniper-Projektilkamera – Machbarkeit

- Sniper laut `guns/Sniper.yml`: `bulletSpeed 4.75` Blöcke/Tick, `maxDistance 128`. Das ergibt etwa 27 Ticks (≈ 1,35 s) Flug bis zur Reichweite; danach fliegt das Projektil mit ¼ Geschwindigkeit weiter (`ai-dev` entfernt diese Restflüge).
- Das Projektil ist ein Snowball-Entity. Der Client sieht es nur innerhalb der Tracking-Reichweite des aufnehmenden Spielers. Positionsupdates kommen für Schneebälle nur in Intervallen; dazwischen rechnet der Client selbst. Die Flugbahn im Replay ist also eine **Client-Vorhersage**. Die genauen Werte hängen von der Server-Konfiguration ab und werden im Test bestätigt.
- **Folge:**
  - Die echte Flugbahn kommt aus dem Server-Recorder (Position pro Tick).
  - Ohne diese Daten meldet die Pipeline „Projektilkamera nicht verfügbar“. Das ist umgesetzt: `projectileCamera.available = false`, `reconstructed = true`.
  - Eine filmische Rekonstruktion bleibt optional und ist ausdrücklich gekennzeichnet.

## 8. Synchronisation Server ↔ Replay

| Option | Prinzip | Genauigkeit | Status |
|---|---|---|---|
| **S1 (empfohlen)** | Der Server schickt das Ereignis per Plugin-Message an den aufnehmenden Client. Das Client-Addon ruft `Recorder.addMarker` auf (öffentliche Methode in 0.43.x). | Tick-genau relativ zu dem, was der Client sieht. Die Latenz ist dieselbe wie bei den Weltpaketen. | Plan (Phase C), braucht Client-Addon |
| S2 | Flashback zeichnet Custom-Payload-Pakete mit auf; diese werden aus `cN.flashback` geparst. | tick-genau | möglich, aber protokollversionsabhängig |
| S3 | Zeitanker: ein Ereignis, das im Replay und im Server-Log bekannt ist → `assign_ticks` | ± Ping + Tick-Jitter | **umgesetzt** (`--anchor-tick/--anchor-ms`) |

## 9. Architektur

```
 Paper/Folia-Server                    Client (Prism, MC 26.2)               E:\AutoCinematic
 ┌──────────────────────┐  Plugin-   ┌───────────────────────────┐        ┌───────────────────────────┐
 │ SwornGuns (unverändert)│ Message   │ Flashback (Aufnahme/Render)│        │ autocinematic (Python)    │
 │ AutoCinematic Recorder ├──────────►│ AC-Client-Addon:           │ ZIP    │  events · flashback ·     │
 │  MONITOR-Listener,     │  (S1)     │  Marker setzen (S1),       ├───────►│  scenes · camera          │
 │  Flugbahn je Tick,     │           │  Kamera-Jobs laden,        │        │  → plan.json              │
 │  JSONL (Backup, S3)    │           │  Export anstoßen (Stufe 2) │◄───────┤  → editor_states/*.json   │
 └──────────────────────┘           └───────────────────────────┘ Key-   │ Musik (librosa) · FFmpeg · │
                                                                   frames │ Remotion → MP4 je Preset   │
                                                                           └───────────────────────────┘
```

Grundsätze dieser Architektur:
- Deterministische Programme übernehmen die Technik. Claude trifft nur kreative Entscheidungen.
- Ohne Freigabe gibt es keine kostenpflichtigen APIs.
- Fehlende Daten werden gemeldet und nicht erfunden.

## 10. In Phase A umgesetzt und getestet

Python-Paket `python/` (ohne Abhängigkeiten, getestet mit 56 Tests unter Python 3.11, 3.12 und 3.13):

- `events`: Ereignisschema v1 (`schema/combat-event.v1.schema.json`), Waffenklassen aus SwornGuns-Namen, JSONL (auch mit BOM unter Windows), Zeitanker-Synchronisation
- `flashback`:
  - liest Replays (ZIP oder Ordner)
  - schreibt Ereignis-Marker in eine **Kopie**; das Original ist per Test byte-gleich geprüft
  - fremde Marker bleiben erhalten und werden bei Kollision verschoben, ohne den exakten Tick im JSON zu verlieren
- `scenes`: Highlights (Sniper-Kill, Kopfschuss, Multi-Kill, Distanzschuss, Feuergefecht) mit Bewertung, Szenenbildung, Formate (short/tiktok/trailer/youtube/all), Zeitlupen-Abschnitte
- `camera`:
  - Plan → Flashback-`editor_states` (CAMERA, CAMERA_ORBIT, SPEED)
  - Orbit-Minimaltest um Marker-Positionen
  - schreibt nie ohne `--force` über einen vorhandenen Zustand; mit `--force` wird vorher gesichert
- `cli`: `info · extract · inject · plan · camera · demo`

**Nicht bewiesen** (braucht Windows und das Spiel):
- dass Flashback 0.43.4 die erzeugte `editor_states`-Datei lädt
- dass die Kamerawinkel im Bild stimmen
- dass der Export eine MP4 liefert

Das ist Phase B.

## 11. Blocker und benötigte Informationen

| # | Blocker | Was ich brauche |
|---|---|---|
| B1 | Claude hat keine Shell auf deinem PC (die lokale Arbeits-VM startet nicht). Alle Windows-Schritte laufen über Skripte, die du startest. | – (Workaround aktiv) |
| B2 | Unklar, welche SwornGuns-Branch und Serverversion live laufen (`endernation`: paper-api 1.21.11, Commit nennt 26.3). Wird `ai-dev` gemergt? | Antwort |
| B3 | Zum Bauen von Java-Plugins sind im Cloud-Container Maven Central, PaperMC und das EnderNation-Repo gesperrt. | Java-Builds laufen auf deinem PC |
| B4 | Für AutoCinematic gibt es kein GitHub-Repository. | Freigabe: `EnderNationTeam/autocinematic` (privat) anlegen, Entwicklungsbranch `dev` |
| B5 | Es gibt noch keine echte Flashback-Aufnahme. | eine Singleplayer-Aufnahme (Phase B), später eine PvP-Aufnahme |
| B6 | Der CineWolf-Quellcode ist nicht öffentlich. | Prüfung des JAR unter Windows |
| B7 | Das `editor_states`-Format wurde aus 0.43.6 abgeleitet; in 0.43.4 ist es noch unbestätigt. | Phase-B-Test |
| S | **Sicherheit:** `minecraft-server-enderguns/gradle.properties` enthält Repo-Zugangsdaten im Klartext. | Rotation empfohlen |

## 12. Nächster Schritt: Phase B (kleinster echter Kameratest)

1. `tools\Install-AutoCinematicTools.cmd` richtet Prism portable, die 26.2-Instanz, FFmpeg, uv und Python ein.
2. Instanz starten, eine Singleplayer-Welt öffnen und ca. 60 s mit Flashback aufnehmen. Dabei **einen Marker mit gespeicherter Position** setzen, dann speichern.
3. Kamera erzeugen:
   ```
   autocinematic camera --replay <replay.zip> --orbit-markers --flashback-dir E:\AutoCinematic\minecraft\launcher\instances\EnderNation-AutoCinematic\minecraft\flashback
   ```
4. In Flashback das Replay öffnen. Dort sollte die Szene „AC Orbit 1“ erscheinen. Exportieren mit 1920×1080 und 60 FPS nach `render\flashback-exports`.
5. `tools\Test-AutoCinematic.cmd -Replay <replay.zip>` ausführen und die MP4 mit ffprobe prüfen. Abnahme erst danach.
