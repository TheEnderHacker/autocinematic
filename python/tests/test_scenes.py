import pytest

from autocinematic.demo import DEMO_TOTAL_TICKS, demo_events
from autocinematic.events import CombatEvent, Player
from autocinematic.scenes import SceneConfig, build_scenes, detect_highlights, make_plan


def kinds(hs):
    return [h.kind for h in hs]


def test_demo_highlights():
    hs = detect_highlights(demo_events())
    k = kinds(hs)
    assert "sniper_kill" in k
    assert "multi_kill" in k
    assert "firefight" in k
    assert k.count("kill") >= 1
    best = max(hs, key=lambda h: h.score)
    assert best.kind == "sniper_kill" and best.shooter == "EnderSniper"
    assert best.events[0].distance == pytest.approx(93.17, abs=0.01)


def test_multikill_counts_and_window():
    a = Player("A")
    evs = [CombatEvent("kill", tick=t, shooter=a, target=Player(f"V{t}")) for t in (0, 50, 100, 400)]
    mk = [h for h in detect_highlights(evs) if h.kind == "multi_kill"]
    assert len(mk) == 1 and len(mk[0].events) == 3 and "Dreifach" in mk[0].label
    # anderer Schuetze unterbricht keine Kette, zaehlt aber nicht mit
    evs2 = evs[:2] + [CombatEvent("kill", tick=60, shooter=Player("B"))]
    mk2 = [h for h in detect_highlights(evs2) if h.kind == "multi_kill"]
    assert len(mk2) == 1 and mk2[0].shooter == "A"


def test_long_shot_and_plain_hits():
    evs = [CombatEvent("hit", tick=100, distance=70, weapon="Rifle"),
           CombatEvent("hit", tick=200, distance=10, weapon="Rifle"),
           CombatEvent("hit", tick=300, distance=60, weapon="Sniper", headshot=True)]
    assert kinds(detect_highlights(evs)) == ["long_shot_hit", "sniper_hit"]


def test_scenes_merge_and_clamp():
    cfg = SceneConfig()
    evs = [CombatEvent("kill", tick=10, shooter=Player("A")), CombatEvent("kill", tick=70, shooter=Player("B")),
           CombatEvent("kill", tick=990, shooter=Player("C"))]
    scenes = build_scenes(detect_highlights(evs, cfg), total_ticks=1000, cfg=cfg)
    assert len(scenes) == 2
    assert scenes[0].start_tick == 0  # nicht negativ
    assert scenes[1].end_tick == 1000  # nicht ueber Replay-Ende
    assert len(scenes[0].highlights) == 2


def test_plan_short_respects_target_and_is_chronological():
    plan = make_plan(demo_events(), fmt="short", total_ticks=DEMO_TOTAL_TICKS)
    assert plan["aspect"] == "9:16"
    ticks = [s["startTick"] for s in plan["scenes"]]
    assert ticks == sorted(ticks)
    assert plan["scenes"], "mindestens eine Szene"
    assert any(s["kind"] == "sniper_kill" for s in plan["scenes"])
    # Sniper-Szene hat Zeitlupe und drei Einstellungen
    sn = next(s for s in plan["scenes"] if s["kind"] == "sniper_kill")
    assert [x["type"] for x in sn["shots"]] == ["tracking", "close_detail", "reveal"]
    assert sn["speed"][0]["speed"] == pytest.approx(0.3)
    assert sn["outputSeconds"] > (sn["endTick"] - sn["startTick"]) / 20
    # Zieldauer wird hoechstens um eine Szene ueberschritten
    longest = max(s["outputSeconds"] for s in plan["scenes"])
    assert plan["estimatedOutputSeconds"] < plan["targetSeconds"] + longest
    assert plan["eventCounts"] == {"shot": 9, "hit": 8, "kill": 4}


def test_plan_all_contains_every_scene_and_unknown_format_fails():
    full = make_plan(demo_events(), fmt="all", total_ticks=DEMO_TOTAL_TICKS)
    assert len(full["scenes"]) == full["sceneCandidates"]
    with pytest.raises(ValueError):
        make_plan([], fmt="kino")


def test_empty_input_gives_empty_plan():
    plan = make_plan([], fmt="short")
    assert plan["scenes"] == [] and plan["estimatedOutputSeconds"] == 0
