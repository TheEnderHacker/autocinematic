"""Liest Bewegungsdaten direkt aus Flashback-Aufnahmen (cN.flashback).

Format (aus dem Flashback-Quelltext, ReplayReader/Recorder 0.43.x):
  int    magic 0xD780E884                      (big-endian, wie Netty/FriendlyByteBuf)
  varint Anzahl Aktionstypen, danach je ein Identifier (varint Laenge + UTF-8)
  int    Groesse des Snapshots, Snapshot-Aktionen, danach die Aktionen
  Aktion: varint Typ-Index, int Laenge, Nutzdaten

Ausgewertet werden nur:
  flashback:action/next_tick                         -> Tick + 1
  flashback:action/create_local_player               -> UUID + Startposition des Aufnehmenden
  flashback:action/accurate_player_position_optional -> genaue Position des Aufnehmenden pro Tick
Alle anderen Aktionen (Pakete, Chunks) werden ueberlesen, nicht interpretiert.
"""
from __future__ import annotations

import math
import struct
import uuid as uuidlib
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

MAGIC = 0xD780E884
A_NEXT_TICK = "flashback:action/next_tick"
A_LOCAL_PLAYER = "flashback:action/create_local_player"
A_ACCURATE_POS = "flashback:action/accurate_player_position_optional"


class ReplayDataError(Exception):
    pass


@dataclass
class Sample:
    tick: int
    x: float
    y: float
    z: float
    yaw: float
    pitch: float

    @property
    def pos(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


@dataclass
class PlayerTrack:
    uuid: Optional[str] = None
    samples: list[Sample] = field(default_factory=list)
    total_ticks: int = 0
    entity_id: Optional[int] = None
    dimension: Optional[str] = None
    accurate: list[Sample] = field(default_factory=list)
    clock: list[tuple[int, int]] = field(default_factory=list)  # (Tick, Unix-ms) aus real_time_clock

    def tick_for_epoch_ms(self, ms: int) -> Optional[int]:
        """Replay-Tick zu einem Zeitpunkt (Unix-ms), linear zwischen Uhr-Stuetzpunkten."""
        if not self.clock:
            return None
        # Flashback-Modell: zwischen zwei Uhr-Eintraegen vergehen genau 50 ms pro Tick.
        base = self.clock[0]
        for pt in self.clock:
            if pt[1] <= ms:
                base = pt
            else:
                break
        tick = base[0] + round((ms - base[1]) / 50)
        nxt = next((pt for pt in self.clock if pt[0] > base[0]), None)
        if nxt is not None and ms >= base[1]:
            tick = min(tick, nxt[0])
        return tick

    def at(self, tick: int) -> Optional[Sample]:
        """Letzte bekannte Position bis einschliesslich `tick` (binaere Suche)."""
        lo, hi, best = 0, len(self.samples) - 1, None
        while lo <= hi:
            mid = (lo + hi) // 2
            if self.samples[mid].tick <= tick:
                best, lo = self.samples[mid], mid + 1
            else:
                hi = mid - 1
        return best


class _Buf:
    def __init__(self, data: bytes, pos: int = 0, end: Optional[int] = None):
        self.d, self.p, self.end = data, pos, len(data) if end is None else end

    def need(self, n: int) -> None:
        if self.p + n > self.end:
            raise ReplayDataError(f"Unerwartetes Dateiende bei Byte {self.p}")

    def int_(self) -> int:
        self.need(4)
        v = struct.unpack_from(">i", self.d, self.p)[0]
        self.p += 4
        return v

    def varint(self) -> int:
        result = shift = 0
        while True:
            self.need(1)
            b = self.d[self.p]
            self.p += 1
            result |= (b & 0x7F) << shift
            if not b & 0x80:
                break
            shift += 7
            if shift > 35:
                raise ReplayDataError("VarInt zu lang")
        return result - (1 << 32) if result & (1 << 31) else result

    def string(self) -> str:
        n = self.varint()
        self.need(n)
        s = self.d[self.p:self.p + n].decode("utf-8")
        self.p += n
        return s

    def double(self) -> float:
        self.need(8)
        v = struct.unpack_from(">d", self.d, self.p)[0]
        self.p += 8
        return v

    def float_(self) -> float:
        self.need(4)
        v = struct.unpack_from(">f", self.d, self.p)[0]
        self.p += 4
        return v

    def uuid(self) -> str:
        self.need(16)
        v = str(uuidlib.UUID(bytes=bytes(self.d[self.p:self.p + 16])))
        self.p += 16
        return v


A_MOVE_ENTITIES = "flashback:action/move_entities"
A_CLOCK = "flashback:action/real_time_clock_optional"


@dataclass
class _State:
    track: "PlayerTrack"
    start: Optional[Sample] = None
    entity_moves: dict = field(default_factory=dict)  # Entity-ID -> [Sample]
    entity_dim: dict = field(default_factory=dict)
    clock_ms: Optional[int] = None


def _parse_chunk(data: bytes, start_tick: int, st: _State) -> int:
    b = _Buf(data)
    if (b.int_() & 0xFFFFFFFF) != MAGIC:
        raise ReplayDataError("Keine Flashback-Chunkdatei (Magic falsch)")
    names = [b.string() for _ in range(b.varint())]
    snapshot_size = b.int_()
    snapshot_end = b.p + snapshot_size
    tick = start_tick
    while b.p < len(data):
        in_snapshot = b.p < snapshot_end
        idx = b.varint()
        size = b.int_()
        if idx < 0 or idx >= len(names) or size < 0:
            raise ReplayDataError(f"Defekte Aktion bei Byte {b.p}")
        b.need(size)
        name, payload_start = names[idx], b.p
        p = _Buf(data, payload_start, payload_start + size)
        if name == A_NEXT_TICK and not in_snapshot:
            tick += 1
            if st.clock_ms is not None:
                st.clock_ms += 50  # Flashback sagt pro Tick +50 ms voraus und speichert nur Abweichungen
        elif name == A_LOCAL_PLAYER:
            st.track.uuid = p.uuid()
            x, y, z = p.double(), p.double(), p.double()
            pitch, yaw = p.float_(), p.float_()
            st.start = Sample(tick, x, y, z, yaw, pitch)
        elif name == A_ACCURATE_POS:
            p.varint()  # Entity-ID
            if p.varint() > 0:
                x, y, z, yaw, pitch = p.double(), p.double(), p.double(), p.float_(), p.float_()
                st.track.accurate.append(Sample(tick, x, y, z, yaw, pitch))
        elif name == A_MOVE_ENTITIES:
            for _ in range(p.varint()):
                dim = p.string()
                for _ in range(p.varint()):
                    eid = p.varint()
                    x, y, z = p.double(), p.double(), p.double()
                    yaw, pitch, _head = p.float_(), p.float_(), p.float_()
                    p.need(1)
                    p.p += 1  # onGround
                    st.entity_moves.setdefault(eid, []).append(Sample(tick, x, y, z, yaw, pitch))
                    st.entity_dim.setdefault(eid, dim)
        elif name == A_CLOCK:
            p.need(1)
            delta = struct.unpack_from(">b", data, p.p)[0]
            p.p += 1
            if delta == 0:
                p.need(8)
                st.clock_ms = struct.unpack_from(">q", data, p.p)[0]
            elif st.clock_ms is not None:
                st.clock_ms += delta
            if st.clock_ms is not None:
                st.track.clock.append((tick, st.clock_ms))
        b.p = payload_start + size
    return tick


def read_player_track(path: str | Path) -> PlayerTrack:
    """Weg des aufnehmenden Spielers (eine Position pro Tick, soweit aufgezeichnet)."""
    import json
    p = Path(path)
    track = PlayerTrack()
    st = _State(track=track)
    with zipfile.ZipFile(p) as zf:
        meta = json.loads(zf.read("metadata.json"))
        tick = 0
        for name, info in (meta.get("chunks") or {}).items():
            try:
                data = zf.read(name)
            except KeyError:
                raise ReplayDataError(f"{p}: Chunk {name} fehlt") from None
            _parse_chunk(data, tick, st)
            tick += int(info.get("duration", 0))
        track.total_ticks = int(meta.get("total_ticks") or tick)
    if st.start is None:
        raise ReplayDataError(f"{p}: kein aufnehmender Spieler gefunden")
    # Entity-ID des Aufnehmenden: das Objekt, dessen erste Bewegung direkt an der Startposition beginnt
    best_id, best_d = None, 1.5
    for eid, moves in st.entity_moves.items():
        d = math.dist(moves[0].pos, st.start.pos)
        if moves[0].tick - st.start.tick <= 40 and d < best_d:
            best_id, best_d = eid, d
    raw = [st.start] + (st.entity_moves.get(best_id, []) if best_id is not None else []) + track.accurate
    track.entity_id = best_id
    track.dimension = st.entity_dim.get(best_id)
    seen, uniq = set(), []
    for s in sorted(raw, key=lambda s: s.tick):
        if s.tick not in seen:
            seen.add(s.tick)
            uniq.append(s)
    track.samples = uniq
    return track


# ------------------------------------------------------------ Auswertung
def find_teleports(track: PlayerTrack, max_blocks_per_tick: float = 8.0) -> list[int]:
    out = []
    for a, b in zip(track.samples, track.samples[1:], strict=False):
        dt = max(1, b.tick - a.tick)
        if math.dist(a.pos, b.pos) / dt > max_blocks_per_tick:
            out.append(b.tick)
    return out


def best_motion_window(track: PlayerTrack, seconds: float = 8.0) -> tuple[int, int, float]:
    """Zeitfenster mit der meisten (ruhigen) Bewegung, ohne Teleports. Liefert (start, ende, Strecke)."""
    import bisect
    length = int(seconds * 20)
    s = track.samples
    tps = set(find_teleports(track))
    # Praefixsummen: Strecke und Anzahl Teleports bis Sample i
    dist_pre, tp_pre = [0.0], [0]
    for a, b in zip(s, s[1:], strict=False):
        jump = b.tick in tps
        dist_pre.append(dist_pre[-1] + (0.0 if jump else math.dist(a.pos, b.pos)))
        tp_pre.append(tp_pre[-1] + (1 if jump else 0))
    ticks = [x.tick for x in s]
    best = (0, min(length, track.total_ticks), -1.0)
    for i, t0 in enumerate(ticks):
        if t0 + length > track.total_ticks:
            break
        j = bisect.bisect_right(ticks, t0 + length) - 1
        if tp_pre[j] - tp_pre[i] > 0:
            continue
        d = dist_pre[j] - dist_pre[i]
        if d > best[2]:
            best = (t0, t0 + length, d)
    return best
