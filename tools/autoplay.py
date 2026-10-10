#!/usr/bin/env python3
"""Balancing-Bot: spielt Runs headless mit einer einfachen, vernünftigen Strategie.

Strategie: vorwärts gehen, nahe ungescannte Passanten anvisieren und beobachten,
bei Ladung scannen, ab Konfidenz-Schwelle schießen (Schusslinie per Tiefe frei
machen), Angreifer sofort erschießen. Ausgabe: Statistik pro Zone über N Runs.

Aufruf: python3 tools/autoplay.py [runs] [schwelle]
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shadegunner import config  # noqa: E402
from shadegunner.sim import ZONES, Run, World  # noqa: E402

DT = 1 / 30


def bot_step(w, thr, mem):
    p = w.player
    inp = dict(move=(1, 0))
    tg = w.target
    for a in w.living():
        if a.state in ("attack", "punch") and w.dist(p, a) < config.SHOOT_RANGE:
            w.target = tg = a
    if tg is not None and tg.alive:
        conf = w.confidence_of(tg)
        hostile = tg.state in ("attack", "punch")
        if hostile or (tg.revealed and conf >= thr):
            blk = w.line_of_fire(tg)
            if blk is not tg and blk is not None:
                inp["move"] = (0, 1 if tg.depth > p.depth else -1)
                return inp
            if mem.get("aim", 0) < 0.25:
                mem["aim"] = mem.get("aim", 0) + DT
                inp["aim"] = True
                inp["move"] = (0, 0)
                return inp
            mem["aim"] = 0
            return dict(move=(0, 0), aim=False)
        if not tg.scanned and w.dist(p, tg) < config.SCAN_RANGE * 0.8 and w.scan_charges >= 1:
            dd = tg.depth - p.depth
            if abs(dd) > 0.08:
                return dict(move=(0, 1 if dd > 0 else -1))
            return dict(move=(0, 0), scan=True)
        if tg.scanned:
            return dict(move=(1, 0), cycle=1)
        if not tg.scanned and w.scan_charges < 1:
            # beobachten, während Ladung kommt
            return dict(move=(0.3 if w.dist(p, tg) > 60 else 0, 0))
    if mem.get("aim"):
        mem["aim"] = 0
        return dict(move=(0, 0), aim=False)
    return inp


def dodge(w, inp):
    """Reaktion wie ein aufmerksamer Spieler: Fahrspur räumen, Angriffen ausspringen."""
    p = w.player
    for v in w.vehicles:
        ahead = (p.x - v["x"]) * v["dir"]
        if -v["L"] * 0.5 < ahead < v["speed"] * 1.5 + v["L"] * 0.5 and abs(p.depth - v["depth"]) < config.LANE_HALF + 0.05:
            side = 1 if p.depth >= v["depth"] else -1
            if v["depth"] + side * 0.15 > config.DEPTH_MAX or v["depth"] + side * 0.15 < config.DEPTH_MIN:
                side = -side
            return dict(move=(0, side))
    mx = inp.get("move", (0, 0))[0]
    if mx and p.z <= 0 and w.blocked(p.x + 8 * (1 if mx > 0 else -1), p.depth, 0.0):
        out = dict(inp)
        out["jump"] = True
        return out
    for a in w.living():
        if a.state in ("leap", "punch") and abs(a.x - p.x) < 50 and abs(a.depth - p.depth) < 0.12 and p.z <= 0:
            out = dict(inp)
            out["jump"] = True
            return out
    return inp


def play(seed, thr):
    rng = random.Random(seed)
    run = Run(seed)
    w = World(run, seed=seed, zone_index=0)
    mem = {}
    rows = []
    t = 0.0
    while True:
        inp = dodge(w, bot_step(w, thr, mem))
        w.update(DT, inp)
        w.events.clear()
        t += DT
        if w.state == "zone_clear":
            rows.append((w.zone_index, dict(w.stats), w.mission_failed))
            run.apply(run.offer(rng)[0][0])
            nw = w.next_world()
            if nw is None:
                return rows, "won", run
            w = nw
            mem = {}
        elif w.state == "failed":
            rows.append((w.zone_index, dict(w.stats), True))
            return rows, w.fail_reason, run
        if w.stats["time"] > 600:
            rows.append((w.zone_index, dict(w.stats), True))
            return rows, "timeout", run


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    thr = float(sys.argv[2]) if len(sys.argv) > 2 else 0.6
    agg = {z: dict(n=0, reps=0, civs=0, esc=0, time=0.0, miss=0) for z in range(len(ZONES))}
    ends = {}
    scores = []
    for s in range(n):
        rows, end, run = play(1000 + s, thr)
        ends[end] = ends.get(end, 0) + 1
        scores.append(run.score)
        for z, st, miss in rows:
            a = agg[z]
            a["n"] += 1
            a["reps"] += st["reps"]
            a["civs"] += st["civs"]
            a["esc"] += st["escaped"]
            a["time"] += st["time"]
            a["miss"] += 1 if miss else 0
    print(f"Schwelle {thr}: Enden {ends}  Ø Punkte {sum(scores) / len(scores):.0f}")
    for z, a in agg.items():
        if a["n"]:
            k = a["n"]
            print(f"  {ZONES[z]['name']:<12} n={k:3d}  Rep {a['reps'] / k:4.1f}/{ZONES[z]['replicants']}  "
                  f"Zivil {a['civs'] / k:4.2f}  Entk {a['esc'] / k:4.2f}  Zeit {a['time'] / k:5.0f}s  "
                  f"verfehlt {a['miss'] / k:4.0%}")


if __name__ == "__main__":
    main()
