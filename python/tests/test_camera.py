import json
import math

import pytest

from autocinematic.camera import (
    UNVERIFIED, CameraError, build_editor_state, direction_from_yaw_pitch, editor_state_path, look_at,
    orbit_scene_for_marker, scene_to_flashback, write_editor_state,
)
from autocinematic.cli import main
from autocinematic.demo import DEMO_TOTAL_TICKS, demo_events, write_demo_replay
from autocinematic.events import CombatEvent, Player
from autocinematic.flashback import ReplayInfo
from autocinematic.scenes import make_plan

# Felder, die Flashbacks Gson-Deserialisierung je Typ braucht (aus dem Quelltext 0.43.x abgeleitet)
REQUIRED = {
    "camera": {"position", "yaw", "pitch", "roll", "interpolation_type"},
    "camera_orbit": {"center", "distance", "yaw", "pitch", "interpolation_type"},
    "track_entity": {"target", "bodyPart", "yawOffset", "pitchOffset", "positionOffset", "viewOffset"},
    "tickrate": {"tickrate", "interpolation_type"},
}
TRACK_TYPE_FOR_KF = {"camera": "CAMERA", "camera_orbit": "CAMERA_ORBIT", "track_entity": "TRACK_ENTITY",
                     "tickrate": "SPEED"}
INTERP = {"SMOOTH", "LINEAR", "EASE_IN", "EASE_OUT", "EASE_IN_OUT", "HOLD", "HERMITE"}


def assert_flashback_shape(state: dict):
    assert isinstance(state["scenes"], list) and state["scenes"]
    for sc in state["scenes"]:
        # EditorScene hat keinen Default-Konstruktor -> alle Felder Pflicht
        assert set(sc) >= {"name", "keyframeTracks", "exportStartTicks", "exportEndTicks", "history"}
        assert sc["history"] == {"entries": [], "position": 0}
        assert 0 <= sc["exportStartTicks"] < sc["exportEndTicks"]
        for tr in sc["keyframeTracks"]:
            assert set(tr) >= {"keyframeType", "keyframesByTick", "enabled", "customColour"}
            ticks = [int(t) for t in tr["keyframesByTick"]]
            assert ticks == sorted(ticks) and len(ticks) >= 2
            assert all(sc["exportStartTicks"] <= t <= sc["exportEndTicks"] for t in ticks)
            for kf in tr["keyframesByTick"].values():
                assert kf["type"] in REQUIRED, kf["type"]
                assert REQUIRED[kf["type"]] <= set(kf)
                assert kf["interpolation_type"] in INTERP
                assert TRACK_TYPE_FOR_KF[kf["type"]] == tr["keyframeType"]
                for key in ("position", "center"):
                    if key in kf:
                        assert len(kf[key]) == 3 and all(math.isfinite(c) for c in kf[key])


@pytest.mark.parametrize("cam,target,yaw,pitch", [
    ((0, 0, 0), (0, 0, 10), 0, 0),      # Sueden
    ((0, 0, 0), (-10, 0, 0), 90, 0),    # Westen
    ((0, 0, 0), (10, 0, 0), -90, 0),    # Osten
    ((0, 0, 0), (0, -10, 10), 0, 45),   # nach unten = positiver Pitch
])
def test_look_at_minecraft_convention(cam, target, yaw, pitch):
    y, p = look_at(cam, target)
    assert y == pytest.approx(yaw) and p == pytest.approx(pitch)
    d = direction_from_yaw_pitch(y, p)
    v = [t - c for t, c in zip(target, cam, strict=True)]
    n = math.sqrt(sum(x * x for x in v))
    assert d == pytest.approx(tuple(x / n for x in v), abs=1e-6)


def test_demo_plan_to_flashback_state():
    events = demo_events()
    plan = make_plan(events, fmt="all", total_ticks=DEMO_TOTAL_TICKS)
    info = ReplayInfo(path=None, raw={"uuid": "u", "name": "n"})
    state, report = build_editor_state(info, plan, events)
    assert_flashback_shape(state)
    assert report["scenesWritten"] == len(state["scenes"]) == report["scenesPlanned"]
    sniper = next(r for r in report["scenes"] if "Sniper" in (r["label"] or ""))
    assert sniper["slowMotion"] is True
    assert sniper["projectileCamera"]["reconstructed"] is True and sniper["projectileCamera"]["available"] is False
    for r in report["scenes"]:
        for shot in r["shots"]:
            assert shot["verified"] is False and UNVERIFIED in shot["warnings"]
    # Sniper-Szene: Kamera beim Treffer schaut auf das Ziel (Kopfhoehe)
    sc = next(s for s in state["scenes"] if "Sniper" in s["name"])
    speed = next(t for t in sc["keyframeTracks"] if t["keyframeType"] == "SPEED")
    rates = [kf["tickrate"] for kf in speed["keyframesByTick"].values()]
    assert rates[0] == 20.0 and min(rates) == pytest.approx(6.0) and rates[-1] == 20.0


def test_scene_without_positions_is_reported_not_invented():
    sc = {"id": 1, "startTick": 0, "endTick": 100, "label": "x", "kind": "kill",
          "shots": [{"type": "tracking", "subject": "A", "startTick": 0, "endTick": 50},
                    {"type": "reveal", "subject": "B", "startTick": 50, "endTick": 100}]}
    res = scene_to_flashback(sc, [CombatEvent("kill", tick=50, shooter=Player("A"), target=Player("B"))], index=1)
    assert res.scene is None
    assert any("nicht rekonstruierbar" in p for p in res.report["problems"])
    assert all("error" in s for s in res.report["shots"])


def test_hard_cut_between_shots_does_not_share_ticks():
    ev = CombatEvent("kill", tick=60, shooter=Player("A"), target=Player("B"), pos=(0, 64, 0), target_pos=(20, 64, 0))
    sc = {"id": 1, "startTick": 0, "endTick": 120, "label": "k", "kind": "kill",
          "shots": [{"type": "tracking", "startTick": 0, "endTick": 60}, {"type": "reveal", "startTick": 60, "endTick": 120}]}
    res = scene_to_flashback(sc, [ev], index=1)
    ticks = sorted(int(t) for t in res.scene["keyframeTracks"][0]["keyframesByTick"])
    assert ticks == [0, 60, 61, 120]


def test_orbit_marker_scene_and_bounds():
    sc = orbit_scene_for_marker(100, (1, 64, 1), seconds=6, total_ticks=150)
    assert_flashback_shape({"scenes": [sc]})
    assert sc["exportStartTicks"] == 40 and sc["exportEndTicks"] == 150
    with pytest.raises(CameraError):
        orbit_scene_for_marker(5, (0, 0, 0), total_ticks=10)


def test_write_never_silently_overwrites(tmp_path):
    p = editor_state_path(tmp_path / "flashback", "abc")
    assert p.as_posix().endswith("flashback/editor_states/abc.json")
    state = {"scenes": [orbit_scene_for_marker(100, (0, 64, 0))], "sceneIndex": 0}
    assert write_editor_state(state, p)["backup"] is None
    p.write_text('{"eigene":"keyframes"}', encoding="utf-8")
    with pytest.raises(CameraError, match="existiert bereits"):
        write_editor_state(state, p)
    info = write_editor_state(state, p, force=True)
    assert json.loads(open(info["backup"], encoding="utf-8").read()) == {"eigene": "keyframes"}
    assert json.loads(p.read_text(encoding="utf-8"))["scenes"]


def test_cli_camera_orbit_markers_and_plan(tmp_path, capsys):
    rp = write_demo_replay(tmp_path / "r.zip")
    fb = tmp_path / "instance" / "minecraft" / "flashback"
    assert main(["camera", "--replay", str(rp), "--orbit-markers", "--flashback-dir", str(fb)]) == 0
    out = json.loads(capsys.readouterr().out)
    state = json.loads(open(out["written"], encoding="utf-8").read())
    assert_flashback_shape(state)
    assert out["scenes"] == 1  # nur der Marker mit Position
    # zweiter Lauf ohne --force bricht ab, mit --force entsteht eine Sicherung
    assert main(["camera", "--replay", str(rp), "--orbit-markers", "--flashback-dir", str(fb)]) == 1
    capsys.readouterr()
    ev = tmp_path / "e.jsonl"
    from autocinematic.events import write_jsonl
    write_jsonl(ev, demo_events())
    assert main(["camera", "--replay", str(rp), "--events", str(ev), "--flashback-dir", str(fb), "--force",
                 "--report", str(tmp_path / "rep.json")]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["backup"] and out["scenes"] >= 3
    assert_flashback_shape(json.loads(open(out["written"], encoding="utf-8").read()))
