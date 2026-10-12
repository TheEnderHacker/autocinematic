"""Kommandozeile: `autocinematic <befehl>` bzw. `python -m autocinematic <befehl>`."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from . import __version__
from .camera import CameraError
from .events import EventError, assign_ticks, read_jsonl, sort_events, write_jsonl
from .flashback import COLOUR_SCENE, Marker, ReplayError, merge_markers, read_replay, write_replay_with_markers
from .scenes import FORMATS, make_plan


def _print_json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _load_events(args) -> list:
    events = []
    if getattr(args, "replay", None):
        events.extend(read_replay(args.replay).events())
    if getattr(args, "events", None):
        events.extend(read_jsonl(args.events))
    if getattr(args, "anchor_tick", None) is not None:
        if args.anchor_ms is None:
            raise EventError("--anchor-tick braucht auch --anchor-ms")
        events = assign_ticks(events, args.anchor_tick, args.anchor_ms)
    return sort_events(events)


def cmd_info(args) -> int:
    info = read_replay(args.replay)
    data = info.summary()
    data["eventCounts"] = {t: sum(1 for e in info.events() if e.type == t) for t in ("shot", "hit", "kill")}
    _print_json(data)
    return 0


def cmd_extract(args) -> int:
    events = read_replay(args.replay).events()
    n = write_jsonl(args.out, sort_events(events))
    print(f"{n} Ereignisse -> {args.out}")
    return 0


def cmd_inject(args) -> int:
    info = read_replay(args.replay)
    events = read_jsonl(args.events)
    if args.anchor_tick is not None:
        if args.anchor_ms is None:
            raise EventError("--anchor-tick braucht auch --anchor-ms")
        events = assign_ticks(events, args.anchor_tick, args.anchor_ms)
    types = ["hit", "kill"] + (["shot"] if args.include_shots else [])
    extra = []
    if args.plan:
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        for sc in plan.get("scenes", []):
            extra.append(Marker(tick=sc["startTick"], colour=COLOUR_SCENE,
                                description=f"Szene {sc['id']} Start: {sc['label']}"))
            extra.append(Marker(tick=sc["endTick"], colour=COLOUR_SCENE, description=f"Szene {sc['id']} Ende"))
    markers, stats = merge_markers(info.markers, events, include_types=types, extra_markers=extra)
    out = write_replay_with_markers(args.replay, args.out, markers)
    print(json.dumps({"out": str(out), **stats}, ensure_ascii=False))
    return 0


def cmd_plan(args) -> int:
    events = _load_events(args)
    total = args.total_ticks
    replay = {}
    if args.replay:
        info = read_replay(args.replay)
        total = total or info.total_ticks
        replay = {"name": info.name, "uuid": info.uuid, "path": str(info.path), "totalTicks": info.total_ticks}
    plan = make_plan(events, fmt=args.format, total_ticks=total, replay=replay)
    text = json.dumps(plan, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"{len(plan['scenes'])} Szenen, ca. {plan['estimatedOutputSeconds']} s -> {args.out}")
    else:
        print(text)
    return 0


def cmd_camera(args) -> int:
    from .camera import (CameraError, build_editor_state, editor_state_path, make_editor_state,
                         orbit_scene_for_marker, write_editor_state)
    info = read_replay(args.replay)
    if not info.uuid:
        raise CameraError("Replay hat keine UUID - Flashback kann den Editorzustand nicht zuordnen")
    if args.orbit_markers:
        scenes, reports = [], []
        for tick, m in sorted(info.markers.items()):
            if m.position is None:
                continue
            scenes.append(orbit_scene_for_marker(tick, m.position, total_ticks=info.total_ticks,
                                                 name=f"AC Orbit {len(scenes) + 1}: {m.description or 'Marker'}"[:60]))
            reports.append({"tick": tick, "position": m.position, "description": m.description})
        if not scenes:
            raise CameraError("Kein Marker mit gespeicherter Position gefunden. In Flashback beim Aufnehmen "
                              "einen Marker MIT Position setzen (Marker-Optionen: 'Save position').")
        state, report = make_editor_state(scenes), {"mode": "orbit-markers", "scenes": reports}
    else:
        events = sort_events(info.events() + (read_jsonl(args.events) if args.events else []))
        if args.plan:
            plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        else:
            plan = make_plan(events, fmt="all", total_ticks=info.total_ticks)
        state, report = build_editor_state(info, plan, events)
    if args.flashback_dir:
        target = editor_state_path(args.flashback_dir, info.uuid)
    elif args.out:
        target = Path(args.out)
    else:
        raise CameraError("--flashback-dir (Flashback-Datenordner der Instanz) oder -o angeben")
    written = write_editor_state(state, target, force=args.force)
    report.update(written)
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _print_json({"written": written["path"], "backup": written["backup"],
                 "scenes": len(state["scenes"]),
                 "problems": [p for s in report.get("scenes", []) if isinstance(s, dict) for p in s.get("problems", [])]})
    return 0


def cmd_demo(args) -> int:
    from .demo import demo_events, write_demo_replay
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    replay = write_demo_replay(out / "demo-replay.zip")
    write_jsonl(out / "demo-events.jsonl", demo_events())
    print(f"Demo erzeugt: {replay} und {out / 'demo-events.jsonl'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="autocinematic", description="EnderNation AutoCinematic - Replay-Analyse")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("info", help="Metadaten und Marker eines Flashback-Replays anzeigen")
    s.add_argument("replay")
    s.set_defaults(func=cmd_info)

    s = sub.add_parser("extract", help="AutoCinematic-Ereignisse aus Replay-Markern als JSONL exportieren")
    s.add_argument("replay")
    s.add_argument("-o", "--out", required=True)
    s.set_defaults(func=cmd_extract)

    s = sub.add_parser("inject", help="Ereignisse (JSONL) als Marker in eine KOPIE des Replays schreiben")
    s.add_argument("replay")
    s.add_argument("--events", required=True)
    s.add_argument("-o", "--out", required=True)
    s.add_argument("--include-shots", action="store_true", help="auch einzelne Schuesse markieren")
    s.add_argument("--plan", help="Szenen aus plan.json zusaetzlich als blaue Marker setzen")
    s.add_argument("--anchor-tick", type=int)
    s.add_argument("--anchor-ms", type=int)
    s.set_defaults(func=cmd_inject)

    s = sub.add_parser("plan", help="Highlights erkennen und Schnittplan erzeugen")
    s.add_argument("--replay")
    s.add_argument("--events")
    s.add_argument("--format", default="short", choices=sorted(FORMATS))
    s.add_argument("--total-ticks", type=int)
    s.add_argument("--anchor-tick", type=int)
    s.add_argument("--anchor-ms", type=int)
    s.add_argument("-o", "--out")
    s.set_defaults(func=cmd_plan)

    s = sub.add_parser("camera", help="Kamerafahrten als Flashback-Editorzustand (Keyframes) schreiben")
    s.add_argument("--replay", required=True)
    s.add_argument("--plan", help="plan.json (sonst: alle erkannten Szenen)")
    s.add_argument("--events", help="zusaetzliche Ereignisse (JSONL)")
    s.add_argument("--orbit-markers", action="store_true",
                   help="Minimaltest: Orbit um jeden Marker mit gespeicherter Position")
    s.add_argument("--flashback-dir", help="z. B. ...\\instances\\<name>\\minecraft\\flashback")
    s.add_argument("-o", "--out", help="statt --flashback-dir: Zieldatei")
    s.add_argument("--force", action="store_true", help="vorhandenen Editorzustand ersetzen (mit Sicherung)")
    s.add_argument("--report", help="Bericht (JSON) mit Warnungen pro Einstellung")
    s.set_defaults(func=cmd_camera)

    s = sub.add_parser("demo", help="Synthetisches Test-Replay + Ereignisse erzeugen")
    s.add_argument("-o", "--out", required=True)
    s.set_defaults(func=cmd_demo)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "plan" and not (args.replay or args.events):
        print("Fehler: --replay und/oder --events angeben", file=sys.stderr)
        return 2
    try:
        return args.func(args)
    except (ReplayError, EventError, CameraError, OSError, ValueError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
