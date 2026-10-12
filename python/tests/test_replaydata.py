import json
import math
import struct
import uuid
import zipfile

import pytest

from autocinematic.camera import follow_scene, look_at
from autocinematic.cli import main
from autocinematic.replaydata import (
    MAGIC, ReplayDataError, best_motion_window, find_teleports, read_player_track,
)

NAMES = ["flashback:action/next_tick", "flashback:action/game_packet", "flashback:action/create_local_player",
         "flashback:action/move_entities", "flashback:action/real_time_clock_optional"]


def varint(v: int) -> bytes:
    v &= 0xFFFFFFFF
    out = b""
    while True:
        b = v & 0x7F
        v >>= 7
        out += bytes([b | (0x80 if v else 0)])
        if not v:
            return out


def string(s: str) -> bytes:
    raw = s.encode()
    return varint(len(raw)) + raw


def action(idx: int, payload: bytes) -> bytes:
    return varint(idx) + struct.pack(">i", len(payload)) + payload


def build_chunk(path_fn, ticks: int, eid: int = 77, start=(0.0, 64.0, 0.0), other=True, clock0=1_700_000_000_000):
    head = struct.pack(">I", MAGIC) + varint(len(NAMES)) + b"".join(string(n) for n in NAMES)
    pid = uuid.UUID("12345678-1234-5678-1234-567812345678").bytes
    snap = action(2, pid + struct.pack(">ddd", *start) + struct.pack(">fff", 0, 0, 0) + struct.pack(">ddd", 0, 0, 0))
    snap += action(1, b"\x00\x01\x02")  # beliebiges Spielpaket, wird ueberlesen
    body = action(4, b"\x00" + struct.pack(">q", clock0))
    for t in range(1, ticks + 1):
        body += action(0, b"")
        if t == 10:
            body += action(4, struct.pack(">b", 3))  # Tick kam 3 ms spaeter als vorhergesagt
        x, y, z = path_fn(t)
        ents = [(eid, x, y, z)] + ([(eid + 1, 50.0, 64.0, 50.0 + t * 0.01)] if other else [])
        payload = varint(1) + string("minecraft:overworld") + varint(len(ents))
        for e, ex, ey, ez in ents:
            payload += varint(e) + struct.pack(">ddd", ex, ey, ez) + struct.pack(">fff", 0, 0, 0) + b"\x01"
        body += action(3, payload)
    return head + struct.pack(">i", len(snap)) + snap + body


def write_replay(tmp_path, chunk: bytes, ticks: int, name="r.zip"):
    p = tmp_path / name
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("metadata.json", json.dumps({"uuid": "u-1", "name": "t", "total_ticks": ticks,
                                                "chunks": {"c0.flashback": {"duration": ticks}}}))
        z.writestr("c0.flashback", chunk)
    return p


def walk(t):  # 0,2 Bloecke pro Tick nach +X
    return (0.2 * t, 64.0, 0.0)


def test_reads_local_player_track_and_clock(tmp_path):
    p = write_replay(tmp_path, build_chunk(walk, 200), 200)
    tr = read_player_track(p)
    assert tr.uuid == "12345678-1234-5678-1234-567812345678"
    assert tr.entity_id == 77 and tr.dimension == "minecraft:overworld"
    assert len(tr.samples) == 201 and tr.samples[-1].pos == pytest.approx((40.0, 64.0, 0.0))
    # Uhr: +50 ms pro Tick, bei Tick 10 zusaetzlich +3 ms
    assert dict(tr.clock)[10] == 1_700_000_000_000 + 10 * 50 + 3
    assert tr.tick_for_epoch_ms(1_700_000_000_000 + 100 * 50 + 3) == 100
    assert tr.at(55).tick == 55 and tr.at(10_000).tick == 200


def test_teleport_and_best_window(tmp_path):
    def path(t):
        if t < 100:
            return (0.0, 64.0, 0.0)            # steht still
        if t < 150:
            return (0.3 * (t - 100), 64.0, 0.0)  # laeuft
        return (500.0, 64.0, 0.0)              # Teleport
    tr = read_player_track(write_replay(tmp_path, build_chunk(path, 300), 300))
    assert find_teleports(tr) == [150]
    s, e, d = best_motion_window(tr, seconds=2.0)
    assert 100 <= s + 40 and e <= 150 + 40 and d > 10   # Fenster liegt im Laufabschnitt, ohne Teleport
    assert not (s < 150 <= e)


def test_bad_magic_is_reported(tmp_path):
    p = write_replay(tmp_path, b"\x00\x00\x00\x01rest", 10)
    with pytest.raises(ReplayDataError, match="Magic"):
        read_player_track(p)


def test_follow_camera_stays_behind_and_looks_at_player(tmp_path):
    tr = read_player_track(write_replay(tmp_path, build_chunk(walk, 200), 200))
    sc = follow_scene(tr, 40, 160)
    kfs = sc["keyframeTracks"][0]["keyframesByTick"]
    assert sc["exportStartTicks"] == 40 and sc["exportEndTicks"] == 160 and "160" in kfs
    for t, kf in kfs.items():
        px = 0.2 * int(t)
        cam = kf["position"]
        assert cam[0] < px - 3          # hinter dem Spieler (er laeuft nach +X)
        assert cam[1] > 64 + 1.6        # ueber Kopfhoehe
        yaw, pitch = look_at(tuple(cam), (px, 64 + 1.62, 0.0))
        assert kf["yaw"] == pytest.approx(yaw, abs=8) and kf["pitch"] == pytest.approx(pitch, abs=8)
    # gleichmaessige Bewegung, keine Spruenge zwischen Keyframes
    pos = [kfs[k]["position"] for k in sorted(kfs, key=int)]
    steps = [math.dist(a, b) for a, b in zip(pos, pos[1:], strict=False)]
    assert max(steps[:-1]) < 2.5


def test_cli_follow_writes_editor_state(tmp_path, capsys):
    p = write_replay(tmp_path, build_chunk(walk, 400), 400)
    assert main(["camera", "--replay", str(p), "--follow", "--seconds", "5",
                 "--flashback-dir", str(tmp_path / "fb")]) == 0
    out = json.loads(capsys.readouterr().out)
    state = json.loads(open(out["written"], encoding="utf-8").read())
    sc = state["scenes"][0]
    assert sc["exportEndTicks"] - sc["exportStartTicks"] == 100
    assert main(["camera", "--replay", str(p), "--follow", "--start", "2", "--end", "6",
                 "-o", str(tmp_path / "x.json")]) == 0
    sc = json.loads((tmp_path / "x.json").read_text(encoding="utf-8"))["scenes"][0]
    assert (sc["exportStartTicks"], sc["exportEndTicks"]) == (40, 120)
