"""Effekte: Regen + Spritzer, Dampf, Funken, Leuchtspuren, Screenshake, Blitze.

Alles in Bildschirm-Koordinaten der Dither-Auflösung; Partikel mit Welt-Anker
(Dampf aus Gullys, Treffer) werden pro Frame neu projiziert.
"""

import math
import random

from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QRadialGradient

from .. import config, persp

W, H = config.RENDER_W, config.RENDER_H


def _soft(radius, rgb, alpha):
    """Weicher Kreis als Partikel-Textur."""
    s = int(radius * 2) + 2
    img = QImage(s, s, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    g = QRadialGradient(s / 2, s / 2, radius)
    g.setColorAt(0.0, QColor(rgb[0], rgb[1], rgb[2], alpha))
    g.setColorAt(0.6, QColor(rgb[0], rgb[1], rgb[2], int(alpha * 0.45)))
    g.setColorAt(1.0, QColor(rgb[0], rgb[1], rgb[2], 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawEllipse(QRectF(0, 0, s, s))
    p.end()
    return img


class FX:
    def __init__(self, seed=0):
        self.rng = random.Random(seed)
        self.rain = []
        self.splashes = []
        self.steam = []
        self.sparks = []
        self.tracers = []
        self.flashes = []
        self.trauma = 0.0
        self.lightning = 0.0
        self.bolt = None
        self._next_bolt = 8.0
        self.hurt = 0.0
        self.intensity = 0.6
        self._steam_tex = [_soft(r, (150, 156, 170), 60) for r in (4, 6, 9, 13)]
        self._puff_acc = 0.0
        self.set_rain(0.6)

    # ------------------------------------------------------------------ Regen
    def set_rain(self, intensity):
        self.intensity = intensity
        n = int(320 * intensity) + 40
        rng = self.rng
        self.rain = []
        for _ in range(n):
            layer = rng.random()
            self.rain.append([rng.uniform(0, W + 60), rng.uniform(-H, H), layer])

    def update_rain(self, dt, cam_dx):
        rng = self.rng
        wind = 0.32
        for r in self.rain:
            layer = r[2]
            sp = 260 + 260 * layer
            r[1] += sp * dt
            r[0] += -sp * wind * dt - cam_dx * (0.2 + 0.8 * layer)
            if r[1] > H:
                r[1] = rng.uniform(-40, -4)
                r[0] = rng.uniform(0, W + 80)
            if r[0] < -20:
                r[0] += W + 80
            elif r[0] > W + 60:
                r[0] -= W + 80
        # Spritzer auf dem Boden
        n = int(self.intensity * 160 * dt * 4)
        for _ in range(n):
            d = rng.random() ** 0.7
            y = persp.ground_y(d * 1.08 - 0.05)
            if y < persp.FACADE_Y:
                continue
            self.splashes.append([rng.uniform(0, W), y, 0.0, 0.5 + d])
        self.splashes = [s for s in self.splashes if s[2] < 0.22]
        for s in self.splashes:
            s[2] += dt

    def draw_rain(self, p, tint):
        lines_far, lines_mid, lines_near = [], [], []
        for x, y, layer in self.rain:
            ln = 4 + 12 * layer
            dx = ln * 0.32
            ln_ = QLineF(x, y, x - dx, y + ln)
            if layer < 0.4:
                lines_far.append(ln_)
            elif layer < 0.8:
                lines_mid.append(ln_)
            else:
                lines_near.append(ln_)
        for lines, f, a in ((lines_far, 0.5, 90), (lines_mid, 0.75, 120), (lines_near, 1.0, 150)):
            pen = QPen(QColor(int(tint[0] * f), int(tint[1] * f), int(tint[2] * f), a))
            pen.setWidth(1)
            p.setPen(pen)
            p.drawLines(lines)

    def draw_splashes(self, p, tint):
        pen = QPen(QColor(tint[0], tint[1], tint[2], 150))
        pen.setWidth(1)
        p.setPen(pen)
        for x, y, t, s in self.splashes:
            k = t / 0.22
            r = 1 + int(3 * s * k)
            if k < 0.35:
                p.drawPoint(QPointF(x, y - 1))
            else:
                p.drawPoint(QPointF(x - r, y - 1 - int(2 * (1 - k))))
                p.drawPoint(QPointF(x + r, y - 1 - int(2 * (1 - k))))

    # ------------------------------------------------------------------ Dampf
    def puff(self, x, y, wx=None, depth=None, scale=1.0):
        self.steam.append(dict(x=x, y=y, wx=wx, d=depth, t=0.0, life=self.rng.uniform(2.0, 3.6),
                               vx=self.rng.uniform(-6, 6), vy=self.rng.uniform(-14, -8),
                               s=scale, tex=self.rng.randrange(2)))

    def update_steam(self, dt):
        for s in self.steam:
            s["t"] += dt
            s["x"] += s["vx"] * dt
            s["y"] += s["vy"] * dt
            s["vx"] += -10 * dt
        self.steam = [s for s in self.steam if s["t"] < s["life"]]

    def draw_steam(self, p, cam_x, cam_fac=None):
        for s in self.steam:
            k = s["t"] / s["life"]
            tex = self._steam_tex[min(3, s["tex"] + int(k * 2.5))]
            sc = s["s"] * (0.6 + 1.6 * k)
            if s["wx"] is not None:
                bx = persp.screen_x(s["wx"], s["d"], cam_x) + (s["x"])
                by = s["y"]
            else:
                bx = s["x"] - cam_x * (cam_fac or 0.0) + W * 0.5
                by = s["y"]
            w = tex.width() * sc
            p.setOpacity(max(0.0, min(1.0, (1 - k) * 1.4 * min(1.0, k * 6))))
            p.drawImage(QRectF(bx - w / 2, by - w / 2, w, w), tex)
        p.setOpacity(1.0)

    # ------------------------------------------------------------------ Kampf
    def tracer(self, sx, sd, ex, ed, hit):
        self.tracers.append(dict(sx=sx, sd=sd, ex=ex, ed=ed, t=0.0, hit=hit))
        self.trauma = min(1.0, self.trauma + 0.35)

    def impact(self, wx, depth, y_off, color, n=14, blood=False):
        rng = self.rng
        for _ in range(n):
            a = rng.uniform(-math.pi, 0.2)
            v = rng.uniform(20, 90)
            self.sparks.append(dict(wx=wx, d=depth, ox=0.0, oy=y_off, vx=math.cos(a) * v, vy=math.sin(a) * v,
                                    t=0.0, life=rng.uniform(0.2, 0.55), c=color if not blood or rng.random() < 0.3
                                    else (138, 32, 56), g=200 if blood else 120))
        self.flashes.append(dict(wx=wx, d=depth, oy=y_off, t=0.0))

    def update_combat(self, dt):
        for t in self.tracers:
            t["t"] += dt
        self.tracers = [t for t in self.tracers if t["t"] < 0.16]
        for s in self.sparks:
            s["t"] += dt
            s["ox"] += s["vx"] * dt
            s["oy"] += s["vy"] * dt
            s["vy"] += s["g"] * dt
        self.sparks = [s for s in self.sparks if s["t"] < s["life"]]
        for f in self.flashes:
            f["t"] += dt
        self.flashes = [f for f in self.flashes if f["t"] < 0.12]
        self.trauma = max(0.0, self.trauma - dt * 1.6)
        self.hurt = max(0.0, self.hurt - dt * 1.8)

    def shake(self):
        t = self.trauma * self.trauma
        if t <= 0.001:
            return 0, 0
        return (int(round(self.rng.uniform(-1, 1) * 5 * t)), int(round(self.rng.uniform(-1, 1) * 4 * t)))

    # ------------------------------------------------------------------ Blitz
    def update_weather(self, dt, rain_level):
        self.lightning = max(0.0, self.lightning - dt * 3.0)
        self._next_bolt -= dt
        if self._next_bolt <= 0 and rain_level > 0.3:
            self._next_bolt = self.rng.uniform(9.0, 22.0)
            self.lightning = 1.0
            x = self.rng.uniform(40, W - 40)
            pts = [(x, 0.0)]
            y = 0.0
            while y < persp.FACADE_Y * 0.55:
                y += self.rng.uniform(6, 14)
                x += self.rng.uniform(-9, 9)
                pts.append((x, y))
            self.bolt = pts
            return True
        if self.lightning < 0.5:
            self.bolt = None
        return False
