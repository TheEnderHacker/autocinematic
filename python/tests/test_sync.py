import json

from autocinematic.cli import main
from autocinematic.events import read_jsonl
from autocinematic.replaydata import PlayerTrack, Sample
from autocinematic.sync import estimate_offset_ms, sync_records

from test_replaydata import build_chunk, walk, write_replay

ME = "12345678-1234-5678-1234-567812345678"
T0 = 1_700_000_000_000


def make_track(ticks=400) -> PlayerTrack:
    # laeuft 0,2 Bloecke/Tick nach +X, Uhr: Tick 0 = T0
    return PlayerTrack(uuid=ME, samples=[Sample(t, 0.2 * t, 64.0, 0.0, 0, 0) for t in range(ticks + 1)],
                       total_ticks=ticks, clock=[(0, T0)])


def rec(type_, tick, server_skew_ms, **kw):
    """Server-Zeile fuer ein Ereignis, das im Replay bei `tick` passiert; Server-Uhr geht um skew vor."""
    r = {"v": 1, "type": type_, "t": T0 + tick * 50 + server_skew_ms,
         "extra": {"serverTick": 10_000 + tick, "session": "s"}}
    r.update(kw)
    return r


def shot(tick, skew, shot_id):
    return rec("shot", tick, skew, shooter={"name": "Me", "uuid": ME}, weapon="Sniper",
               pos=[0.2 * tick, 64.0, 0.0], extra={"serverTick": 10_000 + tick, "session": "s", "shotId": shot_id})


def test_offset_is_estimated_from_own_shots():
    track = make_track()
    records = [shot(t, 750, i) for i, t in enumerate((40, 120, 260))]
    off, err, n = estimate_offset_ms(records, track)
    assert n == 3 and off == -750 and err < 0.01


def test_without_own_events_offset_is_assumed_zero_and_warned():
    track = make_track()
    records = [rec("hit", 100, 0, shooter={"name": "Other", "uuid": "x"}, target={"name": "Me", "uuid": ME})]
    events, report = sync_records(records, track)
    assert report["offsetSource"].startswith("angenommen") and "warning" in report
    assert events[0].tick == 100


def test_sync_maps_ticks_and_attaches_real_trajectory():
    track = make_track()
    skew = 1200
    pts = [[10_000 + 200 + i, 40.0 + i * 4.75, 65.5, 0.0] for i in range(6)]
    records = [
        shot(200, skew, 7),
        {"v": 1, "type": "session", "t": T0},
        rec("hit", 205, skew, shooter={"name": "Me", "uuid": ME}, target={"name": "Foe", "uuid": "f"},
            weapon="Sniper", distance=23.8, headshot=True, lethal=True, pos=[41.0, 64.0, 0.0],
            targetPos=[64.0, 64.0, 0.0],
            extra={"serverTick": 10_205, "session": "s", "shotId": 7, "projectile": "p-1"}),
        rec("kill", 205, skew, shooter={"name": "Me", "uuid": ME}, target={"name": "Foe", "uuid": "f"},
            pos=[41.0, 64.0, 0.0], extra={"serverTick": 10_205, "session": "s", "shotId": 7}),
        rec("trajectory", 206, skew, shooter={"name": "Me", "uuid": ME},
            extra={"serverTick": 10_206, "session": "s", "shotId": 7, "projectile": "p-1",
                   "points": pts, "end": "removed"}),
        rec("hit", 900, skew, shooter={"name": "Me", "uuid": ME}, target={"name": "Foe", "uuid": "f"}),  # nach Replay-Ende
    ]
    events, report = sync_records(records, track)
    assert report["offsetMs"] == -skew and report["outsideReplay"] == 1 and report["trajectories"] == 1
    assert [(e.type, e.tick) for e in events] == [("shot", 200), ("hit", 205), ("kill", 205)]
    hit = events[1]
    traj = hit.extra["trajectory"][0]
    assert traj["source"] == "server" and traj["points"][0][0] == 200 and traj["points"][-1][0] == 205
    assert events[2].extra["trajectory"][0]["points"] == traj["points"]  # Kill ueber shotId verknuepft


def test_cli_sync_with_real_replay_format(tmp_path, capsys):
    ticks = 120
    replay = write_replay(tmp_path, build_chunk(walk, ticks), ticks)
    # Replay-Uhr: Tick 0 = 1_700_000_000_000 (build_chunk), Server-Uhr geht 400 ms nach
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    lines = [shot(t, -400, i) for i, t in enumerate((20, 60, 100))]
    for r in lines:
        r["pos"] = list(walk(int((r["t"] + 400 - T0) / 50)))
    (sessions / "ac-20261012-120000-abcdef12.jsonl").write_text(
        "\n".join(json.dumps(r) for r in lines) + "\n", encoding="utf-8")
    out = tmp_path / "synced.jsonl"
    assert main(["sync", "--replay", str(replay), "--events", str(sessions), "-o", str(out)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["offsetMs"] == 400 and report["written"] == 3
    assert [e.tick for e in read_jsonl(out)] == [20, 60, 100]


def test_read_jsonl_skips_recorder_aux_lines(tmp_path):
    p = tmp_path / "ac.jsonl"
    p.write_text('{"v":1,"type":"trajectory","t":1,"extra":{"points":[]}}\n'
                 '{"v":1,"type":"kill","tick":5}\n', encoding="utf-8")
    assert [e.type for e in read_jsonl(p)] == ["kill"]
