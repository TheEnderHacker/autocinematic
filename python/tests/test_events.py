import json

import pytest

from autocinematic.events import (
    CombatEvent, EventError, Player, assign_ticks, classify_weapon, read_jsonl, sort_events, write_jsonl,
)


@pytest.mark.parametrize("name,cls", [
    ("&eSniper", "sniper"), ("§6Sniper", "sniper"), ("Rifle", "rifle"), ("AutoShotgun", "shotgun"),
    ("DoubleBarrel", "shotgun"), ("RocketLauncher", "explosive"), ("Flamethrower", "flame"),
    ("Revolver", "pistol"), ("Pistol", "pistol"), ("AK-47", "rifle"), ("Banane", "other"), (None, None),
])
def test_classify_weapon_swornguns_names(name, cls):
    assert classify_weapon(name) == cls


def test_distance_is_computed_and_kill_is_lethal():
    ev = CombatEvent("kill", tick=10, pos=(0, 0, 0), target_pos=(3, 4, 0), weapon="&eSniper")
    assert ev.distance == pytest.approx(5.0)
    assert ev.lethal is True
    assert ev.weapon == "Sniper"
    assert ev.weapon_class == "sniper"
    assert ev.seconds == 0.5


def test_roundtrip_dict():
    ev = CombatEvent("hit", tick=42, time_ms=1_700_000_000_000, shooter=Player("A", "u-a"),
                     target=Player("B"), weapon="Rifle", headshot=True, damage=6.0,
                     pos=(1, 2, 3), target_pos=(4, 5, 6), dimension="minecraft:overworld", extra={"k": 1})
    d = ev.to_dict()
    assert d["v"] == 1 and d["type"] == "hit" and d["headshot"] is True
    back = CombatEvent.from_dict(json.loads(json.dumps(d)))
    assert back.to_dict() == d


@pytest.mark.parametrize("bad", [
    {"type": "explosion"}, {"v": 2, "type": "hit"}, {"tick": 1}, {"type": "hit", "tick": -1},
    {"type": "hit", "pos": [1, 2]}, {"type": "hit", "weaponClass": "laser"}, ["kein", "objekt"],
])
def test_invalid_events_are_rejected(bad):
    with pytest.raises(EventError):
        CombatEvent.from_dict(bad)


def test_jsonl_roundtrip_and_error_line_number(tmp_path):
    p = tmp_path / "e.jsonl"
    evs = [CombatEvent("shot", tick=1), CombatEvent("kill", tick=5, shooter=Player("A"))]
    assert write_jsonl(p, evs) == 2
    assert [e.to_dict() for e in read_jsonl(p)] == [e.to_dict() for e in evs]
    p.write_text('{"type":"shot","tick":1}\n# kommentar\n\n{"type":"boom"}\n', encoding="utf-8")
    with pytest.raises(EventError, match=r":4:"):
        read_jsonl(p)


def test_jsonl_with_utf8_bom_from_windows(tmp_path):
    p = tmp_path / "bom.jsonl"
    p.write_bytes('﻿{"type":"hit","tick":3,"shooter":"Spielerä"}\n'.encode("utf-8"))
    (ev,) = read_jsonl(p)
    assert ev.shooter.name == "Spielerä"


def test_assign_ticks_from_server_time():
    evs = [CombatEvent("hit", time_ms=10_000), CombatEvent("kill", time_ms=12_500),
           CombatEvent("shot", time_ms=1_000), CombatEvent("hit", tick=7, time_ms=99_999)]
    out = assign_ticks(evs, anchor_tick=100, anchor_ms=10_000)
    assert [e.tick for e in out] == [100, 150, 7]  # Ereignis vor Replay-Beginn verworfen, vorhandener Tick bleibt
    with pytest.raises(EventError):
        assign_ticks([CombatEvent("hit")], 0, 0)


def test_sort_order_shot_before_hit_before_kill_same_tick():
    evs = [CombatEvent("kill", tick=5), CombatEvent("shot", tick=5), CombatEvent("hit", tick=5), CombatEvent("shot", tick=1)]
    assert [(e.tick, e.type) for e in sort_events(evs)] == [(1, "shot"), (5, "shot"), (5, "hit"), (5, "kill")]


def test_to_dict_matches_json_schema_keys():
    from pathlib import Path
    schema = json.loads((Path(__file__).parents[2] / "schema" / "combat-event.v1.schema.json").read_text(encoding="utf-8"))
    ev = CombatEvent("kill", tick=1, time_ms=5, shooter=Player("A", "u"), target=Player("B"), weapon="Sniper",
                     distance=3.0, headshot=True, damage=2.0, pos=(0, 0, 0), target_pos=(1, 1, 1),
                     dimension="minecraft:overworld", extra={"shotId": 7})
    d = ev.to_dict()
    assert set(d) <= set(schema["properties"])
    assert d["weaponClass"] in schema["properties"]["weaponClass"]["enum"]
    assert set(schema["required"]) <= set(d)
