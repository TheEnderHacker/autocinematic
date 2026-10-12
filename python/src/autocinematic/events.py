"""Kampfereignisse (Schema v1) fuer EnderNation AutoCinematic.

Ein Ereignis beschreibt einen Schuss, Treffer oder Kill aus EnderGuns/SwornGuns.
Quelle ist entweder das Server-Plugin (JSONL-Log) oder ein Flashback-Marker
im Replay. Die Zeit wird bevorzugt als Replay-Tick angegeben (20 Ticks = 1 s).
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Optional, Sequence

SCHEMA_VERSION = 1
TICKS_PER_SECOND = 20
EVENT_TYPES = ("shot", "hit", "kill")
# Zusatzzeilen des Server-Recorders (Flugbahnen, Sitzungsinfos) - werden von read_jsonl uebersprungen
AUX_TYPES = ("trajectory", "session")
WEAPON_CLASSES = ("sniper", "rifle", "shotgun", "pistol", "explosive", "flame", "melee", "other")

Vec3 = tuple[float, float, float]

_COLOR_CODES = re.compile(r"[&§][0-9a-fk-orA-FK-OR]")

# Reihenfolge ist wichtig: spezifischere Muster zuerst.
_WEAPON_PATTERNS: Sequence[tuple[str, tuple[str, ...]]] = (
    ("sniper", ("sniper", "awp", "scout", "kar98", "marksman", "dmr")),
    ("shotgun", ("shotgun", "doublebarrel", "double_barrel", "double barrel", "autoshotgun")),
    ("explosive", ("rocket", "grenade", "launcher", "rpg", "molotov", "flashbang", "c4", "bazooka")),
    ("flame", ("flame", "fire")),
    ("pistol", ("pistol", "revolver", "deagle", "glock", "handgun")),
    ("rifle", ("rifle", "ak", "m4", "smg", "mp5", "uzi", "minigun", "lmg", "carbine")),
    ("melee", ("knife", "sword", "axe", "melee")),
)


class EventError(ValueError):
    """Ungueltiges Ereignis oder ungueltige Ereignisdatei."""


def strip_color_codes(text: str) -> str:
    return _COLOR_CODES.sub("", text).strip()


def classify_weapon(name: Optional[str]) -> Optional[str]:
    """Ordnet einen Waffennamen (z. B. '&eSniper', 'RocketLauncher') einer Waffenklasse zu."""
    if not name:
        return None
    n = strip_color_codes(name).lower()
    for cls, keys in _WEAPON_PATTERNS:
        for k in keys:
            if len(k) <= 2:
                if re.search(rf"(?<![a-z]){re.escape(k)}(?![a-z])", n):
                    return cls
            elif k in n:
                return cls
    return "other"


@dataclass(frozen=True)
class Player:
    name: str
    uuid: Optional[str] = None

    def to_dict(self) -> dict:
        d = {"name": self.name}
        if self.uuid:
            d["uuid"] = self.uuid
        return d

    @classmethod
    def from_any(cls, value) -> Optional["Player"]:
        if value is None:
            return None
        if isinstance(value, Player):
            return value
        if isinstance(value, str):
            return cls(name=value)
        if isinstance(value, dict) and value.get("name"):
            return cls(name=str(value["name"]), uuid=value.get("uuid"))
        raise EventError(f"Ungueltiger Spieler: {value!r}")

    @property
    def key(self) -> str:
        return (self.uuid or self.name).lower()


def _vec(value) -> Optional[Vec3]:
    if value is None:
        return None
    if isinstance(value, dict):
        value = (value.get("x"), value.get("y"), value.get("z"))
    try:
        x, y, z = (float(v) for v in value)
    except (TypeError, ValueError):
        raise EventError(f"Ungueltige Position: {value!r}") from None
    return (x, y, z)


@dataclass
class CombatEvent:
    type: str
    tick: Optional[int] = None
    time_ms: Optional[int] = None
    shooter: Optional[Player] = None
    target: Optional[Player] = None
    weapon: Optional[str] = None
    weapon_class: Optional[str] = None
    distance: Optional[float] = None
    headshot: bool = False
    damage: Optional[float] = None
    lethal: bool = False
    pos: Optional[Vec3] = None
    target_pos: Optional[Vec3] = None
    dimension: Optional[str] = None
    extra: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.type not in EVENT_TYPES:
            raise EventError(f"Unbekannter Ereignistyp {self.type!r} (erlaubt: {', '.join(EVENT_TYPES)})")
        if self.tick is not None:
            self.tick = int(self.tick)
            if self.tick < 0:
                raise EventError("tick darf nicht negativ sein")
        if self.weapon is not None:
            self.weapon = strip_color_codes(self.weapon)
        if self.weapon_class is None:
            self.weapon_class = classify_weapon(self.weapon)
        elif self.weapon_class not in WEAPON_CLASSES:
            raise EventError(f"Unbekannte Waffenklasse {self.weapon_class!r}")
        self.pos = _vec(self.pos)
        self.target_pos = _vec(self.target_pos)
        if self.distance is None and self.pos and self.target_pos:
            self.distance = math.dist(self.pos, self.target_pos)
        if self.type == "kill":
            self.lethal = True

    # ------------------------------------------------------------------ Zeit
    @property
    def seconds(self) -> Optional[float]:
        return None if self.tick is None else self.tick / TICKS_PER_SECOND

    # --------------------------------------------------------------- Ausgabe
    def label(self) -> str:
        """Kurze, lesbare Beschreibung (deutsch) fuer Marker und Logs."""
        who = self.shooter.name if self.shooter else "?"
        tgt = f" -> {self.target.name}" if self.target else ""
        parts = []
        if self.weapon:
            parts.append(self.weapon)
        if self.distance is not None:
            parts.append(f"{self.distance:.0f} m")
        if self.headshot:
            parts.append("Kopfschuss")
        detail = f" ({', '.join(parts)})" if parts else ""
        title = {"shot": "Schuss", "hit": "Treffer", "kill": "Kill"}[self.type]
        return f"{title}: {who}{tgt}{detail}"

    def to_dict(self) -> dict:
        d: dict = {"v": SCHEMA_VERSION, "type": self.type}
        if self.tick is not None:
            d["tick"] = self.tick
        if self.time_ms is not None:
            d["t"] = self.time_ms
        if self.shooter:
            d["shooter"] = self.shooter.to_dict()
        if self.target:
            d["target"] = self.target.to_dict()
        if self.weapon:
            d["weapon"] = self.weapon
        if self.weapon_class:
            d["weaponClass"] = self.weapon_class
        if self.distance is not None:
            d["distance"] = round(self.distance, 2)
        if self.headshot:
            d["headshot"] = True
        if self.damage is not None:
            d["damage"] = round(self.damage, 2)
        if self.lethal and self.type != "kill":
            d["lethal"] = True
        if self.pos:
            d["pos"] = [round(c, 2) for c in self.pos]
        if self.target_pos:
            d["targetPos"] = [round(c, 2) for c in self.target_pos]
        if self.dimension:
            d["dim"] = self.dimension
        if self.extra:
            d["extra"] = self.extra
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "CombatEvent":
        if not isinstance(d, dict):
            raise EventError(f"Ereignis muss ein Objekt sein, nicht {type(d).__name__}")
        v = d.get("v", SCHEMA_VERSION)
        if v != SCHEMA_VERSION:
            raise EventError(f"Nicht unterstuetzte Schema-Version {v} (erwartet {SCHEMA_VERSION})")
        if "type" not in d:
            raise EventError("Feld 'type' fehlt")
        return cls(
            type=d["type"],
            tick=d.get("tick"),
            time_ms=d.get("t"),
            shooter=Player.from_any(d.get("shooter")),
            target=Player.from_any(d.get("target")),
            weapon=d.get("weapon"),
            weapon_class=d.get("weaponClass"),
            distance=None if d.get("distance") is None else float(d["distance"]),
            headshot=bool(d.get("headshot", False)),
            damage=None if d.get("damage") is None else float(d["damage"]),
            lethal=bool(d.get("lethal", False)),
            pos=d.get("pos"),
            target_pos=d.get("targetPos"),
            dimension=d.get("dim"),
            extra=dict(d.get("extra") or {}),
        )


# ---------------------------------------------------------------------- JSONL
def read_jsonl(path: str | Path) -> list[CombatEvent]:
    events: list[CombatEvent] = []
    with open(path, encoding="utf-8-sig") as fh:
        for no, line in enumerate(fh, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                rec = json.loads(line)
                if isinstance(rec, dict) and rec.get("type") in AUX_TYPES:
                    continue
                events.append(CombatEvent.from_dict(rec))
            except (json.JSONDecodeError, EventError) as exc:
                raise EventError(f"{path}:{no}: {exc}") from None
    return events


def write_jsonl(path: str | Path, events: Iterable[CombatEvent]) -> int:
    n = 0
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for ev in events:
            fh.write(json.dumps(ev.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n")
            n += 1
    return n


# -------------------------------------------------------------- Synchronisation
def assign_ticks(events: Iterable[CombatEvent], anchor_tick: int, anchor_ms: int,
                 tps: float = TICKS_PER_SECOND, overwrite: bool = False) -> list[CombatEvent]:
    """Berechnet Replay-Ticks aus Server-Zeitstempeln (ms) ueber einen Ankerpunkt.

    Anker = ein Moment, dessen Replay-Tick und Server-Zeit beide bekannt sind
    (z. B. ein Kill, der im Replay als Marker sichtbar ist).
    Ereignisse vor Replay-Beginn (negativer Tick) werden verworfen.
    """
    out: list[CombatEvent] = []
    for ev in events:
        if ev.tick is None or overwrite:
            if ev.time_ms is None:
                raise EventError("Ereignis ohne tick und ohne Zeitstempel 't' kann nicht synchronisiert werden")
            tick = anchor_tick + round((ev.time_ms - anchor_ms) * tps / 1000.0)
            if tick < 0:
                continue
            ev.tick = tick
        out.append(ev)
    return out


def sort_events(events: Iterable[CombatEvent]) -> list[CombatEvent]:
    order = {"shot": 0, "hit": 1, "kill": 2}
    return sorted(events, key=lambda e: (e.tick if e.tick is not None else -1, order[e.type]))


def iter_kills(events: Iterable[CombatEvent]) -> Iterator[CombatEvent]:
    return (e for e in events if e.type == "kill")
