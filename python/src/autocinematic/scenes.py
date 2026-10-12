"""Szenenerkennung und Schnittplan.

Aus Kampfereignissen werden Highlights (Sniper-Kill, Kopfschuss, Multi-Kill,
Distanzschuss, Feuergefecht) erkannt, zu Szenen mit Vor-/Nachlauf
zusammengefasst, bewertet und fuer ein Zielformat (Short, Trailer, ...)
ausgewaehlt. Pro Szene werden Kameraeinstellungen und Zeitlupen-Abschnitte
vorgeschlagen; die Kameratypen entsprechen den Shot-Typen von
CineWolf AutoDirector (reveal, crane, spiral, tracking, chase, close_detail).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from .events import TICKS_PER_SECOND, CombatEvent, sort_events

PLAN_VERSION = 1


@dataclass
class SceneConfig:
    long_shot_distance: float = 50.0
    multikill_window_ticks: int = 5 * TICKS_PER_SECOND
    firefight_window_ticks: int = 10 * TICKS_PER_SECOND
    firefight_min_hits: int = 6
    preroll_ticks: int = 3 * TICKS_PER_SECOND
    postroll_ticks: int = 2 * TICKS_PER_SECOND
    sniper_preroll_ticks: int = 4 * TICKS_PER_SECOND
    sniper_postroll_ticks: int = 3 * TICKS_PER_SECOND
    merge_gap_ticks: int = 1 * TICKS_PER_SECOND
    slowmo_speed: float = 0.3
    slowmo_before_ticks: int = 8
    slowmo_after_ticks: int = 24


FORMATS: dict[str, dict] = {
    "short": {"targetSeconds": 30, "aspect": "9:16", "maxScenes": 6},
    "tiktok": {"targetSeconds": 25, "aspect": "9:16", "maxScenes": 5},
    "trailer": {"targetSeconds": 75, "aspect": "16:9", "maxScenes": 12},
    "youtube": {"targetSeconds": 180, "aspect": "16:9", "maxScenes": 40},
    "all": {"targetSeconds": None, "aspect": "16:9", "maxScenes": None},
}


@dataclass
class Highlight:
    kind: str
    tick: int
    score: float
    label: str
    shooter: Optional[str] = None
    target: Optional[str] = None
    events: list[CombatEvent] = field(default_factory=list)
    start_tick: int = 0
    end_tick: int = 0

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "tick": self.tick,
            "seconds": round(self.tick / TICKS_PER_SECOND, 2),
            "score": round(self.score, 1),
            "label": self.label,
            "shooter": self.shooter,
            "target": self.target,
            "events": [e.to_dict() for e in self.events],
        }


# ------------------------------------------------------------------ Erkennung
def _name(p) -> Optional[str]:
    return p.name if p else None


def detect_highlights(events: Iterable[CombatEvent], cfg: SceneConfig | None = None) -> list[Highlight]:
    cfg = cfg or SceneConfig()
    evs = [e for e in sort_events(events) if e.tick is not None]
    out: list[Highlight] = []

    def window(kind: str, tick: int) -> tuple[int, int]:
        if kind.startswith("sniper"):
            return tick - cfg.sniper_preroll_ticks, tick + cfg.sniper_postroll_ticks
        return tick - cfg.preroll_ticks, tick + cfg.postroll_ticks

    # Einzel-Kills und besondere Treffer
    for e in evs:
        dist = e.distance or 0.0
        if e.type == "kill":
            if e.weapon_class == "sniper":
                kind, score = "sniper_kill", 90 + min(dist / 10.0, 20) + (15 if e.headshot else 0)
            elif e.headshot:
                kind, score = "headshot_kill", 70 + min(dist / 10.0, 10)
            elif dist >= cfg.long_shot_distance:
                kind, score = "long_shot_kill", 65 + min(dist / 10.0, 15)
            else:
                kind, score = "kill", 40.0
        elif e.type == "hit" and e.weapon_class == "sniper" and (e.headshot or dist >= cfg.long_shot_distance):
            kind, score = "sniper_hit", 35 + min(dist / 10.0, 15) + (10 if e.headshot else 0)
        elif e.type == "hit" and dist >= cfg.long_shot_distance:
            kind, score = "long_shot_hit", 25 + min(dist / 10.0, 10)
        else:
            continue
        s, t = window(kind, e.tick)
        out.append(Highlight(kind=kind, tick=e.tick, score=score, label=e.label(),
                             shooter=_name(e.shooter), target=_name(e.target), events=[e],
                             start_tick=s, end_tick=t))

    # Multi-Kills: Kills desselben Schuetzen, jeweils <= Fenster auseinander
    by_shooter: dict[str, list[CombatEvent]] = {}
    for e in evs:
        if e.type == "kill" and e.shooter:
            by_shooter.setdefault(e.shooter.key, []).append(e)
    names = {2: "Doppel-Kill", 3: "Dreifach-Kill", 4: "Vierfach-Kill"}
    for kills in by_shooter.values():
        chain: list[CombatEvent] = []
        for k in kills + [None]:  # type: ignore[list-item]
            if k is not None and chain and k.tick - chain[-1].tick <= cfg.multikill_window_ticks:
                chain.append(k)
                continue
            if len(chain) >= 2:
                n = len(chain)
                label = f"{names.get(n, f'{n}-fach-Kill')}: {chain[0].shooter.name}"
                out.append(Highlight(kind="multi_kill", tick=chain[-1].tick, score=60 + 25 * (n - 2),
                                     label=label, shooter=chain[0].shooter.name, events=list(chain),
                                     start_tick=chain[0].tick - cfg.preroll_ticks,
                                     end_tick=chain[-1].tick + cfg.postroll_ticks))
            chain = [k] if k is not None else []

    # Feuergefechte: viele Treffer in kurzer Zeit
    hits = [e for e in evs if e.type in ("hit", "kill")]
    i = 0
    while i < len(hits):
        j = i
        while j + 1 < len(hits) and hits[j + 1].tick - hits[i].tick <= cfg.firefight_window_ticks:
            j += 1
        group = hits[i:j + 1]
        players = {p.key for e in group for p in (e.shooter, e.target) if p}
        if len(group) >= cfg.firefight_min_hits and len(players) >= 2:
            out.append(Highlight(kind="firefight", tick=group[len(group) // 2].tick,
                                 score=30 + 2 * len(group), label=f"Feuergefecht ({len(group)} Treffer)",
                                 events=list(group), start_tick=group[0].tick - cfg.preroll_ticks // 2,
                                 end_tick=group[-1].tick + cfg.postroll_ticks))
            i = j + 1
        else:
            i += 1
    return sorted(out, key=lambda h: (h.tick, -h.score))


# ------------------------------------------------------------------- Szenen
@dataclass
class Scene:
    start_tick: int
    end_tick: int
    highlights: list[Highlight]

    @property
    def main(self) -> Highlight:
        return max(self.highlights, key=lambda h: h.score)

    @property
    def score(self) -> float:
        scores = sorted((h.score for h in self.highlights), reverse=True)
        return scores[0] + 0.25 * sum(scores[1:])

    @property
    def source_ticks(self) -> int:
        return self.end_tick - self.start_tick


def build_scenes(highlights: list[Highlight], total_ticks: Optional[int] = None,
                 cfg: SceneConfig | None = None) -> list[Scene]:
    cfg = cfg or SceneConfig()
    scenes: list[Scene] = []
    for h in sorted(highlights, key=lambda h: h.start_tick):
        s = max(0, h.start_tick)
        e = h.end_tick if total_ticks is None else min(total_ticks, h.end_tick)
        if e <= s:
            continue
        if scenes and s <= scenes[-1].end_tick + cfg.merge_gap_ticks:
            scenes[-1].end_tick = max(scenes[-1].end_tick, e)
            scenes[-1].highlights.append(h)
        else:
            scenes.append(Scene(s, e, [h]))
    return scenes


# ------------------------------------------------------- Kamera & Zeitlupe
def suggest_shots(scene: Scene, cfg: SceneConfig) -> tuple[list[dict], list[dict]]:
    h = scene.main
    impact = h.tick
    s, e = scene.start_tick, scene.end_tick
    shooter, target = h.shooter, h.target
    shots: list[dict] = []
    speed: list[dict] = []

    def add(kind: str, subject, a: int, b: int, note: str = ""):
        a, b = max(s, a), min(e, b)
        if b > a:
            d = {"type": kind, "subject": subject, "startTick": a, "endTick": b}
            if note:
                d["note"] = note
            shots.append(d)

    if h.kind in ("sniper_kill", "sniper_hit"):
        add("tracking", shooter, s, impact - 10, "Schuetze legt an")
        add("close_detail", shooter, impact - 10, impact + 2, "Schuss aus naechster Naehe")
        add("reveal", target, impact + 2, e, "Einschlag beim Ziel")
        speed.append({"startTick": max(s, impact - cfg.slowmo_before_ticks),
                      "endTick": min(e, impact + cfg.slowmo_after_ticks), "speed": cfg.slowmo_speed})
    elif h.kind == "multi_kill":
        add("chase", shooter, s, e, "Schuetze verfolgen")
        for ev in h.events:
            speed.append({"startTick": max(s, ev.tick - 4), "endTick": min(e, ev.tick + 10), "speed": 0.5})
    elif h.kind in ("headshot_kill", "long_shot_kill", "long_shot_hit"):
        add("tracking", shooter, s, impact - 4)
        add("spiral", target, impact - 4, e, "Treffer umkreisen")
        speed.append({"startTick": max(s, impact - 6), "endTick": min(e, impact + 16), "speed": 0.4})
    elif h.kind == "firefight":
        add("crane", None, s, e, "Ueberblick ueber das Gefecht")
    else:
        add("tracking", shooter, s, impact)
        add("reveal", target, impact, e)
    return shots, speed


def _output_ticks(scene: Scene, speed: list[dict]) -> float:
    slow = sum((seg["endTick"] - seg["startTick"]) * (1 / seg["speed"] - 1) for seg in speed)
    return scene.source_ticks + slow


# --------------------------------------------------------------------- Plan
def make_plan(events: Iterable[CombatEvent], *, fmt: str = "short", total_ticks: Optional[int] = None,
              cfg: SceneConfig | None = None, replay: Optional[dict] = None) -> dict:
    if fmt not in FORMATS:
        raise ValueError(f"Unbekanntes Format {fmt!r} (verfuegbar: {', '.join(FORMATS)})")
    cfg = cfg or SceneConfig()
    spec = FORMATS[fmt]
    evs = list(events)
    highlights = detect_highlights(evs, cfg)
    scenes = build_scenes(highlights, total_ticks, cfg)

    enriched = []
    for sc in scenes:
        shots, speed = suggest_shots(sc, cfg)
        enriched.append((sc, shots, speed, _output_ticks(sc, speed)))

    # Auswahl nach Bewertung bis Zieldauer / maximale Szenenzahl erreicht
    target = spec["targetSeconds"]
    chosen = []
    total_out = 0.0
    for item in sorted(enriched, key=lambda x: -x[0].score):
        if spec["maxScenes"] is not None and len(chosen) >= spec["maxScenes"]:
            break
        if target is not None and total_out >= target * TICKS_PER_SECOND:
            break
        chosen.append(item)
        total_out += item[3]
    chosen.sort(key=lambda x: x[0].start_tick)  # chronologisch (wie CineWolf plant)

    out_scenes = []
    for n, (sc, shots, speed, out_ticks) in enumerate(chosen, 1):
        out_scenes.append({
            "id": n,
            "startTick": sc.start_tick,
            "endTick": sc.end_tick,
            "startSeconds": round(sc.start_tick / TICKS_PER_SECOND, 2),
            "endSeconds": round(sc.end_tick / TICKS_PER_SECOND, 2),
            "score": round(sc.score, 1),
            "label": sc.main.label,
            "kind": sc.main.kind,
            "focus": sc.main.shooter,
            "highlights": [h.to_dict() for h in sc.highlights],
            "shots": shots,
            "speed": speed,
            "outputSeconds": round(out_ticks / TICKS_PER_SECOND, 2),
        })
    counts = {t: sum(1 for e in evs if e.type == t) for t in ("shot", "hit", "kill")}
    return {
        "planVersion": PLAN_VERSION,
        "format": fmt,
        "aspect": spec["aspect"],
        "targetSeconds": target,
        "replay": replay or {},
        "eventCounts": counts,
        "highlightCount": len(highlights),
        "sceneCandidates": len(scenes),
        "scenes": out_scenes,
        "estimatedOutputSeconds": round(sum(s["outputSeconds"] for s in out_scenes), 2),
    }
