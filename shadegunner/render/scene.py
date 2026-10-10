"""Szenen-Renderer (Software-Komposition): Stadt-Backdrop + Parallax + Aktoren.

Die Szene wird pro Frame auf der CPU in ein RGB-Bytearray komponiert (~5 ms) und
als Textur an den GPU-Pfad übergeben, der Bayer-Dither + CRT darauf anwendet
(siehe render/glrender.py). Die Stadt-Geometrie wird pro Zone einmal erzeugt und
mit Parallax-Faktoren gezeichnet - kein Flackern, reproduzierbar.
"""

import random

from .. import config
from .software import Canvas, draw_pedestrian

C = config.NOIR16
VOID, NIGHT, NAVY, INDIGO = C[0], C[1], C[2], C[3]
BLUE, STEEL, GRAPHITE, SLATE = C[4], C[5], C[6], C[7]
ASH, PALE, WHITE = C[8], C[9], C[10]
TEAL, CYAN, MAGENTA, AMBER, VIOLET = C[11], C[12], C[13], C[14], C[15]
NEON = [CYAN, MAGENTA, AMBER, VIOLET, TEAL]

# Parallax-Faktoren je Ebene (Anteil der Kamera-Bewegung)
FAR_FACTOR = 0.12
MID_FACTOR = 0.38
RAIN_FACTOR = 0.06

_STREET_TOP = (16, 18, 30)
_STREET_BOT = (6, 8, 14)


def make_city(rng, w, h):
    """Backdrop-Geometrie über 2 Bildbreiten (für nahtloses Wrappen bei Parallax)."""
    W2 = 2 * w
    hz = int(config.HORIZON_Y * h)

    far, far_w = [], []
    x = -4
    while x < W2:
        bw = rng.randint(int(w * 0.05), int(w * 0.11))
        bh = rng.randint(int(h * 0.12), int(h * 0.30))
        top = hz - bh
        far.append((x, top, bw, bh + 2, NIGHT if rng.random() < 0.6 else NAVY))
        for wy in range(top + 4, hz - 3, 7):
            for wx in range(x + 3, x + bw - 2, 6):
                if rng.random() < 0.12:
                    far_w.append((wx, wy, INDIGO))
        x += bw + rng.randint(2, 8)

    mid, mid_w, signs = [], [], []
    x = -6
    while x < W2:
        bw = rng.randint(int(w * 0.07), int(w * 0.14))
        bh = rng.randint(int(h * 0.18), int(h * 0.44))
        top = hz - bh
        mid.append((x, top, bw, bh + 3, NAVY if rng.random() < 0.5 else INDIGO))
        for wy in range(top + 5, hz - 3, 8):
            for wx in range(x + 3, x + bw - 2, 7):
                if rng.random() < 0.18:
                    mid_w.append((wx, wy, STEEL if rng.random() < 0.7 else BLUE))
        if rng.random() < 0.6:
            nc = rng.choice(NEON)
            sx = x + rng.randint(2, max(2, bw - 6))
            sy = top + rng.randint(3, max(3, bh // 2))
            sh = rng.randint(int(bh * 0.25), int(bh * 0.6))
            signs.append((sx, sy, sh, nc))
        x += bw + rng.randint(3, 12)

    return dict(w2=W2, far=far, far_w=far_w, mid=mid, mid_w=mid_w, signs=signs)


class Scene:
    """Komponiert Frames. Pro Zone wird die Stadt-Geometrie einmalig erzeugt."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.cav = Canvas(w, h)
        self._zone = None
        self._city = None
        self._rain_particles = [[random.random() * w, random.random() * h, random.randint(4, 9)]
                                for _ in range(160)]

    def ensure_zone(self, zone_index, seed):
        if self._zone == zone_index and self._city is not None:
            return
        self._zone = zone_index
        self._city = make_city(random.Random(1000 + zone_index * 7 + seed), self.w, self.h)
        self._glow = [(44, 32, 64), (52, 34, 68), (86, 44, 96), (72, 44, 60), (40, 44, 76)][zone_index % 5]

    # ------------------------------------------------------------------ Bausteine
    def _sky(self):
        cav, h, hz = self.cav, self.h, int(config.HORIZON_Y * self.h)
        cav.vgrad(0, hz, VOID, self._glow)
        cav.vgrad(hz - hz // 3, hz, self._glow, tuple(min(255, v + 30) for v in self._glow))
        cav.rect(int(self.w * 0.55), hz - int(h * 0.10), int(self.w * 0.22), int(h * 0.10),
                 tuple(int(v * 1.6) for v in self._glow))

    def _layer(self, rects, wins, off):
        cav, W2 = self.cav, self._city["w2"]
        w = self.w
        for (x, y, bw, bh, c) in rects:
            xx = int((x - off) % W2)
            if xx >= w or xx + bw <= 0:
                continue
            cav.rect(xx, y, bw, bh, c)
        for (x, y, c) in wins:
            xx = int((x - off) % W2)
            if xx >= w:
                continue
            cav.rect(xx, y, 2, 3, c)

    def _street(self):
        cav, h = self.cav, self.h
        fy0 = int(config.FLOOR_TOP_Y * h)
        cav.vgrad(fy0, h, _STREET_TOP, _STREET_BOT)
        cav.hline(0, self.w, fy0, SLATE)

    def _reflections(self, off):
        cav, h = self.cav, self.h
        W2 = self._city["w2"]
        fy0 = int(config.FLOOR_TOP_Y * h)
        fy1 = int(config.FLOOR_BOTTOM_Y * h)
        for (sx, _sy, _sh, nc) in self._city["signs"]:
            rx = int((sx - off) % W2)
            if rx >= self.w:
                continue
            length = int((fy1 - fy0) * 0.7)
            for i in range(length):
                yy = fy0 + i
                if yy >= h:
                    break
                f = (1.0 - i / max(1, length)) ** 1.6
                wob = int(2.5 * f * ((i % 6) - 3) / 3.0)
                cav.set(rx + wob, yy, (int(nc[0] * f * 0.42), int(nc[1] * f * 0.42), int(nc[2] * f * 0.42)))

    def _actors(self, world):
        w = self.w
        for a in sorted(world.actors, key=lambda a: a.depth):
            cx, gy, hgt = world.project(a, w, self.h)
            if cx < -hgt or cx > w + hgt:
                continue
            self._actor(a, int(cx), int(gy), int(hgt))

    def _actor(self, a, cx, gy, hgt):
        cav = self.cav
        if a.deactivated:
            cav.rect(cx - hgt // 4, gy - 3, hgt // 2, 3, (18, 20, 30))
            cav.rect(cx - hgt // 4, gy - 3, hgt // 4, 2, a.accent)
            return
        draw_pedestrian(cav, cx, gy, hgt, a.body, a.accent)
        if a.player:
            cav.rect(cx - 1, gy - hgt, 3, 2, WHITE)
        elif a.scanned:
            bw = max(3, hgt // 4)
            cav.rect(cx - bw, gy - hgt - 2, bw * 2, 1, CYAN)
        if a.highlight_t > 0 and a.highlight != (0, 0, 0):
            cav.rect(cx - max(1, hgt // 6), gy - hgt - 4, max(3, hgt // 3), 1, a.highlight)

    def _rain(self, dt, off):
        cav, w, h = self.cav, self.w, self.h
        for p in self._rain_particles:
            p[1] += 320.0 * dt
            p[0] -= (60.0 * dt + off)
            if p[1] > h:
                p[0] = random.random() * w
                p[1] = -p[2]
            if p[0] < -2:
                p[0] += w + 4
            elif p[0] > w + 2:
                p[0] -= w + 4
            x0 = int(p[0])
            y0 = int(p[1])
            for k in range(p[2]):
                cav.set(x0 - k // 2, y0 + k, SLATE if k & 1 else (70, 76, 92))

    # ------------------------------------------------------------------ Frame
    def frame(self, world, dt=0.016):
        off_far = world.camera_x * FAR_FACTOR
        off_mid = world.camera_x * MID_FACTOR
        self._sky()
        self._layer(self._city["far"], self._city["far_w"], off_far)
        self._layer(self._city["mid"], self._city["mid_w"], off_mid)
        self._street()
        self._reflections(off_mid)
        self._actors(world)
        self._rain(dt, world.camera_x * RAIN_FACTOR)
        return self.cav


def render_world(world, w, h, rng=None, seed=0):
    """Standalone-Einzelframe (für Tools/Tests)."""
    sc = Scene(w, h)
    sc.ensure_zone(world.zone_index, seed)
    return sc.frame(world, 0.016)
