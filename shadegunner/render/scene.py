"""Szenen-Komposition (CPU, QPainter): Stadt + Figuren + Licht + Effekte -> QImage.

Pro Frame (~6-9 ms bei 640x360):
  Himmel/Wolken -> Suchscheinwerfer/Spinner -> Skyline fern/mittel (+ Fackeln,
  Warnlichter, Holo-Billboards, Luftschiff) -> Häuserfront (+ Neon, Laternen)
  -> nasser Boden (Spiegelungen, Perspektiv-Textur, Lichtkegel) -> Figuren
  (Schatten, Spiegelbild, Rimlight, Augenreflex) -> Laser/Scan/Leuchtspuren
  -> Regen, Vordergrund -> Glow-Pass (Leuchtschicht verkleinert/vergrößert,
  additiv) -> Blitz/Treffer/Blende.

Danach Bayer-Dither + CRT auf der GPU (render/glrender.py).
"""

import math
import random

from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import (QBrush, QColor, QImage, QLinearGradient, QPainter, QPen,
                         QPolygonF, QRadialGradient, QRegion)

from .. import config, persp
from . import pixfont, sprites, vehicles
from .city import CLOUD_F, MID_F, City, mix, mul, qc, soft_reflection
from .fx import FX

C = config.NOIR16
VOID, NIGHT, NAVY, INDIGO, BLUE, STEEL = C[0], C[1], C[2], C[3], C[4], C[5]
CRIMSON, SODIUM, ASH, PALE, WHITE = C[6], C[7], C[8], C[9], C[10]
SLATE = (112, 118, 132)
TEAL, CYAN, MAGENTA, AMBER, VIOLET = C[11], C[12], C[13], C[14], C[15]

W, H = config.RENDER_W, config.RENDER_H
PLUS = QPainter.CompositionMode.CompositionMode_Plus
OVER = QPainter.CompositionMode.CompositionMode_SourceOver

ADS = ["MEHR MENSCH ALS MENSCH", "TYRELL CORP", "EIN NEUES LEBEN IN DEN KOLONIEN",
       "OFF-WORLD", "SHIMATA DOMINGUEZ", "NEXUS 6", "TRINK KALTEN KAFFEE", "PAN AM"]


def _hash(i, s):
    h = (i * 374761393 + s * 668265263) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF) / 65535.0


# --------------------------------------------------------------------- Billboards

def _billboard_frames(rng, w, h, kind):
    frames = []
    if kind == "face":
        hair = (14, 10, 20)
        for blink in (False, False, False, True):
            img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
            p = QPainter(img)
            g = QLinearGradient(0, 0, 0, h)
            g.setColorAt(0, qc((60, 14, 50)))
            g.setColorAt(1, qc((150, 40, 110)))
            p.fillRect(0, 0, w, h, QBrush(g))
            cx, cy = w * 0.5, h * 0.52
            fw, fh = w * 0.42, h * 0.5
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qc(hair))
            p.drawEllipse(QRectF(cx - fw * 0.75, cy - fh * 0.78, fw * 1.5, fh * 1.25))
            p.setBrush(qc((236, 226, 230)))
            p.drawEllipse(QRectF(cx - fw / 2, cy - fh / 2, fw, fh))
            p.setBrush(qc(hair))
            p.drawRect(QRectF(cx - fw * 0.55, cy - fh * 0.62, fw * 1.1, fh * 0.28))
            ey = cy - fh * 0.05
            p.setBrush(qc((20, 10, 20)))
            for ex in (cx - fw * 0.22, cx + fw * 0.22):
                if blink:
                    p.drawRect(QRectF(ex - 2, ey, 4, 1))
                else:
                    p.drawRect(QRectF(ex - 2, ey - 1, 4, 2))
            p.setBrush(qc((200, 20, 60)))
            p.drawRect(QRectF(cx - 2.5, cy + fh * 0.25, 5, 2))
            p.end()
            frames.append(img)
    elif kind == "logo":
        word = rng.choice(("TYRELL", "NEXUS", "SHIMATA", "ATARU"))
        for k in range(4):
            img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
            p = QPainter(img)
            p.fillRect(0, 0, w, h, qc((10, 20, 40)))
            col = [CYAN, AMBER, WHITE, MAGENTA][k]
            pen = QPen(qc(col))
            p.setPen(pen)
            p.drawRect(2, 2, w - 5, h - 5)
            # Pyramiden-/Ring-Emblem
            cx, cy = w / 2, h * 0.4
            r = min(w, h) * 0.22
            if k % 2 == 0:
                p.drawPolygon(QPolygonF([QPointF(cx - r, cy + r * 0.7), QPointF(cx, cy - r), QPointF(cx + r, cy + r * 0.7)]))
            else:
                p.drawEllipse(QPointF(cx, cy), r, r)
            txt = word[: max(1, (w - 4) // 6)]
            pixfont.draw(p, w // 2, int(h * 0.72), txt, col, 1, None, "center")
            p.end()
            frames.append(img)
    else:  # Kanji-Säule
        for k in range(4):
            img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
            p = QPainter(img)
            p.fillRect(0, 0, w, h, qc((30, 8, 30)))
            col = [MAGENTA, CYAN, AMBER, VIOLET][(k + rng.randint(0, 3)) % 4]
            for gy in range(3, h - 7, 9):
                for gx in range(3, w - 5, 8):
                    for _ in range(4):
                        x0, y0 = gx + rng.randint(0, 4), gy + rng.randint(0, 6)
                        if rng.random() < 0.5:
                            p.fillRect(x0, y0, rng.randint(1, 4), 1, qc(col))
                        else:
                            p.fillRect(x0, y0, 1, rng.randint(1, 5), qc(col))
            p.end()
            frames.append(img)
    return frames


class Scene:
    def __init__(self, w=W, h=H):
        self.w, self.h = w, h
        self.img = QImage(w, h, QImage.Format.Format_RGB32)
        self.emit = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        self.fx = FX(1)
        self.city = None
        self._zone_key = None
        self.t = 0.0
        self.spinners = []
        self.blimp = None
        self.bb_frames = []
        self.screen = {}
        self._refl = {}
        self._last_cam = None
        self.rng = random.Random(5)
        self._gate_open = False
        self.dark = 0.0            # Stromausfall 0..1 (geglättet)
        self.sfx = []              # Geräusch-Ereignisse aus der Szene (vorbeifliegende Spinner)
        self.fog_t = 0.0
        self._fog_d = 0.6          # aktuelle Nebeldichte (atmet über die Zeit)
        self.wisps = []            # Nebelschwaden, die durchs Vordergrundbild ziehen

    # ------------------------------------------------------------------ Zone
    def ensure_zone(self, zone_index, seed, length=None):
        from ..sim import ZONES
        length = length if length is not None else ZONES[zone_index]["length"]
        key = (zone_index, seed, length)
        if key == self._zone_key:
            return
        self._zone_key = key
        self.city = City(zone_index, float(length), seed)
        th = self.city.th
        self.fx.set_rain(th["rain"])
        rng = random.Random(seed + 77)
        self.bb_frames = [_billboard_frames(rng, bb[2], bb[3], rng.choice(("face", "logo", "kanji")))
                          for bb in self.city.billboards]
        self.spinners = []
        for _ in range(th["spinners"]):
            self._spawn_spinner(rng, initial=True)
        self.blimp = None
        if th["blimp"]:
            self.blimp = dict(x=rng.uniform(0, W), y=rng.uniform(28, 60), ad=rng.choice(ADS), off=0.0)
        self._refl.clear()
        self._last_cam = None

    def _spawn_spinner(self, rng, initial=False):
        near = rng.random() < 0.35
        s = rng.uniform(1.0, 1.6) if near else rng.uniform(0.45, 0.8)
        d = rng.choice((-1, 1))
        x = rng.uniform(0, W) if initial else (-40 if d > 0 else W + 40)
        vx = d * rng.uniform(30, 70) * s
        self.spinners.append(dict(x=x, y=rng.uniform(14, persp.FACADE_Y * (0.55 if near else 0.75)),
                                  vx=vx, s=s, near=near, ph=rng.random() * 6,
                                  police=rng.random() < 0.4, bob=rng.random() * 6))
        if near and not initial:
            self.sfx.append(("spinner", d, s))

    # ------------------------------------------------------------------ Events
    def consume(self, world, events):
        fx = self.fx
        for ev in events:
            k = ev[0]
            if k == "shot":
                _, sx, sd, ex, ed, hit = ev
                fx.tracer(sx, sd, ex, ed, hit)
                yo = -persp.figure_h(ed) * 0.62
                fx.impact(ex, ed, yo, (255, 220, 160), n=10 if hit else 6, blood=hit is not None)
            elif k == "hurt":
                fx.hurt = 1.0
                fx.trauma = min(1.0, fx.trauma + 0.6)
            elif k == "kill":
                fx.trauma = min(1.0, fx.trauma + 0.25)

    # ------------------------------------------------------------------ Frame
    def frame(self, world, dt=1 / 60, show_player=True, fade=0.0, power=1.0, cam_override=None):
        if self.city is None or self._zone_key[0] != world.zone_index:
            self.ensure_zone(world.zone_index, getattr(world, "seed", 0), world.length)
        self.t += dt
        t = self.t
        city, th, fx = self.city, self.city.th, self.fx
        seed = getattr(world, "seed", 0)
        self._reflk = 0.6 + 0.7 * th["rain"]     # Regen verstärkt die Spiegelung
        cam = world.camera_x if cam_override is None else cam_override
        cam_dx = 0.0 if self._last_cam is None else (cam - self._last_cam) * persp.PPU_NEAR * 0.6
        self._last_cam = cam

        fx.update_rain(dt, cam_dx)
        fx.update_steam(dt)
        fx.update_combat(dt)
        if fx.update_weather(dt, th["rain"]):
            self.sfx.append(("thunder",))

        self.emit.fill(0)
        p = QPainter(self.img)
        e = QPainter(self.emit)
        sx_, sy_ = fx.shake()
        p.translate(sx_, sy_)
        e.translate(sx_, sy_)

        self._gate_open = world.exit_open() if hasattr(world, "exit_open") else False
        goal = 1.0 if getattr(world, "blackout_t", 0.0) > 0 else 0.0
        self.dark += (goal - self.dark) * min(1.0, dt * (6.0 if goal > self.dark else 1.6))
        if self.dark < 0.01:
            self.dark = 0.0
        self._sky(p, e, cam, t)
        city.far.draw(p, cam)
        self._far_life(p, e, cam, t)
        # Nebel atmet über die Zeit: mal dünn, mal zieht eine dichte Bank durch. Die
        # ferne Skyline liegt immer stärker im Dunst als die Front (Luftperspektive).
        self.fog_t += dt
        slow = 0.5 + 0.5 * math.sin(self.fog_t * 0.07 + seed * 0.017)
        bank = max(0.0, math.sin(self.fog_t * 0.09 + 2.4)) ** 5
        self._fog_d = th["fog_amt"] * (0.85 + 1.15 * slow) + bank * 1.1 * th["fog_amt"] + 0.06
        fd = self._fog_d
        self._fog(p, 0, 24, 168, cam * MID_F * 1.4 + t * 5.0, min(1.0, fd * 0.9))     # hinter der Skyline
        self._air_traffic(p, e, cam, t, far=True)
        self._searchlights(p, cam, t)
        self._blimp(p, e, dt, t)
        city.mid.draw(p, cam)
        self._mid_life(p, e, cam, t)
        self._air_traffic(p, e, cam, t, far=False)
        self._spinners(p, e, dt, t, near=False)
        self._fog_band(p)
        self._fog(p, 0, persp.FACADE_Y - 122, 128, cam * MID_F * 1.4 + t * 5.0, min(1.0, fd * 1.5))
        city.facade.draw(p, cam)
        city.facade.draw(e, cam, img=city.facade_emit, opacity=0.8 * (1.0 - self.dark))
        self._facade_life(p, e, cam, t, dt)
        self._street(p, e, cam, t)
        self._ramen(p, world, cam, t, dt)
        self._fog(p, 1, persp.FACADE_Y - 28, 72, cam * persp.ppu(0.0) + t * 9.0, min(1.0, fd * 0.7))
        self._actors(p, e, world, cam, t, show_player)
        if self.dark > 0:
            p.fillRect(0, 0, W, H, QColor(2, 3, 10, int(165 * self.dark)))
            self._glints(p, e, world, cam, boost=True)
            self._flashlight(p, e, world, cam)
        self._vehicle_lights(p, e, world, cam, t)
        self._combat(p, e, world, cam, t)
        fx.draw_steam(p, cam, city.facade.factor)
        self._patrol(p, e, world, cam, t)
        self._spinners(p, e, dt, t, near=True)
        fx.draw_rain(p, mix(th["fog"], PALE, 0.55))
        self._beam_rain(p)
        self._fog(p, 1, H - 70, 78, cam * persp.ppu(1.15) + t * 14.0, min(1.0, fd * 0.42))
        # Ganzflächiger Nebelschleier: bei dichter Lage verschwimmt auch der Vordergrund
        # (Vordergrund liegt "näher an der Kamera", also über allem anderen).
        self._fog_img(p, city.bank, -30, H + 70, cam * persp.ppu(1.0) * 0.6 + t * 7.0, min(0.46, fd * 0.34))
        self._wisps(p, dt, cam)
        self._foreground(p, cam)
        e.end()

        # Glow-Pass
        p.resetTransform()
        p.setCompositionMode(PLUS)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        small = self.emit.scaled(W // 4, H // 4, Qt.AspectRatioMode.IgnoreAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
        tiny = small.scaled(W // 16, H // 16, Qt.AspectRatioMode.IgnoreAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
        gb = 0.85 + 0.5 * min(1.5, getattr(self, "_fog_d", 0.6))   # Lichter bluten im Nebel
        p.setOpacity(min(1.0, gb))
        p.drawImage(QRectF(0, 0, W, H), small)
        p.setOpacity(min(1.0, gb * 0.85))
        p.drawImage(QRectF(0, 0, W, H), tiny)
        p.setOpacity(1.0)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        if fx.lightning > 0:
            p.setOpacity(fx.lightning * 0.22)
            p.fillRect(0, 0, W, H, qc((200, 210, 255)))
            p.setOpacity(1.0)
        p.setCompositionMode(OVER)
        if fx.hurt > 0:
            g = QRadialGradient(W / 2, H / 2, W * 0.7)
            g.setColorAt(0.5, QColor(0, 0, 0, 0))
            g.setColorAt(1.0, QColor(160, 20, 40, int(200 * fx.hurt)))
            p.fillRect(0, 0, W, H, QBrush(g))
        if fade > 0:
            p.fillRect(0, 0, W, H, QColor(0, 0, 0, int(255 * min(1.0, fade))))
        if power < 1.0:
            self._power_on(p, power)
        p.end()
        return self.img

    # ------------------------------------------------------------------ Himmel
    def _sky(self, p, e, cam, t):
        city, fx = self.city, self.fx
        p.drawImage(0, 0, city.sky)
        if fx.lightning > 0:
            p.setOpacity(fx.lightning * 0.5)
            p.fillRect(0, 0, W, int(persp.FACADE_Y), qc(mix(city.th["cloud_lit"], (200, 200, 255), 0.5)))
            p.setOpacity(1.0)
        for img, speed, fac in city.cloud_layers:
            off = (t * speed + cam * fac) % img.width()
            x = -off
            p.drawImage(QPointF(int(x), 0), img)
            if x + img.width() < W:
                p.drawImage(QPointF(int(x + img.width()), 0), img)
        if fx.bolt:
            pts = [QPointF(x, y) for x, y in fx.bolt]
            for q, a in ((p, 255), (e, 255)):
                pen = QPen(QColor(230, 236, 255, a))
                pen.setWidth(1)
                q.setPen(pen)
                q.drawPolyline(QPolygonF(pts))
        self._spinners(p, e, 0.0, t, near=None)

    def _far_life(self, p, e, cam, t):
        city = self.city
        far = city.far
        # Fackeln (Hades)
        for (L, y, ph, sc) in city.flames:
            x = far.screen_x(L, cam)
            if x < -30 or x > W + 30:
                continue
            n = _hash(int(t * 12 + ph * 10), int(ph * 1000))
            burst = _hash(int(t * 0.4 + ph), int(ph * 777)) > 0.82
            hgt = (4 + 5 * n) * sc * (2.6 if burst else 1.0)
            wid = 2.5 * sc * (1.8 if burst else 1.0)
            for q in (p, e):
                q.setPen(Qt.PenStyle.NoPen)
                q.setBrush(qc(AMBER))
                q.drawPolygon(QPolygonF([QPointF(x - wid, y), QPointF(x + (n - 0.5) * 2, y - hgt), QPointF(x + wid, y)]))
                q.setBrush(qc((255, 240, 200)))
                q.drawRect(QRectF(x - 1, y - hgt * 0.4, 2, hgt * 0.4))
            if burst:
                g = QRadialGradient(x, y - hgt * 0.5, 26 * sc)
                g.setColorAt(0, QColor(255, 140, 50, 90))
                g.setColorAt(1, QColor(0, 0, 0, 0))
                p.setCompositionMode(PLUS)
                p.fillRect(QRectF(x - 30 * sc, y - 40 * sc, 60 * sc, 60 * sc), QBrush(g))
                p.setCompositionMode(OVER)
        self._blinks(p, e, cam, t, "far", far)

    def _blinks(self, p, e, cam, t, which, lay):
        for (wh, L, y, col, ph) in self.city.blinks:
            if wh != which:
                continue
            x = lay.screen_x(L, cam)
            if x < -2 or x > W + 2:
                continue
            on = math.sin(t * 2.2 + ph * 2.1) > 0.55
            if on:
                for q in (p, e):
                    q.fillRect(QRectF(int(x) - 1, y - 1, 2, 2), qc(col))
            else:
                p.fillRect(QRectF(int(x), y, 1, 1), qc(mul(col, 0.4)))

    def _searchlights(self, p, cam, t):
        city = self.city
        if not city.searchlights:
            return
        p.setCompositionMode(PLUS)
        p.setPen(Qt.PenStyle.NoPen)
        tint = mix((170, 180, 220), self.city.th["sky_hor"], 0.25)
        for i, (L, y, sp, ph) in enumerate(city.searchlights):
            x = city.mid.screen_x(L, cam)
            if x < -260 or x > W + 260:
                continue
            ang = math.sin(t * sp + ph) * 0.62 + 0.12 * math.sin(t * sp * 2.7 + ph * 3)
            ln = 330
            tx, ty = x + math.sin(ang) * ln, y - math.cos(ang) * ln
            # weiter, weicher Kegel + enger heller Kern (volumetrisch im Dunst)
            for wdt, a in ((30, 40), (8, 70)):
                nx, ny = math.cos(ang) * wdt, math.sin(ang) * wdt
                g = QLinearGradient(x, y, tx, ty)
                g.setColorAt(0, QColor(tint[0], tint[1], tint[2], a))
                g.setColorAt(0.55, QColor(tint[0], tint[1], tint[2], a // 3))
                g.setColorAt(1, QColor(0, 0, 0, 0))
                p.setBrush(QBrush(g))
                p.drawPolygon(QPolygonF([QPointF(x - 1, y), QPointF(tx - nx, ty - ny), QPointF(tx + nx, ty + ny),
                                         QPointF(x + 1, y)]))
            # Lichtfleck auf den Wolken
            if ty < 70:
                rg = QRadialGradient(tx, max(4, ty), 40)
                rg.setColorAt(0, QColor(tint[0], tint[1], tint[2], 40))
                rg.setColorAt(1, QColor(0, 0, 0, 0))
                p.fillRect(QRectF(tx - 40, max(4, ty) - 40, 80, 80), QBrush(rg))
            p.fillRect(QRectF(int(x) - 1, y - 1, 3, 2), qc(PALE))
        p.setCompositionMode(OVER)

    def _air_traffic(self, p, e, cam, t, far):
        """Luftstraßen: Ketten aus Positionslichtern, die über die Stadt ziehen."""
        span = W + 240
        pale, amber, white, red, bodies = [], [], [], [], []
        for ln in self.city.air:
            if (ln["fac"] < MID_F) != far:
                continue
            d = ln["dir"]
            for k in range(ln["n"]):
                base = ln["ph"] + k * ln["gap"] + t * ln["speed"] * d - cam * ln["fac"]
                x = int(base % span - 120)
                y = int(ln["y"] + ln["slope"] * x + (k % 3) * 2)
                if ln["size"] == 1:
                    (pale if k % 2 else amber).append(QPointF(x, y))
                else:
                    bodies.append(QRectF(x - 2, y, 5, 2))
                    white.append(QPointF(x + 2 * d, y))
                    red.append(QPointF(x - 2 * d, y))
        for r in bodies:
            p.fillRect(r, qc((20, 22, 32)))
        for pts, col, glow in ((pale, PALE, True), (amber, AMBER, False), (white, WHITE, True), (red, (240, 40, 70), True)):
            if not pts:
                continue
            poly = QPolygonF(pts)
            for q in ((p, e) if glow else (p,)):
                q.setPen(qc(col))
                q.drawPoints(poly)

    def _fog(self, p, idx, y, h, scroll, opacity):
        """Kachelnde Nebelschwaden, gestreckt auf Höhe h."""
        self._fog_img(p, self.city.fog_layers[idx], y, h, scroll, opacity)

    def _fog_img(self, p, img, y, h, scroll, opacity):
        if opacity <= 0.01:
            return
        iw = img.width()
        off = scroll % iw
        p.setOpacity(min(1.0, opacity))
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        x = -off
        while x < W:
            p.drawImage(QRectF(x, y, iw, h), img)
            x += iw
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        p.setOpacity(1.0)

    def _blimp(self, p, e, dt, t):
        b = self.blimp
        if b is None:
            return
        b["x"] -= 6.0 * dt
        if b["x"] < -170:
            b["x"] = W + 60
            b["ad"] = random.choice(ADS)
        x, y = b["x"], b["y"]
        bw, bh = 120, 26
        g = QLinearGradient(0, y, 0, y + bh)
        g.setColorAt(0, qc((40, 44, 66)))
        g.setColorAt(1, qc((12, 14, 24)))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QRectF(x, y, bw, bh))
        p.fillRect(QRectF(x + bw - 8, y + 4, 10, 6), qc((20, 22, 34)))
        # Werbe-Laufband
        sx, sy, sw, sh = x + 18, y + 8, 80, 10
        p.fillRect(QRectF(sx - 1, sy - 1, sw + 2, sh + 2), qc(VOID))
        img = pixfont.render(b["ad"] + "   ", AMBER, 1, shadow=None)
        off = int(t * 22) % img.width()
        for q in (p, e):
            q.save()
            q.setClipRect(QRectF(sx, sy, sw, sh))
            q.drawImage(int(sx - off), int(sy + 2), img)
            q.drawImage(int(sx - off + img.width()), int(sy + 2), img)
            q.restore()
        # Lichter + Strahlen nach unten
        for q in (p, e):
            if int(t * 2) % 2 == 0:
                q.fillRect(QRectF(x + 4, y + bh / 2, 2, 2), qc(CRIMSON))
            q.fillRect(QRectF(x + bw / 2, y + bh - 1, 2, 2), qc(PALE))
        p.setCompositionMode(PLUS)
        for k, ph in ((0, 0.0), (1, 2.0)):
            bx = x + 40 + k * 30
            ang = math.sin(t * 0.6 + ph) * 0.35
            ln = 140
            tx, ty = bx + math.sin(ang) * ln, y + bh + math.cos(ang) * ln
            g = QLinearGradient(bx, y + bh, tx, ty)
            g.setColorAt(0, QColor(110, 110, 140, 60))
            g.setColorAt(1, QColor(0, 0, 0, 0))
            p.setBrush(QBrush(g))
            p.drawPolygon(QPolygonF([QPointF(bx - 1, y + bh), QPointF(tx - 16, ty), QPointF(tx + 16, ty),
                                     QPointF(bx + 1, y + bh)]))
        p.setCompositionMode(OVER)

    def _mid_life(self, p, e, cam, t):
        city = self.city
        mid = city.mid
        self._blinks(p, e, cam, t, "mid", mid)
        for i, bb in enumerate(city.billboards):
            L, y, w, h, seed = bb
            x = mid.screen_x(L, cam)
            if x < -w or x > W:
                continue
            frames = self.bb_frames[i]
            k = int(t * 0.5 + seed) % len(frames)
            if frames and len(frames) == 4 and _hash(int(t * 3), seed) < 0.15:
                k = 3
            img = frames[k]
            glitch = _hash(int(t * 8), seed + 1) < 0.08
            for q, op in ((p, 0.92), (e, 0.6)):
                q.setOpacity(op)
                if glitch:
                    for row in range(0, h, 4):
                        off = int((_hash(row + int(t * 30), seed) - 0.5) * 6)
                        q.drawImage(QRectF(int(x) + off, y + row, w, 4), img, QRectF(0, row, w, 4))
                else:
                    q.drawImage(int(x), y, img)
                q.setOpacity(1.0)

    def _spinners(self, p, e, dt, t, near):
        if near is None:   # ferne Spinner hinter der Skyline
            sel = [s for s in self.spinners if not s["near"] and s["s"] < 0.6]
        elif near:
            sel = [s for s in self.spinners if s["near"]]
        else:
            sel = [s for s in self.spinners if not s["near"] and s["s"] >= 0.6]
        if dt > 0 and near is True:
            for s in self.spinners:
                s["x"] += s["vx"] * dt
                if s["x"] < -80 or s["x"] > W + 80:
                    self.spinners.remove(s)
                    self._spawn_spinner(self.rng)
                    break
        for s in sel:
            sc = s["s"]
            x, y = s["x"], s["y"] + math.sin(t * 1.3 + s["bob"]) * 1.5 * sc
            d = 1 if s["vx"] > 0 else -1
            self._spinner_body(p, e, x, y, sc, d, t + s["ph"], near, s["police"])

    def _spinner_body(self, p, e, x, y, sc, d, t, near, police):
        bw, bh = 22 * sc, 6 * sc
        body = QPolygonF([QPointF(x - bw / 2 * d, y), QPointF(x - bw * 0.3 * d, y - bh * 0.9),
                          QPointF(x + bw * 0.25 * d, y - bh), QPointF(x + bw / 2 * d, y - bh * 0.2),
                          QPointF(x + bw * 0.45 * d, y + bh * 0.4), QPointF(x - bw * 0.45 * d, y + bh * 0.4)])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc((18, 20, 30) if not near else (30, 32, 46)))
        p.drawPolygon(body)
        if near:
            # Kantenlicht oben + Unterboden-Leuchtstreifen
            p.fillRect(QRectF(x - bw * 0.3, y - bh * 0.95, bw * 0.55, 1), qc((70, 76, 100)))
            for q in (p, e):
                q.fillRect(QRectF(x - bw * 0.35, y + bh * 0.35, bw * 0.7, 1), qc(CYAN if not police else PALE))
        p.fillRect(QRectF(x - bw * 0.15 * d - (bw * 0.25 if d < 0 else 0), y - bh * 0.75, bw * 0.25, bh * 0.3),
                   qc((120, 150, 190)))
        # Scheinwerfer + Kegel
        hx = x + bw / 2 * d
        for q in (p, e):
            q.fillRect(QRectF(hx - 1, y - 1, 2, 2), qc(PALE))
        p.setCompositionMode(PLUS)
        g = QLinearGradient(hx, y, hx + 60 * sc * d, y + 20 * sc)
        g.setColorAt(0, QColor(120, 120, 140, 70))
        g.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(g))
        p.drawPolygon(QPolygonF([QPointF(hx, y - 1), QPointF(hx + 60 * sc * d, y + 6 * sc),
                                 QPointF(hx + 54 * sc * d, y + 26 * sc), QPointF(hx, y + 1)]))
        p.setCompositionMode(OVER)
        if police:
            c = MAGENTA if int(t * 6) % 2 == 0 else (90, 140, 255)
            for q in (p, e):
                q.fillRect(QRectF(x - 1, y - bh - 1, 3, 2), qc(c))
        elif int(t * 1.5) % 2 == 0:
            for q in (p, e):
                q.fillRect(QRectF(x - bw / 2 * d - 1, y - 1, 2, 1), qc(CRIMSON))

    def _fog_band(self, p):
        """Dunst über der Skyline: die Ferne versinkt stärker im Nebel als die Front."""
        th = self.city.th
        fy = persp.FACADE_Y
        fd = getattr(self, "_fog_d", th["fog_amt"])
        fc = mix(th["fog"], th["sky_hor"], 0.5)
        g = QLinearGradient(0, fy - 150, 0, fy + 6)
        g.setColorAt(0.0, QColor(*fc, 0))
        g.setColorAt(0.55, QColor(*fc, int(255 * min(1.0, fd * 0.3))))
        g.setColorAt(1.0, QColor(*fc, int(255 * min(1.0, fd * 0.75))))
        p.fillRect(QRectF(0, fy - 150, W, 157), QBrush(g))

    def _ramen(self, p, world, cam, t, dt):
        """Warmes Licht und Dampf an den Nudelständen (verbraucht = gedimmt)."""
        spots = getattr(world, "ramen", ())
        if not spots:
            return
        rng = self.rng
        p.setCompositionMode(PLUS)
        p.setPen(Qt.PenStyle.NoPen)
        for r in spots:
            sx = persp.screen_x(r["x"], 0.16, cam)
            if sx < -120 or sx > W + 120:
                continue
            gy = persp.ground_y(0.16)
            lv = 0.3 if r["used"] else 1.0
            g = QRadialGradient(sx, gy, 72)
            g.setColorAt(0.0, QColor(255, 150, 60, int(95 * lv)))
            g.setColorAt(0.5, QColor(255, 120, 40, int(35 * lv)))
            g.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.save()
            p.translate(sx, gy)
            p.scale(1.0, 0.3)
            p.translate(-sx, -gy)
            p.fillRect(QRectF(sx - 72, gy - 72, 144, 144), QBrush(g))
            p.restore()
            if not r["used"] and rng.random() < dt * 3.0:
                self.fx.puff(rng.uniform(-10, 10), gy - 30, wx=r["x"], depth=0.16, scale=1.3)
        p.setCompositionMode(OVER)

    def _new_wisp(self, rng, initial=False):
        x = rng.uniform(0, W) if initial else rng.choice((-170.0, W + 170.0))
        return dict(x=x, y=rng.uniform(persp.FACADE_Y - 30, H - 16),
                    vx=rng.uniform(6, 15) * (1 if x < W * 0.5 else -1), vy=rng.uniform(-1.4, 1.4),
                    s=rng.uniform(320, 900), a=rng.uniform(0.18, 0.44), t=0.0, life=rng.uniform(12, 26))

    def _wisps(self, p, dt, cam):
        """Große, weiche Nebelschwaden ziehen durchs Vordergrundbild und lassen die Sicht
        stellenweise verschwimmen. Dichte folgt der Wetterlage (_fog_d)."""
        rng = self.rng
        if not self.wisps:
            self.wisps = [self._new_wisp(rng, initial=True) for _ in range(9)]
        for w in self.wisps:
            w["t"] += dt
            w["x"] += w["vx"] * dt
            w["y"] += w["vy"] * dt
            if w["t"] > w["life"] or w["x"] < -260 or w["x"] > W + 260:
                w.clear()
                w.update(self._new_wisp(rng))
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        tex = self.city.cloud
        boost = 0.7 + 1.0 * getattr(self, "_fog_d", 0.6)
        for w in self.wisps:
            fade = math.sin(min(1.0, w["t"] / w["life"]) * math.pi)
            a = w["a"] * fade * boost
            if a <= 0.006:
                continue
            p.setOpacity(min(0.5, a))
            sw, sh = w["s"], w["s"] * 0.66
            p.drawImage(QRectF(w["x"] - sw / 2, w["y"] - sh / 2, sw, sh), tex)
        p.setOpacity(1.0)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)

    # ------------------------------------------------------------------ Häuserfront
    def _facade_life(self, p, e, cam, t, dt):
        city = self.city
        fac = city.facade
        rng = self.rng
        # Neon-Schilder (+ Lichthof im Dunst); bei Stromausfall nur Notstrom-Schilder
        halos = []
        L0 = cam * fac.factor - W * 0.5 - 140
        L1 = cam * fac.factor + W * 0.5 + 40
        for s in city.visible(city.signs, city._sign_x, L0, L1):
            x = fac.screen_x(s.L, cam)
            if x < -s.w - 30 or x > W + 30:
                continue
            lv = s.lit(t)
            if self.dark > 0.4 and s.seed % 4 != 0:
                lv = 0.0
            if lv > 0:
                p.drawImage(int(x), s.y, s.on)
                e.drawImage(int(x), s.y, s.emit)
                halos.append((x + s.w / 2, s.y + s.h / 2, max(s.w, s.h) * 0.9 + 10, s.color))
            else:
                p.drawImage(int(x), s.y, s.off)
        if halos:
            p.setCompositionMode(PLUS)
            for (hx, hy, r, c) in halos:
                g = QRadialGradient(hx, hy, r)
                g.setColorAt(0, QColor(c[0], c[1], c[2], 46))
                g.setColorAt(0.5, QColor(c[0], c[1], c[2], 16))
                g.setColorAt(1, QColor(0, 0, 0, 0))
                p.fillRect(QRectF(hx - r, hy - r, 2 * r, 2 * r), QBrush(g))
            p.setCompositionMode(OVER)
        # Fernseher-Fenster
        for (wx, wy, ww, wh, seed) in city.visible(city.tvs, city._tv_x, L0 - fac.lmin, L1 - fac.lmin):
            x = fac.screen_x(wx + fac.lmin, cam)
            if x < -10 or x > W + 10:
                continue
            if self.dark > 0.4:
                p.fillRect(QRectF(int(x), wy, ww, wh), qc((8, 10, 18)))
                continue
            n = _hash(int(t * 6), seed)
            c = mix((40, 60, 140), (150, 190, 255), n)
            if seed % 5 == 0:
                c = mix(MAGENTA, PALE, n * 0.6)
            for q in (p, e):
                q.fillRect(QRectF(int(x), wy, ww, wh), qc(c))
        # Lampions
        for (L, y, c, ph) in city.visible(city.lanterns, city._lan_x, L0, L1):
            x = fac.screen_x(L, cam) + math.sin(t * 1.7 + ph) * 0.8
            if x < -4 or x > W + 4:
                continue
            for q in (p, e):
                q.setPen(Qt.PenStyle.NoPen)
                q.setBrush(qc(c))
                q.drawEllipse(QRectF(int(x) - 2, y, 4, 5))
            p.fillRect(QRectF(int(x) - 1, y + 2, 2, 1), qc(mix(c, WHITE, 0.6)))
        self._blinks(p, e, cam, t, "fac", fac)
        # Dampf aus Lüftungen
        for (L, y) in city.vents:
            x = fac.screen_x(L, cam)
            if -20 < x < W + 20 and rng.random() < dt * 1.3:
                self.fx.puff(L, y, scale=0.8)
        for (mx, md) in city.manholes:
            sx = persp.screen_x(mx, md, cam)
            if -20 < sx < W + 20 and rng.random() < dt * 2.2:
                self.fx.puff(rng.uniform(-6, 6), persp.ground_y(md) - 1, wx=mx, depth=md, scale=1.2)
        # Ausgangstor
        g = getattr(city, "gate", None)
        if g:
            x = fac.screen_x(g["L"], cam)
            if -130 < x < W + 10:
                self._gate(p, e, x, g, t)

    def _gate(self, p, e, x, g, t):
        open_ = self._gate_open
        col = (90, 230, 140) if open_ else CRIMSON
        txt = g["label"]
        tw = pixfont.text_width(txt, 1)
        bx = int(x + g["w"] / 2 - tw / 2 - 5)
        p.fillRect(QRectF(bx, g["y"], tw + 10, 13), qc(VOID))
        for q in (p, e):
            pixfont.draw(q, bx + 5, g["y"] + 3, txt, col, 1, None)
            pen = QPen(qc(col))
            q.setPen(pen)
            q.drawRect(QRectF(bx, g["y"], tw + 9, 12))
        dx, dy, dw, dh = g["door"]
        X = int(x + (dx - g["L"]))
        if open_:
            gr = QLinearGradient(0, dy, 0, dy + dh)
            gr.setColorAt(0, QColor(40, 120, 90))
            gr.setColorAt(1, QColor(200, 255, 220))
            for q in (p, e):
                q.fillRect(QRectF(X, dy, dw, dh), QBrush(gr))
        else:
            blink = int(t * 2) % 2 == 0
            for q in (p, e):
                if blink:
                    q.fillRect(QRectF(X, dy - 3, dw, 2), qc(CRIMSON))

    # ------------------------------------------------------------------ Straße
    def _street(self, p, e, cam, t):
        city = self.city
        th = city.th
        fy = int(persp.FACADE_Y)
        p.fillRect(0, fy, W, H - fy, qc(th["street"]))
        city.draw_ground(p, cam)
        # Reflexionen liegen AUF dem nassen Asphalt (die Oberfläche spiegelt, nicht
        # der Untergrund): erst der Baukörper normal, dann die Neon-Leuchten additiv.
        fac = city.facade
        x0 = fac.lmin - cam * fac.factor + W * 0.5
        band = 12
        k = getattr(self, "_reflk", 1.0) * (1.0 - 0.8 * self.dark)
        for refl, mode, op in ((city.facade_refl_body, OVER, min(1.0, 0.8 * k)),
                               (city.facade_refl, PLUS, min(1.0, 0.95 * k))):
            p.setCompositionMode(mode)
            p.setOpacity(op)
            for kb in range(0, min(refl.height(), H - fy), band):
                off = math.sin(t * 2.3 + kb * 0.37) * 1.2
                p.drawImage(QRectF(0, fy + kb, W, band), refl, QRectF(-x0 - off, kb, W, band))
            p.setOpacity(1.0)
        p.setCompositionMode(OVER)
        # In Pfützen ist die Fahrbahn noch nasser -> Reflexion dort klar verstärkt.
        reg = QRegion()
        vis = []
        for (wx, pd, rw, rh) in city.puddles:
            sx = persp.screen_x(wx, pd, cam)
            if sx < -80 or sx > W + 80:
                continue
            y = persp.ground_y(pd)
            rx = max(3.0, rw * persp.ppu(pd))
            ry = max(5.0, rh * 3.2)
            vis.append((sx, y, rx, ry))
            reg = reg.united(QRegion(QRectF(sx - rx, y - ry, 2 * rx, 2 * ry).toRect(),
                                     QRegion.RegionType.Ellipse))
        if not reg.isEmpty():
            p.save()
            p.setClipRegion(reg)
            for refl, mode, op in ((city.facade_refl_body, OVER, min(1.0, 0.95 * k)),
                                   (city.facade_refl, PLUS, min(1.0, 1.0 * k))):
                p.setCompositionMode(mode)
                p.setOpacity(op)
                for kb in range(0, min(refl.height(), H - fy), band):
                    off = math.sin(t * 2.3 + kb * 0.37) * 1.2
                    p.drawImage(QRectF(0, fy + kb, W, band), refl, QRectF(-x0 - off, kb, W, band))
                p.setOpacity(1.0)
            p.restore()
            p.setCompositionMode(OVER)
        # Pfützen-Glanz: heller Schimmer, damit die nassen Stellen als Pfützen erkennbar sind
        p.setCompositionMode(PLUS)
        p.setPen(Qt.PenStyle.NoPen)
        for (sx, y, rx, ry) in vis:
            g = QRadialGradient(sx, y, max(rx, 8))
            g.setColorAt(0.0, QColor(120, 150, 195, int(52 * k)))
            g.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.save()
            p.translate(sx, y)
            p.scale(1.0, max(0.22, ry / max(rx, 8)))
            p.translate(-sx, -y)
            p.fillRect(QRectF(sx - rx, y - rx, 2 * rx, 2 * rx), QBrush(g))
            p.restore()
        p.setCompositionMode(OVER)
        # Neon-Spiegelung (live, mit Flackern) - ebenfalls weich
        p.setCompositionMode(PLUS)
        L0 = cam * fac.factor - W * 0.5 - 140
        for s in city.visible(city.signs, city._sign_x, L0, L0 + W + 180):
            x = fac.screen_x(s.L, cam)
            if x < -s.w or x > W or s.lit(t) <= 0 or (self.dark > 0.4 and s.seed % 4 != 0):
                continue
            ry = fy + (fy - s.y - s.h)
            if ry > H:
                continue
            r = self._refl.get(("sign", id(s)))
            if r is None:
                r = self._refl[("sign", id(s))] = soft_reflection(s.emit)
            p.setOpacity(min(1.0, 0.48 * k))
            p.drawImage(QRectF(int(x), ry, s.w, s.h * 1.9), r)
        p.setOpacity(1.0)
        p.setCompositionMode(OVER)
        # Asphalt-Körnung noch einmal mit reduzierter Deckkraft darüber: die Reflexion
        # sinkt in die Textur, die Straße bleibt als Straße lesbar (kein voller Spiegel).
        p.setOpacity(0.42)
        city.draw_ground(p, cam)
        p.setOpacity(1.0)
        # Laternen: Kopf, Kegel, Lichtpfütze
        p.setCompositionMode(PLUS)
        for lamp in city.lamps:
            x = fac.screen_x(lamp.L, cam)
            if x < -120 or x > W + 120:
                continue
            lv = lamp.level(t) * (1.0 - self.dark)
            if lv <= 0.01:
                continue
            hx = x + lamp.arm
            hy = lamp.y + 4
            c = lamp.color
            px = persp.screen_x(lamp.x + lamp.arm / fac.factor, 0.25, cam)
            gy = persp.ground_y(0.25)
            g = QLinearGradient(hx, hy, hx, gy)
            g.setColorAt(0, QColor(c[0], c[1], c[2], int(34 * lv)))
            g.setColorAt(1, QColor(c[0], c[1], c[2], 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(g))
            p.drawPolygon(QPolygonF([QPointF(hx - 2, hy), QPointF(hx + 2, hy), QPointF(px + 30, gy),
                                     QPointF(px - 30, gy)]))
            rg = QRadialGradient(px, gy, 60)
            rg.setColorAt(0, QColor(c[0], c[1], c[2], int(95 * lv)))
            rg.setColorAt(0.5, QColor(c[0], c[1], c[2], int(30 * lv)))
            rg.setColorAt(1, QColor(0, 0, 0, 0))
            p.save()
            p.translate(px, gy)
            p.scale(1.0, 0.32)
            p.translate(-px, -gy)
            p.fillRect(QRectF(px - 60, gy - 60, 120, 120), QBrush(rg))
            p.restore()
        p.setCompositionMode(OVER)
        for lamp in city.lamps:
            x = fac.screen_x(lamp.L, cam)
            if x < -20 or x > W + 20:
                continue
            lv = lamp.level(t) * (1.0 - self.dark)
            c = lamp.color if lv > 0.5 else mul(lamp.color, 0.3)
            for q in ((p, e) if lv > 0.5 else (p,)):
                q.fillRect(QRectF(int(x + lamp.arm) - 2, lamp.y + 3, 5, 2), qc(c))
        # Suchscheinwerfer: die nasse Fahrbahn wirft unter jedem Leuchtkörper einen weichen
        # Lichtschleier zurück (kein harter Strahl - nur diffuser Schimmer).
        tint = mix((170, 180, 220), th["sky_hor"], 0.25)
        p.setCompositionMode(PLUS)
        p.setPen(Qt.PenStyle.NoPen)
        for (L, y, sp, ph) in city.searchlights:
            x = city.mid.screen_x(L, cam)
            if x < -80 or x > W + 80:
                continue
            warm = 0.4 + 0.6 * abs(math.sin(t * sp + ph))
            g = QLinearGradient(0, fy, 0, fy + 120)
            g.setColorAt(0, QColor(tint[0], tint[1], tint[2], int(34 * warm * (1 - self.dark))))
            g.setColorAt(0.4, QColor(tint[0], tint[1], tint[2], int(14 * warm * (1 - self.dark))))
            g.setColorAt(1, QColor(0, 0, 0, 0))
            p.setBrush(QBrush(g))
            p.drawPolygon(QPolygonF([QPointF(x - 2, fy), QPointF(x + 2, fy),
                                     QPointF(x + 10, fy + 120), QPointF(x - 10, fy + 120)]))
        p.setCompositionMode(OVER)
        self.fx.draw_splashes(p, mix(city.th["fog"], PALE, 0.5))

    # ------------------------------------------------------------------ Figuren
    def _rim_for(self, a, cam):
        best, bd = None, 110.0
        for lamp in self.city.lamps:
            d = abs(lamp.x - a.x)
            if d < bd:
                best, bd = lamp, d
        if best is not None:
            side = 1 if best.x + 6 >= a.x else -1
            return best.color, side
        return self.city.th["rim"], 1

    def _mirror(self, img):
        """Wet-Street-Reflexion (progressiv scharf->weich, city.soft_reflection).
        Einmal pro Sprite gerechnet und gecacht - Rendern kostet nur ein drawImage."""
        key = img.cacheKey()
        r = self._refl.get(key)
        if r is None:
            if len(self._refl) > 6000:
                self._refl.clear()
            r = self._refl[key] = soft_reflection(img)
        return r

    def _actors(self, p, e, world, cam, t, show_player):
        """Figuren, Fahrzeuge und Hindernisse gemeinsam nach Tiefe sortiert."""
        self.screen = {}
        items = [(a.depth if a.alive else a.depth - 0.002, 0, a) for a in world.actors
                 if not a.escaped and (show_player or not a.player)]
        items += [(v["depth"] - 0.001, 1, v) for v in getattr(world, "vehicles", ())]
        items += [(o["d"] + o["dd"] * 0.5, 2, o) for o in getattr(world, "obstacles", ())]
        items.sort(key=lambda it: it[0])
        patrol = getattr(world, "patrol", None)
        for _d, kind, obj in items:
            if kind == 0:
                lit = patrol is not None and patrol["on"] > 0.3 and world.in_beam(obj)
                self._draw_actor(p, e, obj, cam, t, lit)
            elif kind == 1:
                self._draw_vehicle(p, e, obj, cam, t)
            else:
                self._draw_obstacle(p, e, obj, cam, t)

    def _draw_actor(self, p, e, a, cam, t, lit=False):
        th = self.city.th
        fog_rgb = th["fog"]
        cx = persp.screen_x(a.x, a.depth, cam)
        hgt = persp.figure_h(a.depth) * a.look.get("hf", 1.0)
        if cx < -hgt * 1.4 or cx > W + hgt * 1.4:
            return
        gy = persp.ground_y(a.depth)
        lift = int(round(a.z * persp.ppu(a.depth)))
        fog = th["fog_amt"] * 0.85 * (1 - a.depth) ** 1.6
        rim, side = self._rim_for(a, cam)
        if a.player:
            rim, fog = CYAN, 0.0
        if not a.alive:
            # Liegende Körper: kein Nebel, kühles Oberlicht -> heben sich vom nassen Asphalt ab
            rim, fog, side = (200, 210, 232), 0.0, 1
        if lit:
            rim, fog = WHITE, 0.0
        outline = (4, 5, 10)
        if not a.alive and a.dead_t > 0.5:
            # „Kreide“-Umriss: liegende Körper bleiben auf dem nassen Asphalt lesbar
            outline = (150, 40, 64) if not a.is_replicant else (120, 170, 190)
        img, em, ax, ay, meta = sprites.get(a.look, a.anim, getattr(a, "frame", 0), hgt, a.facing,
                                            rim=rim, rim_side=side * a.facing, fog_rgb=fog_rgb, fog=fog,
                                            outline=outline)
        x0, y0 = int(cx) - ax, int(gy) - ay - lift
        if not a.alive:
            # Lache: Menschen dunkelrot, Replikanten milchig-weiß
            k = min(1.0, a.dead_t / 2.5)
            if k > 0.05:
                rw = hgt * (0.3 + 0.6 * k)
                px_ = cx + meta["head"][0] * 0.55 - rw / 2
                c, hl = ((150, 24, 50), (220, 70, 96)) if not a.is_replicant else ((176, 192, 206), (240, 248, 255))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(qc(c, 225))
                p.drawEllipse(QRectF(px_, gy - rw * 0.08, rw, rw * 0.2))
                p.fillRect(QRectF(int(px_ + rw * 0.3), int(gy - rw * 0.04), max(1, int(rw * 0.3)), 1), qc(hl))
            p.drawImage(x0, y0, img)
            p.setCompositionMode(PLUS)
            p.setOpacity(0.22)
            p.drawImage(x0, y0, img)
            p.setOpacity(1.0)
            p.setCompositionMode(OVER)
            if em is not None:
                e.drawImage(x0, y0, em)
            self.screen[a.uid] = (cx, gy, hgt, meta)
            return
        # Schatten (bleibt am Boden, schrumpft beim Sprung)
        sw = hgt * 0.42 * max(0.45, 1.0 - a.z / 40.0)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 110))
        p.drawEllipse(QRectF(cx - sw / 2, gy - sw * 0.07, sw, sw * 0.16))
        # Spiegelbild im nassen Asphalt
        p.setOpacity(min(1.0, 0.46 * getattr(self, "_reflk", 1.0)))
        p.drawImage(x0, int(gy) + lift - (img.height() - 1 - ay), self._mirror(img))
        p.setOpacity(1.0)
        if a.player:
            rw = hgt * 0.5
            for q, al in ((p, 120), (e, 90)):
                pen = QPen(QColor(64, 210, 220, al))
                pen.setWidth(1)
                q.setPen(pen)
                q.setBrush(Qt.BrushStyle.NoBrush)
                q.drawEllipse(QRectF(cx - rw / 2, gy - rw * 0.1, rw, rw * 0.2))
        p.drawImage(x0, y0, img)
        if em is not None:
            e.drawImage(x0, y0, em)
        if lit:
            p.setCompositionMode(PLUS)
            p.setOpacity(0.28)
            p.drawImage(x0, y0, img)
            p.setOpacity(1.0)
            p.setCompositionMode(OVER)
        if a.flash_t > 0:
            p.setCompositionMode(PLUS)
            p.setOpacity(min(1.0, a.flash_t * 4))
            p.drawImage(x0, y0, img)
            p.drawImage(x0, y0, img)
            p.setOpacity(1.0)
            p.setCompositionMode(OVER)
        if a.player and a.invuln > 0 and int(t * 16) % 2 == 0:
            p.setOpacity(0.5)
            p.drawImage(x0, y0, img)
            p.setOpacity(1.0)
        if a.glint_t > 0 and self.dark <= 0:
            ex, ey = meta["eye"]
            gx, gy2 = int(cx + ex), int(gy + ey) - lift
            for q in (p, e):
                q.fillRect(QRectF(gx, gy2, 2, 1), qc(AMBER))
                q.fillRect(QRectF(gx, gy2, 1, 1), qc((255, 230, 180)))
        self.screen[a.uid] = (cx, gy - lift, hgt, meta)

    def _glints(self, p, e, world, cam, boost=False):
        """Augenreflexe über dem Stromausfall-Schleier: die Replikantenaugen glühen."""
        for a in world.actors:
            if a.player or not a.alive or a.escaped or a.glint_t <= 0:
                continue
            sc = self.screen.get(a.uid)
            if sc is None:
                continue
            cx, gy, hgt, meta = sc
            ex, ey = meta["eye"]
            gx, gy2 = int(cx + ex), int(gy + ey)
            p.fillRect(QRectF(gx - 1, gy2, 3, 1), qc(AMBER))
            p.fillRect(QRectF(gx, gy2, 1, 1), qc(WHITE))
            e.fillRect(QRectF(gx - 2, gy2 - 1, 5, 3), qc(AMBER))

    def _flashlight(self, p, e, world, cam):
        """Taschenlampe des Blade Runners im Stromausfall."""
        pl = world.player
        sc = self.screen.get(pl.uid)
        if sc is None or not pl.alive:
            return
        cx, gy, hgt, meta = sc
        d = pl.facing
        hx, hy = cx + d * hgt * 0.12, gy - hgt * 0.55
        ln = 170 * self.dark
        tx = hx + d * ln
        p.setCompositionMode(PLUS)
        g = QLinearGradient(hx, hy, tx, hy)
        g.setColorAt(0, QColor(150, 200, 210, 120))
        g.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawPolygon(QPolygonF([QPointF(hx, hy - 1), QPointF(tx, hy - hgt * 0.7), QPointF(tx, gy + hgt * 0.15),
                                 QPointF(hx, hy + 1)]))
        p.setCompositionMode(OVER)

    def _draw_vehicle(self, p, e, v, cam, t):
        d = v["depth"]
        k = persp.ppu(d)
        cx = persp.screen_x(v["x"], d, cam)
        if cx < -v["L"] * k or cx > W + v["L"] * k:
            return
        gy = persp.ground_y(d)
        img, em, ax, ay, _lpx = vehicles.vehicle_image(v["kind"], v["seed"], k, self.city.th["rim"], v["dir"])
        x0, y0 = int(cx) - ax, int(gy) - ay
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 130))
        p.drawEllipse(QRectF(cx - v["L"] * k * 0.55, gy - 3 * k, v["L"] * k * 1.1, 5 * k))
        p.setOpacity(min(1.0, 0.5 * getattr(self, "_reflk", 1.0)))
        p.drawImage(x0, int(gy) - (img.height() - 1 - ay), self._mirror(img))
        p.setOpacity(1.0)
        p.drawImage(x0, y0, img)
        e.drawImage(x0, y0, em)
        if v["kind"] == "police":
            on = int(t * 7 + v["seed"]) % 2 == 0
            c = MAGENTA if on else (90, 140, 255)
            k = k * vehicles.VEH_SCALE
            top = gy - 17.5 * k
            for q in (p, e):
                q.fillRect(QRectF(cx - 6 * k + (0 if on else 6 * k), top, 6 * k, 2 * k), qc(c))

    def _vehicle_lights(self, p, e, world, cam, t):
        """Scheinwerferkegel und Lichtflecken auf der nassen Fahrbahn (additiv)."""
        vs = getattr(world, "vehicles", ())
        if not vs:
            return
        p.setCompositionMode(PLUS)
        for v in vs:
            d = v["depth"]
            k = persp.ppu(d)
            cx = persp.screen_x(v["x"], d, cam)
            if cx < -300 or cx > W + 300:
                continue
            gy = persp.ground_y(d)
            dr = v["dir"]
            fx_ = cx + dr * v["L"] * 0.5 * k
            hy = gy - (11 if v["kind"] == "truck" else 8.5) * k * vehicles.VEH_SCALE
            vehicles.headlight(p, fx_, hy, dr, k, gy, length=120.0, a=80)
            rg = QRadialGradient(fx_ + dr * 50 * k, gy, 60 * k)
            rg.setColorAt(0, QColor(255, 240, 210, 70))
            rg.setColorAt(1, QColor(0, 0, 0, 0))
            p.save()
            p.translate(fx_ + dr * 50 * k, gy)
            p.scale(1.0, 0.25)
            p.translate(-(fx_ + dr * 50 * k), -gy)
            p.fillRect(QRectF(fx_ + dr * 50 * k - 60 * k, gy - 60 * k, 120 * k, 120 * k), QBrush(rg))
            p.restore()
            # Rücklicht-Schimmer
            bx = cx - dr * v["L"] * 0.5 * k
            rg = QRadialGradient(bx, gy - 7 * k, 16 * k)
            rg.setColorAt(0, QColor(240, 40, 70, 70))
            rg.setColorAt(1, QColor(0, 0, 0, 0))
            p.fillRect(QRectF(bx - 16 * k, gy - 23 * k, 32 * k, 32 * k), QBrush(rg))
        p.setCompositionMode(OVER)

    def _draw_obstacle(self, p, e, o, cam, t):
        d = o["d"]
        k = persp.ppu(d)
        cx = persp.screen_x(o["x"], d, cam)
        if cx < -60 or cx > W + 60:
            return
        gy = persp.ground_y(d)
        img, em, ax, ay = vehicles.obstacle_image(o["kind"], o["seed"], k, self.city.th["rim"])
        x0, y0 = int(cx) - ax, int(gy) - ay
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 120))
        p.drawEllipse(QRectF(cx - o["w"] * k * 1.1, gy - 2 * k, o["w"] * k * 2.2, 4 * k))
        p.setOpacity(min(1.0, 0.46 * getattr(self, "_reflk", 1.0)))
        p.drawImage(x0, int(gy) - (img.height() - 1 - ay), self._mirror(img))
        p.setOpacity(1.0)
        p.drawImage(x0, y0, img)
        e.drawImage(x0, y0, em)
        kind = o["kind"]
        light = None
        if kind == "barrier" and int(t * 2.5 + o["seed"]) % 2 == 0:
            for q in (p, e):
                q.fillRect(QRectF(cx - 1 * k, gy - 12 * k, 2 * k + 1, 2 * k + 1), qc(AMBER))
            light = (AMBER, 30, 40)
        elif kind == "barrel":
            for i in range(3):
                n = _hash(int(t * 14) + i * 7, o["seed"])
                fh = (5 + 6 * n) * k
                bx = cx + (i - 1) * 2.2 * k
                poly = QPolygonF([QPointF(bx - 1.6 * k, gy - 9 * k), QPointF(bx + (n - 0.5) * 2 * k, gy - 9 * k - fh),
                                  QPointF(bx + 1.6 * k, gy - 9 * k)])
                for q in (p, e):
                    q.setPen(Qt.PenStyle.NoPen)
                    q.setBrush(qc(AMBER if i != 1 else (255, 220, 150)))
                    q.drawPolygon(poly)
            light = (AMBER, 70 + int(25 * _hash(int(t * 9), o["seed"])), 70)
            if self.rng.random() < 0.05:
                self.fx.puff(0, gy - 16 * k, wx=o["x"], depth=d, scale=0.6)
        elif kind == "vending":
            light = ((150, 200, 255), 45, 50)
        if light is not None:
            c, a, r = light
            r *= k
            p.setCompositionMode(PLUS)
            rg = QRadialGradient(cx, gy, r)
            rg.setColorAt(0, QColor(c[0], c[1], c[2], a))
            rg.setColorAt(1, QColor(0, 0, 0, 0))
            p.save()
            p.translate(cx, gy)
            p.scale(1.0, 0.35)
            p.translate(-cx, -gy)
            p.fillRect(QRectF(cx - r, gy - r, 2 * r, 2 * r), QBrush(rg))
            p.restore()
            if kind == "barrel":
                rg = QRadialGradient(cx, gy - 14 * k, r * 0.7)
                rg.setColorAt(0, QColor(c[0], c[1], c[2], a // 2))
                rg.setColorAt(1, QColor(0, 0, 0, 0))
                p.fillRect(QRectF(cx - r, gy - 14 * k - r, 2 * r, 2 * r), QBrush(rg))
            p.setCompositionMode(OVER)

    # ------------------------------------------------------------------ Polizei-Suchlicht
    def _patrol_geom(self, world, cam, t):
        P = getattr(world, "patrol", None)
        if P is None:
            return None
        sx = persp.screen_x(P["x"], 0.35, cam)
        sy = 46 + math.sin(t * 1.4) * 2.0
        bx = persp.screen_x(P["bx"], P["bd"], cam)
        by = persp.ground_y(P["bd"])
        rx = 34 * persp.ppu(P["bd"])
        ry = 0.13 * (persp.ground_y(1) - persp.ground_y(0))
        return P, sx, sy, bx, by, rx, ry

    def _patrol(self, p, e, world, cam, t):
        g = self._patrol_geom(world, cam, t)
        self._beam_poly = None
        if g is None:
            return
        P, sx, sy, bx, by, rx, ry = g
        on = P["on"]
        if on > 0.02:
            poly = QPolygonF([QPointF(sx - 2, sy + 4), QPointF(bx - rx, by), QPointF(bx + rx, by), QPointF(sx + 2, sy + 4)])
            self._beam_poly = (poly, on)
            p.setCompositionMode(PLUS)
            p.setPen(Qt.PenStyle.NoPen)
            for wf, a in ((1.0, 34), (0.55, 40)):
                pl = QPolygonF([QPointF(sx - 2, sy + 4), QPointF(bx - rx * wf, by), QPointF(bx + rx * wf, by),
                                QPointF(sx + 2, sy + 4)])
                gr = QLinearGradient(sx, sy, bx, by)
                gr.setColorAt(0, QColor(210, 225, 255, int(a * 2.2 * on)))
                gr.setColorAt(1, QColor(210, 225, 255, int(a * on)))
                p.setBrush(QBrush(gr))
                p.drawPolygon(pl)
            rg = QRadialGradient(bx, by, rx)
            rg.setColorAt(0, QColor(230, 240, 255, int(120 * on)))
            rg.setColorAt(0.7, QColor(200, 220, 255, int(50 * on)))
            rg.setColorAt(1, QColor(0, 0, 0, 0))
            p.save()
            p.translate(bx, by)
            p.scale(1.0, ry / rx)
            p.translate(-bx, -by)
            p.fillRect(QRectF(bx - rx, by - rx, 2 * rx, 2 * rx), QBrush(rg))
            p.restore()
            p.setCompositionMode(OVER)
        # Der Spinner selbst
        d = P["dir"] if P.get("leaving") else (1 if (P["bx"] - P["x"]) >= 0 else -1)
        self._spinner_body(p, e, sx, sy, 2.4, d, t, True, True)
        # Scheinwerfer-Gondel unter dem Rumpf
        for q in (p, e):
            q.fillRect(QRectF(sx - 2, sy + 3, 4, 2), qc(WHITE))

    def _beam_rain(self, p):
        """Regentropfen im Suchlicht hell nachzeichnen (wie im Film)."""
        bp = getattr(self, "_beam_poly", None)
        if not bp:
            return
        poly, on = bp
        p.save()
        p.setClipRegion(QRegion(poly.toPolygon()))
        p.setCompositionMode(PLUS)
        self.fx.draw_rain(p, (int(200 * on), int(210 * on), int(240 * on)))
        p.restore()

    # ------------------------------------------------------------------ Kampf-Overlays
    def _hand(self, world):
        p = world.player
        sc = self.screen.get(p.uid)
        if sc is None:
            cx = persp.screen_x(p.x, p.depth, world.camera_x)
            gy = persp.ground_y(p.depth)
            return cx, gy - persp.figure_h(p.depth) * 0.62
        cx, gy, hgt, meta = sc
        hx, hy = meta["hand"]
        return cx + hx + p.facing * 2, gy + hy

    def _chest(self, a, cam):
        sc = self.screen.get(a.uid)
        if sc is not None:
            cx, gy, hgt, _m = sc
            return cx, gy - hgt * 0.62, hgt
        cx = persp.screen_x(a.x, a.depth, cam)
        hgt = persp.figure_h(a.depth)
        return cx, persp.ground_y(a.depth) - hgt * 0.62, hgt

    def _combat(self, p, e, world, cam, t):
        fx = self.fx
        # Scan-Strahl
        if world.scan_t >= 0 and world.scan_target is not None and world.player.uid in self.screen:
            tg = world.scan_target
            hx, hy = self._hand(world)
            tx, ty, th_ = self._chest(tg, cam)
            k = world.scan_t / max(0.01, config.SCAN_TIME * world.run.mods["scan_time"])
            sweep = ty - th_ * 0.38 + th_ * 0.9 * (0.5 + 0.5 * math.sin(k * math.pi * 3))
            p.setCompositionMode(PLUS)
            g = QLinearGradient(hx, hy, tx, ty)
            g.setColorAt(0, QColor(64, 210, 220, 140))
            g.setColorAt(1, QColor(64, 210, 220, 40))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(g))
            p.drawPolygon(QPolygonF([QPointF(hx, hy - 0.5), QPointF(tx, sweep - th_ * 0.12),
                                     QPointF(tx, sweep + th_ * 0.12), QPointF(hx, hy + 0.5)]))
            p.setCompositionMode(OVER)
            for q in (p, e):
                q.fillRect(QRectF(tx - th_ * 0.22, sweep, th_ * 0.44, 1), qc(CYAN))
        # Laservisier
        if world.aiming:
            hx, hy = self._hand(world)
            b = world.blocker
            tgt = world.target
            if b is not None:
                ex, ey, _h = self._chest(b, cam)
            elif tgt is not None:
                ex, ey, _h = self._chest(tgt, cam)
            else:
                ex = hx + world.player.facing * config.SHOOT_RANGE * persp.ppu(world.player.depth)
                ey = hy
            blocked = b is not None and b is not tgt
            col = (255, 60, 80) if not blocked else AMBER
            steady = min(1.0, world.aim_t / max(0.05, world.run.mods["aim_min"] + 0.01))
            for q, a_ in ((p, 200), (e, 160)):
                pen = QPen(QColor(col[0], col[1], col[2], int(a_ * (0.4 + 0.6 * steady))))
                pen.setWidth(1)
                q.setPen(pen)
                q.drawLine(QLineF(hx, hy, ex, ey))
                q.fillRect(QRectF(int(ex) - 1, int(ey) - 1, 3, 3), qc(col))
        # Leuchtspuren
        for tr in fx.tracers:
            k = tr["t"] / 0.16
            hx, hy = self._hand(world)
            ex = persp.screen_x(tr["ex"], tr["ed"], cam)
            ey = persp.ground_y(tr["ed"]) - persp.figure_h(tr["ed"]) * 0.62
            sx, sy = hx, hy
            a_ = int(255 * (1 - k))
            for q in (p, e):
                pen = QPen(QColor(255, 250, 230, a_))
                pen.setWidth(2)
                q.setPen(pen)
                q.drawLine(QLineF(sx + (ex - sx) * k * 0.6, sy + (ey - sy) * k * 0.6, ex, ey))
                pen = QPen(QColor(64, 210, 220, a_))
                pen.setWidth(1)
                q.setPen(pen)
                q.drawLine(QLineF(sx, sy - 1, ex, ey - 1))
        for f in fx.flashes:
            x = persp.screen_x(f["wx"], f["d"], cam)
            y = persp.ground_y(f["d"]) + f["oy"]
            r = 3 + 10 * (1 - f["t"] / 0.12)
            g = QRadialGradient(x, y, r)
            g.setColorAt(0, QColor(255, 240, 210, 255))
            g.setColorAt(1, QColor(255, 140, 60, 0))
            for q in (p, e):
                q.setCompositionMode(PLUS)
                q.fillRect(QRectF(x - r, y - r, 2 * r, 2 * r), QBrush(g))
                q.setCompositionMode(OVER)
        for s in fx.sparks:
            sc = persp.scale(s["d"])
            x = persp.screen_x(s["wx"], s["d"], cam) + s["ox"] * sc
            y = persp.ground_y(s["d"]) + s["oy"]
            if y > persp.ground_y(s["d"]):
                continue
            c = s["c"]
            p.fillRect(QRectF(int(x), int(y), 1, 1), qc(c))
            if c[0] > 200:
                e.fillRect(QRectF(int(x), int(y), 1, 1), qc(c))

    # ------------------------------------------------------------------ Vordergrund
    def _foreground(self, p, cam):
        """Säulen/Masten sehr nah an der Kamera (Tiefe 1.35) und Kabel oben."""
        d = 1.35
        k = persp.ppu(d)
        spacing = 620.0
        first = math.floor((cam - W / k) / spacing) - 1
        for i in range(first, first + 4):
            wx = i * spacing + 230 * _hash(i, 3)
            x = persp.screen_x(wx, d, cam)
            if x < -40 or x > W + 40:
                continue
            kind = _hash(i, 9)
            if kind < 0.5:
                w = 14
                p.fillRect(QRectF(int(x), 0, w, H), qc((5, 6, 10)))
                p.fillRect(QRectF(int(x) + w - 2, 0, 1, H), qc(mul(self.city.th["rim"], 0.35)))
                p.fillRect(QRectF(int(x), int(H * 0.55), w, 3), qc(mul(self.city.th["neon"][0], 0.5)))
            else:
                # Hängendes Kabel quer durchs Bild
                pen = QPen(qc((8, 9, 14)))
                pen.setWidth(2)
                p.setPen(pen)
                y0 = 10 + 18 * _hash(i, 5)
                pts = [QPointF(x - 200 + j * 20, y0 + 26 * math.sin(math.pi * j / 20)) for j in range(21)]
                p.drawPolyline(QPolygonF(pts))

    # ------------------------------------------------------------------ CRT-Einschalten
    def _power_on(self, p, k):
        """k 0..1: Bild öffnet sich vom Leuchtstrich zur vollen Höhe."""
        if k <= 0:
            p.fillRect(0, 0, W, H, qc(VOID))
            return
        open_h = H * max(0.0, (k - 0.25) / 0.75) ** 1.5
        band = max(1.0, open_h)
        top = (H - band) / 2
        p.fillRect(QRectF(0, 0, W, top), qc(VOID))
        p.fillRect(QRectF(0, top + band, W, H - top - band), qc(VOID))
        if k < 0.4:
            wv = W * min(1.0, k / 0.25)
            p.fillRect(QRectF((W - wv) / 2, H / 2 - 1, wv, 2), qc(WHITE))
