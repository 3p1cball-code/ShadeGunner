"""Spielwelt und Kern-Loop (reine Simulation, kein Rendering).

Der Renderer konsumiert nur diesen Zustand plus die `events`-Liste (Schüsse,
Tode, Scans ...) für Effekte und Sound. Die Projektion Welt -> Bildschirm liegt
in persp.py und wird von beiden Seiten benutzt.

Ein Run (`Run`) überdauert die Zonen: Punkte, Integrität, Suspicion, Upgrades.
Eine Zone (`World`) ist eine Straße mit Bevölkerung, Auftrag und Ausgang.
"""

import math
import random

from . import config, persp, procgen
from .detection import ORDER, STRONG_TELLS, TELLS, WEAK_TELLS, confidence
from .entities import Actor
from .render.sprites import COATS, PLAYER_LOOK, describe, frame_count, random_look

DU = config.DEPTH_UNITS

# Zonen-Sequenz von den Außenbezirken bis Tyrell HQ (DESIGN.md §6).
# density = Passanten pro 100 Welt-Einheiten; camo = Tarntiefe 0..1;
# aggression = Anteil Replikanten, die bei Entdeckung angreifen statt fliehen.
# traffic = mittlerer Abstand zwischen Fahrzeugen (s); patrol = Abstand der Polizei-
# Suchlicht-Patrouillen (s, None = keine); blackout = Chance auf einen Stromausfall.
ZONES = [
    dict(name="Außenbezirk", length=2000, density=1.6, replicants=5, quota=3, camo=0.0, aggression=0.0, flee=0.45,
         traffic=13.0, patrol=None, blackout=0.0),
    dict(name="Vorstadt",    length=2300, density=2.0, replicants=6, quota=3, camo=0.25, aggression=0.15, flee=0.5,
         traffic=10.0, patrol=55.0, blackout=0.5),
    dict(name="Innenstadt",  length=2600, density=2.6, replicants=8, quota=4, camo=0.5, aggression=0.3, flee=0.55,
         traffic=6.5, patrol=40.0, blackout=0.6),
    dict(name="Hafen",       length=2400, density=2.2, replicants=8, quota=5, camo=0.7, aggression=0.5, flee=0.6,
         traffic=9.0, patrol=45.0, blackout=0.8),
    dict(name="Tyrell",      length=2300, density=2.3, replicants=9, quota=5, camo=0.9, aggression=0.65, flee=0.6,
         traffic=8.0, patrol=30.0, blackout=0.5),
]

# Kopfgeld-Replikanten (Nexus-6 aus der Akte) je Zone
BOUNTY_NAMES = ["HODGE", "LEON", "ZHORA", "PRIS", "ROY"]

# Verkehr: Art -> (Länge u, Höhe u, Tempo u/s)
VEHICLES = {
    "car": (87.0, 25.5, 170.0), "taxi": (84.0, 25.5, 185.0), "truck": (138.0, 45.0, 135.0),
    "bike": (45.0, 22.5, 230.0), "police": (90.0, 27.0, 215.0), "limo": (126.0, 24.0, 160.0),
}
ZONE_TRAFFIC = [
    ["truck", "car", "car", "bike"],
    ["car", "car", "taxi", "bike", "police"],
    ["taxi", "taxi", "car", "bike", "police", "car"],
    ["truck", "truck", "car", "bike"],
    ["limo", "police", "car", "limo"],
]

# Upgrades zwischen den Zonen (eins aus drei). Nie ein Freifahrtschein (§7).
UPGRADES = [
    ("akku", "SCAN-AKKU", "+2 SCAN-LADUNGEN"),
    ("schnell", "SCHNELLSCAN", "SCANS 45% KÜRZER"),
    ("tief", "TIEFENSCAN", "SCAN ZEIGT ALLE TELLS, SERIE AUF DISTANZ"),
    ("auge", "FELDBLICK", "BEOBACHTUNG DOPPELT SO SCHNELL"),
    ("weste", "PANZERWESTE", "+1 INTEGRITÄT, VOLL GEHEILT"),
    ("sprint", "LAUFSCHUHE", "+20% TEMPO"),
    ("hand", "RUHIGE HAND", "SOFORT SCHIESSEN, KEINE ZIELZEIT"),
    ("kalt", "KALTES BLUT", "FEHLER KOSTEN 35% WENIGER VERDACHT"),
    ("peil", "PEILSENDER", "FLÜCHTENDE SIND 30% LANGSAMER"),
    ("instinkt", "INSTINKT", "AUGENREFLEXE DOPPELT SO HÄUFIG"),
]


class Run:
    """Zustand, der über Zonen hinweg erhalten bleibt."""

    def __init__(self, seed=0):
        self.seed = seed
        self.score = 0
        self.max_hp = config.PLAYER_HP
        self.hp = self.max_hp
        self.suspicion = 0.0
        self.upgrades = []
        self.zone_index = 0
        self.totals = dict(reps=0, civs=0, escaped=0, scans=0, shots=0, time=0.0)
        self.mods = dict(scan_max=config.SCAN_CHARGES, scan_time=1.0, deep=False, observe=1.0,
                         speed=1.0, aim_min=config.AIM_MIN, susp=1.0, flee=1.0, glint=1.0)

    def apply(self, key):
        m = self.mods
        self.upgrades.append(key)
        if key == "akku":
            m["scan_max"] += 2
        elif key == "schnell":
            m["scan_time"] *= 0.55
        elif key == "tief":
            m["deep"] = True
        elif key == "auge":
            m["observe"] *= 2.0
        elif key == "weste":
            self.max_hp += 1
            self.hp = self.max_hp
        elif key == "sprint":
            m["speed"] *= 1.2
        elif key == "hand":
            m["aim_min"] = 0.0
        elif key == "kalt":
            m["susp"] *= 0.65
        elif key == "peil":
            m["flee"] *= 0.7
        elif key == "instinkt":
            m["glint"] *= 2.0

    def offer(self, rng, n=3):
        pool = [u for u in UPGRADES if not (u[0] in self.upgrades and u[0] in ("tief", "hand"))]
        return rng.sample(pool, min(n, len(pool)))


class World:
    def __init__(self, run=None, seed=0, zone_index=None):
        self.run = run or Run(seed)
        if zone_index is not None:
            self.run.zone_index = zone_index
        self.zone_index = self.run.zone_index
        self.rng = random.Random(seed * 31 + self.zone_index * 7 + 1)
        self.seed = seed
        self.zone = ZONES[self.zone_index]
        self.length = float(self.zone["length"])
        self.camo = self.zone["camo"]
        self.time = 0.0

        self.player = Actor(x=40.0, depth=0.7, player=True, look=PLAYER_LOOK, uid=0, state="idle")
        self.player.hp = self.run.hp
        self.camera_x = self.player.x + 60.0

        self.actors = []
        acts, self._uid = procgen.populate(self.rng, self.zone, 140.0, self.length + 60.0, 1, self.zone_index)
        self.actors.extend(acts)
        self.actors.append(self.player)
        self.prior = sum(1 for a in acts if a.is_replicant) / max(1, len(acts))
        self.bounty = self._make_bounty(acts)

        # Ramen-Stände (Herzen auffüllen) und Straße: Hindernisse, Verkehr, Patrouillen
        self.ramen = [dict(x=x, depth=0.16, used=False, t=0.0)
                      for x in procgen.ramen_positions(self.length, seed, self.zone_index)]
        self.obstacles = procgen.obstacles(self.rng, self.zone_index, self.length,
                                           [r["x"] for r in self.ramen])
        self.vehicles = []
        self.traffic_cd = self.rng.uniform(3.0, 7.0)
        self.patrol = None
        self.patrol_cd = self.rng.uniform(16.0, 28.0) if self.zone.get("patrol") else None
        self.watched = False
        # Endboss (nur Tyrell)
        self.boss = None
        self.boss_spawned = False
        self.boss_line = 0
        self.boss_hits = 0
        self.boss_speak_t = 0.0
        self.blackout_t = 0.0
        self.blackout_at = self.rng.uniform(35.0, 85.0) if self.rng.random() < self.zone.get("blackout", 0) else None
        self._veh_uid = 0

        m = self.run.mods
        self.scan_max = m["scan_max"]
        self.scan_charges = float(self.scan_max)
        self.replicants_total = sum(1 for a in self.actors if a.is_replicant)
        self.quota = min(self.zone["quota"], self.replicants_total)
        self.combo = 1
        self.state = "playing"          # playing | zone_clear | failed
        self.fail_reason = ""
        self.stats = dict(reps=0, civs=0, escaped=0, scans=0, shots=0, score=0, time=0.0, bounty=False)

        self.target = None
        self.manual_target = False
        self.aim_t = 0.0
        self.aim_latch = False
        self.aiming = False
        self.shot_cd = 0.0
        self.scan_t = -1.0              # >= 0: Scan läuft
        self.scan_target = None
        self.blocker = None
        self.events = []
        self.floaters = []
        self.log = []
        self._gate_msg_cd = 0.0
        self._prev_aim = False

    # ------------------------------------------------------------------ Kopfgeld
    def _make_bounty(self, acts):
        """Ein benannter Nexus-6 mit Personenbeschreibung; ab Innenstadt mit Doppelgänger."""
        self.bounty_desc = None
        if self.zone_index == 4:
            return None            # In Tyrell ist ROY der Boss, kein Kopfgeld im Volk
        reps = sorted((a for a in acts if a.is_replicant), key=lambda a: a.x)
        if not reps:
            return None
        rng = self.rng
        b = rng.choice(reps[len(reps) // 3:])
        zi = self.zone_index
        b.bounty = True
        b.name = BOUNTY_NAMES[zi % len(BOUNTY_NAMES)]
        b.hp = 2 if zi >= 2 else 1
        b.aggressive = zi >= 1
        lk = b.look
        if b.name == "ZHORA":
            lk.update(outfit="cloak", head="long", umbrella=None, hair=(14, 14, 20))
        elif b.name == "PRIS":
            lk.update(outfit="dress", head="short", hair=(226, 210, 160))
        elif b.name == "ROY":
            lk.update(outfit="long", head="short", hair=(214, 220, 226), coat=COATS[7][0], coat_name=COATS[7][1])
        elif b.name == "LEON":
            lk.update(outfit="jacket", head="short")
        humans = [a for a in acts if not a.is_replicant]
        desc = describe(lk)
        same = [a for a in humans if describe(a.look) == desc]
        # Höchstens ein Doppelgänger: alle weiteren bekommen einen anderen Kopf
        for a in same[1:]:
            a.look["head"] = "beanie" if a.look["head"] != "beanie" else "cap"
        if zi >= 2 and not same and humans:
            d = rng.choice(humans)
            for key in ("outfit", "head", "coat", "coat_name", "umbrella", "hair"):
                d.look[key] = lk[key]
        self.bounty_desc = desc
        return b

    # ------------------------------------------------------------------ Hilfen
    @property
    def suspicion(self):
        return self.run.suspicion

    @suspicion.setter
    def suspicion(self, v):
        self.run.suspicion = v

    @property
    def points(self):
        return self.stats["reps"]

    def _say(self, text):
        self.log.append(text)
        if len(self.log) > 5:
            self.log.pop(0)

    def floater(self, text, a, color, t=1.6):
        busy = {f["slot"] for f in self.floaters if f["uid"] == a.uid and f["t"] < f["life"] * 0.8}
        slot = next(i for i in range(8) if i not in busy)
        self.floaters.append(dict(text=text, x=a.x, depth=a.depth, t=0.0, life=t, color=color,
                                  uid=a.uid, slot=slot))

    def dist(self, a, b):
        return math.hypot(a.x - b.x, (a.depth - b.depth) * DU)

    def confidence_of(self, a):
        return confidence(a.revealed, a.tells, self.camo, self.prior)

    def living(self):
        return [a for a in self.actors if not a.player and a.alive and not a.escaped]

    def reps_remaining(self):
        return sum(1 for a in self.actors if a.is_replicant and a.alive and not a.escaped)

    def on_screen(self, a, margin=6):
        sx = persp.screen_x(a.x, a.depth, self.camera_x)
        return margin < sx < persp.W - margin

    # ------------------------------------------------------------------ Update
    def update(self, dt, inp=None):
        inp = inp or {}
        if isinstance(inp, tuple):            # Kompatibilität: (mx, md)
            inp = dict(move=inp)
        self.time += dt
        for f in self.floaters:
            f["t"] += dt
        self.floaters = [f for f in self.floaters if f["t"] < f["life"]]
        self._update_dead(dt)
        if self.state != "playing":
            self._update_traffic(dt, spawn=False)
            self._update_patrol(dt)
            self._update_npcs(dt, frozen=True)
            self._physics_z(self.player, dt)
            self._animate(self.player, dt)
            return
        self.stats["time"] += dt
        self._gate_msg_cd = max(0.0, self._gate_msg_cd - dt)
        self.shot_cd = max(0.0, self.shot_cd - dt)
        if self.scan_charges < self.scan_max:
            self.scan_charges = min(self.scan_max, self.scan_charges + dt / config.SCAN_RECHARGE_S)
        self._update_blackout(dt)

        self._update_player(dt, inp)
        self._update_target(inp)
        self._update_traffic(dt)
        self._update_patrol(dt)
        self._update_npcs(dt)
        self._observe(dt)
        self._update_ramen(dt)
        self._update_boss(dt)

        # Kamera: führt in Blickrichtung
        p = self.player
        lead = 46.0 * p.facing
        cam_t = min(max(p.x + lead, 20.0), self.length + 40.0)
        self.camera_x += (cam_t - self.camera_x) * min(1.0, dt * 3.0)

        if self.suspicion >= 1.0 and self.state == "playing":
            self._fail("suspicion")

    # ------------------------------------------------------------------ Spieler
    def _update_player(self, dt, inp):
        p = self.player
        m = self.run.mods
        p.invuln = max(0.0, p.invuln - dt)
        p.flash_t = max(0.0, p.flash_t - dt)
        mx, md = inp.get("move", (0, 0))
        aim = bool(inp.get("aim"))
        self._physics_z(p, dt)

        if p.state == "hurt":
            p.timer -= dt
            p.x = min(max(0.0, p.x + p.knock * dt), self.length + 2)
            p.knock *= 0.88
            if p.timer <= 0:
                p.state = "idle"
            self._animate(p, dt)
            self._prev_aim = aim
            return

        if inp.get("jump") and p.z <= 0.0 and p.vz <= 0.0:
            if self.scan_t >= 0.0:
                self.scan_t = -1.0
                self.scan_target = None
                self.events.append(("scan_abort",))
            p.vz = config.JUMP_V
            p.z = 0.01
            self.events.append(("jump", p.uid))

        # Scan-Kanal
        if self.scan_t >= 0.0:
            t = self.scan_target
            self.scan_t += dt
            if t is None or not t.alive or t.escaped or self.dist(p, t) > config.SCAN_RANGE * 1.25:
                self.scan_t = -1.0
                self.scan_target = None
                self.events.append(("scan_abort",))
                self._say("Scan abgebrochen.")
            else:
                p.facing = 1 if t.x >= p.x else -1
                if self.scan_t >= config.SCAN_TIME * m["scan_time"]:
                    self._finish_scan(t)
            p.state = "scan"
            self._animate(p, dt)
            self._prev_aim = aim
            return

        # Zielen abbrechen: Waffe senken, ohne zu feuern. Bleibt gesenkt, solange die
        # Zieltaste gedrückt bleibt (aim_latch), bis man sie loslässt.
        if inp.get("cancel") and self.aiming and not self.aim_latch:
            self.aim_latch = True
            self.aiming = False
            self.aim_t = 0.0
            self.blocker = None
            self.events.append(("holster",))
            self._say("Waffe gesenkt - Schuss abgebrochen.")
        if not aim:
            self.aim_latch = False
        aim = aim and not self.aim_latch

        if inp.get("scan"):
            self.scan()

        if aim:
            self.aim_t += dt
            self.aiming = True
            p.state = "aim" if self.shot_cd <= 0.2 else "shoot"
            t = self.target
            if t is not None:
                p.facing = 1 if t.x >= p.x else -1
                t.aimed_t += dt * 2.0
                self.blocker = self.line_of_fire(t)
            else:
                self.blocker = self.line_of_fire(None)
        else:
            if self._prev_aim and self.aiming:
                if self.aim_t >= m["aim_min"]:
                    self.fire()
            self.aiming = False
            self.aim_t = 0.0
            self.blocker = None
            sprint = bool(inp.get("sprint"))
            speed = (config.PLAYER_SPRINT_SPEED if sprint else config.PLAYER_WALK_SPEED) * m["speed"]
            if self.shot_cd > config.SHOT_COOLDOWN - 0.25:
                speed *= 0.2
            p.vx = mx * speed
            nx = min(max(0.0, p.x + p.vx * dt), self.length + 2)
            nd = min(config.DEPTH_MAX, max(config.DEPTH_MIN, p.depth + md * config.PLAYER_DEPTH_SPEED * dt))
            if not self.blocked(p.x, p.depth, p.z) and self.blocked(nx, nd, p.z):
                if not self.blocked(nx, p.depth, p.z):
                    nd = p.depth
                elif not self.blocked(p.x, nd, p.z):
                    nx = p.x
                else:
                    nx, nd = p.x, p.depth
                p.vx = (nx - p.x) / max(dt, 1e-4)
            p.x, p.depth = nx, nd
            if mx:
                p.facing = 1 if mx > 0 else -1
            if self.shot_cd > config.SHOT_COOLDOWN - 0.22:
                p.state = "shoot"
            elif mx or md:
                p.state = "run" if (sprint and mx) else "walk"
            else:
                p.state = "idle"
            if p.x >= self.length:
                self._try_exit()
        self._prev_aim = aim
        self._animate(p, dt, depth_move=md)

    def exit_open(self):
        if self.boss_spawned and self.boss is not None:
            return not self.boss.alive      # Tor öffnet erst, wenn ROY liegt
        return (self.stats["reps"] >= self.quota or self.reps_remaining() == 0
                or self.stats["reps"] + self.reps_remaining() < self.quota)

    def _try_exit(self):
        if self.exit_open():
            self._zone_clear()
            return
        self.player.x = self.length - 0.5
        if self._gate_msg_cd <= 0:
            self._gate_msg_cd = 2.5
            self.events.append(("gate_locked",))
            self._say(f"Ausgang gesperrt: Auftrag {self.stats['reps']}/{self.quota}.")

    # ------------------------------------------------------------------ Zielerfassung
    def _target_ok(self, a):
        rng_ = config.TARGET_RANGE * (1.7 if self.manual_target else 1.0)
        return (a is not None and a.alive and not a.escaped and not a.player
                and self.dist(self.player, a) <= rng_ and self.on_screen(a, 2))

    def set_target(self, a):
        """Manuelle Zielwahl (Maus): bleibt, bis das Ziel weg/außer Sicht ist."""
        if a is None or a.player or not a.alive or a.escaped:
            return False
        if self.scan_t >= 0 and a is not self.scan_target:
            return False
        if a is not self.target:
            self.target = a
            self.events.append(("target",))
        self.manual_target = True
        return True

    def _candidates(self):
        p = self.player
        return [a for a in self.living() if self.dist(p, a) <= config.TARGET_RANGE and self.on_screen(a)]

    def _update_target(self, inp):
        if inp.get("cycle"):
            self.cycle_target(inp.get("cycle"))
        if self._target_ok(self.target):
            return
        self.manual_target = False
        if self.aiming or self.scan_t >= 0:
            if not self._target_ok(self.target):
                self.target = None
            return
        p = self.player
        best, bs = None, 1e9
        for a in self._candidates():
            s = self.dist(p, a)
            if (a.x - p.x) * p.facing < -4:
                s += 70.0
            if a.state == "attack":
                s -= 200.0
            if s < bs:
                best, bs = a, s
        self.target = best

    def cycle_target(self, direction=1):
        cands = sorted(self._candidates(), key=lambda a: persp.screen_x(a.x, a.depth, self.camera_x))
        if not cands:
            self.target = None
            return
        if self.target in cands:
            i = (cands.index(self.target) + (1 if direction >= 0 else -1)) % len(cands)
        else:
            i = 0
        self.target = cands[i]
        self.manual_target = True
        self.events.append(("target",))

    # ------------------------------------------------------------------ Schusslinie
    def muzzle(self):
        p = self.player
        return p.x + p.facing * 9.0, p.depth

    def line_of_fire(self, target):
        """Erster Aktor auf der Linie Spieler -> Ziel (oder geradeaus). None = ins Leere."""
        sx, sd = self.muzzle()
        if target is not None:
            tx, td = target.x, target.depth
        else:
            tx, td = sx + self.player.facing * config.SHOOT_RANGE, sd
        vx, vy = tx - sx, (td - sd) * DU
        L2 = vx * vx + vy * vy
        if L2 < 1e-6:
            return target
        best, best_s = target, 1.0
        if target is not None and math.sqrt(L2) > config.SHOOT_RANGE:
            best, best_s = None, config.SHOOT_RANGE / math.sqrt(L2)
        for a in self.living():
            if a is target:
                continue
            s = ((a.x - sx) * vx + (a.depth - sd) * DU * vy) / L2
            if 0.02 < s < best_s:
                dx = a.x - (sx + vx * s)
                dy = (a.depth - sd) * DU - vy * s
                if abs(dx) < 5.5 and abs(dy) < 7.0:
                    best, best_s = a, s
        return best

    # ------------------------------------------------------------------ Aktionen
    def scan(self):
        """Startet einen Scan auf das aktuelle Ziel. Rückgabe (status, aktor)."""
        if self.state != "playing":
            return "no_target", None
        if self.player.z > 0.0:
            return "airborne", None
        if self.scan_charges < 1.0:
            self.events.append(("no_charge",))
            self._say("Keine Scan-Ladung.")
            return "no_charge", None
        t = self.target
        if t is not None and self.dist(self.player, t) > config.SCAN_RANGE:
            # Gewähltes Ziel bleibt gewählt - kein stilles Umschwenken auf jemand anderen
            self.events.append(("no_target",))
            self._say("Ziel zu weit für den Scan - näher ran.")
            self.floater("ZU WEIT", t, (162, 168, 180), 1.0)
            return "too_far", t
        if t is None:
            cands = [a for a in self.living() if not a.scanned and self.dist(self.player, a) <= config.SCAN_RANGE]
            if not cands:
                self.events.append(("no_target",))
                return "no_target", None
            t = min(cands, key=lambda a: self.dist(self.player, a))
            self.target = t
        self.scan_charges -= 1.0
        self.scan_t = 0.0
        self.scan_target = t
        self.stats["scans"] += 1
        self.events.append(("scan_start", t.uid))
        return "ok", t

    def _finish_scan(self, t):
        self.scan_t = -1.0
        self.scan_target = None
        deep = self.run.mods["deep"]
        close = self.dist(self.player, t) <= 70.0
        for n in STRONG_TELLS:
            if n == "serial" and not (close or deep):
                continue
            t.revealed.add(n)
        if deep:
            for n in WEAK_TELLS:
                t.revealed.add(n)
        t.scanned = True
        t.flash_t = 0.35
        conf = self.confidence_of(t)
        self.events.append(("scan_done", t.uid, conf))
        self.floater(f"P {int(round(conf * 100))}%", t, (64, 210, 220) if conf >= 0.66 else (
            (255, 138, 44) if conf >= 0.33 else (162, 168, 180)), 1.4)
        # Reaktion
        if t.is_replicant:
            if self.rng.random() < self.zone["flee"]:
                self._alert(t)
        elif self.rng.random() < 0.12:
            self._panic_one(t, self.player.x)

    def fire(self):
        if self.shot_cd > 0 or self.state != "playing":
            return "cooldown", None
        self.shot_cd = config.SHOT_COOLDOWN
        self.stats["shots"] += 1
        t = self.target
        hit = self.line_of_fire(t)
        sx, sd = self.muzzle()
        if hit is not None:
            ex, ed = hit.x, hit.depth
        elif t is not None:
            ex, ed = t.x, t.depth
            k = config.SHOOT_RANGE / max(1.0, self.dist(self.player, t))
            ex, ed = sx + (ex - sx) * k, sd + (ed - sd) * k
        else:
            ex, ed = sx + self.player.facing * config.SHOOT_RANGE, sd
        self.events.append(("shot", sx, sd, ex, ed, hit.uid if hit else None))
        self.player.state = "shoot"
        self._panic_area(sx, config.PANIC_RADIUS, exclude=hit)
        if hit is None:
            return "miss", None
        return self._hit(hit), hit

    def _hit(self, a):
        if a.boss:
            if a.boss_invuln:               # während seiner Rede abgewehrt
                self.events.append(("boss_blocked",))
                self.floater("ABGEWEHRT", a, (162, 168, 180), 0.9)
                return "blocked"
            a.hp -= 1
            a.flash_t = 0.3
            a.knock = 44.0 * (1 if a.x >= self.player.x else -1)
            self.events.append(("boss_hit", a.hp))
            if a.hp <= 0:
                self._kill(a)
                self.events.append(("boss_dead",))
                self._say("ROY deaktiviert.")
                return "boss_dead"
            self.boss_hits += 1
            if self.boss_hits >= config.ROY_PER_LINE and self.boss_line < len(config.ROY_LINES) - 1:
                self.boss_hits = 0
                self.boss_line += 1
                self.boss_speak_t = config.ROY_SPEAK_S
                a.boss_invuln = True
                self.events.append(("boss_line", self.boss_line))
            return "boss"
        if a.is_replicant and a.hp > 1:
            a.hp -= 1
            a.flash_t = 0.3
            a.knock = 60.0 * (1 if a.x >= self.player.x else -1)
            self.floater("ZÄH! NOCH EINMAL", a, (255, 138, 44), 1.4)
            self.events.append(("tough", a.uid))
            a.alert = False
            a.aggressive = True
            self._alert(a)
            return "tough"
        return self._kill(a)

    def neutralize(self):
        """Sofortschuss auf das aktuelle Ziel (Kompatibilität/Tests)."""
        if self.target is None or not self._target_ok(self.target):
            self._update_target({})
        a = self.target
        if a is None or self.dist(self.player, a) > config.SHOOT_RANGE:
            return "no_target", None
        self.shot_cd = 0.0
        res, hit = self.fire()
        return res, hit

    def _kill(self, a):
        a.alive = False
        a.state = "dead"
        a.dead_t = 0.0
        a.flash_t = 0.25
        a.knock = 26.0 * (1 if a.x >= self.player.x else -1)
        a.facing = -1 if a.knock > 0 else 1
        if self.target is a:
            self.target = None
        if a.is_replicant:
            pts = config.POINTS_REPLICANT * self.combo
            if not a.scanned:
                pts += config.POINTS_INSTINCT
            self.run.score += pts
            self.stats["score"] += pts
            self.stats["reps"] += 1
            self.run.totals["reps"] += 1
            self.floater(f"REPLIKANT +{pts}", a, (64, 210, 220), 2.0)
            if self.combo > 1:
                self.floater(f"KETTE X{self.combo}", a, (255, 138, 44), 1.6)
            if a.bounty:
                self.run.score += config.POINTS_BOUNTY
                self.stats["score"] += config.POINTS_BOUNTY
                self.stats["bounty"] = True
                self.floater(f"KOPFGELD {a.name} +{config.POINTS_BOUNTY}", a, (255, 138, 44), 2.6)
                self.events.append(("bounty", a.uid))
            self.combo = min(config.COMBO_MAX, self.combo + 1)
            self._say(f"Kopfgeld kassiert: {a.name}." if a.bounty else "Replikant deaktiviert.")
            self.events.append(("kill", a.uid, True))
            if self.stats["reps"] == self.quota:
                self.events.append(("quota",))
                self._say("Auftrag erfüllt - Ausgang offen.")
            return "replicant"
        watched = config.SUSPICION_WATCHED if self.watched else 1.0
        self.suspicion = min(1.0, self.suspicion + config.SUSPICION_PER_CIVILIAN * self.run.mods["susp"] * watched)
        if self.watched:
            self.floater("VOR DEN AUGEN DER POLIZEI", a, (224, 72, 90), 2.2)
        self.run.score += config.POINTS_CIVILIAN
        self.stats["score"] += config.POINTS_CIVILIAN
        self.stats["civs"] += 1
        self.run.totals["civs"] += 1
        self.combo = 1
        self.floater(f"MENSCH  {config.POINTS_CIVILIAN}", a, (224, 72, 90), 2.2)
        self._say("MENSCH getötet! Verdacht steigt.")
        self.events.append(("kill", a.uid, False))
        if self.suspicion >= 1.0:
            self._fail("suspicion")
        return "civilian"

    # ------------------------------------------------------------------ Schaden
    def hurt_player(self, src, knock=90.0, text="-1 INTEGRITÄT"):
        p = self.player
        if p.invuln > 0 or self.state != "playing":
            return False
        src_x = src["x"] if isinstance(src, dict) else src.x
        p.hp -= 1
        self.run.hp = p.hp
        p.invuln = 1.3
        p.flash_t = 0.3
        p.state = "hurt"
        p.timer = 0.45
        p.knock = knock * (1 if p.x >= src_x else -1)
        self.scan_t = -1.0
        self.scan_target = None
        self.aiming = False
        self.events.append(("hurt", p.hp))
        self.floater(text, p, (224, 72, 90), 1.4)
        if p.hp <= 0:
            self._fail("hp")
        return True

    # ------------------------------------------------------------------ Höhe / Hindernisse
    def _physics_z(self, a, dt):
        if a.z > 0.0 or a.vz > 0.0:
            a.vz -= config.GRAVITY * dt
            a.z += a.vz * dt
            if a.z <= 0.0:
                a.z = 0.0
                a.vz = 0.0
                self.events.append(("land", a.uid))

    def blocked(self, x, d, z, r=4.0):
        for o in self.obstacles:
            if abs(x - o["x"]) < o["w"] + r and abs(d - o["d"]) < o["dd"] + 0.02 and z < o["h"]:
                return True
        return False

    def _obstacle_ahead(self, a, look=26.0):
        if a.vx == 0.0:
            return None
        s = 1 if a.vx > 0 else -1
        for o in self.obstacles:
            ahead = (o["x"] - a.x) * s
            if -o["w"] < ahead < o["w"] + look and abs(a.depth - o["d"]) < o["dd"] + 0.035:
                return o
        return None

    # ------------------------------------------------------------------ Verkehr
    def _update_traffic(self, dt, spawn=True):
        rng = self.rng
        p = self.player
        if spawn and self.zone.get("traffic"):
            self.traffic_cd -= dt
            if self.traffic_cd <= 0:
                self.traffic_cd = rng.uniform(0.55, 1.45) * self.zone["traffic"]
                lane, dr = rng.choice(config.LANES)
                kind = rng.choice(ZONE_TRAFFIC[self.zone_index % len(ZONE_TRAFFIC)])
                L, h, sp = VEHICLES[kind]
                sp *= rng.uniform(0.9, 1.15)
                self._veh_uid += 1
                x = self.camera_x - dr * (sp * 0.8 + 300.0)
                self.vehicles.append(dict(x=x, depth=lane, dir=dr, speed=sp, kind=kind, L=L, h=h,
                                          seed=rng.randint(0, 9999), honk=False, uid=-1000 - self._veh_uid))
                self.events.append(("vehicle", kind, dr))
        keep = []
        for v in self.vehicles:
            v["x"] += v["dir"] * v["speed"] * dt
            if (v["x"] - self.camera_x) * v["dir"] > 640.0:
                continue
            keep.append(v)
            lane = v["depth"]
            # Spieler: Hupen, Treffer
            if p.alive:
                in_lane = abs(p.depth - lane) < config.LANE_HALF + 0.02
                ahead = (p.x - v["x"]) * v["dir"]
                if in_lane and 0 < ahead < v["speed"] * 1.3 + v["L"] and not v["honk"]:
                    v["honk"] = True
                    self.events.append(("honk", v["kind"]))
                if in_lane and abs(p.x - v["x"]) < v["L"] * 0.5 + 3 and p.z < v["h"] * 0.75:
                    if self.hurt_player(v, knock=60.0, text="ANGEFAHREN! -1"):
                        p.depth = lane + (config.LANE_HALF + 0.05) * (1 if p.depth >= lane else -1)
                        p.depth = min(config.DEPTH_MAX, max(config.DEPTH_MIN, p.depth))
                        self.events.append(("car_hit",))
            # Passanten weichen aus
            for a in self.actors:
                if a.player or not a.alive or a.escaped:
                    continue
                rel = (a.x - v["x"]) * v["dir"]
                if -v["L"] < rel < v["speed"] * 2.3 and abs(a.depth - lane) < config.LANE_HALF + 0.045:
                    if a.dodge_t <= 0.0:
                        side = 1 if a.depth >= lane else -1
                        td = lane + side * (config.LANE_HALF + 0.07)
                        if td < config.DEPTH_MIN + 0.01 or td > 0.98:
                            td = lane - side * (config.LANE_HALF + 0.07)
                        a.target_depth = min(0.98, max(config.DEPTH_MIN + 0.01, td))
                    a.dodge_t = 0.8
        self.vehicles = keep

    # ------------------------------------------------------------------ Polizei-Suchlicht
    def _update_patrol(self, dt):
        rng = self.rng
        p = self.player
        P = self.patrol
        if P is None:
            if self.patrol_cd is not None and self.state == "playing":
                self.patrol_cd -= dt
                if self.patrol_cd <= 0:
                    self.patrol_cd = rng.uniform(0.8, 1.2) * (self.zone.get("patrol") or 60.0)
                    dr = rng.choice((-1, 1))
                    self.patrol = dict(x=self.camera_x - dr * 330.0, dir=dr, t=0.0, life=rng.uniform(18.0, 25.0),
                                       ph=rng.random() * 6.28, on=0.0, bx=0.0, bd=0.5, leaving=False)
                    self.events.append(("patrol",))
                    self._say("Polizei-Spinner mit Suchlicht über der Straße.")
            self.watched = False
            for a in self.actors:
                a.lit_t = 0.0
            return
        P["t"] += dt
        t = P["t"]
        if t > P["life"] or self.state != "playing":
            P["leaving"] = True
        if P["leaving"]:
            P["x"] += P["dir"] * 140.0 * dt
            P["on"] = max(0.0, P["on"] - dt * 1.5)
            if abs(P["x"] - self.camera_x) > 420.0:
                self.patrol = None
                return
        else:
            goal = p.x + 40.0 * math.sin(t * 0.23)
            sp = 150.0 if abs(goal - P["x"]) > 120 else 34.0
            P["x"] += max(-sp * dt, min(sp * dt, goal - P["x"]))
            if abs(goal - P["x"]) < 160:
                P["on"] = min(1.0, P["on"] + dt * 0.8)
        P["bx"] = P["x"] + 78.0 * math.sin(t * 0.52 + P["ph"])
        P["bd"] = 0.55 + 0.38 * math.sin(t * 0.39 + P["ph"] * 1.7)
        lit_on = P["on"] > 0.5
        self.watched = lit_on and self.in_beam(p)
        for a in self.actors:
            if a.player or not a.alive or a.escaped:
                continue
            if lit_on and self.in_beam(a):
                a.lit_t += dt
                if a.tells.get("pupils") and a.glint_t <= 0 and int(a.lit_t * 1.25) != int((a.lit_t - dt) * 1.25):
                    a.glint_t = 0.3
                    self._glint_seen(a, "SUCHLICHT: AUGENREFLEX", config.OBSERVE_RANGE * 1.3)
                elif not a.tells.get("pupils") and a.lit_t > 1.6 and "pupils" not in a.revealed \
                        and self.dist(p, a) <= config.OBSERVE_RANGE * 1.3:
                    a.revealed.add("pupils")
                    if a is self.target:
                        self.floater("SUCHLICHT: AUGEN NORMAL", a, (162, 168, 180), 1.4)
            else:
                a.lit_t = max(0.0, a.lit_t - dt * 2.0)

    def in_beam(self, a):
        P = self.patrol
        if P is None:
            return False
        return ((a.x - P["bx"]) / 34.0) ** 2 + ((a.depth - P["bd"]) / 0.13) ** 2 < 1.0

    def _glint_seen(self, a, text, rng_):
        if "pupils" in a.revealed or self.dist(self.player, a) > rng_:
            return
        a.revealed.add("pupils")
        self.floater(text, a, (255, 138, 44), 1.6)
        self.events.append(("tell", a.uid, "pupils"))

    # ------------------------------------------------------------------ Ramen
    def _update_ramen(self, dt):
        """Kurz am Nudelstand stehen bleiben füllt ein Herz auf (einmal pro Stand)."""
        p = self.player
        if p.hp >= self.run.max_hp:
            for r in self.ramen:
                r["t"] = 0.0
            return
        for r in self.ramen:
            if r["used"]:
                r["t"] = 0.0
                continue
            if abs(p.x - r["x"]) < config.RAMEN_RANGE and p.depth < 0.6 and p.z <= 0.0:
                r["t"] += dt
                if r["t"] >= config.RAMEN_TIME:
                    r["used"] = True
                    p.hp = min(self.run.max_hp, p.hp + 1)
                    self.run.hp = p.hp
                    self.events.append(("ramen",))
                    self.floater("RAMEN  +1 ♥", p, (255, 138, 44), 2.2)
                    self._say("Am Nudelstand gestärkt: +1 Integrität.")
            else:
                r["t"] = max(0.0, r["t"] - dt)

    # ------------------------------------------------------------------ Endboss ROY
    def _spawn_boss(self):
        rng = self.rng
        look = random_look(rng, 900)
        look.update(outfit="long", head="short", umbrella=None, hair=(214, 220, 226),
                    coat=(22, 22, 28), coat_name="schwarz", collar=True, bag=None,
                    wf=1.12, hf=1.07, cig=False, led=False, mask=False, old=False)
        b = Actor(x=min(self.length - 70.0, self.player.x + 120.0), depth=self.player.depth,
                  look=look, uid=900, is_replicant=True, facing=-1, speed=24.0,
                  phase=0.0, target_depth=self.player.depth)
        b.hp = config.ROY_HP
        b.aggressive = True
        b.boss = True
        b.name = "ROY"
        b.state = "idle"
        b.timer = 99.0
        b.boss_invuln = True
        self.actors.append(b)
        self.boss = b
        self.boss_spawned = True
        self.boss_line = 0
        self.boss_hits = 0
        self.boss_speak_t = config.ROY_SPEAK_S + 0.8
        self.events.append(("boss",))
        self.target = b
        self.manual_target = True

    def _update_boss(self, dt):
        if self.zone_index != 4 or self.state != "playing":
            return
        if not self.boss_spawned:
            if self.player.x > self.length - config.ROY_TRIGGER:
                self._spawn_boss()
            return
        b = self.boss
        if b is None or not b.alive:
            return
        if self.boss_speak_t > 0.0:            # während der Rede: stehen, unverwundbar
            self.boss_speak_t -= dt
            b.boss_invuln = True
            b.state = "idle"
            b.vx = 0.0
            b.timer = 99.0
            b.facing = 1 if self.player.x >= b.x else -1
            if self.boss_speak_t <= 0.0:
                self.boss_speak_t = 0.0
        else:
            b.boss_invuln = False
            if b.state not in ("attack", "punch", "leap"):   # nach der Rede angreifen
                b.alert = True
                b.aggressive = True
                b.state = "attack"
                b.timer = 99.0

    # ------------------------------------------------------------------ Stromausfall
    def _update_blackout(self, dt):
        if self.blackout_at is not None and self.time >= self.blackout_at:
            self.blackout_at = None
            self.blackout_t = 9.0
            self.events.append(("blackout",))
            self._say("Stromausfall! Im Dunkeln leuchten Replikantenaugen.")
        if self.blackout_t > 0.0:
            self.blackout_t -= dt
            if self.blackout_t <= 0.0:
                self.blackout_t = 0.0
                self.events.append(("blackout_end",))

    def _fail(self, reason):
        if self.state != "playing":
            return
        self.state = "failed"
        self.fail_reason = reason
        if reason == "hp":
            self.player.alive = False
            self.player.state = "dead"
            self.player.dead_t = 0.0
        self.events.append(("fail", reason))

    # ------------------------------------------------------------------ NPC-Verhalten
    def _alert(self, a):
        if a.alert or not a.alive:
            return
        a.alert = True
        if a.aggressive:
            a.state = "attack"
            a.timer = 99.0
            self.events.append(("attack", a.uid))
        else:
            a.state = "flee"
            a.timer = 99.0
            self.events.append(("flee", a.uid))
        a.target_depth = self.rng.uniform(config.DEPTH_MIN, 0.95)

    def _panic_one(self, a, src_x):
        if not a.alive or a.state in ("flee", "attack"):
            return
        a.state = "panic"
        a.timer = self.rng.uniform(2.5, 4.5)
        a.facing = 1 if a.x >= src_x else -1
        a.target_depth = self.rng.uniform(config.DEPTH_MIN, 0.95)

    def _panic_area(self, x, radius, exclude=None):
        for a in self.living():
            if a is exclude:
                continue
            if abs(a.x - x) < radius:
                if a.is_replicant and not a.alert and self.rng.random() < 0.35 and (a.scanned or a.aimed_t > 0.5):
                    self._alert(a)
                else:
                    self._panic_one(a, x)

    def _update_npcs(self, dt, frozen=False):
        p = self.player
        m = self.run.mods
        L = self.length
        for a in self.actors:
            if a.player or not a.alive or a.escaped:
                continue
            a.flash_t = max(0.0, a.flash_t - dt)
            a.attack_cd = max(0.0, a.attack_cd - dt)
            if not (self.aiming and self.target is a):
                a.aimed_t = max(0.0, a.aimed_t - dt)
            # Augenreflex
            if a.glint_t > 0:
                a.glint_t -= dt
            dark = self.blackout_t > 0.0
            if a.tells.get("pupils"):
                a.glint_next -= dt * m["glint"] * (4.0 if dark else 1.0)
                if a.glint_next <= 0:
                    a.glint_t = 0.45 if dark else 0.24
                    a.glint_next = self.rng.uniform(5.0, 10.0)
                    if dark:
                        self._glint_seen(a, "AUGENREFLEX IM DUNKELN", config.TARGET_RANGE)
                    elif a is self.target:
                        self._glint_seen(a, "AUGENREFLEX!", config.OBSERVE_RANGE)
            a.dodge_t = max(0.0, a.dodge_t - dt)
            self._physics_z(a, dt)
            if frozen and a.state in ("attack", "punch", "leap"):
                a.state = "walk"
                a.timer = 4.0
            st = a.state
            a.timer -= dt
            if st == "walk":
                a.vx = a.facing * a.speed
                if a.timer <= 0:
                    if not a.tells.get("gait") and self.rng.random() < 0.35:
                        a.state = "idle"
                        a.timer = self.rng.uniform(1.5, 5.0)
                    else:
                        a.timer = self.rng.uniform(3.0, 9.0)
                        if self.rng.random() < 0.3:
                            a.target_depth = self.rng.uniform(config.DEPTH_MIN + 0.02, 0.97)
                if a.x < 30 and a.facing < 0 or a.x > L + 80 and a.facing > 0:
                    a.facing = -a.facing
            elif st == "idle":
                a.vx = 0.0
                if a.timer <= 0:
                    a.state = "walk"
                    a.facing = self.rng.choice((-1, 1))
                    a.timer = self.rng.uniform(3.0, 9.0)
            elif st == "panic":
                a.vx = a.facing * 52.0
                if a.timer <= 0:
                    a.state = "walk"
                    a.timer = self.rng.uniform(3.0, 6.0)
            elif st == "cower":
                a.vx = 0.0
                if a.timer <= 0 and a.aimed_t <= 0.1:
                    a.state = "walk"
                    a.facing = 1 if a.x >= p.x else -1
                    a.timer = 3.0
            elif st == "flee":
                a.facing = 1 if a.x >= p.x else -1
                a.vx = a.facing * 76.0 * m["flee"]
                gone = abs(a.x - p.x) > 360.0 or a.x < -60 or a.x > L + 200
                if gone and not frozen and not self.on_screen(a, -30):
                    self._escape(a)
                    continue
            elif st == "attack":
                a.facing = 1 if p.x >= a.x else -1
                dx = abs(p.x - a.x)
                dd = abs(p.depth - a.depth)
                a.target_depth = p.depth
                agile = self.zone_index >= 2 or a.bounty
                if dx < 15.0 and dd < 0.08 and a.attack_cd <= 0 and p.alive:
                    a.state = "punch"
                    a.timer = 0.42
                    a.attack_cd = 1.7
                    a.vx = 0.0
                    a.phase = 0.0
                    a.hit_done = False
                    self.events.append(("punch", a.uid))
                elif (agile and 36.0 < dx < 85.0 and dd < 0.12 and a.attack_cd <= 0 and a.z <= 0
                      and p.alive and self.rng.random() < dt * 1.4):
                    # Nexus-Sprungangriff: ausweichen per Sprung oder Tiefenschritt
                    a.state = "leap"
                    a.vz = 150.0
                    a.z = 0.01
                    a.vx = a.facing * min(220.0, dx * 3.4)
                    a.timer = 1.2
                    a.attack_cd = 2.4
                    a.hit_done = False
                    self.events.append(("leap", a.uid))
                else:
                    a.vx = a.facing * (88.0 if dx > 15 else 0.0)
            elif st == "leap":
                if not a.hit_done and abs(p.x - a.x) < 14.0 and abs(p.depth - a.depth) < 0.09 \
                        and p.z < config.JUMP_SAFE_Z:
                    a.hit_done = True
                    self.hurt_player(a, knock=120.0)
                if a.z <= 0.0 and a.vz <= 0.0 and a.timer < 1.1:
                    a.state = "attack"
                    a.vx = 0.0
            elif st == "punch":
                a.vx = 0.0
                if a.timer < 0.22 and not a.hit_done:
                    a.hit_done = True
                    if abs(p.x - a.x) < 22.0 and abs(p.depth - a.depth) < 0.1:
                        if p.z < config.JUMP_SAFE_Z:
                            self.hurt_player(a)
                        else:
                            self.floater("AUSGEWICHEN", p, (64, 210, 220), 0.9)
                if a.timer <= 0:
                    a.state = "attack"
            # Auf Zielen reagieren
            if a.aimed_t > 0.9 and a.state in ("walk", "idle", "panic"):
                if a.is_replicant and self.rng.random() < dt * 0.9:
                    self._alert(a)
                elif not a.is_replicant:
                    a.state = "cower"
                    a.timer = 1.2
            # Hindernisse: Replikanten auf der Flucht springen drüber, alle anderen gehen außen herum
            if a.z <= 0.0 and a.state not in ("punch", "cower", "idle"):
                o = self._obstacle_ahead(a)
                if o is not None:
                    if a.is_replicant and a.state in ("flee", "attack") and self.zone_index >= 1:
                        a.vz = 135.0
                        a.z = 0.01
                    elif a.dodge_t <= 0.0:
                        up = o["d"] - o["dd"] - 0.05
                        dn = o["d"] + o["dd"] + 0.05
                        td = up if (abs(a.depth - up) < abs(a.depth - dn) and up > config.DEPTH_MIN) else dn
                        if td > 0.99:
                            td = up
                        a.target_depth = td
                        a.dodge_t = 0.5
            # Bewegung
            nx = a.x + (a.vx + a.knock) * dt
            if not self.blocked(a.x, a.depth, a.z, 2.0) and self.blocked(nx, a.depth, a.z, 2.0):
                nx = a.x
                if a.state == "walk" and a.dodge_t <= 0.0:
                    a.facing = -a.facing
                    a.timer = self.rng.uniform(2.0, 5.0)
            a.x = nx
            a.knock *= 0.85
            dd = a.target_depth - a.depth
            sp = 0.45 if a.dodge_t > 0 else (0.35 if a.state in ("flee", "panic", "attack", "leap") else 0.08)
            a.depth += max(-sp * dt, min(sp * dt, dd))
            a.depth = min(config.DEPTH_MAX, max(config.DEPTH_MIN, a.depth))
            self._animate(a, dt)

    def _escape(self, a):
        a.escaped = True
        a.alive = False
        if self.target is a:
            self.target = None
        if a.is_replicant:
            self.stats["escaped"] += 1
            self.run.totals["escaped"] += 1
            self.run.score += config.POINTS_ESCAPE
            self.stats["score"] += config.POINTS_ESCAPE
            self.suspicion = min(1.0, self.suspicion + config.SUSPICION_PER_ESCAPE)
            self.combo = 1
            self.events.append(("escape", a.uid))
            self._say("Ein Replikant ist entkommen.")

    def _update_dead(self, dt):
        for a in self.actors:
            if not a.alive and not a.escaped:
                a.dead_t += dt
                a.x += a.knock * dt
                a.knock *= 0.82
                if a.z > 0.0 or a.vz != 0.0:
                    a.vz = min(a.vz, 0.0)
                    self._physics_z(a, dt)
                self._animate(a, dt)

    # ------------------------------------------------------------------ Beobachtung
    def _observe(self, dt):
        p = self.player
        rate = self.run.mods["observe"]
        for a in self.living():
            d = self.dist(p, a)
            if d > config.OBSERVE_RANGE:
                a.exposure = max(0.0, a.exposure - dt)
                continue
            focus = a is self.target
            a.exposure += dt * rate * (1.0 if focus else 0.2)
            if a.exposure >= config.OBSERVE_SECONDS:
                a.exposure = 0.0
                remaining = [t for t in WEAK_TELLS if t not in a.revealed]
                if remaining:
                    t = remaining[0]
                    a.revealed.add(t)
                    if focus:
                        lbl = TELLS[t][3]
                        present = a.tells.get(t)
                        self.floater(f"{lbl}: {'AUFFÄLLIG' if present else 'NORMAL'}", a,
                                     (255, 138, 44) if present else (162, 168, 180), 1.6)
                        self.events.append(("tell", a.uid, t))

    # ------------------------------------------------------------------ Animation
    def _animate(self, a, dt, depth_move=0):
        if not a.alive and not a.escaped:
            a.anim = "die"
            n = frame_count("die")
            a.phase = min(1.0, a.dead_t / 0.9)
            a.frame = min(n - 1, int(a.phase * (n - 1) + 0.0001))
            return
        st = a.state
        speed = abs(a.vx)
        if (a.z > 0.0 or st == "leap") and st not in ("aim", "shoot", "hurt"):
            a.anim = "jump"
            a.frame = 0
            return
        if st in ("walk", "panic", "flee", "attack", "run") or (a.player and st in ("walk", "run")):
            moving = speed > 1.0 or (a.player and depth_move)
            if a.player:
                anim = "run" if st == "run" else ("walk" if moving else "idle")
            elif st == "panic":
                anim = "panic" if moving else "idle"
            elif st in ("flee", "attack"):
                anim = "run" if moving else "idle"
            else:
                anim = "walk" if moving else "idle"
            if anim in ("walk", "run", "panic"):
                adv = max(speed, 26.0 if (a.player and depth_move) else 0.0)
                a.phase = (a.phase + adv * dt / (config.STRIDE_UNITS * (1.6 if anim != "walk" else 1.0))) % 1.0
            else:
                a.phase = (a.phase + dt * 0.4) % 1.0
        elif st == "idle":
            anim = "idle"
            a.phase = (a.phase + dt * 0.4) % 1.0
        elif st == "cower":
            anim = "cower"
            a.phase = (a.phase + dt * 2.0) % 1.0
        elif st == "punch":
            anim = "punch"
            a.phase = min(0.99, 1.0 - max(0.0, a.timer) / 0.42)
        elif st in ("aim", "shoot", "scan", "hurt"):
            anim = st
            if st == "shoot":
                a.phase = min(0.99, (config.SHOT_COOLDOWN - self.shot_cd) / 0.25)
            else:
                a.phase = (a.phase + dt * 2.0) % 1.0
        else:
            anim = "idle"
        a.anim = anim
        n = frame_count(anim)
        a.frame = int(a.phase * n) % n

    # ------------------------------------------------------------------ Zonen
    def _zone_clear(self):
        if self.state != "playing":
            return
        missed = self.stats["reps"] < self.quota
        self.state = "zone_clear"
        self.mission_failed = missed
        if missed:
            self.suspicion = min(1.0, self.suspicion + 0.15)
        else:
            bonus = 250 + 50 * (self.stats["reps"] - self.quota)
            self.run.score += bonus
            self.stats["score"] += bonus
        self.run.hp = self.player.hp
        for k in ("scans", "shots"):
            self.run.totals[k] += self.stats[k]
        self.run.totals["time"] += self.stats["time"]
        self.events.append(("zone_clear", missed))
        self._say(f"Zone '{self.zone['name']}' geschafft.")

    def next_world(self, seed=None):
        """Neue World für die nächste Zone (oder None, wenn Tyrell geschafft)."""
        if self.zone_index + 1 >= len(ZONES):
            return None
        self.run.zone_index = self.zone_index + 1
        self.run.suspicion = max(0.0, self.run.suspicion - 0.1)
        return World(self.run, seed=self.seed if seed is None else seed)

    def advance_zone(self):
        """Kompatibilität: wechselt in-place in die nächste Zone."""
        if self.state != "zone_clear":
            return False
        nw = self.next_world()
        if nw is None:
            self.state = "finished"
            return False
        self.__dict__.update(nw.__dict__)
        return True

    # ------------------------------------------------------------------ Projektion
    def project(self, actor, w=None, h=None):
        """Welt -> Bildschirm: (cx, ground_y, height_px)."""
        return (persp.screen_x(actor.x, actor.depth, self.camera_x), persp.ground_y(actor.depth),
                persp.figure_h(actor.depth))


TELL_ORDER = ORDER
