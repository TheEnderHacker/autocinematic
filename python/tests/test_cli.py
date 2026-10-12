import json

from autocinematic.cli import main


def test_end_to_end_demo_pipeline(tmp_path, capsys):
    d = tmp_path / "demo"
    assert main(["demo", "-o", str(d)]) == 0
    replay, events = d / "demo-replay.zip", d / "demo-events.jsonl"

    assert main(["plan", "--replay", str(replay), "--events", str(events), "--format", "short",
                 "-o", str(d / "plan.json")]) == 0
    plan = json.loads((d / "plan.json").read_text(encoding="utf-8"))
    assert plan["replay"]["name"] == "AutoCinematic Demo" and plan["scenes"]

    assert main(["inject", str(replay), "--events", str(events), "--plan", str(d / "plan.json"),
                 "-o", str(d / "marked.zip")]) == 0
    capsys.readouterr()
    assert main(["info", str(d / "marked.zip")]) == 0
    info = json.loads(capsys.readouterr().out)
    assert info["eventCounts"]["kill"] == 4 and info["autocinematicMarkers"] >= 1

    assert main(["extract", str(d / "marked.zip"), "-o", str(d / "back.jsonl")]) == 0
    assert len((d / "back.jsonl").read_text(encoding="utf-8").splitlines()) == 12  # 8 Treffer + 4 Kills

    # Plan nur aus dem markierten Replay ergibt dieselben Szenen-Starts
    assert main(["plan", "--replay", str(d / "marked.zip"), "--format", "short", "-o", str(d / "plan2.json")]) == 0
    plan2 = json.loads((d / "plan2.json").read_text(encoding="utf-8"))
    assert [s["kind"] for s in plan2["scenes"]] == [s["kind"] for s in plan["scenes"]]


def test_cli_errors_are_reported_not_raised(tmp_path, capsys):
    assert main(["info", str(tmp_path / "fehlt.zip")]) == 1
    assert "nicht gefunden" in capsys.readouterr().err
    assert main(["plan"]) == 2
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"type":"boom"}\n', encoding="utf-8")
    assert main(["plan", "--events", str(bad)]) == 1
