"""Lesen und Ergaenzen von Flashback-Replays.

Ein Flashback-Replay ist ein ZIP (oder ein entpackter Aufnahmeordner) mit
`metadata.json` im Wurzelverzeichnis. Darin stehen u. a. `total_ticks` und
`markers` = {"<tick>": {"colour": int, "position": {"position": [x,y,z],
"dimension": "..."}, "description": "..."}} (pro Tick genau ein Marker).

AutoCinematic legt Ereignisse als Marker ab. Der maschinenlesbare Teil steht
in der Beschreibung als `[[AC1 {...}]]` bzw. `[[AC1 [{...},{...}]]]`.

Das Original-Replay wird NIE veraendert: `write_replay_with_markers` schreibt
immer eine neue Datei.
"""
from __future__ import annotations

import json
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from .events import SCHEMA_VERSION, TICKS_PER_SECOND, CombatEvent, EventError

METADATA = "metadata.json"
TAG_RE = re.compile(r"\[\[AC(\d+) (.+?)\]\]\s*$", re.S)

COLOUR_SHOT = 0x9E9E9E
COLOUR_HIT = 0xFB8C00
COLOUR_KILL = 0xE53935
COLOUR_HIGHLIGHT = 0xFFC107  # Sniper- oder Kopfschuss-Kill
COLOUR_SCENE = 0x1E88E5


class ReplayError(Exception):
    pass


@dataclass
class Marker:
    tick: int
    colour: int = 0xFFFFFF
    description: Optional[str] = None
    position: Optional[tuple[float, float, float]] = None
    dimension: Optional[str] = None

    @classmethod
    def from_json(cls, tick: int, data: dict) -> "Marker":
        pos = dim = None
        p = data.get("position")
        if isinstance(p, dict) and p.get("position") is not None:
            pos = tuple(float(c) for c in p["position"])  # type: ignore[assignment]
            dim = p.get("dimension")
        return cls(tick=tick, colour=int(data.get("colour", 0xFFFFFF)),
                   description=data.get("description"), position=pos, dimension=dim)

    def to_json(self) -> dict:
        d: dict = {"colour": int(self.colour)}
        if self.position is not None:
            d["position"] = {"position": [float(c) for c in self.position],
                             "dimension": self.dimension or "minecraft:overworld"}
        if self.description is not None:
            d["description"] = self.description
        return d

    @property
    def is_autocinematic(self) -> bool:
        return bool(self.description and TAG_RE.search(self.description))

    def events(self) -> list[CombatEvent]:
        """Liest die im Marker eingebetteten AutoCinematic-Ereignisse."""
        if not self.description:
            return []
        m = TAG_RE.search(self.description)
        if not m:
            return []
        if int(m.group(1)) != SCHEMA_VERSION:
            raise EventError(f"Marker bei Tick {self.tick}: Schema-Version AC{m.group(1)} nicht unterstuetzt")
        try:
            payload = json.loads(m.group(2))
        except json.JSONDecodeError as exc:
            raise EventError(f"Marker bei Tick {self.tick}: defektes JSON ({exc})") from None
        items = payload if isinstance(payload, list) else [payload]
        out = []
        for item in items:
            ev = CombatEvent.from_dict(item)
            if ev.tick is None:
                ev.tick = self.tick
            out.append(ev)
        return out


@dataclass
class ReplayInfo:
    path: Path
    raw: dict
    markers: dict[int, Marker] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.raw.get("name", "Unnamed")

    @property
    def uuid(self) -> Optional[str]:
        return self.raw.get("uuid")

    @property
    def total_ticks(self) -> Optional[int]:
        t = self.raw.get("total_ticks")
        if t is None:  # Fallback: Summe der Chunk-Laengen
            chunks = self.raw.get("chunks") or {}
            s = sum(int(c.get("duration", 0)) for c in chunks.values() if isinstance(c, dict))
            return s or None
        return int(t)

    @property
    def duration_seconds(self) -> Optional[float]:
        t = self.total_ticks
        return None if t is None else t / TICKS_PER_SECOND

    @property
    def version_string(self) -> Optional[str]:
        return self.raw.get("version_string")

    @property
    def world_name(self) -> Optional[str]:
        return self.raw.get("world_name")

    def events(self) -> list[CombatEvent]:
        out: list[CombatEvent] = []
        for tick in sorted(self.markers):
            out.extend(self.markers[tick].events())
        return out

    def summary(self) -> dict:
        ac = sum(1 for m in self.markers.values() if m.is_autocinematic)
        return {
            "path": str(self.path),
            "name": self.name,
            "uuid": self.uuid,
            "version": self.version_string,
            "world": self.world_name,
            "totalTicks": self.total_ticks,
            "durationSeconds": self.duration_seconds,
            "markers": len(self.markers),
            "autocinematicMarkers": ac,
            "mods": sorted((self.raw.get("mod_versions") or {}).keys()),
        }


# ------------------------------------------------------------------- Lesen
def _parse_meta(path: Path, text: str) -> ReplayInfo:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ReplayError(f"{path}: metadata.json ist kein gueltiges JSON ({exc})") from None
    if not isinstance(raw, dict) or "uuid" not in raw:
        raise ReplayError(f"{path}: metadata.json ist keine Flashback-Metadatei (Feld 'uuid' fehlt)")
    markers: dict[int, Marker] = {}
    for key, value in (raw.get("markers") or {}).items():
        try:
            tick = int(key)
        except ValueError:
            continue
        if isinstance(value, dict):
            markers[tick] = Marker.from_json(tick, value)
    return ReplayInfo(path=path, raw=raw, markers=markers)


def read_replay(path: str | Path) -> ReplayInfo:
    """Liest ein Flashback-Replay (.zip oder Ordner mit metadata.json)."""
    p = Path(path)
    if p.is_dir():
        meta = p / METADATA
        if not meta.is_file():
            raise ReplayError(f"{p}: keine {METADATA} gefunden")
        return _parse_meta(p, meta.read_text(encoding="utf-8"))
    if not p.is_file():
        raise ReplayError(f"{p}: Datei nicht gefunden")
    if not zipfile.is_zipfile(p):
        raise ReplayError(f"{p}: keine ZIP-Datei")
    with zipfile.ZipFile(p) as zf:
        try:
            text = zf.read(METADATA).decode("utf-8")
        except KeyError:
            raise ReplayError(f"{p}: {METADATA} fehlt im ZIP") from None
    return _parse_meta(p, text)


# --------------------------------------------------------------- Schreiben
def event_colour(ev: CombatEvent) -> int:
    if ev.type == "kill":
        return COLOUR_HIGHLIGHT if (ev.weapon_class == "sniper" or ev.headshot) else COLOUR_KILL
    if ev.type == "hit":
        return COLOUR_HIT
    return COLOUR_SHOT


def build_marker(tick: int, events: list[CombatEvent]) -> Marker:
    """Ein Marker fuer alle Ereignisse eines Ticks (Flashback erlaubt nur einen pro Tick)."""
    rank = {"kill": 2, "hit": 1, "shot": 0}
    main = max(events, key=lambda e: (rank[e.type], e.headshot, e.distance or 0))
    label = main.label()
    if len(events) > 1:
        label += f" (+{len(events) - 1})"
    payload = [e.to_dict() for e in events]
    body = payload[0] if len(payload) == 1 else payload
    desc = f"{label} [[AC{SCHEMA_VERSION} {json.dumps(body, ensure_ascii=False, separators=(',', ':'))}]]"
    pos = main.target_pos if main.type != "shot" and main.target_pos else main.pos
    return Marker(tick=tick, colour=event_colour(main), description=desc,
                  position=pos, dimension=main.dimension if pos else None)


def merge_markers(existing: dict[int, Marker], events: Iterable[CombatEvent],
                  *, include_types: Iterable[str] = ("hit", "kill"),
                  replace_autocinematic: bool = True, max_shift: int = 10,
                  extra_markers: Iterable[Marker] = ()) -> tuple[dict[int, Marker], dict]:
    """Fuegt Ereignis-Marker zu vorhandenen Markern hinzu.

    - Fremde (manuell gesetzte) Marker bleiben immer erhalten.
    - Ist ein Tick schon von einem fremden Marker belegt, wird der neue Marker
      bis zu `max_shift` Ticks verschoben; der exakte Tick steht weiterhin im JSON.
    """
    include = set(include_types)
    result: dict[int, Marker] = {
        t: m for t, m in existing.items() if not (replace_autocinematic and m.is_autocinematic)
    }
    grouped: dict[int, list[CombatEvent]] = {}
    skipped_no_tick = 0
    for ev in events:
        if ev.type not in include:
            continue
        if ev.tick is None:
            skipped_no_tick += 1
            continue
        grouped.setdefault(ev.tick, []).append(ev)

    stats = {"written": 0, "shifted": 0, "dropped": 0, "skippedNoTick": skipped_no_tick}
    pending: list[tuple[int, Marker]] = [(t, build_marker(t, evs)) for t, evs in sorted(grouped.items())]
    pending += [(m.tick, m) for m in extra_markers]
    for tick, marker in pending:
        placed = None
        for delta in [0] + [d for k in range(1, max_shift + 1) for d in (k, -k)]:
            cand = tick + delta
            if cand >= 0 and cand not in result:
                placed = cand
                break
        if placed is None:
            stats["dropped"] += 1
            continue
        if placed != tick:
            stats["shifted"] += 1
        marker.tick = placed
        result[placed] = marker
        stats["written"] += 1
    return dict(sorted(result.items())), stats


def write_replay_with_markers(src: str | Path, dst: str | Path, markers: dict[int, Marker]) -> Path:
    """Kopiert ein Replay-ZIP nach `dst` und ersetzt dort nur die Marker in metadata.json."""
    src_p, dst_p = Path(src).resolve(), Path(dst).resolve()
    if src_p == dst_p:
        raise ReplayError("Ziel darf nicht das Original sein - das Original wird nie veraendert")
    if not zipfile.is_zipfile(src_p):
        raise ReplayError(f"{src_p}: keine ZIP-Datei (entpackte Ordner bitte vorher zippen)")
    dst_p.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst_p.with_name(dst_p.name + ".part")
    with zipfile.ZipFile(src_p) as zin:
        raw = json.loads(zin.read(METADATA).decode("utf-8"))
        if markers:
            raw["markers"] = {str(t): m.to_json() for t, m in sorted(markers.items())}
        else:
            raw.pop("markers", None)
        with zipfile.ZipFile(tmp, "w") as zout:
            for info in zin.infolist():
                if info.filename == METADATA:
                    zi = zipfile.ZipInfo(METADATA, date_time=info.date_time)
                    zi.compress_type = zipfile.ZIP_DEFLATED
                    zout.writestr(zi, json.dumps(raw, ensure_ascii=False, indent=2).encode("utf-8"))
                    continue
                with zin.open(info) as fin, zout.open(info, "w") as fout:
                    shutil.copyfileobj(fin, fout, 1024 * 1024)
    tmp.replace(dst_p)
    return dst_p
