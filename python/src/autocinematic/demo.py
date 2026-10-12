"""Erzeugt ein synthetisches Flashback-Replay plus Ereignisse zum Testen der Pipeline.

Das Replay enthaelt nur metadata.json und Platzhalter-Dateien (keine echten
Minecraft-Pakete); es dient ausschliesslich zum Testen der Analyse und darf
nicht in Flashback geoeffnet werden.
"""
from __future__ import annotations

import json
import uuid
import zipfile
from pathlib import Path

from .events import CombatEvent, Player

DEMO_TOTAL_TICKS = 20 * 120  # 2 Minuten


def demo_events() -> list[CombatEvent]:
    a = Player("EnderSniper", "00000000-0000-0000-0000-00000000000a")
    b = Player("Gegner_B", "00000000-0000-0000-0000-00000000000b")
    c = Player("Gegner_C", "00000000-0000-0000-0000-00000000000c")
    d = Player("Rusher_D", "00000000-0000-0000-0000-00000000000d")
    ev: list[CombatEvent] = []
    # 0:10 Feuergefecht mit Gewehr
    for i in range(8):
        ev.append(CombatEvent("shot", tick=200 + i * 6, shooter=d, weapon="Rifle", pos=(10, 64, 10)))
        ev.append(CombatEvent("hit", tick=203 + i * 6, shooter=d if i % 2 else b, target=b if i % 2 else d,
                              weapon="Rifle", damage=4.0, pos=(10, 64, 10), target_pos=(25, 64, 18)))
    # 0:40 Sniper-Kopfschuss-Kill ueber 92 Bloecke
    ev.append(CombatEvent("shot", tick=800, shooter=a, weapon="&eSniper", pos=(0, 80, 0)))
    ev.append(CombatEvent("kill", tick=804, shooter=a, target=b, weapon="&eSniper", headshot=True,
                          damage=12.0, pos=(0, 80, 0), target_pos=(90, 64, 18), dimension="minecraft:overworld"))
    # 1:10 Doppel-Kill mit Schrotflinte
    ev.append(CombatEvent("kill", tick=1400, shooter=d, target=c, weapon="Shotgun", pos=(40, 64, 40), target_pos=(43, 64, 41)))
    ev.append(CombatEvent("kill", tick=1460, shooter=d, target=a, weapon="Shotgun", pos=(41, 64, 40), target_pos=(44, 64, 39)))
    # 1:40 einfacher Pistolen-Kill
    ev.append(CombatEvent("kill", tick=2000, shooter=c, target=d, weapon="Pistol", pos=(5, 64, 5), target_pos=(12, 64, 9)))
    return ev


def write_demo_replay(path: str | Path, *, with_user_marker: bool = True) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "uuid": str(uuid.UUID(int=0xAC)),
        "name": "AutoCinematic Demo",
        "version_string": "26.3",
        "world_name": "enderguns_demo",
        "data_version": 0,
        "protocol_version": 0,
        "total_ticks": DEMO_TOTAL_TICKS,
        "chunks": {"c0.flashback": {"duration": DEMO_TOTAL_TICKS, "forcePlaySnapshot": False}},
    }
    if with_user_marker:
        meta["markers"] = {
            "804": {"colour": 0x00AAFF, "description": "Mein eigener Marker"},
            "1200": {"colour": 0x00FF00, "description": "Turm",
                     "position": {"position": [12.5, 70.0, -3.5], "dimension": "minecraft:overworld"}},
        }
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("metadata.json", json.dumps(meta, indent=2))
        zf.writestr("c0.flashback", b"\x00DEMO-CHUNK" * 1000)
        zf.writestr("level_chunk_caches/0", b"\x01" * 4096)
        zf.writestr("icon.png", b"\x89PNG\r\n\x1a\n")
    return p
