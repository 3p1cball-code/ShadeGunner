"""Szenen-Renderer (Software): Stadt-Backdrop + Aktoren aus dem Sim-Zustand.

Wird von Tools (Preview, SimShots) benutzt und ist die visuelle Referenz für den
späteren GPU-Renderer. Nutzt ausschließlich `World.project` für die Projektion,
damit Software und GPU dieselbe Bildkomposition ergeben.
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


def draw_backdrop(cav, w, h, rng, zone_index=0):
    """Himmel, ferne + mittlere Skyline, Straße. Reine Kulisse."""
    hz = int(config.HORIZON_Y * h)
    # Himmel verschiebt sich pro Zone ein wenig (kälter -> neon-giftiger)
    glow = [(44, 32, 64), (52, 34, 68), (86, 44, 96), (72, 44, 60), (40, 44, 76)][zone_index % 5]
    cav.vgrad(0, hz, VOID, glow)
    cav.vgrad(hz - hz // 3, hz, glow, tuple(min(255, v + 30) for v in glow))
    cav.rect(int(w * 0.55), hz - int(h * 0.10), int(w * 0.22), int(h * 0.10),
             tuple(int(v * 1.6) for v in glow))

    x = -4
    while x < w:
        bw = rng.randint(int(w * 0.05), int(w * 0.11))
        bh = rng.randint(int(h * 0.12), int(h * 0.30))
        top = hz - bh
        cav.rect(x, top, bw, bh + 2, NIGHT if rng.random() < 0.6 else NAVY)
        for wy in range(top + 4, hz - 3, 7):
            for wx in range(x + 3, x + bw - 2, 6):
                if rng.random() < 0.12:
                    cav.rect(wx, wy, 2, 3, INDIGO)
        x += bw + rng.randint(2, 8)

    signs = []
    x = -6
    while x < w:
        bw = rng.randint(int(w * 0.07), int(w * 0.14))
        bh = rng.randint(int(h * 0.18), int(h * 0.44))
        top = hz - bh
        cav.rect(x, top, bw, bh + 3, NAVY if rng.random() < 0.5 else INDIGO)
        for wy in range(top + 5, hz - 3, 8):
            for wx in range(x + 3, x + bw - 2, 7):
                if rng.random() < 0.18:
                    cav.rect(wx, wy, 2, 3, STEEL if rng.random() < 0.7 else BLUE)
        if rng.random() < 0.6:
            nc = rng.choice(NEON)
            sx = x + rng.randint(2, max(2, bw - 6))
            sy = top + rng.randint(3, max(3, bh // 2))
            sh = rng.randint(int(bh * 0.25), int(bh * 0.6))
            cav.rect(sx, sy, 3, sh, nc)
            signs.append((sx, sh, nc))
        x += bw + rng.randint(3, 12)

    fy0 = int(config.FLOOR_TOP_Y * h)
    fy1 = int(config.FLOOR_BOTTOM_Y * h)
    cav.vgrad(fy0, h, (16, 18, 30), (6, 8, 14))
    cav.hline(0, w, fy0, SLATE)

    for (sx, _sh, nc) in signs:
        rx = sx + rng.randint(-4, 4)
        length = int((fy1 - fy0) * rng.uniform(0.25, 0.9))
        for i in range(length):
            yy = fy0 + i
            if yy >= h:
                break
            f = (1.0 - i / max(1, length)) ** 1.6
            wob = int(2.5 * f * ((i % 6) - 3) / 3.0)
            cav.set(rx + wob, yy, (int(nc[0] * f * 0.42), int(nc[1] * f * 0.42), int(nc[2] * f * 0.42)))

    _rain(cav, w, h, rng)


def _rain(cav, w, h, rng):
    for _ in range(150):
        rx = rng.randint(0, w)
        ry = rng.randint(0, int(h * 0.8))
        for k in range(rng.randint(3, 7)):
            cav.set(rx - k // 2, ry + k, SLATE if k % 2 else (70, 76, 92))


def _draw_actor(cav, world, a, w, h):
    cx, gy, hgt = world.project(a, w, h)
    cx, gy, hgt = int(cx), int(gy), int(hgt)
    if a.deactivated:
        # deaktiviert: am Boden liegend
        cav.rect(cx - hgt // 4, gy - 3, hgt // 2, 3, (18, 20, 30))
        cav.rect(cx - hgt // 4, gy - 3, hgt // 4, 2, a.accent)
        return
    draw_pedestrian(cav, cx, gy, hgt, a.body, a.accent)
    if a.player:
        cav.rect(cx - 1, gy - hgt, 3, 2, WHITE)
    elif a.scanned:
        # Scan-Klammer über dem Kopf
        bw = max(3, hgt // 4)
        cav.rect(cx - bw, gy - hgt - 2, bw * 2, 1, CYAN)
    if a.highlight_t > 0 and a.highlight != (0, 0, 0):
        cav.rect(cx - max(1, hgt // 6), gy - hgt - 4, max(3, hgt // 3), 1, a.highlight)


def render_world(world, w, h, rng=None):
    rng = rng or random.Random(1234)
    cav = Canvas(w, h)
    draw_backdrop(cav, w, h, rng, world.zone_index)
    # hinten -> vorne zeichnen
    for a in sorted(world.actors, key=lambda a: a.depth):
        _draw_actor(cav, world, a, w, h)
    return cav
