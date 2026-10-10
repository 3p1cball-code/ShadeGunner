#!/usr/bin/env python3
"""Headless-Sim-Tests (kein pytest nötig): python3 tests/test_sim.py"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from voight import config  # noqa: E402
from voight.detection import STRONG_TELLS, TELLS, confidence  # noqa: E402
from voight.sim import ZONES, World  # noqa: E402


def test_population():
    w = World(seed=1)
    assert len(w.actors) > 5, "zu wenige Aktoren"
    reps = [a for a in w.actors if a.is_replicant]
    assert len(reps) >= 1, "keine Replikanten erzeugt"
    assert w.replicants_total == len(reps)


def test_confidence_calibration():
    tells = {k: True for k in TELLS}
    all_rev = set(TELLS)
    hi = confidence(all_rev, tells)
    assert hi > 0.9, f"alle starken Tells sollten hohe Konfidenz geben, war {hi}"

    none_rev = set()
    mid = confidence(none_rev, tells)
    assert 0.2 < mid < 0.4, f"ohne Tells nahe Prior erwartet, war {mid}"

    human = {k: False for k in TELLS}
    lo = confidence(all_rev, human)
    assert lo < 0.05, f"keinerlei Tells -> niedrig erwartet, war {lo}"


def test_scan_reveals_and_costs():
    w = World(seed=2)
    target = next(a for a in w.actors if not a.player)
    w.player.x = target.x
    before = w.scan_charges
    res, a = w.scan()
    assert res == "ok" and a is target
    assert w.scan_charges < before, "Scan sollte Ladung kosten"
    assert STRONG_TELLS[0] in target.revealed, "Scan sollte starke Tells aufdecken"
    assert target.scanned


def test_neutralize_outcomes():
    w = World(seed=3, zone_index=2)
    rep = next(a for a in w.actors if a.is_replicant)
    w.player.x = rep.x
    res, a = w.neutralize()
    assert res == "replicant" and not rep.alive
    assert w.points == 1

    civ = next(a for a in w.actors if not a.is_replicant and a.alive)
    w.player.x = civ.x
    s_before = w.suspicion
    res, _ = w.neutralize()
    assert res == "civilian"
    assert w.suspicion > s_before


def test_failure_on_too_many_civilians():
    w = World(seed=4, zone_index=2)
    killed = 0
    for a in list(w.actors):
        if a.is_replicant or a.player or not a.alive:
            continue
        w.player.x = a.x
        w.neutralize()
        killed += 1
        if w.state == "failed":
            break
    assert w.state == "failed", "genug Zivilisten -> Run muss scheitern"


def test_zone_progression():
    w = World(seed=5)
    w.player.x = w.length + 1
    w.update(0.016, (0, 0))
    assert w.state == "zone_clear"
    assert w.advance_zone() is True
    assert w.zone_index == 1 and w.state == "playing"

    # letzte Zone -> finished
    w.zone_index = len(ZONES) - 1
    w.state = "zone_clear"
    assert w.advance_zone() is False
    assert w.state == "finished"


def test_projection_monotonic():
    w = World(seed=6)
    near = w.project(type("A", (), {"x": 0.0, "depth": 0.95})(), 512, 288)
    far = w.project(type("A", (), {"x": 0.0, "depth": 0.2})(), 512, 288)
    # näher = größer und weiter unten
    assert near[2] > far[2], "nähere Figur muss größer sein"
    assert near[1] > far[1], "nähere Figur muss weiter unten stehen"


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    fails = 0
    for t in tests:
        try:
            t()
            print(f"  ok   {t.__name__}")
        except AssertionError as exc:
            fails += 1
            print(f"  FAIL {t.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            fails += 1
            print(f"  ERR  {t.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - fails}/{len(tests)} bestanden")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
