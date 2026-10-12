"""Kameraplanung -> Flashback-Editorzustand.

Flashback speichert die Keyframes eines Replays in
`<spielordner>/flashback/editor_states/<replay-uuid>.json` (Gson, siehe
EditorStateManager/EditorState in Flashback). Dieses Modul erzeugt genau
diese Datei: pro geplanter Szene eine Flashback-"Scene" mit Kamera-,
Orbit-, Entity-Tracking- und Geschwindigkeits-Spuren sowie dem Exportbereich.

Ehrlichkeit vor Optik:
- Positionen stammen ausschliesslich aus aufgezeichneten Ereignis- bzw.
  Markerdaten. Fehlen sie, wird die Szene NICHT erzeugt, sondern gemeldet.
- Sichtlinie und Block-Kollisionen koennen ohne Weltdaten nicht geprueft
  werden; jede Einstellung traegt daher `verified: false` und eine Warnung.
- Eine Projektil-Kamera entlang der Linie Schuetze->Ziel ist eine
  REKONSTRUKTION (gerade Linie) und wird als solche markiert.

Das Format wurde aus dem Flashback-Quelltext 0.43.x (MC 26.3) abgeleitet und
muss je Flashback-Version im Spiel verifiziert werden.
"""
from __future__ import annotations

import json
import math
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from .events import CombatEvent
from .flashback import ReplayInfo

EYE = 1.62
Vec = tuple[float, float, float]

TRACK_CAMERA = "CAMERA"
TRACK_ORBIT = "CAMERA_ORBIT"
TRACK_ENTITY = "TRACK_ENTITY"
TRACK_SPEED = "SPEED"
TRACK_FOV = "FOV"

UNVERIFIED = "Sichtlinie/Block-Kollision nicht geprueft (keine Weltdaten) - im Flashback-Editor kontrollieren"


class CameraError(Exception):
    pass


# ----------------------------------------------------------------- Mathematik
def _add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a: Vec, s: float) -> Vec:
    return (a[0] * s, a[1] * s, a[2] * s)


def _norm_xz(dx: float, dz: float) -> tuple[float, float]:
    length = math.hypot(dx, dz)
    if length < 1e-6:
        return (0.0, 1.0)  # Standard: Blick nach Sueden (+Z), wie Minecraft-Yaw 0
    return (dx / length, dz / length)


def look_at(cam: Vec, target: Vec) -> tuple[float, float]:
    """Minecraft-Konvention: Yaw 0 = +Z (Sueden), Yaw 90 = -X (Westen); Pitch > 0 = nach unten."""
    dx, dy, dz = target[0] - cam[0], target[1] - cam[1], target[2] - cam[2]
    yaw = math.degrees(math.atan2(-dx, dz))
    pitch = -math.degrees(math.atan2(dy, math.hypot(dx, dz)))
    return (round(yaw, 3), round(pitch, 3))


def direction_from_yaw_pitch(yaw: float, pitch: float) -> Vec:
    y, p = math.radians(yaw), math.radians(pitch)
    return (-math.sin(y) * math.cos(p), -math.sin(p), math.cos(y) * math.cos(p))


# ------------------------------------------------------- Flashback-JSON-Bausteine
def kf_camera(eye: Vec, yaw: float, pitch: float, roll: float = 0.0, interp: str = "SMOOTH") -> dict:
    """`eye` = gewuenschte Kameraposition (Augpunkt). Flashback setzt die Keyframe-Position wie die
    FUESSE der Kamerafigur und blickt aus Augenhoehe (+1,62) -> hier umrechnen (in Phase B gemessen)."""
    pos = (eye[0], eye[1] - EYE, eye[2])
    return {"position": [round(c, 4) for c in pos], "yaw": yaw, "pitch": pitch, "roll": roll,
            "type": "camera", "interpolation_type": interp}


def camera_eye(kf: dict) -> Vec:
    """Tatsaechlicher Augpunkt eines CAMERA-Keyframes."""
    x, y, z = kf["position"]
    return (x, y + EYE, z)


def kf_orbit(center: Vec, distance: float, yaw: float, pitch: float, interp: str = "SMOOTH") -> dict:
    return {"center": [round(c, 4) for c in center], "distance": round(distance, 3), "yaw": round(yaw, 3),
            "pitch": round(pitch, 3), "type": "camera_orbit", "interpolation_type": interp}


def kf_track_entity(uuid: str, body: str = "HEAD", yaw_offset: float = 0.0, pitch_offset: float = 0.0,
                    position_offset: Vec = (0.0, 0.0, 0.0), view_offset: Vec = (0.0, 0.0, 0.0),
                    interp: str = "SMOOTH") -> dict:
    return {"target": uuid, "bodyPart": body, "yawOffset": yaw_offset, "pitchOffset": pitch_offset,
            "positionOffset": list(position_offset), "viewOffset": list(view_offset), "type": "track_entity",
            "roll": 0.0, "interpolation_type": interp}


def kf_tickrate(rate: float, interp: str = "LINEAR") -> dict:
    return {"tickrate": round(rate, 3), "type": "tickrate", "interpolation_type": interp}


def make_track(type_id: str, keyframes: dict[int, dict], name: Optional[str] = None) -> dict:
    t = {"keyframeType": type_id,
         "keyframesByTick": {str(k): v for k, v in sorted(keyframes.items())},
         "enabled": True, "customColour": 0}
    if name:
        t["customName"] = name
    return t


def make_scene(name: str, tracks: list[dict], start: int, end: int) -> dict:
    # EditorScene hat keinen parameterlosen Konstruktor -> alle Felder muessen gesetzt sein
    return {"name": name, "keyframeTracks": tracks, "exportStartTicks": int(start), "exportEndTicks": int(end),
            "history": {"entries": [], "position": 0}}


def make_editor_state(scenes: list[dict]) -> dict:
    if not scenes:
        raise CameraError("Keine Szene erzeugt - es gibt nichts, was Flashback laden koennte")
    return {"scenes": scenes, "sceneIndex": 0, "zoomMin": 0.0, "zoomMax": 1.0}


# --------------------------------------------------------- Einstellungsplanung
@dataclass
class ShotResult:
    keyframes: dict[int, dict]
    report: dict


@dataclass
class SceneCameraResult:
    scene: Optional[dict]
    report: dict = field(default_factory=dict)


def _subjects(events: Iterable[CombatEvent]) -> tuple[Optional[Vec], Optional[Vec], Optional[str], Optional[str]]:
    shooter_pos = target_pos = None
    shooter_uuid = target_uuid = None
    for e in events:
        if e.pos and shooter_pos is None:
            shooter_pos = e.pos
            shooter_uuid = e.shooter.uuid if e.shooter else None
        if e.target_pos and target_pos is None:
            target_pos = e.target_pos
            target_uuid = e.target.uuid if e.target else None
    return shooter_pos, target_pos, shooter_uuid, target_uuid


def _shot_keyframes(kind: str, a: int, b: int, shooter: Optional[Vec], target: Optional[Vec],
                    centroid: Optional[Vec]) -> tuple[Optional[dict[int, dict]], dict]:
    """Zwei bis vier Kamera-Keyframes fuer eine Einstellung zwischen Tick a und b."""
    rep = {"type": kind, "startTick": a, "endTick": b, "verified": False, "warnings": [UNVERIFIED]}
    if kind in ("tracking", "close_detail", "chase") and shooter is None:
        rep["error"] = "keine Schuetzenposition aufgezeichnet"
        return None, rep
    if kind in ("reveal", "spiral") and target is None:
        rep["error"] = "keine Zielposition aufgezeichnet"
        return None, rep
    if kind == "crane" and centroid is None:
        rep["error"] = "keine Positionsdaten fuer Ueberblick"
        return None, rep

    if shooter and target:
        fx, fz = _norm_xz(target[0] - shooter[0], target[2] - shooter[2])
    else:
        fx, fz = (0.0, 1.0)
    right = (-fz, 0.0, fx)  # rechts relativ zur Schussrichtung
    fwd = (fx, 0.0, fz)
    kfs: dict[int, dict] = {}

    if kind in ("tracking", "chase"):
        eye = _add(shooter, (0, EYE, 0))
        aim = _add(eye, _mul(fwd, 12)) if target is None else _add(target, (0, EYE, 0))
        p0 = _add(_add(eye, _mul(fwd, -5.0)), _add(_mul(right, 1.6), (0, 0.6, 0)))
        p1 = _add(_add(eye, _mul(fwd, -3.2)), _add(_mul(right, 1.1), (0, 0.35, 0)))  # langsames Heranfahren
        for t, p in ((a, p0), (b, p1)):
            kfs[t] = kf_camera(p, *look_at(p, _add(_mul(_add(aim, _mul(eye, -1)), 0.35), eye)))
    elif kind == "close_detail":
        eye = _add(shooter, (0, EYE, 0))
        p0 = _add(_add(eye, _mul(fwd, 1.4)), _mul(right, 1.0))
        p1 = _add(_add(eye, _mul(fwd, 1.2)), _mul(right, 0.8))
        for t, p in ((a, p0), (b, p1)):
            kfs[t] = kf_camera(p, *look_at(p, eye))
    elif kind == "reveal":
        eye = _add(target, (0, EYE, 0))
        p0 = _add(_add(eye, _mul(fwd, -7.0)), (0, 3.0, 0))
        p1 = _add(_add(eye, _mul(fwd, -3.5)), _add(_mul(right, 2.0), (0, 0.4, 0)))
        for t, p in ((a, p0), (b, p1)):
            kfs[t] = kf_camera(p, *look_at(p, eye))
    elif kind == "spiral":
        eye = _add(target, (0, EYE, 0))
        base = math.degrees(math.atan2(-fx, fz))
        steps = 3
        for i in range(steps + 1):
            t = a + round((b - a) * i / steps)
            ang = math.radians(base + 180 + 100 * i / steps)
            p = (eye[0] - math.sin(ang) * 4.5, eye[1] + 1.2 + 0.6 * i / steps, eye[2] + math.cos(ang) * 4.5)
            kfs[t] = kf_camera(p, *look_at(p, eye))
    elif kind == "crane":
        c = _add(centroid, (0, 1.0, 0))
        p0 = _add(c, (-18.0, 4.0, -18.0))
        p1 = _add(c, (-14.0, 16.0, -14.0))
        for t, p in ((a, p0), (b, p1)):
            kfs[t] = kf_camera(p, *look_at(p, c))
    else:
        rep["error"] = f"unbekannter Einstellungstyp {kind!r}"
        return None, rep
    return kfs, rep


def scene_to_flashback(plan_scene: dict, events: list[CombatEvent], *, index: int) -> SceneCameraResult:
    """Wandelt eine Szene aus plan.json in eine Flashback-EditorScene um."""
    s, e = int(plan_scene["startTick"]), int(plan_scene["endTick"])
    report: dict = {"id": plan_scene.get("id", index), "label": plan_scene.get("label"),
                    "startTick": s, "endTick": e, "shots": [], "problems": []}
    in_scene = [ev for ev in events if ev.tick is not None and s <= ev.tick <= e]
    main_events = [ev for ev in in_scene if ev.type in ("kill", "hit")] or in_scene
    shooter, target, shooter_uuid, target_uuid = _subjects(main_events)
    pts = [p for ev in in_scene for p in (ev.pos, ev.target_pos) if p]
    centroid = (tuple(sum(c) / len(pts) for c in zip(*pts, strict=True)) if pts else None)  # type: ignore[assignment]

    camera_kfs: dict[int, dict] = {}
    for shot in plan_scene.get("shots", []):
        a, b = int(shot["startTick"]), int(shot["endTick"])
        if camera_kfs and a <= max(camera_kfs):
            a = max(camera_kfs) + 1  # harter Schnitt: neue Einstellung beginnt einen Tick spaeter
        if b <= a:
            continue
        kfs, rep = _shot_keyframes(shot["type"], a, b, shooter, target, centroid)
        report["shots"].append(rep)
        if kfs:
            camera_kfs.update(kfs)
        else:
            report["problems"].append(f"Einstellung {shot['type']} uebersprungen: {rep['error']}")

    if not camera_kfs:
        report["problems"].append("Szene nicht rekonstruierbar: keine verwertbaren Positionsdaten")
        return SceneCameraResult(scene=None, report=report)

    tracks = [make_track(TRACK_CAMERA, camera_kfs, "AutoCinematic Kamera")]

    speed_kfs: dict[int, dict] = {}
    for seg in plan_scene.get("speed", []):
        a, b, sp = int(seg["startTick"]), int(seg["endTick"]), float(seg["speed"])
        ramp = 4
        speed_kfs.setdefault(max(s, a - ramp), kf_tickrate(20.0))
        speed_kfs[a] = kf_tickrate(20.0 * sp)
        speed_kfs[b] = kf_tickrate(20.0 * sp)
        speed_kfs[min(e, b + ramp)] = kf_tickrate(20.0)
    if speed_kfs:
        tracks.append(make_track(TRACK_SPEED, speed_kfs, "AutoCinematic Zeitlupe"))
        report["slowMotion"] = True

    if plan_scene.get("kind", "").startswith("sniper") and shooter and target:
        report["projectileCamera"] = {
            "available": False,
            "reconstructed": True,
            "note": "Keine aufgezeichnete Flugbahn vorhanden; eine Projektilkamera waere nur eine "
                    "gerade Linie zwischen Schuss- und Trefferposition (Rekonstruktion) und wird "
                    "deshalb erst mit Server-Flugbahndaten (Phase C) erzeugt.",
        }

    name = f"AC {report['id']}: {plan_scene.get('label') or 'Szene'}"[:60]
    return SceneCameraResult(scene=make_scene(name, tracks, s, e), report=report)


def orbit_scene_for_marker(tick: int, pos: Vec, *, seconds: float = 6.0, radius: float = 6.0,
                           pitch: float = 20.0, sweep: float = 120.0, total_ticks: Optional[int] = None,
                           name: Optional[str] = None) -> dict:
    """Kleinster Kameratest: Orbit um eine gespeicherte Marker-Position."""
    half = int(seconds * 20 / 2)
    s = max(0, tick - half)
    e = tick + half if total_ticks is None else min(total_ticks, tick + half)
    if e - s < 20:
        raise CameraError(f"Marker bei Tick {tick}: zu wenig Replay-Zeit fuer einen Orbit")
    center = _add(pos, (0, 1.0, 0))
    kfs = {s: kf_orbit(center, radius, 0.0, pitch), e: kf_orbit(center, radius, sweep, pitch)}
    return make_scene(name or f"AC Orbit Tick {tick}", [make_track(TRACK_ORBIT, kfs, "AutoCinematic Orbit")], s, e)


def trail_scene(track, start: int, end: int, *, distance: float = 4.5, cam_height: float = 1.5,
                step: int = 5, damp_ticks: int = 15, name: Optional[str] = None) -> tuple[dict, dict]:
    """Kollisionsfreie Verfolgerkamera: Die Kamera faehrt auf dem EIGENEN Weg des Spielers hinterher.

    Wo der Spieler vor kurzem war, war Platz fuer seinen Koerper (1,8 Bloecke hoch) -> eine Kamera
    in 1,5 Bloecken Hoehe ueber einem frueheren Wegpunkt steckt nicht in einem Block (Ausnahme:
    Bloecke, die danach gesetzt wurden). Abstand = `distance` Bloecke entlang des Weges.
    """
    if end - start < 20:
        raise CameraError("Zeitfenster zu kurz fuer eine Verfolgerkamera")
    pts = [s for s in track.samples if s.tick <= end]
    if len(pts) < 2:
        raise CameraError("Keine aufgezeichneten Spielerpositionen im Zeitfenster")
    # kumulierte Wegstrecke
    cum = [0.0]
    for a, b in zip(pts, pts[1:], strict=False):
        cum.append(cum[-1] + math.dist(a.pos, b.pos))
    ticks = [p.tick for p in pts]
    import bisect

    kfs: dict[int, dict] = {}
    fallback_ticks = 0
    for t in list(range(start, end, step)) + [end]:
        i = max(0, bisect.bisect_right(ticks, t) - 1)
        player = pts[i]
        target_len = cum[i] - distance
        if target_len <= 0:
            cam_base = pts[0]
            fallback_ticks += 1 if cum[i] < distance * 0.5 else 0
        else:
            k = bisect.bisect_left(cum, target_len)
            cam_base = pts[max(0, k)]
        # Hoehe gegen Wippen (Spruenge, Double-Jump) daempfen, aber nur innerhalb des Koerpervolumens
        # (Fuesse .. Fuesse+1,8) am Wegpunkt -> bleibt kollisionsfrei.
        ys = [q.pos[1] for q in pts if abs(q.tick - cam_base.tick) <= damp_ticks]
        y_smooth = min(ys) if ys else cam_base.y  # Bodenhoehe im Umfeld
        cam_y = min(max(y_smooth + cam_height, cam_base.y + 0.2), cam_base.y + 1.7)
        cam = (cam_base.x, cam_y, cam_base.z)
        tys = [q.pos[1] for q in pts if abs(q.tick - player.tick) <= damp_ticks]
        look_y = (min(tys) if tys else player.y) + EYE
        eye = (player.x, look_y, player.z)
        if math.dist(cam, eye) < 1.0:  # Spieler steht noch am Startpunkt: leicht erhoeht hinter ihm
            d = direction_from_yaw_pitch(player.yaw, 0.0)
            cam = _add(cam, (-d[0] * 0.01, 0.0, -d[2] * 0.01))
        kfs[t] = kf_camera(cam, *look_at(cam, eye))
    report = {"mode": "trail", "verified": "frei laut Spielerweg (ausser spaeter gesetzte Bloecke)",
              "keyframes": len(kfs), "ticksNearStart": fallback_ticks}
    return (make_scene(name or f"AC Verfolger (Weg) {start}-{end}",
                       [make_track(TRACK_CAMERA, kfs, "AutoCinematic Weg-Kamera")], start, end), report)


def follow_scene(track, start: int, end: int, *, distance: float = 5.0, height: float = 2.0,
                 side: float = 1.2, step: int = 10, smooth: int = 12, name: Optional[str] = None) -> dict:
    """Verfolgerkamera entlang des ECHTEN Laufwegs (Positionen aus der Aufnahme).

    Ziel = geglaettete Spielerposition; Kamera steht hinter/ueber/seitlich davon in
    Bewegungsrichtung und schaut auf Kopfhoehe. Keyframes alle `step` Ticks (SMOOTH).
    """
    if end - start < 20:
        raise CameraError("Zeitfenster zu kurz fuer eine Verfolgerkamera")
    samples = [s for s in track.samples if start - smooth - 1 <= s.tick <= end + smooth + 1]
    if len(samples) < 2:
        raise CameraError("Im Zeitfenster gibt es keine aufgezeichneten Spielerpositionen")

    def avg_pos(t: int) -> Vec:
        win = [s for s in samples if abs(s.tick - t) <= smooth] or [track.at(t)]
        win = [w for w in win if w is not None]
        return tuple(sum(c) / len(win) for c in zip(*(w.pos for w in win), strict=True))  # type: ignore[return-value]

    kfs: dict[int, dict] = {}
    last_dir = None
    ticks = list(range(start, end, step)) + [end]
    for t in ticks:
        p = avg_pos(t)
        a, b = avg_pos(max(start, t - step)), avg_pos(min(end, t + step))
        dx, dz = b[0] - a[0], b[2] - a[2]
        if math.hypot(dx, dz) > 0.3:
            fx, fz = _norm_xz(dx, dz)
        elif last_dir is not None:
            fx, fz = last_dir
        else:
            s = track.at(t)
            d = direction_from_yaw_pitch(s.yaw if s else 0.0, 0.0)
            fx, fz = _norm_xz(d[0], d[2])
        last_dir = (fx, fz)
        eye = _add(p, (0, EYE, 0))
        right = (-fz, 0.0, fx)
        cam = _add(_add(eye, _mul((fx, 0.0, fz), -distance)), _add(_mul(right, side), (0, height - 0.6, 0)))
        kfs[t] = kf_camera(cam, *look_at(cam, eye))
    return make_scene(name or f"AC Verfolger {start}-{end}",
                      [make_track(TRACK_CAMERA, kfs, "AutoCinematic Verfolger")], start, end)


# ----------------------------------------------------------------- Schreiben
def build_editor_state(info: ReplayInfo, plan: dict, events: list[CombatEvent]) -> tuple[dict, dict]:
    scenes, reports = [], []
    for i, sc in enumerate(plan.get("scenes", []), 1):
        res = scene_to_flashback(sc, events, index=i)
        reports.append(res.report)
        if res.scene:
            scenes.append(res.scene)
    report = {"replay": info.name, "replayUuid": info.uuid, "scenesPlanned": len(plan.get("scenes", [])),
              "scenesWritten": len(scenes), "scenes": reports}
    return make_editor_state(scenes), report


def editor_state_path(flashback_dir: str | Path, replay_uuid: str) -> Path:
    return Path(flashback_dir) / "editor_states" / f"{replay_uuid}.json"


def write_editor_state(state: dict, path: str | Path, *, force: bool = False) -> dict:
    """Schreibt den Editorzustand. Ein vorhandener Zustand wird nur mit force ersetzt
    und vorher als Sicherungskopie daneben abgelegt (nichts wird geloescht)."""
    p = Path(path)
    info: dict = {"path": str(p), "backup": None}
    if p.exists():
        if not force:
            raise CameraError(f"{p} existiert bereits (eigene Keyframes?) - mit --force ersetzen, "
                              "es wird dann eine Sicherungskopie angelegt")
        backup = p.with_name(p.name + f".autocinematic-backup-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(p, backup)
        info["backup"] = str(backup)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".part")
    tmp.write_text(json.dumps(state, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(p)
    return info
