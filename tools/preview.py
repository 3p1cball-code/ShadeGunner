#!/usr/bin/env python3
"""Software-Preview: rendert eine Teststraße (M0) nach PNG.

Zweck: den Look (16 Farben, Bayer-Dither) remote validieren, ohne GPU/Display.
Aufruf:  python3 tools/preview.py [ausgabe.png] [palette]
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shadegunner import config  # noqa: E402
from shadegunner.palette import dither  # noqa: E402
from shadegunner.render import pngmin  # noqa: E402
from shadegunner.render.software import Canvas, draw_pedestrian  # noqa: E402


def build_scene(w, h, seed=7):
    C = config.NOIR16
    void, night, navy, indigo = C[0], C[1], C[2], C[3]
    blue, steel, graphite, slate = C[4], C[5], C[6], C[7]
    ash, pale, white = C[8], C[9], C[10]
    teal, cyan, magenta, amber, violet = C[11], C[12], C[13], C[14], C[15]

    cav = Canvas(w, h)
    rng = random.Random(seed)
    hz = int(config.HORIZON_Y * h)

    # --- Himmel: kalt oben, Neon-Dunst am Horizont ---
    cav.vgrad(0, hz, void, (44, 32, 64))
    cav.vgrad(hz - hz // 3, hz, (44, 32, 64), (86, 52, 104))
    # großflächiger Schimmer über der Innenstadt
    cav.rect(int(w * 0.55), hz - int(h * 0.10), int(w * 0.22), int(h * 0.10), (66, 44, 84))

    # --- Ferne Skyline (hintere Parallax-Ebene, dunstig) ---
    x = -4
    while x < w:
        bw = rng.randint(int(w * 0.05), int(w * 0.11))
        bh = rng.randint(int(h * 0.12), int(h * 0.30))
        top = hz - bh
        col = night if rng.random() < 0.6 else navy
        cav.rect(x, top, bw, bh + 2, col)
        for wy in range(top + 4, hz - 3, 7):
            for wx in range(x + 3, x + bw - 2, 6):
                if rng.random() < 0.12:
                    cav.rect(wx, wy, 2, 3, indigo)
        x += bw + rng.randint(2, 8)

    # --- Mittlere Skyline (mittlere Parallax-Ebene) mit Neon ---
    neon = [cyan, magenta, amber, violet, teal]
    signs = []           # (x, y_top, h, color) für Reflexionen
    x = -6
    while x < w:
        bw = rng.randint(int(w * 0.07), int(w * 0.14))
        bh = rng.randint(int(h * 0.18), int(h * 0.44))
        top = hz - bh
        col = navy if rng.random() < 0.5 else indigo
        cav.rect(x, top, bw, bh + 3, col)
        for wy in range(top + 5, hz - 3, 8):
            for wx in range(x + 3, x + bw - 2, 7):
                if rng.random() < 0.18:
                    wc = steel if rng.random() < 0.7 else blue
                    cav.rect(wx, wy, 2, 3, wc)
        if rng.random() < 0.6:
            nc = neon[rng.randrange(len(neon))]
            sx = x + rng.randint(2, max(2, bw - 6))
            sy = top + rng.randint(3, max(3, bh // 2))
            sh = rng.randint(int(bh * 0.25), int(bh * 0.6))
            cav.rect(sx, sy, 3, sh, nc)
            signs.append((sx, sy, sh, nc))
        x += bw + rng.randint(3, 12)

    # --- Straße (Perspektive) ---
    fy0 = int(config.FLOOR_TOP_Y * h)
    fy1 = int(config.FLOOR_BOTTOM_Y * h)
    cav.vgrad(fy0, h, (16, 18, 30), (6, 8, 14))
    cav.hline(0, w, fy0, slate)

    # --- neon-reflexionen auf nassem Asphalt ---
    for (sx, sy, sh, nc) in signs:
        depth = rng.uniform(0.25, 0.9)
        rx = sx + rng.randint(-4, 4)
        length = int((fy1 - fy0) * depth)
        for i in range(length):
            yy = fy0 + i
            if yy >= h:
                break
            f = (1.0 - i / max(1, length)) ** 1.6
            wob = int(2.5 * f * ((i % 6) - 3) / 3.0)
            r = int(nc[0] * f * 0.42)
            g = int(nc[1] * f * 0.42)
            b = int(nc[2] * f * 0.42)
            cav.set(rx + wob, yy, (r, g, b))
            cav.set(rx + wob + 1, yy, (int(r * 0.5), int(g * 0.5), int(b * 0.5)))

    # --- Menge (hinten -> vorne) ---
    body_dark = (26, 30, 50)
    body_mid = (44, 50, 78)
    accent_pool = [cyan, magenta, amber, violet, teal, pale, ash]
    peds = [(rng.random() ** 0.7, rng.randint(0, w)) for _ in range(16)]
    peds.sort()
    for d, px in peds:
        gy = int(fy0 + (fy1 - fy0) * d)
        out_h = int((h * 0.06) + (h * 0.14) * d)
        body = body_dark if d < 0.55 else body_mid
        acc = accent_pool[rng.randrange(len(accent_pool))]
        draw_pedestrian(cav, px, gy, out_h, body, acc)

    # --- Spieler (vorderste Bahn, Cyan-Akzent + Bodenschatten) ---
    px = int(w * 0.30)
    gy = int(fy0 + (fy1 - fy0) * 0.86)
    ph = int(h * 0.18)
    # Bodenschatten
    cav.rect(px - ph // 5, gy - 2, ph // 2, 3, (4, 5, 10))
    draw_pedestrian(cav, px, gy, ph, (66, 78, 118), cyan)
    # Umriss-Akzent am Kopf (erkennbarer Spieler)
    cav.rect(px - 1, gy - ph, 3, 2, white)

    # --- Regen (dünne diagonale Striche) ---
    for _ in range(150):
        rx = rng.randint(0, w)
        ry = rng.randint(0, int(h * 0.8))
        ln = rng.randint(3, 7)
        for k in range(ln):
            cav.set(rx - k // 2, ry + k, slate if k % 2 else (70, 76, 92))

    return cav


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/opencode/shadegunner_preview.png"
    pal = sys.argv[2] if len(sys.argv) > 2 else config.DEFAULT_PALETTE
    w, h = config.RENDER_W, config.RENDER_H
    cav = build_scene(w, h)
    framed = dither(cav.buf, w, h, palette_name=pal)
    pngmin.write_png(out, framed, w, h)
    print(f"geschrieben: {out}  ({w}x{h}, Palette {pal})")


if __name__ == "__main__":
    main()
