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
    w.actors = [w.player, t, b]
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


def test_vehicle_brakes_for_player_in_lane():
    w = World(seed=6, zone_index=2)
    _quiet(w)
    w.actors = [w.player]
    p = w.player
    lane, dr = config.LANES[1]
    p.depth = lane
    w.vehicles.append(dict(x=p.x - dr * 220, depth=lane, dir=dr, speed=170.0, vmax=170.0, kind="car",
                           L=87.0, h=25.5, seed=1, honk=False, uid=-1, react=0.3))
    hp, honks = p.hp, 0
    for _ in range(int(5 / DT)):
        w.update(DT, {})
        honks += sum(1 for e in w.events if e[0] == "honk")
        w.events.clear()
    assert p.hp == hp, "gebremstes Auto darf kein Herz kosten"
    assert honks >= 1, "Auto hat den Spieler in der Spur nicht angehupt"
    v = w.vehicles[0]
    assert v["speed"] < 20.0, f"Auto bremst nicht ({v['speed']:.0f})"


def test_vehicle_bump_costs_no_heart():
    w = World(seed=6, zone_index=2)
    _quiet(w)
    w.actors = [w.player]
    p = w.player
    lane, dr = config.LANES[0]
    p.depth = lane
    hp = p.hp
    w.vehicles.append(dict(x=p.x, depth=lane, dir=dr, speed=0.0, vmax=0.0, kind="car",
                           L=87.0, h=25.5, seed=1, honk=False, uid=-1, react=0.3))
    bumps = 0
    for _ in range(30):
        w.update(DT, {})
        bumps += sum(1 for e in w.events if e[0] == "bump")
        w.events.clear()
    assert bumps >= 1, "kein Rempler"
    assert p.hp == hp, "Rempler darf kein Herz kosten"
    assert abs(p.depth - lane) > config.LANE_HALF, "Spieler nicht aus der Spur geschoben"


def test_vehicle_frontal_hit_at_speed():
    w = World(seed=6, zone_index=2)
    _quiet(w)
    w.actors = [w.player]
    w.car_escape = 0.0                       # keine Rettung in letzter Sekunde
    p = w.player
    lane, dr = config.LANES[1]
    p.depth = lane
    hp = p.hp
    w.vehicles.append(dict(x=p.x - dr * 20, depth=lane, dir=dr, speed=200.0, vmax=200.0, kind="car",
                           L=87.0, h=25.5, seed=1, honk=False, uid=-1, react=0.6))
    for _ in range(30):
        w.update(DT, {})
        w.events.clear()
    assert p.hp == hp - 1, "frontal mit Tempo muss ein Herz kosten"
    assert abs(p.depth - lane) > config.LANE_HALF, "Spieler nicht aus der Spur geschleudert"


def test_engine_sound_quieter_when_dense():
    def avg_vol(z):
        w = World(seed=7, zone_index=z)
        vols = []
        for _ in range(int(12 / DT)):
            w.update(DT, {})
            vols += [e[3] for e in w.events if e[0] == "vehicle"]
            w.events.clear()
        return sum(vols) / max(1, len(vols))
    assert avg_vol(0) > avg_vol(2) + 0.3, "dichter Verkehr klingt nicht leiser"


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


def test_spinner_lands_blocks_and_lifts_off():
    w = World(seed=12, zone_index=2)
    _quiet(w)
    w.obstacles.clear()
    w.ramen.clear()
    p = w.player
    p.x, p.depth = 600.0, 0.8
    w.camera_x = p.x + 40
    old = config.SPINNER_LAND_CHANCE
    config.SPINNER_LAND_CHANCE = 1.0
    try:
        w.patrol_cd = 0.1
        landed = False
        for _ in range(int(25 / DT)):
            w.update(DT, {})
            P = w.patrol
            if P is not None and P["phase"] == "landed":
                landed = True
                assert any(o["kind"] == "spinner" for o in w.obstacles), "gelandeter Spinner blockiert nicht"
                assert w.blocked(P["x"], config.LAND_DEPTH, 0.0), "Landeplatz nicht gesperrt"
                assert w.blocked(P["x"], config.LAND_DEPTH, 30.0), "über den Spinner springen darf nicht gehen"
            if landed and (P is None or P["phase"] in ("lift", "fly")):
                break
        assert landed, "Spinner ist nie gelandet"
        assert not any(o["kind"] == "spinner" for o in w.obstacles), "Sperre nach dem Abheben nicht entfernt"
    finally:
        config.SPINNER_LAND_CHANCE = old


def test_spinner_downdraft_pushes_away():
    w = World(seed=13, zone_index=2)
    _quiet(w)
    w.obstacles.clear()
    civ = next(a for a in w.actors if not a.player)
    civ.state, civ.vx, civ.timer = "idle", 0.0, 99
    civ.x, civ.depth, civ.target_depth = 500.0, config.LAND_DEPTH, config.LAND_DEPTH
    w.patrol = dict(x=490.0, dir=1, t=10.0, life=90.0, ph=0.0, on=0.0, bx=0.0, bd=0.5, leaving=False,
                    mode="land", phase="descend", alt=0.3, face=1, obs=None, land_t=0.0, lx=490.0)
    x0 = civ.x
    for _ in range(30):
        w._update_patrol(DT)
    assert civ.x > x0 + 5, "Abwind hat die Figur nicht weggeschoben"


def test_origami_pickup():
    w = World(seed=14, zone_index=4)
    _quiet(w)
    assert w.origami, "keine Origami-Figur platziert"
    o = w.origami[0]
    assert o["kind"] == "einhorn", "Tyrell-Zone sollte das Einhorn haben"
    p = w.player
    w.scan_charges = 0.0
    score = w.run.score
    p.x, p.depth = o["x"] - 8, o["depth"]
    w.update(DT, {})
    assert o["taken"] and w.stats["origami"], "Origami nicht aufgehoben"
    assert w.run.score == score + config.POINTS_ORIGAMI
    assert w.scan_charges >= w.scan_max - 0.01, "Scanner nicht voll geladen"
    assert w.run.origami == ["EINHORN"]


def test_ramen_cook_greets():
    w = World(seed=15, zone_index=1)
    _quiet(w)
    r = w.ramen[0]
    p = w.player
    p.hp = w.run.max_hp - 1
    p.x, p.depth = r["x"] - 40, 0.3
    w.update(DT, {})
    assert r.get("greet"), "Koch hat nicht gegrüßt"
    assert any("IRASSHAI" in f["text"] for f in w.floaters)


def _crowd_around(w, n=8, stim_every=3):
    """n Menschen dicht vor dem Spieler, jeder stim_every-te mit REIZ-Tell."""
    p = w.player
    humans = [a for a in w.actors if not a.player and not a.is_replicant][:n]
    for i, a in enumerate(humans):
        a.x, a.depth, a.target_depth = p.x + 20 + i * 8, p.depth, p.depth
        a.state, a.vx, a.timer = "idle", 0.0, 99
        a.tells["stimulus"] = (i % stim_every == 0)
        a.revealed.discard("stimulus")
    return humans


def test_shout_ducks_crowd_and_reveals_stimulus():
    w = World(seed=21, zone_index=2)
    _quiet(w)
    w.actors = [a for a in w.actors if a.player or not a.is_replicant]
    config_scatter, config_unrest = config.SHOUT_SCATTER, config.UNREST_PER_SHOUT
    config.SHOUT_SCATTER = config.UNREST_PER_SHOUT = 0.0
    try:
        crowd = _crowd_around(w)
        assert w.shout_crowd() == "ok"
        for _ in range(int(1.5 / DT)):          # Welle + Schrecksekunde abwarten
            w._update_reactions(DT)
        for a in crowd:
            assert "stimulus" in a.revealed, "Ruf hat REIZ nicht aufgedeckt"
            want = "freeze" if a.tells["stimulus"] else "duck"
            assert a.state == want, f"{a.state} statt {want}"
        assert w.shout_crowd() == "cooldown", "Ruf ohne Abklingzeit"
    finally:
        config.SHOUT_SCATTER, config.UNREST_PER_SHOUT = config_scatter, config_unrest


def test_shot_passes_over_ducking():
    w = World(seed=22, zone_index=2)
    _quiet(w)
    p = w.player
    rep = next(a for a in w.actors if a.is_replicant)
    civ = next(a for a in w.actors if not a.player and not a.is_replicant)
    rep.x, rep.depth, rep.state, rep.timer = p.x + 80, p.depth, "idle", 99
    civ.x, civ.depth, civ.state, civ.timer = p.x + 40, p.depth, "idle", 99
    w.actors = [p, rep, civ]
    w.target = rep
    assert w.line_of_fire(rep) is civ, "Passant sollte die Schusslinie blockieren"
    civ.state, civ.timer = "duck", 3.0
    assert w.line_of_fire(rep) is rep, "Kugel geht nicht über den Geduckten"
    w._panic_area(p.x, 200.0)
    assert civ.state == "duck", "Geduckter steht bei Schüssen wieder auf"


def test_shout_wave_reaches_far_later():
    w = World(seed=23, zone_index=2)
    _quiet(w)
    w.actors = [a for a in w.actors if a.player or not a.is_replicant]
    p = w.player
    near, far = [a for a in w.actors if not a.player][:2]
    for a, dx in ((near, 15.0), (far, 140.0)):
        a.x, a.depth, a.target_depth, a.state, a.timer = p.x + dx, p.depth, p.depth, "idle", 99
        a.tells["stimulus"] = False
        a.react_t = 0.2
    w.shout_crowd(160.0)
    for _ in range(int(0.35 / DT)):
        w._update_reactions(DT)
    assert near.state in ("duck", "panic") and far.state == "idle", "Welle wirkt nicht verzögert"
    for _ in range(int(0.8 / DT)):
        w._update_reactions(DT)
    assert far.state in ("duck", "panic"), "Ferner Passant hat nicht reagiert"


def test_hold_v_vs_tap():
    w = World(seed=24, zone_index=2)
    _quiet(w)
    p = w.player
    civ = next(a for a in w.actors if not a.player and not a.is_replicant)
    civ.x, civ.depth, civ.state, civ.timer = p.x + 30, p.depth, "idle", 99
    civ.tells["stimulus"] = False
    w.target = civ
    w._shout_input(DT, True)
    w._shout_input(DT, False)                 # kurz getippt -> Ansprache
    assert w.talk_cd > 0 and w.shout_cd == 0, "Tippen sollte ansprechen, nicht rufen"
    for _ in range(int(1.0 / DT)):
        w._update_reactions(DT)
    assert civ.state == "hands", f"Angesprochener hebt nicht die Hände ({civ.state})"
    for _ in range(int(0.8 / DT)):
        w._shout_input(DT, True)              # gehalten -> Ruf an die Menge
    r = w.shout_radius()
    w._shout_input(DT, False)
    assert w.shout_cd > 0 and w.wave is not None and w.wave["R"] == r
    assert w.unrest > 0.3, "Ruf erhöht die Unruhe nicht"


def test_groups_loiter_and_are_scannable():
    w = World(seed=25, zone_index=2)
    _quiet(w)
    grp = [a for a in w.actors if a.group >= 0]
    side = [a for a in w.actors if a.home is not None]
    assert len(grp) >= 6 and side, "keine Gruppen / Gehweg-Passanten"
    assert all(a.state == "loiter" for a in grp)
    for _ in range(int(3 / DT)):
        w.update(DT, {})
    still = [a for a in grp if a.alive and a.state == "loiter"]
    assert still and all(abs(a.vx) < 1e-6 for a in still), "Gruppe steht nicht"
    a = still[0]
    p = w.player
    p.x, p.depth = a.x - 30, max(config.DEPTH_MIN, a.depth)
    w.target = a
    w.scan_charges = 3.0
    assert w.scan()[0] == "ok", "Gruppenmitglied nicht scanbar"
    assert min(x.depth for x in side) < config.DEPTH_MIN, "Gehweg-Band nicht hinter der Spielertiefe"


def test_difficulty_scales_density():
    from shadegunner.sim import Run
    n = {}
    for d in ("leicht", "normal", "schwer"):
        w = World(Run(5, d), seed=5, zone_index=2)
        n[d] = len(w.actors)
    assert n["leicht"] < n["normal"] < n["schwer"], n


def test_traffic_denser_and_slower_by_zone():
    w0, w2 = World(seed=7, zone_index=0), World(seed=7, zone_index=2)
    assert w2.traffic_gap < w0.traffic_gap and w2.traffic_slow < w0.traffic_slow
    for w in (w0, w2):
        for _ in range(int(20 / DT)):
            w.update(DT, {})
    near = [v for v in w2.vehicles if abs(v["x"] - w2.camera_x) < 330]
    assert len(near) >= 3, "Innenstadt-Verkehr zu dünn"
    assert max(v["speed"] for v in w2.vehicles) < 0.8 * 230.0, "dichter Verkehr fährt zu schnell"
    # Kolonne: niemand fährt in den Vordermann
    for lane, _d in config.LANES:
        q = sorted((v for v in w2.vehicles if v["depth"] == lane), key=lambda v: v["x"])
        for a, b in zip(q, q[1:]):
            assert b["x"] - a["x"] > (a["L"] + b["L"]) * 0.5 - 2.0, "Fahrzeuge überlappen"


def test_parked_cars_block_and_cannot_be_jumped():
    w = World(seed=7, zone_index=2)
    pk = [o for o in w.obstacles if o["kind"] == "parked"]
    assert len(pk) >= 5, "zu wenig parkende Fahrzeuge"
    o = pk[0]
    assert w.blocked(o["x"], o["d"], 0.0) and w.blocked(o["x"], o["d"], config.JUMP_V ** 2 / (2 * config.GRAVITY))
    for a in w.actors:
        if not a.player:
            assert not any(abs(a.x - q["x"]) < q["w"] and abs(a.depth - q["d"]) < q["dd"] for q in pk), \
                "Passant steht im parkenden Auto"


def test_steam_slows_observation():
    w = World(seed=7, zone_index=2)
    _quiet(w)
    m = w.manholes[0]
    m["base"], m["every"] = 1.0, 1e9
    w._update_steam(DT)
    assert w.steam_at(m["x"] + m["drift"], m["d"]) > 0.8 and w.steam_at(m["x"] + 200, m["d"]) == 0.0
    a = next(x for x in w.actors if not x.player)
    w.player.x, w.player.depth = m["x"] - 40, max(config.DEPTH_MIN, m["d"])
    gain = {}
    for where in ("frei", "dampf"):
        a.x, a.depth = (m["x"] + m["drift"], m["d"]) if where == "dampf" else (m["x"] - 80, m["d"])
        a.exposure, w.target = 0.0, a
        w._observe(0.1)
        gain[where] = a.exposure
    assert gain["dampf"] < gain["frei"] * 0.5, gain


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
