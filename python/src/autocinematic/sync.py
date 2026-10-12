"""Server-Ereignisse (AutoCinematic Recorder, JSONL) einer Flashback-Aufnahme zuordnen.

Zeitbasis:
  Server-Zeile:  t = Unix-ms der Server-Uhr, extra.serverTick
  Aufnahme:      Echtzeit-Uhr des Client-PCs pro Tick (real_time_clock in cN.flashback)

Server- und PC-Uhr weichen voneinander ab (NTP: meist < 100 ms, ohne Sync auch Sekunden).
Dazu kommt die Netzwerklatenz. Der Versatz wird deshalb automatisch geschaetzt: Fuer alle
Ereignisse, deren Schuetze der aufnehmende Spieler ist, wird die Server-Position mit dem
aufgezeichneten Laufweg verglichen und der Versatz mit dem kleinsten Abstand gewaehlt.
Ohne solche Ereignisse wird 0 angenommen und das im Bericht als unsicher gemeldet.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Optional

from .events import CombatEvent, EventError, sort_events
from .replaydata import PlayerTrack

COMBAT_TYPES = ("shot", "hit", "kill")


def load_server_records(path: str | Path) -> list[dict]:
    out = []
    with open(path, encoding="utf-8-sig") as fh:
        for no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                raise EventError(f"{path}:{no}: kein gueltiges JSON ({exc})") from None
            if isinstance(rec, dict) and "t" in rec and "type" in rec:
                out.append(rec)
    return out


def _uuid(p: Optional[dict]) -> Optional[str]:
    return (p or {}).get("uuid")


def estimate_offset_ms(records: list[dict], track: PlayerTrack, *, search_ms: int = 5000,
                       step_ms: int = 50) -> tuple[Optional[int], Optional[float], int]:
    """Versatz (ms), der auf die Server-Zeit addiert wird, damit sie zur Aufnahme-Uhr passt.

    Liefert (offset, mittlerer Abstand in Bloecken, Anzahl Stuetzpunkte); offset None = nicht schaetzbar.
    """
    anchors = [(r["t"], tuple(r["pos"])) for r in records
               if r.get("type") in COMBAT_TYPES and r.get("pos") and track.uuid
               and _uuid(r.get("shooter")) == track.uuid]
    if not anchors or not track.clock:
        return None, None, 0
    best: tuple[float, int] = (math.inf, 0)
    for off in range(-search_ms, search_ms + 1, step_ms):
        total, n = 0.0, 0
        for t, pos in anchors:
            tick = track.tick_for_epoch_ms(t + off)
            s = track.at(tick) if tick is not None and 0 <= tick <= track.total_ticks else None
            if s is None:
                continue
            total += math.dist(s.pos, pos)
            n += 1
        if n and n >= max(1, len(anchors) // 2):
            mean = total / n
            # bei Gleichstand den Versatz naeher an 0 bevorzugen
            if mean < best[0] - 1e-9 or (abs(mean - best[0]) < 1e-9 and abs(off) < abs(best[1])):
                best = (mean, off)
    if math.isinf(best[0]):
        return None, None, len(anchors)
    return best[1], best[0], len(anchors)


def sync_records(records: list[dict], track: PlayerTrack, *, offset_ms: Optional[int] = None) -> tuple[list[CombatEvent], dict]:
    report: dict = {"records": len(records)}
    if offset_ms is None:
        est, residual, n = estimate_offset_ms(records, track)
        offset_ms = est if est is not None else 0
        report.update({"offsetMs": offset_ms, "offsetSource": "geschaetzt" if est is not None else "angenommen (0)",
                       "offsetAnchors": n, "meanPositionErrorBlocks": None if residual is None else round(residual, 2)})
        if est is None:
            report["warning"] = ("Kein Ereignis des aufnehmenden Spielers gefunden - Uhrenversatz unbekannt, "
                                 "Zuordnung kann um die Abweichung der Uhren danebenliegen")
    else:
        report.update({"offsetMs": offset_ms, "offsetSource": "vorgegeben"})

    def to_tick(t_ms: int) -> Optional[int]:
        tick = track.tick_for_epoch_ms(t_ms + offset_ms)
        if tick is None or tick < 0 or tick > track.total_ticks:
            return None
        return tick

    # Flugbahnen (Server-Ticks) -> Replay-Ticks, nach shotId/pellet und Projektil-UUID
    trajectories: dict = {}
    for r in records:
        if r.get("type") != "trajectory":
            continue
        x = r.get("extra") or {}
        end_tick = to_tick(r["t"])
        pts = x.get("points") or []
        if end_tick is None or not pts or "serverTick" not in x:
            continue
        conv = [[end_tick - (x["serverTick"] - p[0]), p[1], p[2], p[3]] for p in pts]
        traj = {"points": conv, "end": x.get("end"), "source": "server"}
        if "shotId" in x:
            trajectories.setdefault(("shot", x["shotId"]), []).append(traj)
        if "projectile" in x:
            trajectories[("proj", x["projectile"])] = [traj]

    events: list[CombatEvent] = []
    skipped = {"outsideReplay": 0, "invalid": 0}
    for r in records:
        if r.get("type") not in COMBAT_TYPES:
            continue
        tick = to_tick(r["t"])
        if tick is None:
            skipped["outsideReplay"] += 1
            continue
        d = dict(r)
        d["tick"] = tick
        d["extra"] = dict(d.get("extra") or {})
        x = d["extra"]
        traj = None
        if ("proj", x.get("projectile")) in trajectories:
            traj = trajectories[("proj", x["projectile"])]
        elif ("shot", x.get("shotId")) in trajectories:
            traj = trajectories[("shot", x["shotId"])]
        if traj:
            x["trajectory"] = traj
        try:
            events.append(CombatEvent.from_dict(d))
        except EventError:
            skipped["invalid"] += 1
    report.update({"events": len(events), "trajectories": sum(len(v) for k, v in trajectories.items() if k[0] == "proj"),
                   **skipped})
    return sort_events(events), report
