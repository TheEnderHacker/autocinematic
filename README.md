# EnderNation AutoCinematic

Automatische Cinematic- und Trailer-Produktion aus Minecraft-Flashback-Replays für EnderNation.

Stand: **Phase A abgeschlossen** (Bestand und Machbarkeit, Analysekern). Phase B (echter Flashback-Kameratest) steht als Nächstes an.
Die Details stehen in [`docs/PHASE-A.md`](docs/PHASE-A.md); der laufende Stand steht in [`HANDOFF.md`](HANDOFF.md).

## Inhalt

| Pfad | Inhalt |
|---|---|
| `python/` | Analysekern `autocinematic`: Ereignisse, Flashback-Replays, Szenenerkennung, Kamera → Flashback-Keyframes |
| `schema/` | JSON-Schema der Kampfereignisse (v1) |
| `docs/` | Phase-A-Bericht, Architektur, Blocker |

## Schnellstart (Windows, E:\AutoCinematic)

```bat
E:\AutoCinematic\tools\Install-AutoCinematicTools.cmd   :: einmalig: uv, FFmpeg, Prism, Instanz, Python
E:\AutoCinematic\tools\Test-AutoCinematic.cmd           :: Selbsttest, Protokoll in logs\
```

Danach kannst du in der AutoCinematic-Konsole (`env\Start-AutoCinematicShell.cmd`) folgende Befehle verwenden:

```bat
autocinematic info   <replay.zip>
autocinematic plan   --replay <replay.zip> --format short -o plan.json
autocinematic camera --replay <replay.zip> --plan plan.json --flashback-dir <instanz>\minecraft\flashback
autocinematic camera --replay <replay.zip> --orbit-markers --flashback-dir <instanz>\minecraft\flashback
```

## Tests

```bat
cd python
python -m pytest
```
