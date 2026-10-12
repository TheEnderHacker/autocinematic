import hashlib
import json
import zipfile

import pytest

from autocinematic.demo import DEMO_TOTAL_TICKS, demo_events, write_demo_replay
from autocinematic.events import CombatEvent, Player
from autocinematic.flashback import (
    COLOUR_HIGHLIGHT, Marker, ReplayError, merge_markers, read_replay, write_replay_with_markers,
)


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_read_demo_replay(tmp_path):
    rp = write_demo_replay(tmp_path / "r.zip")
    info = read_replay(rp)
    assert info.name == "AutoCinematic Demo"
    assert info.total_ticks == DEMO_TOTAL_TICKS
    assert info.duration_seconds == 120
    assert set(info.markers) == {804, 1200}
    assert info.markers[1200].position == (12.5, 70.0, -3.5)
    assert not info.markers[804].is_autocinematic
    assert info.events() == []


def test_read_extracted_folder(tmp_path):
    d = tmp_path / "rec"
    d.mkdir()
    (d / "metadata.json").write_text(json.dumps({"uuid": "x", "name": "Ordner", "chunks": {
        "c0.flashback": {"duration": 100}, "c1.flashback": {"duration": 60}}}), encoding="utf-8")
    info = read_replay(d)
    assert info.name == "Ordner" and info.total_ticks == 160  # Fallback ueber Chunk-Laengen


@pytest.mark.parametrize("content,msg", [
    (None, "Datei nicht gefunden"), (b"kein zip", "keine ZIP"), ("nozip-meta", "fehlt im ZIP"),
    ("badjson", "kein gueltiges JSON"), ("nouuid", "uuid"),
])
def test_read_errors(tmp_path, content, msg):
    p = tmp_path / "x.zip"
    if isinstance(content, bytes):
        p.write_bytes(content)
    elif content == "nozip-meta":
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("a.txt", "x")
    elif content == "badjson":
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("metadata.json", "{")
    elif content == "nouuid":
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("metadata.json", "{}")
    with pytest.raises(ReplayError, match=msg):
        read_replay(p)


def test_inject_preserves_original_and_other_entries(tmp_path):
    src = write_demo_replay(tmp_path / "orig.zip")
    before = _digest(src)
    info = read_replay(src)
    markers, stats = merge_markers(info.markers, demo_events())
    dst = write_replay_with_markers(src, tmp_path / "out" / "marked.zip", markers)

    assert _digest(src) == before, "Original wurde veraendert!"
    with zipfile.ZipFile(src) as a, zipfile.ZipFile(dst) as b:
        assert sorted(a.namelist()) == sorted(b.namelist())
        for name in a.namelist():
            if name != "metadata.json":
                assert a.read(name) == b.read(name), name
        meta_a, meta_b = json.loads(a.read("metadata.json")), json.loads(b.read("metadata.json"))
    for k in meta_a:
        if k != "markers":
            assert meta_a[k] == meta_b[k]

    out = read_replay(dst)
    # Eigener Marker bei 804 bleibt; der Sniper-Kill (ebenfalls Tick 804) wird verschoben
    assert out.markers[804].description == "Mein eigener Marker"
    assert stats["shifted"] == 1 and stats["dropped"] == 0
    kills = [e for e in out.events() if e.type == "kill"]
    sniper = next(e for e in kills if e.weapon_class == "sniper")
    assert sniper.tick == 804, "exakter Tick muss im JSON erhalten bleiben"
    shifted_marker = next(m for m in out.markers.values() if m.is_autocinematic and m.events()[0].tick == 804)
    assert shifted_marker.colour == COLOUR_HIGHLIGHT
    assert shifted_marker.position == pytest.approx((90, 64, 18))
    # Schuesse werden standardmaessig nicht markiert
    assert all(e.type != "shot" for e in out.events())
    assert len(out.events()) == sum(1 for e in demo_events() if e.type in ("hit", "kill"))


def test_same_tick_events_share_one_marker_and_reinject_is_idempotent(tmp_path):
    src = write_demo_replay(tmp_path / "r.zip", with_user_marker=False)
    evs = [CombatEvent("hit", tick=50, shooter=Player("A"), target=Player("B")),
           CombatEvent("kill", tick=50, shooter=Player("A"), target=Player("B"), headshot=True)]
    m1, _ = merge_markers(read_replay(src).markers, evs)
    assert list(m1) == [50]
    assert "(+1)" in m1[50].description and m1[50].description.startswith("Kill:")
    first = write_replay_with_markers(src, tmp_path / "a.zip", m1)
    # Erneutes Einfuegen ersetzt alte AutoCinematic-Marker statt sie zu verdoppeln
    m2, _ = merge_markers(read_replay(first).markers, evs)
    second = write_replay_with_markers(first, tmp_path / "b.zip", m2)
    assert len(read_replay(second).events()) == 2


def test_marker_json_matches_flashback_format():
    m = Marker(tick=5, colour=0xFF0000, description="d", position=(1.5, 2, 3), dimension="minecraft:the_nether")
    assert m.to_json() == {"colour": 0xFF0000, "description": "d",
                           "position": {"position": [1.5, 2.0, 3.0], "dimension": "minecraft:the_nether"}}
    assert Marker.from_json(5, m.to_json()) == m
    assert Marker(tick=1).to_json() == {"colour": 0xFFFFFF}


def test_refuses_to_overwrite_original(tmp_path):
    src = write_demo_replay(tmp_path / "r.zip")
    with pytest.raises(ReplayError, match="Original"):
        write_replay_with_markers(src, src, {})


def test_shift_limit_drops_when_no_free_tick():
    existing = {t: Marker(tick=t, description="frei") for t in range(0, 30)}
    _, stats = merge_markers(existing, [CombatEvent("kill", tick=10)], max_shift=3)
    assert stats["dropped"] == 1 and stats["written"] == 0
