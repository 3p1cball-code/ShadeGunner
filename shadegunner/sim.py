"""Spielwelt und Kern-Loop (reine Simulation, kein Rendering).

Der Renderer (Software oder GPU) konsumiert nur diesen Zustand. Die Projektion
Welt -> Bildschirm liegt bewusst hier, damit beide Renderer gleich aussehen.
"""

import math
import random

from . import config, procgen
from .detection import STRONG_TELLS, WEAK_TELLS, confidence
from .entities import Actor

# Zonen-Sequenz von den Außenbezirken bis Tyrell HQ (DESIGN.md §6).
# density = Aktoren pro 18 Welt-Einheiten Straße (1.0 -> auf dem Bildschirm
# dicht an dicht). Bestimmt die Passantendichte, die man tatsächlich sieht.
ZONES = [
    dict(name="Außenbezirk", length=1500, density=0.55, replicant_ratio=0.22, subtlety=0.45),
    dict(name="Vorstadt",    length=1800, density=0.85, replicant_ratio=0.28, subtlety=0.62),
    dict(name="Innenstadt",  length=2000, density=1.25, replicant_ratio=0.34, subtlety=0.78),
    dict(name="Hafen",       length=1900, density=1.05, replicant_ratio=0.42, subtlety=0.90),
    dict(name="Tyrell",      length=1500, density=0.95, replicant_ratio=0.55, subtlety=1.00),
]


class World:
    def __init__(self, skills=None, seed=0, zone_index=0):
        self.rng = random.Random(seed)
        self.skills = dict(skills or {})
        self.zone_index = zone_index
        self.zone = ZONES[zone_index]
        self.length = float(self.zone["length"])

        self.player = Actor(x=0.0, depth=0.82, player=True,
                            body=(66, 78, 118), accent=(64, 210, 220), uid=0)
        self.camera_x = self.player.x

        self.actors = []
        self._uid = 1
        self._populate()
        self.actors.append(self.player)

        self.scan_max = config.SCAN_CHARGES + int(self.skills.get("scan_charges", 0))
        self.scan_charges = float(self.scan_max)
        self.suspicion = 0.0
        self.points = 0
        self.replicants_total = sum(1 for a in self.actors if a.is_replicant)
        self.escaped = 0
        self.state = "playing"          # playing | zone_clear | failed | finished
        self.log = []

    # ------------------------------------------------------------------ Aufbau
    def _populate(self):
        acts, self._uid = procgen.populate(self.rng, self.zone, 60.0, self.length, self._uid)
        self.actors.extend(acts)

    def _say(self, text):
        self.log.append(text)
        if len(self.log) > 6:
            self.log.pop(0)

    # ------------------------------------------------------------------ Update
    def update(self, dt, move=(0.0, 0.0)):
        if self.state != "playing":
            return
        mx, md = move
        p = self.player
        p.x = max(0.0, p.x + mx * config.PLAYER_WALK_SPEED * dt)
        p.depth = min(1.0, max(0.15, p.depth + md * config.PLAYER_DEPTH_SPEED * dt))

        # Kamera weich nachziehen
        self.camera_x += (p.x - self.camera_x) * min(1.0, dt * 6.0)

        # Ladungen regenerieren
        if self.scan_charges < self.scan_max:
            self.scan_charges = min(self.scan_max, self.scan_charges + dt / config.SCAN_RECHARGE_S)

        # NPC-Wanderung + Beobachtung/Reveal
        for a in self.actors:
            if a is p:
                continue
            a.highlight_t = max(0.0, a.highlight_t - dt)
            a.phase += dt
            a.x += math.sin(a.phase * 0.5) * a.speed * dt * 0.15
            self._observe(a, dt)

        if p.x >= self.length:
            self._zone_clear()

    def _observe(self, a, dt):
        if a.deactivated or not a.alive:
            return
        if abs(a.x - self.player.x) > config.OBSERVE_RANGE:
            a.exposure = 0.0
            return
        a.exposure += dt
        if a.exposure >= config.OBSERVE_SECONDS:
            a.exposure = 0.0
            remaining = [t for t in WEAK_TELLS if t not in a.revealed]
            if remaining:
                a.revealed.add(self.rng.choice(remaining))

    # ------------------------------------------------------------------ Aktionen
    def _nearest(self, rng_dist, unscanned_only=False):
        best, bd = None, rng_dist
        for a in self.actors:
            if a is self.player or a.deactivated or not a.alive:
                continue
            if unscanned_only and a.scanned:
                continue
            d = abs(a.x - self.player.x)
            if d <= bd:
                best, bd = a, d
        return best

    def scan(self):
        if self.scan_charges < 1.0:
            return "no_charge", None
        a = self._nearest(config.SCAN_RANGE, unscanned_only=True)
        if a is None:
            return "no_target", None
        self.scan_charges -= 1.0
        a.scanned = True
        for t in STRONG_TELLS:
            a.revealed.add(t)
        a.mark((64, 210, 220), 0.5)
        return "ok", a

    def neutralize(self):
        a = self._nearest(config.DEACTIVATE_RANGE)
        if a is None:
            return "no_target", None
        a.alive = False
        a.deactivated = True
        if a.is_replicant:
            self.points += 1
            a.mark((85, 255, 140), 0.6)
            self._say("Replikant deaktiviert.")
            return "replicant", a
        self.suspicion = min(1.0, self.suspicion + config.SUSPICION_PER_CIVILIAN)
        a.mark((255, 70, 40), 0.7)
        self._say("MENSCH getötet! Suspicion steigt.")
        if self.suspicion >= 1.0:
            self.state = "failed"
        return "civilian", a

    def confidence_of(self, a):
        return confidence(a.revealed, a.tells)

    # ------------------------------------------------------------------ Zonen
    def _zone_clear(self):
        self.escaped = sum(1 for a in self.actors
                           if a.is_replicant and a.alive and not a.deactivated)
        if self.escaped:
            self.suspicion = min(1.0, self.suspicion + 0.04 * self.escaped)
        self.state = "zone_clear"
        self._say(f"Zone '{self.zone['name']}' geschafft. Entkommen: {self.escaped}.")

    def advance_zone(self):
        if self.state != "zone_clear":
            return False
        self.zone_index += 1
        if self.zone_index >= len(ZONES):
            self.state = "finished"
            return False
        # neue Zone, Suspicion leicht zurücksetzen (neuer Auftrag)
        carry_points = self.points
        self.zone = ZONES[self.zone_index]
        self.length = float(self.zone["length"])
        self.player.x = 0.0
        self.player.depth = 0.82
        self.camera_x = 0.0
        self.actors = [self.player]
        self._populate()
        self.points = carry_points
        self.suspicion = max(0.0, self.suspicion - 0.15)
        self.scan_charges = float(self.scan_max)
        self.replicants_total = sum(1 for a in self.actors if a.is_replicant)
        self.escaped = 0
        self.state = "playing"
        self._say(f"Betrete '{self.zone['name']}'.")
        return True

    # ------------------------------------------------------------------ Projektion
    def project(self, actor, w, h):
        """Welt -> Bildschirm: (cx, ground_y, height_px).

        Belt-Scroller-Projektion. Tiefe steuert Grundlinie UND Größe UND die
        horizontale Skala: nahe Figuren sind größer und ziehen im gleichen Maße
        schneller über den Schirm als ferne (Perspektive).
        """
        fy0 = int(config.FLOOR_TOP_Y * h)
        fy1 = int(config.FLOOR_BOTTOM_Y * h)
        d = actor.depth
        ground_y = fy0 + (fy1 - fy0) * d
        scale = 0.40 + 0.60 * d
        px_per_unit = (w / config.VIEW_SPAN_NEAR) * scale
        cx = w * 0.5 + (actor.x - self.camera_x) * px_per_unit
        height = (h * 0.06 + h * 0.15 * d)
        return cx, ground_y, height
