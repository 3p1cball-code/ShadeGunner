#!/usr/bin/env python3
"""Headless-Sim-Tests (kein pytest nötig): python3 tests/test_sim.py"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shadegunner import config, persp  # noqa: E402
from shadegunner.detection import ORDER, STRONG_TELLS, confidence, likelihoods, spawn_tells  # noqa: E402
from shadegunner.sim import ZONES, Run, World  # noqa: E402

DT = 1 / 60


def _place_near(w, a, dx=20.0):
    w.player.x = a.x - dx
    w.player.depth = a.depth
    w.player.facing = 1
    w.camera_x = w.player.x + 40


def _run_scan(w, a):
    _place_near(w, a)
    w.target = a
    res, t = w.scan()
    for _ in range(200):
        if w.scan_t < 0:
            break
        w.update(DT, {})
    return res, t


def test_population():
    w = World(seed=1)
    assert len(w.actors) > 10, "zu wenige Aktoren"
    reps = [a for a in w.actors if a.is_replicant]
    assert len(reps) == ZONES[0]["replicants"]
    assert w.replicants_total == len(reps)
    assert 0 < w.prior < 0.5


def test_confidence_calibration():
    tells = {k: True for k in ORDER}
    hi = confidence(set(ORDER), tells, 0.5, 0.1)
    assert hi > 0.9, f"alle Tells -> hohe Konfidenz erwartet, war {hi}"
    mid = confidence(set(), tells, 0.5, 0.1)
    assert abs(mid - 0.1) < 1e-6, f"ohne Tells = Prior erwartet, war {mid}"
    lo = confidence(set(ORDER), {k: False for k in ORDER}, 0.5, 0.1)
    assert lo < 0.02, f"keine Tells -> niedrig erwartet, war {lo}"


def test_camo_makes_it_harder():
    """Außenbezirk muss leichter sein als Tyrell (früherer Bug: umgekehrt)."""
    easy, hard = likelihoods(0.0), likelihoods(1.0)
    for n in ORDER:
        assert easy[n][0] > hard[n][0], f"{n}: Replikanten-Tells sollen mit Tarnung seltener werden"
        assert easy[n][1] < hard[n][1], f"{n}: Gegen-Tells sollen mit Tarnung häufiger werden"


def test_calibration_empirical():
    """Gemeldete Konfidenz ~ tatsächliche Trefferquote (Bins), d. h. ehrlich kalibriert."""
    rng = random.Random(3)
    camo, prior = 0.5, 0.15
    bins = {}
    for _ in range(40000):
        rep = rng.random() < prior
        tells = spawn_tells(rng, rep, camo)
        c = confidence(set(ORDER), tells, camo, prior)
        b = min(4, int(c * 5))
        n, k = bins.get(b, (0, 0))
        bins[b] = (n + 1, k + (1 if rep else 0))
    for b, (n, k) in bins.items():
        if n < 400:
            continue
        rate = k / n
        assert b / 5 - 0.08 <= rate <= (b + 1) / 5 + 0.08, f"Bin {b}: Quote {rate:.2f} passt nicht"


def test_scan_reveals_and_costs():
    w = World(seed=2)
    target = next(a for a in w.actors if not a.player)
    before = w.scan_charges
    res, a = _run_scan(w, target)
    assert res == "ok" and a is target
    assert w.scan_charges < before, "Scan sollte Ladung kosten"
    assert target.scanned and STRONG_TELLS[0] in target.revealed
    assert "serial" in target.revealed, "Nahscan sollte die Seriennummer zeigen"


def test_scan_far_hides_serial():
    w = World(seed=2)
    target = next(a for a in w.actors if not a.player)
    w.player.x = target.x - 110
    w.player.depth = target.depth
    w.camera_x = w.player.x + 60
    w.target = target
    w.scan()
    for _ in range(200):
        if w.scan_t < 0:
            break
        w.update(DT, {})
    if target.scanned:
        assert "serial" not in target.revealed


def test_kill_outcomes():
    w = World(seed=3, zone_index=2)
    rep = next(a for a in w.actors if a.is_replicant)
    _place_near(w, rep)
    w.target = rep
    for a in w.actors:          # Schusslinie frei räumen
        if a is not rep and not a.player and abs(a.x - rep.x) < 40:
            a.depth = 0.12 if rep.depth > 0.5 else 0.97
    res, hit = w.fire()
    assert res == "replicant" and not rep.alive and hit is rep
    assert w.stats["reps"] == 1 and w.run.score > 0

    civ = next(a for a in w.actors if not a.is_replicant and a.alive and not a.player)
    _place_near(w, civ)
    w.target = civ
    w.shot_cd = 0
    for a in w.actors:
        if a is not civ and not a.player and a.alive and abs(a.x - civ.x) < 40:
            a.depth = 0.12 if civ.depth > 0.5 else 0.97
    s0 = w.suspicion
    res, _ = w.fire()
    assert res == "civilian" and w.suspicion > s0


def test_line_of_fire_blocker():
    w = World(seed=4, zone_index=2)
    npcs = [a for a in w.actors if not a.player][:2]
    t, b = npcs
    w.player.x, w.player.depth = 100.0, 0.5
    t.x, t.depth = 180.0, 0.5
    b.x, b.depth = 140.0, 0.5
    w.target = t
    assert w.line_of_fire(t) is b, "Person dazwischen muss die Kugel fangen"
    b.depth = 0.9
    assert w.line_of_fire(t) is t, "nach Tiefenwechsel ist die Linie frei"


def test_failure_on_too_many_civilians():
    w = World(seed=4, zone_index=2)
    for a in list(w.actors):
        if a.is_replicant or a.player or not a.alive:
            continue
        w.shot_cd = 0
        _place_near(w, a)
        w.target = a
        w.fire()
        if w.state == "failed":
            break
    assert w.state == "failed" and w.fail_reason == "suspicion"


def test_exit_locked_until_quota():
    w = World(seed=5)
    w.player.x = w.length + 5
    w.update(DT, dict(move=(1, 0)))
    assert w.state == "playing", "Ausgang muss ohne Auftrag gesperrt sein"
    for a in w.actors:
        if a.is_replicant and w.stats["reps"] < w.quota:
            w._kill(a)
    w.player.x = w.length + 5
    w.update(DT, dict(move=(1, 0)))
    assert w.state == "zone_clear"


def test_zone_progression_and_run_carry():
    run = Run(7)
    w = World(run, seed=7, zone_index=0)
    for a in w.actors:
        if a.is_replicant:
            w._kill(a)
    w._zone_clear()
    score = run.score
    run.apply("akku")
    nw = w.next_world()
    assert nw is not None and nw.zone_index == 1 and nw.state == "playing"
    assert nw.run.score == score and nw.scan_max == config.SCAN_CHARGES + 2
    w.zone_index = len(ZONES) - 1
    assert w.next_world() is None


def test_attacker_hurts_player():
    w = World(seed=8, zone_index=4)
    rep = next(a for a in w.actors if a.is_replicant)
    rep.aggressive = True
    w._alert(rep)
    rep.x, rep.depth = w.player.x + 30, w.player.depth
    rep.target_depth = rep.depth
    hp0 = w.player.hp
    for _ in range(300):
        w.update(DT, {})
        if w.player.hp < hp0:
            break
    assert w.player.hp < hp0, "angreifender Replikant muss Schaden machen"


def test_long_random_play_no_crash():
    """Zufallsspieler über alle Zonen: keine Ausnahme, Zustände konsistent."""
    rng = random.Random(11)
    run = Run(11)
    w = World(run, seed=11, zone_index=0)
    steps = 0
    while steps < 60 * 400:
        inp = dict(move=(rng.choice((1, 1, 1, 0, -1)), rng.choice((0, 0, 1, -1))),
                   sprint=rng.random() < 0.3, aim=rng.random() < 0.2,
                   scan=rng.random() < 0.01, cycle=1 if rng.random() < 0.01 else 0)
        w.update(DT, inp)
        w.events.clear()
        steps += 1
        if w.state == "zone_clear":
            run.apply(run.offer(rng)[0][0])
            nw = w.next_world()
            if nw is None:
                break
            w = nw
        elif w.state == "failed":
            break
    assert steps > 100


def test_projection_monotonic():
    assert persp.figure_h(0.95) > persp.figure_h(0.2)
    assert persp.ground_y(0.95) > persp.ground_y(0.2)
    # Häuserfront liegt hinter der Straße und scrollt langsamer
    assert persp.FACADE_Y < persp.ground_y(0.0) and persp.FACADE_PPU < persp.ppu(0.0)


def _quiet(w):
    """Keine Zufallsereignisse, die einen Einzeltest stören."""
    w.traffic_cd = 1e9
    w.patrol_cd = None
    w.blackout_at = None
    w.vehicles.clear()


def test_jump_clears_obstacle():
    w = World(seed=4, zone_index=1)
    _quiet(w)
    o = dict(x=500.0, d=0.5, w=8.0, dd=0.05, h=9.0, kind="crates", seed=1)
    w.obstacles = [o]
    w.actors = [w.player]
    p = w.player
    p.x, p.depth = 480.0, 0.5
    for _ in range(60):
        w.update(DT, dict(move=(1, 0)))
    assert p.x < o["x"] - o["w"], f"ohne Sprung durchs Hindernis gelaufen (x={p.x:.1f})"
    w.update(DT, dict(move=(1, 0), jump=True))
    peak = 0.0
    for _ in range(90):
        w.update(DT, dict(move=(1, 0)))
        peak = max(peak, p.z)
    assert peak > o["h"], f"Sprung zu niedrig ({peak:.1f})"
    assert p.x > o["x"] + o["w"], f"nicht drübergesprungen (x={p.x:.1f})"
    assert p.z == 0.0, "nicht gelandet"


def test_jump_dodges_punch():
    w = World(seed=5, zone_index=2)
    _quiet(w)
    rep = next(a for a in w.actors if a.is_replicant)
    w.actors = [w.player, rep]
    p = w.player
    rep.x, rep.depth = p.x + 10, p.depth
    rep.state, rep.timer, rep.hit_done = "punch", 0.25, False
    p.vz, p.z = config.JUMP_V, 0.01
    for _ in range(3):
        w.update(DT, {})
    hp = p.hp
    for _ in range(10):
        w.update(DT, {})
    assert p.hp == hp, "Schlag hätte im Sprung ins Leere gehen müssen"


def test_vehicle_hits_player_in_lane():
    w = World(seed=6, zone_index=2)
    _quiet(w)
    w.actors = [w.player]
    p = w.player
    lane, dr = config.LANES[1]
    p.depth = lane
    w.vehicles.append(dict(x=p.x - dr * 120, depth=lane, dir=dr, speed=200.0, kind="car", L=87.0, h=25.5,
                           seed=1, honk=False, uid=-1))
    hp = p.hp
    for _ in range(90):
        w.update(DT, {})
    assert p.hp == hp - 1, "Fahrzeug hat den Spieler nicht erwischt"
    assert abs(p.depth - lane) > config.LANE_HALF, "Spieler nicht aus der Spur geschleudert"


def test_npcs_dodge_traffic():
    w = World(seed=7, zone_index=2)
    _quiet(w)
    lane, dr = config.LANES[0]
    civ = next(a for a in w.actors if not a.player and not a.is_replicant)
    civ.depth = civ.target_depth = lane
    civ.state, civ.vx = "idle", 0.0
    civ.timer = 99
    w.vehicles.append(dict(x=civ.x - dr * 300, depth=lane, dir=dr, speed=180.0, kind="car", L=87.0, h=25.5,
                           seed=1, honk=False, uid=-1))
    for _ in range(int(1.4 / DT)):
        w.update(DT, {})
    assert abs(civ.depth - lane) > config.LANE_HALF - 0.01, f"Passant blieb auf der Spur ({civ.depth:.2f})"


def test_bounty_and_tough():
    w = World(seed=8, zone_index=2)
    _quiet(w)
    b = w.bounty
    assert b is not None and b.is_replicant and b.hp == 2 and w.bounty_desc
    _place_near(w, b, 30)
    w.target = b
    score = w.run.score
    w.shot_cd = 0
    assert w._hit(b) == "tough" and b.alive
    assert w._hit(b) == "replicant" and not b.alive
    assert w.run.score - score >= config.POINTS_REPLICANT + config.POINTS_BOUNTY


def test_cancel_aim_no_shot():
    w = World(seed=11, zone_index=1)
    _quiet(w)
    civ = next(a for a in w.living() if not a.is_replicant)
    _place_near(w, civ, 30)
    civ.state, civ.timer, civ.vx = "idle", 99, 0.0
    w.set_target(civ)
    for _ in range(30):
        w.update(DT, dict(aim=True))
    assert w.aiming
    w.update(DT, dict(aim=True, cancel=True))          # abbrechen, während gehalten wird
    assert not w.aiming and w.aim_latch
    for _ in range(40):
        w.update(DT, dict(aim=True))                    # weiter gehalten -> kein Schuss
    assert civ.alive and w.stats["shots"] == 0, "Schuss trotz Abbruch!"
    w.update(DT, {})                                    # loslassen -> Sperre lösen
    assert not w.aim_latch
    for _ in range(30):
        w.update(DT, dict(aim=True))
    w.update(DT, {})                                    # erneut loslassen -> feuert
    assert w.stats["shots"] == 1


def test_boss_flow():
    w = World(seed=3, zone_index=4)
    _quiet(w)
    w.player.x = w.length - config.ROY_TRIGGER + 5
    w.update(DT, {})
    assert not w.boss_spawned, "ROY spawnt, obwohl der Auftrag nicht erfüllt ist"
    w.stats["reps"] = w.quota          # Tyrell-Auftrag erfüllt
    w.update(DT, {})
    b = w.boss
    assert w.boss_spawned and b is not None and b.alive and b.hp == config.ROY_HP
    assert b.boss_invuln, "ROY redet nicht zu Beginn"
    assert not w.exit_open(), "Tor offen, obwohl ROY lebt"
    w._hit(b)
    assert b.hp == config.ROY_HP, "Treffer während der Rede hat gezählt"
    for _ in range(config.ROY_HP):     # Rede überspringen und Treffer landen
        b.boss_invuln = False
        w.boss_speak_t = 0.0
        w._hit(b)
    assert not b.alive
    assert w.exit_open(), "Tor blieb nach ROY zu"


def test_manual_target_scan_too_far():
    w = World(seed=9, zone_index=1)
    _quiet(w)
    far = max((a for a in w.living() if w.on_screen(a)), key=lambda a: w.dist(w.player, a), default=None)
    near = [a for a in w.living() if w.dist(w.player, a) < config.SCAN_RANGE]
    if far is None or w.dist(w.player, far) <= config.SCAN_RANGE:
        return
    assert w.set_target(far)
    res, t = w.scan()
    assert res == "too_far" and w.target is far, "gewähltes Ziel wurde stillschweigend gewechselt"
    assert w.scan_t < 0
    _ = near


def test_blackout_and_patrol_reveal():
    w = World(seed=10, zone_index=2)
    _quiet(w)
    rep = next(a for a in w.actors if a.is_replicant)
    rep.tells["pupils"] = True
    rep.revealed.discard("pupils")
    _place_near(w, rep, 40)
    rep.state, rep.timer = "idle", 99
    w.blackout_at = w.time
    for _ in range(int(4 / DT)):
        w.update(DT, {})
        rep.state, rep.vx = "idle", 0.0
    assert "pupils" in rep.revealed, "Augenreflex im Stromausfall nicht aufgedeckt"


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
            import traceback
            traceback.print_exc()
            print(f"  ERR  {t.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - fails}/{len(tests)} bestanden")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
