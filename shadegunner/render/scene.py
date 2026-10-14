"""Szenen-Komposition (CPU, QPainter): Stadt + Figuren + Licht + Effekte -> QImage.

Pro Frame (~6-9 ms bei 640x360):
  Himmel/Wolken -> Suchscheinwerfer/Spinner -> Skyline fern/mittel (+ Fackeln,
  Warnlichter, Holo-Billboards, Luftschiff) -> Häuserfront (+ Neon, Laternen)
  -> nasser Boden (Spiegelungen, Perspektiv-Textur, Lichtkegel) -> Figuren
  (Schatten, Spiegelbild, Rimlight, Augenreflex) -> Laser/Scan/Leuchtspuren
  -> Regen, Vordergrund -> Glow-Pass (Leuchtschicht verkleinert/vergrößert,
  additiv) -> Treffer/Blende.

Danach Bayer-Dither + CRT auf der GPU (render/glrender.py).
"""

import bisect
import math
import random

from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import (QBrush, QColor, QImage, QLinearGradient, QPainter, QPen,
                         QPolygonF, QRadialGradient, QRegion)

from .. import config, persp
from . import holo, pixfont, props, sprites, vehicles
from .city import CLOUD_F, MID_F, City, mix, mul, qc, soft_reflection
from .fx import FX

C = config.NOIR16
VOID, NIGHT, NAVY, INDIGO, BLUE, STEEL = C[0], C[1], C[2], C[3], C[4], C[5]
RED, SODIUM, NBLUE, PALE, WHITE = C[6], C[7], C[8], C[9], C[10]
CRIMSON = (150, 28, 40)          # dunkles Rot (Blut, Rost) - dithert Signalrot/Schwarz
ASH = (150, 162, 168)            # Beton-/Regengrau - dithert Stahl/Pale
SLATE = (104, 118, 126)
TEAL, CYAN, MAGENTA, AMBER, GREEN = C[11], C[12], C[13], C[14], C[15]

W, H = config.RENDER_W, config.RENDER_H
_NULL_IMG = QImage()        # Reflexionen aus: drawImage zeichnet nichts
PLUS = QPainter.CompositionMode.CompositionMode_Plus
OVER = QPainter.CompositionMode.CompositionMode_SourceOver

ADS = ["MEHR MENSCH ALS MENSCH", "TYRELL CORP", "EIN NEUES LEBEN IN DEN KOLONIEN",
       "OFF-WORLD", "SHIMATA DOMINGUEZ", "NEXUS 6", "TRINK KALTEN KAFFEE", "PAN AM"]


def _hash(i, s):
    h = (i * 374761393 + s * 668265263) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF) / 65535.0


# --------------------------------------------------------------------- Billboards

def _billboard_frames(rng, w, h, kind, neon=(RED, CYAN, AMBER, GREEN)):
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
            col = neon[(k + rng.randint(0, 3)) % len(neon)]
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
        self.bikes = []            # Radfahrer: reine Kulisse, nicht Teil der Simulation
        self.doves = []            # ROYs Taube (nur wenn man ihn verschont)
        self._bike_next = 12.0
        self.litter = []           # flatternder Müll (Zeitungen, Papier) - Kulisse
        self._gust = 6.0
        self._fg_img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        self._nb_img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)   # nah, leicht unscharf
        self._near = []
        # Leistungs-Optionen (Einstellungen; wie im Android-Port). Default = volle Pracht.
        self.opt_reflections = True
        self.opt_rain = "viel"        # "viel" | "wenig" | "aus"
        self.opt_fog = True
        self.opt_fx = True
        self.opt_quality = "hoch"     # "hoch" | "mittel" | "niedrig" (u. a. Kabel-Auflösung)
        self._rain_applied = "viel"

    def _apply_rain(self):
        """Regenmenge gemäß opt_rain (Ausgangsmenge der Zone bleibt sonst gleich)."""
        f = {"wenig": 0.6, "aus": 0.0}.get(self.opt_rain, 1.0)
        self.fx.set_rain(self.city.th["rain"] * f)
        self._rain_applied = self.opt_rain

    # ------------------------------------------------------------------ Zone
    def ensure_zone(self, zone_index, seed, length=None):
        from ..sim import ZONES
        length = length if length is not None else ZONES[zone_index]["length"]
        key = (zone_index, seed, length)
        if key == self._zone_key:
            return
        self._zone_key = key
        vehicles.set_zone(zone_index)
        self.city = City(zone_index, float(length), seed)
        th = self.city.th
        self._apply_rain()
        rng = random.Random(seed + 77)
        self.bb_frames = [_billboard_frames(rng, bb[2], bb[3], rng.choice(("face", "logo", "kanji")), th["neon"])
                          for bb in self.city.billboards]
        self.spinners = []
        for _ in range(th["spinners"]):
            self._spawn_spinner(rng, initial=True)
        self.blimp = None
        if th["blimp"]:
            self.blimp = dict(x=rng.uniform(0, W), y=rng.uniform(28, 60), ad=rng.choice(ADS), off=0.0)
        self._refl.clear()
        self._last_cam = None
        self.bikes = []
        self._bike_next = random.Random(seed + 5).uniform(8.0, 25.0)
        self.litter = []
        self._gust = random.Random(seed + 6).uniform(4.0, 12.0)

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
            elif k == "dove":
                _, x, d = ev
                self.doves.append(dict(x=x, d=d, z=persp.figure_h(d) / persp.ppu(d) * 0.55, t=0.0,
                                       vx=6.0, vz=10.0))


    # ------------------------------------------------------------------ Frame
    def frame(self, world, dt=1 / 60, show_player=True, fade=0.0, power=1.0, cam_override=None):
        if self.city is None or self._zone_key[0] != world.zone_index:
            self.ensure_zone(world.zone_index, getattr(world, "seed", 0), world.length)
        self.t += dt
        t = self.t
        city, th, fx = self.city, self.city.th, self.fx
        config.ACTIVE["palette"] = config.zone_look(city.zone)["name"]
        seed = getattr(world, "seed", 0)
        self._reflk = 0.6 + 0.7 * th["rain"]     # Regen verstärkt die Spiegelung
        cam = world.camera_x if cam_override is None else cam_override
        cam_dx = 0.0 if self._last_cam is None else (cam - self._last_cam) * persp.PPU_NEAR * 0.6
        self._last_cam = cam

        if self.opt_rain != self._rain_applied:
            self._apply_rain()
        fx.update_rain(dt, cam_dx)
        fx.update_steam(dt)
        self._update_bikes(dt, cam)
        for dv in self.doves:
            dv["t"] += dt
            tt = dv["t"]
            # erst ein paar unsichere Flügelschläge, dann steigt sie steil in den Regen
            dv["vz"] = 10.0 + 34.0 * min(1.0, tt / 1.6)
            dv["vx"] = 6.0 + 10.0 * math.sin(tt * 0.7)
            dv["x"] += dv["vx"] * dt
            dv["z"] += dv["vz"] * dt
        self.doves = [dv for dv in self.doves if dv["t"] < 14.0]
        self._update_litter(dt, cam)
        fx.update_combat(dt)

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
        self._holos(p, e, cam, t, "giant")
        self._fog_band(p)
        self._fog(p, 0, persp.FACADE_Y - 122, 128, cam * MID_F * 1.4 + t * 5.0, min(1.0, fd * 1.5))
        city.facade.draw(p, cam)
        city.facade.draw(e, cam, img=city.facade_emit, opacity=0.8 * (1.0 - self.dark))
        self._facade_life(p, e, cam, t, dt)
        self._street(p, e, cam, t)
        self._holos(p, e, cam, t, "street")
        self._ramen(p, e, world, cam, t, dt)
        if self.opt_fx:
            self._shout_fx(p, e, world, cam, t)
        self._fog(p, 1, persp.FACADE_Y - 28, 72, cam * persp.ppu(0.0) + t * 9.0, min(1.0, fd * 0.7))
        self._spans_back(p, e, cam, t)
        self._near = []
        self._actors(p, e, world, cam, t, show_player)
        self._near_layer(p, e, cam, t)
        self._spans_front(p, e, cam, t)
        for dv in self.doves:
            self._draw_dove(p, e, dv, cam)
        if self.dark > 0:
            p.fillRect(0, 0, W, H, QColor(2, 3, 10, int(165 * self.dark)))
            if self.opt_fx:
                self._glints(p, e, world, cam, boost=True)
            self._flashlight(p, e, world, cam)
        self._vehicle_lights(p, e, world, cam, t)
        if self.opt_fx:
            self._combat(p, e, world, cam, t)
            fx.draw_steam(p, cam, city.facade.factor)
        self._patrol(p, e, world, cam, t)
        self._spinners(p, e, dt, t, near=True)
        if self.opt_rain != "aus":
            dry = self._span_clip(cam)
            if dry is not None:
                p.save()
                p.setClipRegion(QRegion(0, 0, W, H).subtracted(dry))
            fx.draw_rain(p, mix(th["fog"], PALE, 0.55))
            if dry is not None:
                p.restore()
            self._beam_rain(p)
        self._fog(p, 1, H - 70, 78, cam * persp.ppu(1.15) + t * 14.0, min(1.0, fd * 0.42))
        # Ganzflächiger Nebelschleier: bei dichter Lage verschwimmt auch der Vordergrund
        # (Vordergrund liegt "näher an der Kamera", also über allem anderen).
        self._fog_img(p, city.bank, -30, H + 70, cam * persp.ppu(1.0) * 0.6 + t * 7.0, min(0.46, fd * 0.34))
        if self.opt_fx:
            self._wisps(p, dt, cam)
        self._fg_e = e
        self._foreground(p, cam)
        self._fg_e = None
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
        for img, speed, fac in city.cloud_layers:
            off = (t * speed + cam * fac) % img.width()
            x = -off
            p.drawImage(QPointF(int(x), 0), img)
            if x + img.width() < W:
                p.drawImage(QPointF(int(x + img.width()), 0), img)
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
        if not self.opt_fog or opacity <= 0.01:
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
        """Fliegender Spinner (gleiche Silhouette wie am Boden), Anker = Rumpfmitte."""
        ppx = 22 * sc / vehicles.SPIN_L
        far = near is None or (not near and sc < 0.9)
        self._spinner_sprite(p, e, x, y + 10 * ppx, ppx, d, t, police, far=far, cone=True)

    def _spinner_sprite(self, p, e, x, gy, ppx, d, t, police, far=False, cone=True):
        img, em, ax, _ayc, ayg = vehicles.spinner_image(ppx, police, d, far)
        kq = max(0.25, round(ppx * 8) / 8)
        x0, y0 = int(x) - ax, int(gy) - ayg
        p.drawImage(x0, y0, img)
        if not far:
            e.drawImage(x0, y0, em)
        nx, ny = vehicles.SPIN_NOSE
        hx, hy = x + nx * kq * d, gy + ny * kq
        if cone:
            p.setCompositionMode(PLUS)
            ln = 60 * kq / 0.35 if not far else 30 * kq / 0.35
            g = QLinearGradient(hx, hy, hx + ln * d, hy + ln * 0.3)
            g.setColorAt(0, QColor(130, 130, 150, 70 if not far else 30))
            g.setColorAt(1, QColor(0, 0, 0, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(g))
            p.drawPolygon(QPolygonF([QPointF(hx, hy - 1), QPointF(hx + ln * d, hy + ln * 0.08),
                                     QPointF(hx + ln * 0.9 * d, hy + ln * 0.42), QPointF(hx, hy + 1)]))
            p.setCompositionMode(OVER)
        if police:
            self._spinner_lights(p, e, x, gy, kq, kq, d, t)
        elif int(t * 1.5) % 2 == 0:
            tx, ty = vehicles.SPIN_TAIL
            for q in (p, e):
                q.fillRect(QRectF(x + tx * kq * d - 1, gy + ty * kq, 2, 1), qc(CRIMSON))

    def _spinner_lights(self, p, e, cx, gy, kx, ky, d, t):
        """Lichtbalken (rot/blau im Wechsel) + Mittelscheinwerfer + Blitzer am Unterboden."""
        bx, by, bw, bh = vehicles.SPIN_BAR
        ph = int(t * 7) % 4
        w2 = bw * kx / 2
        x0 = cx + bx * kx * d + (0 if d > 0 else -bw * kx)
        y0 = gy + by * ky
        hh = max(1.0, bh * ky)
        left = MAGENTA if ph in (0, 1) else (40, 20, 30)
        right = (90, 140, 255) if ph in (2, 3) else (20, 30, 50)
        if ph == 1:
            right = WHITE
        for q in (p, e):
            q.fillRect(QRectF(x0, y0, w2, hh), qc(left))
            q.fillRect(QRectF(x0 + w2, y0, w2, hh), qc(right))
            q.fillRect(QRectF(cx + (bx + 4.2) * kx * d - kx, y0 - max(1.0, 1.2 * ky), max(1.0, 2.4 * kx),
                              max(1.0, 1.2 * ky)), qc(WHITE))
        if ph in (0, 2):
            c = MAGENTA if ph == 0 else (90, 140, 255)
            p.setCompositionMode(PLUS)
            rg = QRadialGradient(x0 + w2, y0, 18 * kx)
            rg.setColorAt(0, QColor(c[0], c[1], c[2], 90))
            rg.setColorAt(1, QColor(0, 0, 0, 0))
            p.fillRect(QRectF(x0 + w2 - 18 * kx, y0 - 18 * kx, 36 * kx, 36 * kx), QBrush(rg))
            p.setCompositionMode(OVER)

    def _fog_band(self, p):
        """Dunst über der Skyline: die Ferne versinkt stärker im Nebel als die Front."""
        if not self.opt_fog:
            return
        th = self.city.th
        fy = persp.FACADE_Y
        fd = getattr(self, "_fog_d", th["fog_amt"])
        fc = mix(th["fog"], th["sky_hor"], 0.5)
        g = QLinearGradient(0, fy - 150, 0, fy + 6)
        g.setColorAt(0.0, QColor(*fc, 0))
        g.setColorAt(0.55, QColor(*fc, int(255 * min(1.0, fd * 0.3))))
        g.setColorAt(1.0, QColor(*fc, int(255 * min(1.0, fd * 0.75))))
        p.fillRect(QRectF(0, fy - 150, W, 157), QBrush(g))

    def _ramen(self, p, e, world, cam, t, dt):
        """Nudelbar lebt: Lichtpool auf dem nassen Asphalt, Glühbirnen, Laternen,
        Koch mit Nudelsieb, flackernde Drachenzunge, Tropfen vom Vordach, Dampf."""
        city = self.city
        fac = city.facade
        rng = self.rng
        spots = getattr(world, "ramen", ())
        pl = world.player
        lv_dark = 1.0 - 0.55 * self.dark
        p.setPen(Qt.PenStyle.NoPen)
        for sp in city.ramen_spots:
            x0 = fac.screen_x(sp["L"], cam)
            if x0 < -240 or x0 > W + 60:
                continue
            base = sp["base"]
            cxw = (sp["L"] + sp["w"] / 2) / fac.factor
            r = next((r for r in spots if abs(r["x"] - cxw) < 6), None)
            used = r is not None and r["used"]
            # Lichtpool auf der Straße (breit, warm) + Lichtkegel der Birnen
            p.setCompositionMode(PLUS)
            gx = persp.screen_x(cxw, 0.16, cam)
            gy = persp.ground_y(0.16)
            g = QRadialGradient(gx, gy, 110)
            g.setColorAt(0.0, QColor(255, 150, 60, int(62 * lv_dark)))
            g.setColorAt(0.5, QColor(255, 110, 40, int(22 * lv_dark)))
            g.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.save()
            p.translate(gx, gy)
            p.scale(1.0, 0.28)
            p.translate(-gx, -gy)
            p.fillRect(QRectF(gx - 110, gy - 110, 220, 220), QBrush(g))
            p.restore()
            for i, (bl, by) in enumerate(sp["bulbs"]):
                bx = fac.screen_x(bl, cam)
                fl = 0.2 if (i == 2 and _hash(int(t * 15), int(bl)) < 0.12) else 1.0
                rg = QRadialGradient(bx, by + 1, 18)
                rg.setColorAt(0, QColor(255, 206, 140, int(55 * fl * lv_dark)))
                rg.setColorAt(1, QColor(0, 0, 0, 0))
                p.fillRect(QRectF(bx - 18, by - 17, 36, 36), QBrush(rg))
                if fl < 1.0:        # Wackelkontakt: Birne kurz aus
                    p.setCompositionMode(OVER)
                    p.fillRect(QRectF(bx - 1, by, 3, 3), qc((70, 50, 30)))
                    p.setCompositionMode(PLUS)
            for (ll, ly) in sp["lanterns"]:
                lx = fac.screen_x(ll, cam)
                rg = QRadialGradient(lx, ly, 16)
                rg.setColorAt(0, QColor(255, 60, 60, int(50 * lv_dark)))
                rg.setColorAt(1, QColor(0, 0, 0, 0))
                p.fillRect(QRectF(lx - 16, ly - 16, 32, 32), QBrush(rg))
            p.setCompositionMode(OVER)
            # Koch: grüßt, wenn der Blade Runner herankommt; reicht beim Essen die Schale
            near = r is not None and abs(pl.x - r["x"]) < 70 and pl.depth < 0.7
            serving = r is not None and r["t"] > 0.05 and not used
            self._cook(p, e, fac.screen_x(sp["cook"], cam), base, t, near and not serving, serving)
            if used:   # leere Schale am freien Platz
                cx = int(fac.screen_x(sp["cook"], cam))
                p.fillRect(QRectF(cx - 2, base - 20, 5, 2), qc((200, 202, 210)))
            # Drachenzunge (rot, flackert wie im Film)
            tl, ty = sp["tongue"]
            tx = int(fac.screen_x(tl, cam))
            if _hash(int(t * 11), int(tl)) > 0.35 and self.dark < 0.4:
                for q in (p, e):
                    q.fillRect(QRectF(tx - 3, ty, 3, 1), qc((255, 50, 70)))
                    q.fillRect(QRectF(tx - 4, ty - 1, 1, 1), qc((255, 50, 70)))
                    q.fillRect(QRectF(tx - 4, ty + 1, 1, 1), qc((255, 50, 70)))
            # Wok-Flamme
            wl, wy = sp["wok"]
            wx = fac.screen_x(wl, cam)
            fh = 2 + 3 * _hash(int(t * 20), int(wl))
            for q in (p, e):
                q.fillRect(QRectF(wx - 6, wy + 4, 12, 1), qc((90, 140, 255)))
                q.fillRect(QRectF(wx - 4, wy + 4 - fh, 2, fh), qc(AMBER))
                q.fillRect(QRectF(wx + 2, wy + 5 - fh, 2, fh - 1), qc(AMBER))
            # Tropfen vom Vordach
            lip = sp["lip"]
            fall = base - lip - 2
            for k, dl in enumerate(sp["drips"]):
                ph = (t * 0.9 + _hash(k, int(sp["L"])) * 7.0) % 1.0
                dx = int(fac.screen_x(dl, cam))
                if ph < 0.7:
                    y = lip + fall * (ph / 0.7) ** 2
                    p.fillRect(QRectF(dx, int(y), 1, 2), qc((170, 182, 204)))
                elif ph < 0.8:
                    p.fillRect(QRectF(dx - 1, base - 1, 3, 1), qc((150, 160, 186)))
            # Dampf: Suppentopf, Wok, Schalen
            if rng.random() < dt * 4.0:
                pl_, py_ = sp["pot"]
                self.fx.puff(pl_ + rng.uniform(-6, 6), py_, scale=0.8)
            if rng.random() < dt * 1.5:
                self.fx.puff(wl + rng.uniform(-3, 3), wy - 2, scale=0.6)
            for bl in sp.get("bowls", ()):
                if rng.random() < dt * 0.5:
                    self.fx.puff(bl, base - 22, scale=0.4)

    def _cook(self, p, e, cx, base, t, greet, serving):
        """Koch hinter der Theke: weiße Jacke, Stirnband, schüttelt das Nudelsieb."""
        x = int(cx + math.sin(t * 1.3) * 2)
        top_c = base - 18
        jacket, shade, skin = (214, 196, 170), (150, 126, 100), (150, 104, 72)
        p.setPen(Qt.PenStyle.NoPen)
        p.fillRect(QRectF(x - 5, base - 31, 10, top_c - base + 31), qc(jacket))
        p.fillRect(QRectF(x - 5, base - 31, 2, top_c - base + 31), qc(shade))
        p.fillRect(QRectF(x - 1, base - 31, 2, 2), qc(skin))
        p.setBrush(qc(skin))
        p.drawEllipse(QRectF(x - 3, base - 38, 7, 8))
        p.fillRect(QRectF(x - 3, base - 38, 7, 2), qc((30, 24, 20)))
        p.fillRect(QRectF(x - 4, base - 36, 9, 1), qc((240, 240, 244)))
        p.fillRect(QRectF(x - 3, base - 38, 7, 1), qc(mix((30, 24, 20), AMBER, 0.5)))
        pen = QPen(qc(jacket))
        pen.setWidth(2)
        if greet:          # winkt: „Irasshai!“
            a = -1.9 + 0.35 * math.sin(t * 9)
            sx, sy = x + 4, base - 31
            hx, hy = sx + math.cos(a) * 7, sy + math.sin(a) * 7
            p.setPen(pen)
            p.drawLine(QPointF(sx, sy), QPointF(hx, hy))
            p.setPen(Qt.PenStyle.NoPen)
            p.fillRect(QRectF(hx - 1, hy - 2, 3, 3), qc(skin))
        elif serving:      # reicht die Schale über den Tresen
            p.setPen(pen)
            p.drawLine(QPointF(x + 4, base - 30), QPointF(x + 3, top_c - 3))
            p.drawLine(QPointF(x - 4, base - 30), QPointF(x - 3, top_c - 3))
            p.setPen(Qt.PenStyle.NoPen)
            p.fillRect(QRectF(x - 4, top_c - 3, 9, 3), qc((226, 228, 234)))
            p.fillRect(QRectF(x - 3, top_c - 4, 7, 1), qc((214, 150, 80)))
        else:              # Nudelsieb schütteln
            k = math.sin(t * 7.0) * 2.0 if (t % 4.0) < 2.4 else 0.0
            sx, sy = x + 4, base - 31
            hx, hy = x + 9, top_c - 4 + k
            p.setPen(pen)
            p.drawLine(QPointF(sx, sy), QPointF(hx, hy))
            p.setPen(Qt.PenStyle.NoPen)
            p.fillRect(QRectF(hx, hy, 5, 1), qc((120, 124, 134)))
            p.setBrush(qc((150, 154, 166)))
            p.drawChord(QRectF(hx + 4, hy - 1, 5, 4), 180 * 16, 180 * 16)
            p.fillRect(QRectF(hx + 5, hy + 1, 3, 1), qc((230, 200, 120)))

    # ------------------------------------------------------------------ Hologramme
    def _holos(self, p, e, cam, t, kind):
        city = self.city
        hs = getattr(city, "holos", ())
        if not hs:
            return
        dim = 1.0 - 0.85 * self.dark          # Stromausfall: Hologramme fallen (fast) aus
        if dim <= 0.05:
            return
        for hd in hs:
            if hd["kind"] != kind:
                continue
            lay = city.mid if kind == "giant" else city.facade
            x = lay.screen_x(hd["L"], cam)
            h = hd["h"]
            if x < -h or x > W + h:
                continue
            if kind == "street":
                # Projektorsockel mit Linse + schwacher Lichtsäule
                b = hd["base"]
                p.fillRect(QRectF(int(x) - 6, b - 4, 12, 5), qc((26, 28, 40)))
                p.fillRect(QRectF(int(x) - 6, b - 4, 12, 1), qc(mul(self.city.th["rim"], 0.8)))
                for q in (p, e):
                    q.fillRect(QRectF(int(x) - 3, b - 5, 6, 1), qc(hd["col"]))
                p.setCompositionMode(PLUS)
                g = QLinearGradient(x, b - 5, x, b - h)
                c = hd["col"]
                g.setColorAt(0, QColor(c[0], c[1], c[2], int(40 * dim)))
                g.setColorAt(1, QColor(0, 0, 0, 0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(g))
                p.drawPolygon(QPolygonF([QPointF(x - 3, b - 5), QPointF(x - h * 0.3, b - h),
                                         QPointF(x + h * 0.3, b - h), QPointF(x + 3, b - 5)]))
                p.setCompositionMode(OVER)
                holo.render(p, e, x, b - 5, h, c, t, hd["seed"], reflect=0.4, alpha=0.95 * dim,
                            mirror=hd["mirror"])
            else:
                holo.render(p, e, x, hd["base"], h, hd["col"], t * 0.85, hd["seed"], alpha=0.6 * dim,
                            mirror=hd["mirror"])

    # ------------------------------------------------------------------ Ruf
    def _shout_fx(self, p, e, world, cam, t):
        """Rufwelle als Ring auf dem nassen Asphalt; beim Halten von V ein Lade-Ring."""
        pl = world.player
        rings = []
        w = getattr(world, "wave", None)
        if w is not None and w["r"] > 0:
            k = w["r"] / max(1.0, w["R"])
            rings.append((w["x"], w["depth"], w["r"], max(0.0, 1.0 - k) * 0.9 + 0.1, (214, 220, 226)))
        hold = getattr(world, "shout_hold", -1.0)
        if hold >= config.SHOUT_TAP and pl.alive:
            R = world.shout_radius()
            pulse = 0.55 + 0.25 * math.sin(t * 14)
            rings.append((pl.x, pl.depth, R, pulse, (255, 138, 44)))
        if not rings:
            return
        p.setCompositionMode(PLUS)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for (x, d, r, a, col) in rings:
            # Kreis in Welt-Einheiten (x, Tiefe*DEPTH_UNITS) -> Ellipse auf dem Boden
            cx = persp.screen_x(x, d, cam)
            cy = persp.ground_y(d)
            rx = r * persp.ppu(d)
            ry = r / config.DEPTH_UNITS * (persp.ground_y(1) - persp.ground_y(0))
            for wd, aa in ((3, 0.35), (1, 1.0)):
                pen = QPen(QColor(col[0], col[1], col[2], int(150 * a * aa)))
                pen.setWidth(wd)
                p.setPen(pen)
                p.drawEllipse(QRectF(cx - rx, cy - ry, 2 * rx, 2 * ry))
        p.setPen(Qt.PenStyle.NoPen)
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
        self._fires(p, e, cam, t)
        self._walk_signals(p, e, cam, t)
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

    def _fires(self, p, e, cam, t):
        """Feuertonnen an der gegenüberliegenden Häuserfront: Flammenzungen + Lichthof."""
        fac = self.city.fac if hasattr(self.city, "fac") else self.city.facade
        halos = []
        for (L, y, s, seed) in self.city.fires:
            x = fac.screen_x(L, cam)
            if x < -30 or x > W + 30:
                continue
            for q in (p, e):
                for i in range(5):
                    n = _hash(int(t * 11) + i * 7, seed + i)
                    hx = x + (i - 2) * 1.3 + math.sin(t * 9 + i * 2.1 + seed) * 0.8
                    h = s * (4 + 9 * n) * (1.0 if i in (1, 2, 3) else 0.6)
                    col = (255, 236, 170) if i == 2 else ((255, 150, 40) if i % 2 else (230, 70, 30))
                    q.setPen(Qt.PenStyle.NoPen)
                    q.setBrush(qc(col))
                    q.drawPolygon(QPolygonF([QPointF(hx - 1.6, y + 1), QPointF(hx + 1.6, y + 1),
                                             QPointF(hx + math.sin(t * 13 + i) * 1.2, y - h)]))
            if _hash(int(t * 7), seed) < 0.18:      # Funke
                fy_ = y - 6 - 18 * _hash(int(t * 7) + 1, seed)
                for q in (p, e):
                    q.fillRect(QRectF(int(x + 6 * (_hash(int(t * 7) + 2, seed) - 0.5)), int(fy_), 1, 1),
                               qc((255, 200, 120)))
            halos.append((x, y - 4, 26 + 4 * math.sin(t * 7 + seed)))
        if halos:
            p.setCompositionMode(PLUS)
            for (hx, hy, r) in halos:
                g = QRadialGradient(hx, hy, r)
                g.setColorAt(0, QColor(255, 140, 50, 70))
                g.setColorAt(0.5, QColor(255, 110, 40, 22))
                g.setColorAt(1, QColor(0, 0, 0, 0))
                p.fillRect(QRectF(hx - r, hy - r, 2 * r, 2 * r), QBrush(g))
            p.setCompositionMode(OVER)

    # 7x7-Piktogramme wie im Film: Pfeil nach oben (grün) und die rote Hand
    _ARROW = ("...#...", "..###..", ".#####.", "#######", "..###..", "..#.#..", "..###..")
    _HAND = ("#.#.#..", "#.#.#.#", "#.#.#.#", "#######", "######.", ".#####.", "..###..")

    def _walk_icon(self, p, e, bx, y, sz, t, ph):
        """Ein Ampelpaar (grüner Pfeil / rote Hand) bei bx,y; sz = Feldgröße in Pixeln."""
        ph_t = (t + ph) % 9.0
        go = ph_t < 4.0
        blink = not go and ph_t > 7.6 and int(t * 4) % 2 == 0
        cell = sz / 8.0
        for k, (icon, col, lit) in enumerate(((self._ARROW, (40, 200, 150), go),
                                              (self._HAND, (236, 70, 52), not go and not blink))):
            x0 = bx + k * (sz + cell)
            if self.dark > 0.4:
                lit = False
            fill = col if lit else mul(col, 0.3)
            for q in ((p, e) if lit else (p,)):
                q.fillRect(QRectF(x0, y, sz, sz + cell), qc(fill))
            ink = qc((10, 12, 12) if lit else mul(col, 0.12))
            for r, row in enumerate(icon):
                for c_, ch in enumerate(row):
                    if ch == "#":
                        p.fillRect(QRectF(x0 + (c_ + 0.5) * cell, y + (r + 1) * cell, max(1.0, cell),
                                          max(1.0, cell)), ink)

    def _draw_tower(self, p, e, o, cam, t):
        """Ampelturm als freistehendes Objekt (Schatten, Spiegelung, Umriss, Ampel live)."""
        d = o["d"]
        k = persp.ppu(d)
        cx = persp.screen_x(o["x"], d, cam)
        sc = k / persp.FACADE_PPU * o.get("size", 1.0)
        if cx < -45 * sc or cx > W + 45 * sc:
            return
        gy = persp.ground_y(d)
        key = ("tower", o["seed"], round(sc * 8) / 8, self.city.th["rim"])
        hit = self._refl.get(key)
        if hit is None:
            img, em, ax, ay, walks, blinks = props.tower_sprite(o["seed"], round(sc * 8) / 8, self.city.th)
            hit = self._refl[key] = (vehicles._outline(img), em, ax, ay, walks, blinks)
        img, em, ax, ay, walks, blinks = hit
        s = round(sc * 8) / 8
        x0, y0 = int(cx) - ax, int(gy) - ay
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 120))
        p.drawEllipse(QRectF(cx - 16 * s, gy - 2 * s, 32 * s, 4 * s))
        if gy < H:
            p.setOpacity(min(1.0, 0.4 * getattr(self, "_reflk", 1.0)))
            p.drawImage(x0, int(gy) - (img.height() - 1 - ay), self._mirror(img))
            p.setOpacity(1.0)
        p.drawImage(x0, y0, img)
        e.drawImage(x0, y0, em)
        for (L, y, ph, sz) in walks:
            self._walk_icon(p, e, cx + L * s, gy + y * s, sz * s, t, ph)
        for (_w, L, y, col, ph) in blinks:
            if math.sin(t * 2.2 + ph * 2.1) > 0.55 and self.dark < 0.4:
                bx, by = cx + L * s, gy + y * s
                for q in (p, e):
                    q.fillRect(QRectF(bx - s, by - s, 2 * s, 2 * s), qc(col))

    NEAR_BLUR = 2            # Unschärfe der kameranahen Ebene (Vordergrund-Kabel: 3)
    WIRE_SHARP = 1.15        # Kabelstücke ab dieser Tiefe kommen in die unscharfe Ebene

    def _near_layer(self, p, e, cam, t):
        """Kabel quer über die Straße (hinten scharf, vorn leicht unscharf) und die
        kameranahen Ampeltürme - beide in einer eigenen, weichgezeichneten Ebene."""
        wires = self._wire_segments(cam, t)
        if not wires and not self._near:
            return
        nb = self._nb_img
        nb.fill(0)
        q = QPainter(nb)
        q.translate(p.transform().dx(), p.transform().dy())
        for o in self._near:
            self._draw_tower(q, e, o, cam, t)
        rim = self.city.th["rim"]
        hl = QPen(QColor(rim[0], rim[1], rim[2], 60))
        hl.setWidthF(1.0)
        for (pts, wd, col, near) in wires:
            pen = QPen(qc(col))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            for i in range(len(pts) - 1):
                pen.setWidthF(max(1.0, wd[i]))
                tgt = q if near[i] else p
                tgt.setPen(pen)
                tgt.drawLine(pts[i], pts[i + 1])
                if wd[i] > 1.6:                        # Streiflicht oben: liest sich gegen den Himmel
                    off = QPointF(0, -wd[i] * 0.45)
                    tgt.setPen(hl)
                    tgt.drawLine(pts[i] + off, pts[i + 1] + off)
        p.setPen(Qt.PenStyle.NoPen)
        q.end()
        b = self.NEAR_BLUR
        small = nb.scaled(W // b, H // b, Qt.AspectRatioMode.IgnoreAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
        p.save()
        p.resetTransform()
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.drawImage(QRectF(0, 0, W, H), small)
        p.restore()

    def _wire_segments(self, cam, t):
        """Bildschirm-Polylinien der Querkabel: (punkte, breiten, farbe, nah-flags)."""
        out = []
        city = self.city
        ws = getattr(city, "wires", ())
        if not ws:
            return out
        lo = cam - W / persp.ppu(-0.075) * 0.5 - 120
        hi = cam + W / persp.ppu(-0.075) * 0.5 + 120
        i0 = bisect.bisect_left([w["x"] for w in ws], lo)
        n = {"hoch": 28, "mittel": 20}.get(self.opt_quality, 14)
        d_end = 2.4
        for w in ws[i0:]:
            if w["x"] > hi:
                break
            sway = math.sin(t * 0.6 + w["seed"]) * 3.0
            for st in w["strands"]:
                pts, wd, near = [], [], []
                for j in range(n + 1):
                    u = j / n
                    d = -0.075 + (d_end + 0.075) * u
                    hgt = w["h0"] + (w["h1"] - w["h0"]) * u - (w["sag"] + st["dsag"] + sway) * 4 * u * (1 - u) + st["dh"]
                    k = persp.ppu(d)
                    x = persp.screen_x(w["x"] + w["dx"] * u + st["dx"], d, cam)
                    y = persp.ground_y(d) - hgt * k
                    pts.append(QPointF(x, y))
                    wd.append(st["w"] * k)
                    near.append(d > self.WIRE_SHARP)
                    if y < -30 and u > 0.5:
                        break
                if len(pts) > 1:
                    out.append((pts, wd, w["col"], near))
        return out

    def _walk_signals(self, p, e, cam, t):
        """Fußgängerampeln der Ampeltürme: grünes Feld mit Pfeil / rotes Feld mit Hand,
        im Wechsel; das jeweils andere Feld glimmt nur."""
        fac = self.city.facade
        for (L, y, ph, sz) in self.city.walks:
            x = int(fac.screen_x(L, cam))
            if -24 <= x <= W + 24:
                self._walk_icon(p, e, x, y, sz, t, ph)

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
                               (city.facade_refl, PLUS, min(1.0, 0.95 * k))) if self.opt_reflections else ():
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
                                   (city.facade_refl, PLUS, min(1.0, 1.0 * k))) if self.opt_reflections else ():
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
        for s in city.visible(city.signs, city._sign_x, L0, L0 + W + 180) if self.opt_reflections else ():
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
        if self.opt_fx:
            self.fx.draw_splashes(p, mix(city.th["fog"], PALE, 0.5))

    # ------------------------------------------------------------------ Überbauten
    D_FAR = config.FACADE_DEPTH
    D_NEAR = 1.7

    @staticmethod
    def _pt(x, d, h, cam):
        return QPointF(persp.screen_x(x, d, cam), persp.ground_y(d) - h * persp.ppu(d))

    @staticmethod
    def _hull(pts):
        pts = sorted(set((round(q.x(), 2), round(q.y(), 2)) for q in pts))
        if len(pts) < 3:
            return QPolygonF([QPointF(x, y) for x, y in pts])

        def cross(o, a, b):
            return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
        lo, hi = [], []
        for q in pts:
            while len(lo) >= 2 and cross(lo[-2], lo[-1], q) <= 0:
                lo.pop()
            lo.append(q)
        for q in reversed(pts):
            while len(hi) >= 2 and cross(hi[-2], hi[-1], q) <= 0:
                hi.pop()
            hi.append(q)
        return QPolygonF([QPointF(x, y) for x, y in lo[:-1] + hi[:-1]])

    def _spans_on(self, cam):
        for s in getattr(self.city, "spans", ()):
            a = min(persp.screen_x(s["x0"], self.D_NEAR, cam), persp.screen_x(s["x0"], self.D_FAR, cam))
            b = max(persp.screen_x(s["x1"], self.D_NEAR, cam), persp.screen_x(s["x1"], self.D_FAR, cam))
            if b > -30 and a < W + 30:
                yield s

    def _span_volume(self, s, cam):
        """Bildschirm-Polygon des Raums unter dem Überbau (trocken, dunkler)."""
        return self._hull([self._pt(x, d, h, cam) for x in (s["x0"], s["x1"])
                           for d in (self.D_FAR, self.D_NEAR) for h in (0.0, s["hu"])])

    def _span_clip(self, cam):
        reg = None
        for s in self._spans_on(cam):
            r = QRegion(self._span_volume(s, cam).toPolygon()).united(QRegion(self._hull(
                [self._pt(x, d, h, cam) for x in (s["x0"], s["x1"]) for d in (self.D_FAR, self.D_NEAR)
                 for h in (s["hu"], s["hu"] + s["t"])]).toPolygon()))
            reg = r if reg is None else reg.united(r)
        return reg

    def _spans_back(self, p, e, cam, t):
        """Brücken / überhängende Gebäude: Schatten am Boden, Pfeiler, Baukörper, Lichter."""
        th = self.city.th
        rim = th["rim"]
        P = self._pt
        for s in self._spans_on(cam):
            x0, x1, hu, T, col = s["x0"], s["x1"], s["hu"], s["t"], s["col"]
            bridge = s["kind"] == "bridge"
            p.setPen(Qt.PenStyle.NoPen)
            # Schatten auf Gehweg/Fahrbahn und an der Hauswand darunter
            sh = 150 if bridge else 120
            p.setBrush(QColor(0, 0, 0, sh))
            p.drawPolygon(QPolygonF([P(x0, self.D_FAR, 0, cam), P(x1, self.D_FAR, 0, cam), P(x1, 1.3, 0, cam),
                                     P(x0, 1.3, 0, cam)]))
            p.setBrush(QColor(0, 0, 0, sh))
            p.drawPolygon(QPolygonF([P(x0, self.D_FAR, hu, cam), P(x1, self.D_FAR, hu, cam),
                                     P(x1, self.D_FAR, 0, cam), P(x0, self.D_FAR, 0, cam)]))
            # Pfeiler (Brücke) auf der anderen Straßenseite
            for pier in s["piers"]:
                d = -0.035
                k = persp.ppu(d)
                xp = persp.screen_x(pier, d, cam)
                pw = 20 * k
                gy = persp.ground_y(d)
                top = gy - hu * k
                g = QLinearGradient(0, top, 0, gy)
                g.setColorAt(0, qc(mul(col, 0.6)))
                g.setColorAt(1, qc(mul(col, 1.5)))
                p.fillRect(QRectF(xp - pw / 2, top, pw, gy - top), QBrush(g))
                e.fillRect(QRectF(xp - pw / 2, top, pw, gy - top), QColor(0, 0, 0))
                p.fillRect(QRectF(xp - pw / 2, top, 1, gy - top), qc(mul(rim, 0.45)))
                p.fillRect(QRectF(xp + pw / 2 - 3, top, 3, gy - top), qc(mul(col, 0.5)))
                p.fillRect(QRectF(xp - pw / 2 - 2, gy - 6, pw + 4, 6), qc(mul(col, 1.2)))
                for yy in range(int(top) + 8, int(gy) - 8, 14):
                    p.fillRect(QRectF(xp - pw / 2 + 1, yy, pw - 4, 1), qc(mul(col, 0.8)))
            # Baukörper
            corners = [P(x, d, h, cam) for x in (x0, x1) for d in (self.D_FAR, self.D_NEAR) for h in (hu, hu + T)]
            hull = self._hull(corners)
            yb = P(x0, self.D_FAR, hu, cam).y()
            lit = mix(col, rim, 0.22)
            g = QLinearGradient(0, yb - 70, 0, yb)
            g.setColorAt(0, qc(mul(col, 0.45)))
            g.setColorAt(0.75, qc(col))
            g.setColorAt(1, qc(lit))
            p.setBrush(QBrush(g))
            p.drawPolygon(hull)
            e.setPen(Qt.PenStyle.NoPen)
            e.setBrush(QColor(0, 0, 0))                 # verdeckt das Leuchten dahinter
            e.drawPolygon(hull)
            # sichtbare Stirnseite
            for x, vis in ((x0, cam < x0), (x1, cam > x1)):
                if not vis:
                    continue
                face = self._hull([P(x, d, h, cam) for d in (self.D_FAR, self.D_NEAR) for h in (hu, hu + T)])
                p.setBrush(qc(mul(col, 0.8)))
                p.drawPolygon(face)
                if bridge:
                    # Fachwerkträger zwischen Unter- und Obergurt
                    pen = QPen(qc(mul(lit, 0.8)))
                    p.setPen(pen)
                    dd, up = self.D_FAR, True
                    while dd < self.D_NEAR:
                        d2 = dd + 0.09
                        p.drawLine(P(x, dd, hu if up else hu + T, cam), P(x, d2, hu + T if up else hu, cam))
                        p.drawLine(P(x, d2, hu, cam), P(x, d2, hu + T, cam))
                        dd, up = d2, not up
                    pen = QPen(qc(mul(rim, 0.7)))
                    p.setPen(pen)
                    p.drawLine(P(x, self.D_FAR, hu + T, cam), P(x, self.D_NEAR, hu + T, cam))
                    p.setPen(Qt.PenStyle.NoPen)
                    for k in range(6):            # Geländerleuchten
                        q_ = P(x, self.D_FAR + 0.15 + k * 0.22, hu + T + 2, cam)
                        for q in (p, e):
                            q.fillRect(QRectF(q_.x() - 1, q_.y() - 1, 2, 2), qc(AMBER))
                else:
                    # Stirnwand des Überhangs: Fensterreihen in die Tiefe
                    wins = self.city.th["win"]
                    rr = random.Random(s["seed"])
                    for row in range(6):
                        h = hu + 14 + row * 16
                        dd = self.D_FAR + 0.04
                        while dd < self.D_NEAR - 0.1:
                            a, b = P(x, dd, h, cam), P(x, dd + 0.05, h + 7, cam)
                            on = rr.random() < 0.35
                            c = mul(wins[rr.randrange(len(wins))][0], 0.6) if on else mul(col, 0.45)
                            poly = QPolygonF([a, P(x, dd + 0.05, h, cam), b, P(x, dd, h + 7, cam)])
                            p.setBrush(qc(c))
                            p.drawPolygon(poly)
                            if on:
                                e.setBrush(qc(mul(c, 0.5)))
                                e.drawPolygon(poly)
                            dd += 0.09
                pen = QPen(qc(mul(rim, 0.8)))
                p.setPen(pen)
                p.drawLine(P(x, self.D_FAR, hu, cam), P(x, self.D_NEAR, hu, cam))
                p.setPen(Qt.PenStyle.NoPen)
            # Unterkante zur Straße hin
            pen = QPen(qc(mul(rim, 0.5)))
            p.setPen(pen)
            p.drawLine(self._pt(x0, self.D_FAR, hu, cam), self._pt(x1, self.D_FAR, hu, cam))
            p.setPen(Qt.PenStyle.NoPen)
            self._span_lights(p, e, s, cam, t)

    def _span_lights(self, p, e, s, cam, t):
        x0, x1, hu = s["x0"], s["x1"], s["hu"]
        w = x1 - x0
        dark = self.dark > 0.4
        pools = []
        if s["kind"] == "bridge":
            # Natriumlampen an kurzen Abhängern unter dem Deck
            for f in (0.3, 0.7):
                d = 0.12
                x = x0 + w * f
                top = self._pt(x, d, hu, cam)
                lamp = self._pt(x, d, hu - 16, cam)
                p.setPen(QPen(qc((14, 14, 16))))
                p.drawLine(top, lamp)
                p.setPen(Qt.PenStyle.NoPen)
                c = (255, 160, 70)
                if not dark:
                    for q in (p, e):
                        q.fillRect(QRectF(lamp.x() - 2, lamp.y(), 5, 2), qc(c))
                    pools.append((x, d, c, 0.9))
            # rote Positionslichter an der Kante
            for k in range(4):
                if (int(t * 1.5) + k) % 4 == 0 and not dark:
                    q_ = self._pt(x0 + w * (k + 0.5) / 4, self.D_FAR, hu, cam)
                    for q in (p, e):
                        q.fillRect(QRectF(q_.x(), q_.y() - 1, 2, 2), qc(RED))
        else:
            # Neonröhren unter der Vorderkante (wie die Lichtschläuche im Film)
            for i, c in enumerate(s["tubes"]):
                a = self._pt(x0 + 6, self.D_FAR, hu, cam)
                b = self._pt(x1 - 6, self.D_FAR, hu, cam)
                y = a.y() + 3 + i * 4
                n = 6
                for j in range(n):
                    if _hash(j + i * 11, s["seed"]) < 0.18:
                        continue                       # kaputtes Segment
                    flick = _hash(int(t * 14) + j, s["seed"] + i) < 0.03
                    xa = a.x() + (b.x() - a.x()) * j / n + 1
                    xb = a.x() + (b.x() - a.x()) * (j + 1) / n - 1
                    cc = mul(c, 0.25) if (dark or flick) else c
                    for q in ((p,) if dark or flick else (p, e)):
                        q.fillRect(QRectF(xa, y, xb - xa, 2), qc(cc))
                    p.fillRect(QRectF(xa, y + 2, xb - xa, 1), qc(mul(cc, 0.35)))
                if not dark:
                    pools.append((x0 + w * 0.5, 0.05 + 0.1 * i, c, 0.55))
            # hängende Schilder
            for (f, c, word, drop, sd) in s["signs"]:
                x = x0 + w * f
                top = self._pt(x, self.D_FAR + 0.03, hu, cam)
                tw = pixfont.text_width(word)
                bx, by = int(top.x()), int(top.y() + drop)
                p.setPen(QPen(qc((16, 16, 18))))
                p.drawLine(QPointF(bx + 2, top.y()), QPointF(bx + 2, by))
                p.drawLine(QPointF(bx + tw + 4, top.y()), QPointF(bx + tw + 4, by))
                p.setPen(Qt.PenStyle.NoPen)
                p.fillRect(QRectF(bx, by, tw + 7, 10), qc((10, 12, 14)))
                lit = not dark and _hash(int(t * 9), sd) > 0.02
                for q in ((p, e) if lit else (p,)):
                    pixfont.draw(q, bx + 4, by + 2, word, c if lit else mul(c, 0.3), 1, None)
        # Lichtpfützen am Boden unter den Lampen
        if pools:
            p.setCompositionMode(PLUS)
            for (x, d, c, k) in pools:
                gx, gy = persp.screen_x(x, d, cam), persp.ground_y(d)
                r = 46 * persp.scale(d)
                rg = QRadialGradient(gx, gy, r)
                rg.setColorAt(0, QColor(c[0], c[1], c[2], int(90 * k)))
                rg.setColorAt(1, QColor(0, 0, 0, 0))
                p.save()
                p.translate(gx, gy)
                p.scale(1.0, 0.35)
                p.translate(-gx, -gy)
                p.fillRect(QRectF(gx - r, gy - r, 2 * r, 2 * r), QBrush(rg))
                p.restore()
            p.setCompositionMode(OVER)

    def _spans_front(self, p, e, cam, t):
        """Unter dem Überbau ist es dunkler; von den Kanten tropft das Regenwasser."""
        th = self.city.th
        drip = mix(th["fog"], PALE, 0.6)
        for s in self._spans_on(cam):
            # unter dem Überbau ist es dunkler - auch auf den Leuten (Leuchtendes glüht weiter)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 70 if s["kind"] == "bridge" else 45))
            p.drawPolygon(self._span_volume(s, cam))
            # Wasservorhang an den Stirnkanten
            for x in (s["x0"], s["x1"]):
                for k in range(14):
                    d = self.D_FAR + (k + _hash(k, s["seed"])) * 0.09
                    if d > 1.2:
                        break
                    q_ = self._pt(x, d, s["hu"], cam)
                    gy = persp.ground_y(d)
                    ph = (t * (1.6 + _hash(k, 7)) + _hash(k, s["seed"] + 3)) % 1.0
                    y = q_.y() + (gy - q_.y()) * ph
                    ln = 3 + 8 * persp.scale(d)
                    p.fillRect(QRectF(q_.x(), y, 1, ln), qc(drip, 120))

    # ------------------------------------------------------------------ Radfahrer (Kulisse)
    # je Zone: (mittlerer Abstand s, Gruppengröße min/max). Nur ab und zu ein Pulk wie im
    # Film - nie ein Dauerstrom.
    BIKE_RATE = [(55.0, 3, 4), (45.0, 3, 4), (30.0, 3, 6), (60.0, 3, 4), (0.0, 0, 0)]
    CADENCE = 6.5                    # rad/s Kurbel (~1 Umdrehung pro Sekunde, gemütlich)
    BIKE_BANDS = ((0.10, 0.14), (0.42, 0.46))
    PONCHO = [(40, 44, 40), (62, 52, 42), (30, 40, 50), (70, 40, 36), (52, 56, 60), (36, 30, 28)]

    def _draw_dove(self, p, e, dv, cam):
        """Weiße Taube: Körper, zwei Flügel im Schlag, leicht leuchtend im Gegenlicht."""
        d = dv["d"]
        k = persp.ppu(d) * 2.2
        x = persp.screen_x(dv["x"], d, cam)
        y = persp.ground_y(d) - dv["z"] * persp.ppu(d)
        if y < -20:
            return
        flap = math.sin(dv["t"] * 15.0)
        body = (236, 240, 240)
        p.setPen(Qt.PenStyle.NoPen)
        p.setCompositionMode(PLUS)                # weicher Schein, damit sie im Regen lesbar bleibt
        g = QRadialGradient(x, y, 10 * k)
        g.setColorAt(0, QColor(200, 210, 220, 60))
        g.setColorAt(1, QColor(0, 0, 0, 0))
        p.fillRect(QRectF(x - 10 * k, y - 10 * k, 20 * k, 20 * k), QBrush(g))
        p.setCompositionMode(OVER)
        for q, a in ((p, 255), (e, 120)):
            q.setPen(Qt.PenStyle.NoPen)
            q.setBrush(QColor(body[0], body[1], body[2], a))
            q.drawEllipse(QRectF(x - 2.2 * k, y - 1.0 * k, 4.4 * k, 2.0 * k))
            q.drawEllipse(QRectF(x + 1.6 * k, y - 1.6 * k, 1.6 * k, 1.4 * k))          # Kopf
            for s_ in (-1, 1):
                tip_y = y - flap * 3.4 * k * s_ ** 2
                q.drawPolygon(QPolygonF([QPointF(x - 1.2 * k, y), QPointF(x + 1.0 * k, y),
                                         QPointF(x - 0.4 * k + s_ * 0.6 * k, tip_y - 0.6 * k)]))
            q.drawPolygon(QPolygonF([QPointF(x - 2.0 * k, y - 0.3 * k), QPointF(x - 3.6 * k, y - 0.9 * k),
                                     QPointF(x - 3.6 * k, y + 0.5 * k)]))                    # Schwanz
        p.fillRect(QRectF(x + 2.8 * k, y - 1.1 * k, max(1.0, 0.6 * k), max(1.0, 0.4 * k)), qc((200, 150, 90)))

    # ------------------------------------------------------------------ Müll im Wind
    # je Zone: (mittlerer Abstand der Böen s, Stücke je Böe). Tyrell ist sauber.
    LITTER = [(9.0, (3, 7)), (16.0, (2, 4)), (14.0, (2, 5)), (10.0, (3, 6)), (0.0, (0, 0))]
    PAPER = [(170, 166, 150), (140, 146, 140), (120, 108, 88), (190, 150, 110), (90, 96, 92)]

    def _update_litter(self, dt, cam):
        rate, (nmin, nmax) = self.LITTER[self.city.zone % 5]
        for m in self.litter:
            m["x"] += m["vx"] * dt
            m["ph"] += m["spin"] * dt
            m["t"] += dt
            # Auftrieb in Böen, dann taumelnd wieder runter
            m["vz"] += (-9.0 + 22.0 * max(0.0, math.sin(m["t"] * 1.7 + m["seed"]))) * dt
            m["vz"] = max(-14.0, min(16.0, m["vz"]))
            m["z"] = max(0.0, m["z"] + m["vz"] * dt)
            if m["z"] <= 0.0:
                m["vx"] *= max(0.0, 1.0 - 1.6 * dt)        # liegt: Reibung, kommt fast zur Ruhe
                m["vz"] = max(0.0, m["vz"])
        half = W / 2 / persp.ppu(0.3) + 80
        self.litter = [m for m in self.litter if abs(m["x"] - cam) < half + 60][-40:]
        if rate <= 0:
            return
        self._gust -= dt
        if self._gust > 0:
            return
        rng = self.rng
        self._gust = rng.uniform(0.5, 1.5) * rate
        side = rng.choice((-1, 1))
        v = -side * rng.uniform(55, 95)
        for _ in range(rng.randint(nmin, nmax)):
            d = rng.uniform(0.05, 1.0)
            self.litter.append(dict(x=cam + side * (W / 2 / persp.ppu(d) + rng.uniform(5, 60)), d=d,
                                    z=rng.uniform(2, 26), vz=rng.uniform(-2, 8), vx=v * rng.uniform(0.7, 1.2),
                                    ph=rng.uniform(0, 6.28), spin=rng.uniform(5, 12) * rng.choice((-1, 1)),
                                    t=0.0, seed=rng.uniform(0, 6.28), col=rng.choice(self.PAPER),
                                    w=rng.uniform(3.0, 6.0)))

    def _draw_litter(self, p, m, cam):
        """Ein Blatt Papier, das sich im Wind dreht (Breite pulsiert mit der Drehung)."""
        d = m["d"]
        k = persp.ppu(d)
        x = persp.screen_x(m["x"], d, cam)
        if x < -10 or x > W + 10:
            return
        gy = persp.ground_y(d)
        y = gy - m["z"] * k
        w = max(1.0, m["w"] * k * abs(math.cos(m["ph"])))
        h = max(1.0, m["w"] * k * 0.6 * abs(math.sin(m["ph"] * 0.7)) + 0.6)
        col = mix(m["col"], self.city.th["fog"], 0.3 * (1 - d))
        lit = 0.75 + 0.35 * math.cos(m["ph"])           # Vorder-/Rückseite fangen das Licht verschieden
        p.setPen(Qt.PenStyle.NoPen)
        if m["z"] > 0.5:
            p.fillRect(QRectF(x - w / 2, gy - 0.5, w, 1), QColor(0, 0, 0, 60))
        p.fillRect(QRectF(x - w / 2, y - h / 2, w, h), qc(mul(col, lit)))

    def _update_bikes(self, dt, cam):
        rate, gmin, gmax = self.BIKE_RATE[self.city.zone % 5]
        rng = self.rng
        for b in self.bikes:
            b["x"] += b["v"] * dt
            b["ph"] += self.CADENCE * dt * abs(b["v"]) / 50.0
        k = persp.ppu(0.1)
        half = W / 2 / k + 60
        self.bikes = [b for b in self.bikes if abs(b["x"] - cam) < half + 160]
        if rate <= 0:
            return
        self._bike_next -= dt
        if self._bike_next > 0:
            return
        self._bike_next = rng.uniform(0.6, 1.4) * rate
        side = rng.choice((-1, 1))
        v = -side * rng.uniform(40, 58)
        band = rng.choice(self.BIKE_BANDS)
        d0 = rng.uniform(*band)
        x0 = cam + side * half
        for j in range(rng.randint(gmin, gmax)):
            self.bikes.append(dict(x=x0 + side * (j * rng.uniform(14, 26)), d=d0 + rng.uniform(-0.02, 0.02),
                                   v=v * rng.uniform(0.92, 1.06), ph=rng.uniform(0, 6.28),
                                   poncho=rng.choice(self.PONCHO), hat=rng.random() < 0.7,
                                   umb=rng.random() < 0.3, glow=rng.random() < 0.4, seed=rng.randint(0, 999)))

    def _draw_bike(self, p, e, b, cam, t):
        """Radfahrer im Poncho mit Kegelhut (Chinatown-Sequenz): Lampe am Lenker,
        manchmal ein Schirm. Gezeichnet in Welt-Einheiten, skaliert mit der Tiefe."""
        d = b["d"]
        k = persp.ppu(d)
        gx, gy = persp.screen_x(b["x"], d, cam), persp.ground_y(d)
        if gx < -40 or gx > W + 40:
            return
        sd = 1 if b["v"] > 0 else -1
        fog = self.city.th["fog"]
        fk = 0.25 * (1 - d)            # hinten mehr im Dunst

        def U(u, v):
            return QPointF(gx + u * k * sd, gy - v * k)

        def c_(col):
            return qc(mix(col, fog, fk))
        frame = (22, 24, 26)
        # Schatten
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 90))
        p.drawEllipse(QRectF(gx - 10 * k, gy - 1.2 * k, 20 * k, 2.4 * k))
        pen = QPen(c_(frame))
        pen.setWidthF(max(1.0, 0.7 * k))
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for wx in (-7.0, 7.0):
            c = U(wx, 4.5)
            p.drawEllipse(c, 4.5 * k, 4.5 * k)
        p.drawPolyline(QPolygonF([U(-7, 4.5), U(0, 5), U(-2, 12), U(-7, 4.5)]))
        p.drawPolyline(QPolygonF([U(0, 5), U(6, 12), U(7, 4.5)]))
        p.drawLine(U(6, 12), U(7, 14.5))
        # Beine (Kurbel)
        a = b["ph"]
        hip = U(-2, 14)
        for s_ in (0, math.pi):
            pd = U(3 * math.cos(a + s_), 5 - 3 * math.sin(a + s_))   # oben vorwärts
            kn = QPointF((hip.x() + pd.x()) / 2 + 3 * k * sd, (hip.y() + pd.y()) / 2 - 1.5 * k)
            pen = QPen(c_((20, 20, 24) if s_ == 0 else (14, 14, 16)))
            pen.setWidthF(max(1.0, 1.6 * k))
            p.setPen(pen)
            p.drawPolyline(QPolygonF([hip, kn, pd]))
        # Poncho + Arm
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c_(b["poncho"]))
        p.drawPolygon(QPolygonF([U(-6, 13), U(5, 15), U(2, 27), U(-1, 27.5)]))
        pen = QPen(c_(mul(b["poncho"], 0.7)))
        pen.setWidthF(max(1.0, 1.4 * k))
        p.setPen(pen)
        p.drawLine(U(1, 25), U(6.5, 14.5))
        p.setPen(Qt.PenStyle.NoPen)
        # Kopf + Kegelhut / Kapuze
        p.setBrush(c_((120, 96, 80)))
        p.drawEllipse(U(1, 30), 2.4 * k, 2.6 * k)
        if b["hat"]:
            p.setBrush(c_((128, 108, 76)))
            p.drawPolygon(QPolygonF([U(-5, 30.6), U(7, 30.6), U(1, 35.5)]))
            p.setBrush(c_((90, 74, 52)))
            p.drawPolygon(QPolygonF([U(-5, 30.6), U(7, 30.6), U(1, 31.6)]))
        else:
            p.setBrush(c_(mul(b["poncho"], 0.8)))
            p.drawEllipse(U(0.6, 31), 3.0 * k, 3.0 * k)
        # Schirm (Papierschirm, manchmal mit leuchtendem Schaft)
        if b["umb"]:
            shaft = CYAN if b["glow"] else (50, 46, 40)
            pen = QPen(qc(shaft))
            pen.setWidthF(max(1.0, 0.6 * k))
            for q in ((p, e) if b["glow"] else (p,)):
                q.setPen(pen)
                q.drawLine(U(3, 22), U(1, 41))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c_((176, 146, 100)))
            p.drawPolygon(QPolygonF([U(-10, 37), U(1, 43), U(12, 37), U(1, 39)]))
        # Lampe am Lenker + Lichtkegel auf dem Boden
        if True:
            hl = U(7.4, 13)
            for q in (p, e):
                q.fillRect(QRectF(hl.x() - 1, hl.y() - 1, 2, 2), qc((255, 246, 210)))
            p.setCompositionMode(PLUS)
            g = QRadialGradient(gx + 20 * k * sd, gy, 16 * k)
            g.setColorAt(0, QColor(255, 240, 200, 60))
            g.setColorAt(1, QColor(0, 0, 0, 0))
            p.save()
            p.translate(gx + 20 * k * sd, gy)
            p.scale(1.0, 0.3)
            p.translate(-(gx + 20 * k * sd), -gy)
            p.fillRect(QRectF(gx + 4 * k * sd - 16 * k if sd > 0 else gx - 36 * k, gy - 16 * k, 32 * k, 32 * k),
                       QBrush(g))
            p.restore()
            p.setCompositionMode(OVER)

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
        if not self.opt_reflections:
            return _NULL_IMG
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
        items += [(o["d"] + o["dd"] * 0.5, 2, o) for o in getattr(world, "obstacles", ())
                  if o["kind"] not in ("spinner", "stack")]
        items += [(m["d"] + 0.012, 5, m) for m in getattr(world, "manholes", ())]
        patrol = getattr(world, "patrol", None)
        if patrol is not None and patrol.get("alt", 1.0) < 1.0:
            items.append((config.LAND_DEPTH, 3, patrol))
        items += [(o["depth"], 4, o) for o in getattr(world, "origami", ()) if not o["taken"]]
        items += [(b["d"], 6, b) for b in self.bikes]
        items += [(m["d"], 7, m) for m in self.litter]
        items.sort(key=lambda it: it[0])
        for _d, kind, obj in items:
            if kind == 0:
                lit = patrol is not None and patrol["on"] > 0.3 and world.in_beam(obj)
                self._draw_actor(p, e, obj, cam, t, lit)
            elif kind == 1:
                self._draw_vehicle(p, e, obj, cam, t)
            elif kind == 2:
                self._draw_obstacle(p, e, obj, cam, t)
            elif kind == 3:
                self._draw_landing(p, e, obj, cam, t)
            elif kind == 5:
                self._draw_steam(p, e, obj, cam, t)
            elif kind == 6:
                self._draw_bike(p, e, obj, cam, t)
            elif kind == 7:
                self._draw_litter(p, obj, cam)
            else:
                self._draw_origami(p, e, obj, cam, t)

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
        peaceful = getattr(a, "peaceful", False)
        if not a.alive and a.dead_t > 0.5 and not peaceful:
            # „Kreide“-Umriss: liegende Körper bleiben auf dem nassen Asphalt lesbar
            outline = (150, 40, 64) if not a.is_replicant else (120, 170, 190)
        img, em, ax, ay, meta = sprites.get(a.look, a.anim, getattr(a, "frame", 0), hgt, a.facing,
                                            rim=rim, rim_side=side * a.facing, fog_rgb=fog_rgb, fog=fog,
                                            outline=outline)
        x0, y0 = int(cx) - ax, int(gy) - ay - lift
        if not a.alive:
            # Lache: Menschen dunkelrot, Replikanten milchig-weiß
            k = 0.0 if peaceful else min(1.0, a.dead_t / 2.5)
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
            kk = k * vehicles.VEH_SCALE
            self._spinner_lights(p, e, cx, gy, kk * 60.0 / vehicles.SPIN_L, kk, v["dir"], t + v["seed"])

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
            hy = gy - {"truck": 11.0, "bus": 12.0, "police": 8.4}.get(v["kind"], 9.0) * k * vehicles.VEH_SCALE
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

    # Gaffs Origami: Silhouetten in Welt-Einheiten (Boden y = 0, Blick nach +x)
    ORIGAMI_SHAPES = {
        "huhn": [((-4, 0), (-1, -5), (3, -5), (4, 0)), ((-4, -2), (-6.5, -7), (-2, -4)),
                 ((2, -5), (3.5, -9), (5, -8.5), (4, -5)), ((5, -8.5), (7, -8), (5, -7.6))],
        "mann": [((-0.6, 0), (-0.2, -6), (0.6, -6), (0.2, 0)), ((-3, 0), (-0.4, -5.6), (0.2, -5.2), (-2.2, 0)),
                 ((3, 0), (0.4, -5.6), (-0.2, -5.2), (2.2, 0)), ((-3.4, -6.6), (0, -7.4), (3.4, -6.6), (0, -6.2)),
                 ((-1.2, -8), (0, -9.8), (1.2, -8), (0, -7.2)), ((0.4, -4.4), (3.2, -3.4), (0.4, -3.8))],
        "schaf": [((-4.5, -2.5), (-3, -6.5), (3, -6.5), (4.5, -2.5)), ((-4, -2.5), (-3.4, 0), (-2.8, -2.5)),
                  ((3, -2.5), (3.6, 0), (4.2, -2.5)), ((3.5, -6), (6.5, -7.5), (7, -4.5), (4.5, -4))],
        "kranich": [((-6, -3), (0, -1), (6, -3), (0, -3.6)), ((-1.5, -3.2), (1, -9), (2, -3.2)),
                    ((-6, -3), (-8, -7), (-5, -3.4)), ((6, -3), (8, -7.5), (9, -7), (5, -3.4))],
        "einhorn": [((-4.5, -3), (-3.5, -7), (3.5, -7), (4.5, -3)), ((-4, -3), (-3.6, 0), (-2.8, -3)),
                    ((3, -3), (3.6, 0), (4.2, -3)), ((3, -6.5), (5.5, -10.5), (7, -9.5), (5, -6)),
                    ((6, -10), (9, -14), (6.8, -9.6)), ((-4.5, -6.6), (-7, -4), (-4.4, -5))],
    }

    def _draw_origami(self, p, e, o, cam, t):
        """Gefaltete Papierfigur am Straßenrand; blinkt alle paar Sekunden kurz auf."""
        d = o["depth"]
        k = persp.ppu(d) * 1.4
        cx = persp.screen_x(o["x"], d, cam)
        if cx < -30 or cx > W + 30:
            return
        gy = persp.ground_y(d)
        paper = (200, 210, 230) if o["kind"] == "einhorn" else (220, 222, 228)
        fold = mul(paper, 0.7)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 110))
        p.drawEllipse(QRectF(cx - 6 * k, gy - 1.2 * k, 12 * k, 2.4 * k))
        for i, poly in enumerate(self.ORIGAMI_SHAPES[o["kind"]]):
            pts = QPolygonF([QPointF(cx + x * k, gy + y * k) for x, y in poly])
            p.setBrush(qc(paper if i % 2 == 0 else fold))
            p.drawPolygon(pts)
            p.setOpacity(0.35 * getattr(self, "_reflk", 1.0))
            p.drawPolygon(QPolygonF([QPointF(cx + x * k, gy - y * k * 0.8) for x, y in poly]))
            p.setOpacity(1.0)
        # Glanzpunkt: alle ~2,4 s ein kurzer Stern
        ph = (t + o["seed"] * 0.01) % 2.4
        if ph < 0.35:
            a = 1.0 - ph / 0.35
            sy = gy - 9 * k
            r = 2 + 5 * a
            for q in (p, e):
                q.fillRect(QRectF(cx - r, sy, 2 * r + 1, 1), qc(WHITE, int(255 * a)))
                q.fillRect(QRectF(cx, sy - r, 1, 2 * r + 1), qc(WHITE, int(255 * a)))

    def _draw_parked(self, p, e, o, cam, t):
        """Geparktes Fahrzeug: Motor aus, Lichter fast dunkel, manche mit Warnblinker."""
        d = o["d"]
        k = persp.ppu(d)
        cx = persp.screen_x(o["x"], d, cam)
        if cx < -o["w"] * 2 * k or cx > W + o["w"] * 2 * k:
            return
        gy = persp.ground_y(d)
        img, em, ax, ay, _lpx = vehicles.vehicle_image(o["veh"], o["seed"], k, self.city.th["rim"], o["dir"])
        x0, y0 = int(cx) - ax, int(gy) - ay
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 140))
        p.drawEllipse(QRectF(cx - o["w"] * k * 1.1, gy - 3 * k, o["w"] * k * 2.2, 5 * k))
        p.setOpacity(min(1.0, 0.5 * getattr(self, "_reflk", 1.0)))
        p.drawImage(x0, int(gy) - (img.height() - 1 - ay), self._mirror(img))
        p.setOpacity(1.0)
        p.drawImage(x0, y0, img)
        e.setOpacity(0.12)
        e.drawImage(x0, y0, em)
        e.setOpacity(1.0)
        if o["veh"] == "police":
            kk = k * vehicles.VEH_SCALE
            self._spinner_lights(p, e, cx, gy, kk * 60.0 / vehicles.SPIN_L, kk, o["dir"], t + o["seed"])
        elif o.get("hazard") and int(t * 1.7 + o["seed"] * 0.01) % 2 == 0:
            hy = gy - 8 * k
            for sx in (cx - o["w"] * k * 0.92, cx + o["w"] * k * 0.92):
                for q in (p, e):
                    q.fillRect(QRectF(sx - 1.2 * k, hy, 2.4 * k + 1, 1.6 * k + 1), qc(AMBER))
                rg = QRadialGradient(sx, gy, 18 * k)
                rg.setColorAt(0, QColor(255, 150, 40, 60))
                rg.setColorAt(1, QColor(0, 0, 0, 0))
                p.setCompositionMode(PLUS)
                p.fillRect(QRectF(sx - 18 * k, gy - 5 * k, 36 * k, 10 * k), QBrush(rg))
                p.setCompositionMode(OVER)

    def _draw_steam(self, p, e, m, cam, t):
        """Dampfender Gulli (oder gestreifter Dampfschlot): Deckel mit Glut im Spalt,
        darüber Schwaden, die aufsteigen, wachsen, abdriften und das Neon fangen."""
        d = m["d"]
        k = persp.ppu(d)
        cx = persp.screen_x(m["x"], d, cam)
        if cx < -90 * k or cx > W + 90 * k:
            return
        gy = persp.ground_y(d)
        s = m.get("s", 0.5)
        p.setPen(Qt.PenStyle.NoPen)
        if m["stack"]:
            # Con-Ed-Schlot: orange-weiß gestreift, schwarze Kappe
            sw, sh = 3.6 * k, 14.0 * k
            p.setBrush(QColor(0, 0, 0, 120))
            p.drawEllipse(QRectF(cx - sw, gy - 1.5 * k, sw * 2, 3 * k))
            n = 6
            for i in range(n):
                col = (232, 104, 34) if i % 2 == 0 else (226, 222, 214)
                y0 = gy - sh * (i + 1) / n
                p.fillRect(QRectF(cx - sw / 2, y0, sw, sh / n + 1), qc(mul(col, 0.62)))
                p.fillRect(QRectF(cx - sw / 2, y0, sw * 0.35, sh / n + 1), qc(mul(col, 0.85)))
            p.fillRect(QRectF(cx - sw / 2 - 0.6 * k, gy - sh - 1.4 * k, sw + 1.2 * k, 1.6 * k), qc((26, 26, 32)))
            src_y, rise = gy - sh - 1.0 * k, 95.0
        else:
            p.setBrush(qc((14, 14, 20)))
            p.drawEllipse(QRectF(cx - 6.5 * k, gy - 1.3 * k, 13 * k, 2.6 * k))
            p.setBrush(Qt.BrushStyle.NoBrush)
            pen = QPen(qc((70, 72, 86)))
            pen.setWidthF(max(1.0, 0.6 * k))
            p.setPen(pen)
            p.drawEllipse(QRectF(cx - 6.5 * k, gy - 1.3 * k, 13 * k, 2.6 * k))
            p.setPen(Qt.PenStyle.NoPen)
            glow = int(90 + 80 * s)
            for q in (p, e):                                  # Glut in den Löchern
                for i in (-2, 0, 2):
                    q.fillRect(QRectF(cx + i * 1.8 * k - 0.5 * k, gy - 0.3 * k, 1.0 * k + 1, 0.6 * k + 1),
                               QColor(255, 120, 40, glow))
            src_y, rise = gy - 0.5 * k, 75.0
        # Bodennebel um den Gulli
        tint = mix((222, 222, 232), self.city.th["fog"], 0.3)
        rg = QRadialGradient(cx, gy, 34 * k)
        rg.setColorAt(0.0, QColor(tint[0], tint[1], tint[2], int(70 * s)))
        rg.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.save()
        p.translate(cx, gy)
        p.scale(1.0, 0.22)
        p.fillRect(QRectF(-34 * k, -34 * k, 68 * k, 68 * k), QBrush(rg))
        p.restore()
        # Schwaden: dichter Strahl an der Quelle, darüber aufsteigende, wachsende Ballen
        n = 22
        side = 1 if m["seed"] % 2 else -1
        rate = 0.32
        for i in range(n):
            u = (t + m["seed"] * 0.37) * rate + i / n
            age = u % 1.0
            fade = min(1.0, age / 0.05) * (1.0 - age) ** 1.6
            a = min(1.0, s * 1.25) * fade
            if a < 0.04:
                continue
            h = _hash(i * 13 + int(u), m["seed"])
            ox = (m.get("drift", 0.0) * age + age * age * (34.0 + 26 * h) * side
                  + math.sin(age * 6.0 + i * 1.7) * 3.5 * age + (h - 0.5) * 4.0 * age)
            r = (2.2 + 15.0 * age ** 0.9 + 3.5 * h) * k
            px, py = cx + ox * k, src_y - (age ** 0.8) * rise * k
            col = mix(tint, (250, 250, 255), max(0.0, 0.5 - age))     # unten heller
            rg = QRadialGradient(px, py, r)
            rg.setColorAt(0.0, QColor(col[0], col[1], col[2], int(235 * a)))
            rg.setColorAt(0.55, QColor(col[0], col[1], col[2], int(150 * a)))
            rg.setColorAt(1.0, QColor(col[0], col[1], col[2], 0))
            p.setBrush(QBrush(rg))
            p.drawEllipse(QRectF(px - r, py - r * 0.85, 2 * r, 1.7 * r))
            if age < 0.5:                                 # unten fängt der Dampf das Licht
                rg.setColorAt(0.0, QColor(col[0], col[1], col[2], int(34 * a)))
                rg.setColorAt(0.55, QColor(col[0], col[1], col[2], int(10 * a)))
                e.setBrush(QBrush(rg))
                e.setPen(Qt.PenStyle.NoPen)
                e.drawEllipse(QRectF(px - r, py - r * 0.85, 2 * r, 1.7 * r))

    def _draw_obstacle(self, p, e, o, cam, t):
        if o["kind"] == "parked":
            self._draw_parked(p, e, o, cam, t)
            return
        if o["kind"] == "tower":
            if o["d"] > 1.0:
                self._near.append(o)            # vor der Kamera: eigene, leicht unscharfe Ebene
            else:
                self._draw_tower(p, e, o, cam, t)
            return
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
        k = k * vehicles.OB_SCALE.get(kind, 1.0)      # Zeichenmaßstab wie im Bild
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
        bx = persp.screen_x(P["bx"], P["bd"], cam)
        by = persp.ground_y(P["bd"])
        rx = 34 * persp.ppu(P["bd"])
        ry = 0.13 * (persp.ground_y(1) - persp.ground_y(0))
        alt = P.get("alt", 1.0)
        sx = persp.screen_x(P["x"], 0.35, cam)
        sy = 46 + math.sin(t * 1.4) * 2.0
        if alt >= 1.0:
            return P, sx, sy + 4, bx, by, rx, ry
        k = self._land_pose(P, cam, t)
        x, yg, ppx, d = k
        nx, ny = vehicles.SPIN_NOSE
        return P, x + nx * ppx * d, yg + ny * ppx, bx, by, rx, ry

    def _land_pose(self, P, cam, t):
        """Bildposition eines landenden Spinners: (x, y_boden, px pro Zeichen-Einheit, d)."""
        alt = P.get("alt", 1.0)
        u = alt * alt * (3 - 2 * alt)
        ppx_s = 22 * 2.4 / vehicles.SPIN_L
        sx = persp.screen_x(P["x"], 0.35, cam)
        sy = 46 + math.sin(t * 1.4) * 2.0 + 10 * ppx_s
        D = config.LAND_DEPTH
        ppx_g = persp.ppu(D) * vehicles.VEH_SCALE
        gx = persp.screen_x(P["x"], D, cam)
        gy = persp.ground_y(D) - (0.0 if P.get("phase") == "landed" else 2.0 * math.sin(t * 3.0) * (1 - u))
        return (gx + (sx - gx) * u, gy + (sy - gy) * u, ppx_g + (ppx_s - ppx_g) * u, P.get("face", 1))

    def _draw_landing(self, p, e, P, cam, t):
        """Landender/gelandeter Spinner, nach Tiefe einsortiert (mit Schatten, Spiegelung,
        Turbinenglühen, Abwind und rot-blauem Lichtschein auf dem nassen Asphalt)."""
        x, yg, ppx, d = self._land_pose(P, cam, t)
        D = config.LAND_DEPTH
        gx, gy = persp.screen_x(P["x"], D, cam), persp.ground_y(D)
        alt = P.get("alt", 1.0)
        L = vehicles.SPIN_L * ppx
        # Schatten wächst, je tiefer er kommt
        sh = max(0.0, 1.0 - alt)
        if sh > 0.02:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, int(140 * sh)))
            w = persp.ppu(D) * 90 * (0.6 + 0.5 * sh)
            p.drawEllipse(QRectF(gx - w / 2, gy - 4, w, 8))
        img, em, ax, _ayc, ayg = vehicles.spinner_image(ppx, True, d, False)
        if alt < 0.25:
            p.setOpacity(min(1.0, 0.5 * getattr(self, "_reflk", 1.0)) * (1 - alt * 4))
            p.drawImage(int(x) - ax, int(gy) - (img.height() - 1 - ayg) + int(gy - yg), self._mirror(img))
            p.setOpacity(1.0)
        # Abwind: heller Luftschleier unter dem Rumpf + Gischt am Boden
        wash = P.get("wash", 0.0)
        p.setCompositionMode(PLUS)
        if alt > 0.0 or wash > 0:
            g = QLinearGradient(x, yg - 6 * ppx, x, gy)
            a = int(60 * max(wash, 0.4 if alt < 1 else 0.0))
            g.setColorAt(0, QColor(200, 210, 230, a))
            g.setColorAt(1, QColor(200, 210, 230, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(g))
            p.drawPolygon(QPolygonF([QPointF(x - L * 0.3, yg - 4 * ppx), QPointF(x + L * 0.3, yg - 4 * ppx),
                                     QPointF(x + L * 0.75, gy + 3), QPointF(x - L * 0.75, gy + 3)]))
        if wash > 0.05:
            for k in range(3):     # Druckwellen-Ringe auf dem Wasserfilm
                ph = (t * 1.6 + k / 3.0) % 1.0
                rw = L * (0.4 + 1.2 * ph)
                pen = QPen(QColor(190, 200, 230, int(90 * wash * (1 - ph))))
                pen.setWidth(1)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QRectF(gx - rw / 2, gy - rw * 0.06, rw, rw * 0.12))
            p.setPen(Qt.PenStyle.NoPen)
            if self.rng.random() < wash * 0.9:
                self.fx.puff(self.rng.uniform(-40, 40), gy - 4, wx=P["x"], depth=D, scale=1.4)
        # Rot-blauer Schein auf der nassen Straße, wenn er steht
        if P.get("phase") == "landed":
            on = int(t * 7) % 4 < 2
            c = (224, 72, 150) if on else (90, 140, 255)
            rg = QRadialGradient(gx, gy, L * 0.9)
            rg.setColorAt(0, QColor(c[0], c[1], c[2], 55))
            rg.setColorAt(1, QColor(0, 0, 0, 0))
            p.save()
            p.translate(gx, gy)
            p.scale(1.0, 0.3)
            p.translate(-gx, -gy)
            p.fillRect(QRectF(gx - L, gy - L, 2 * L, 2 * L), QBrush(rg))
            p.restore()
        p.setCompositionMode(OVER)
        self._spinner_sprite(p, e, x, yg, ppx, d, t, True, far=False, cone=alt > 0.05)
        if alt > 0.0:       # Turbinen glühen nach unten
            for q in (p, e):
                q.fillRect(QRectF(x - L * 0.32, yg - 3.6 * ppx, L * 0.5, max(1.0, ppx * 0.9)), qc((255, 200, 140)))

    def _patrol(self, p, e, world, cam, t):
        g = self._patrol_geom(world, cam, t)
        self._beam_poly = None
        if g is None:
            return
        P, sx, sy, bx, by, rx, ry = g
        on = P["on"]
        if on > 0.02:
            poly = QPolygonF([QPointF(sx - 2, sy), QPointF(bx - rx, by), QPointF(bx + rx, by), QPointF(sx + 2, sy)])
            self._beam_poly = (poly, on)
            p.setCompositionMode(PLUS)
            p.setPen(Qt.PenStyle.NoPen)
            for wf, a in ((1.0, 34), (0.55, 40)):
                pl = QPolygonF([QPointF(sx - 2, sy), QPointF(bx - rx * wf, by), QPointF(bx + rx * wf, by),
                                QPointF(sx + 2, sy)])
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
        if P.get("alt", 1.0) < 1.0:
            return          # steht/landet: wird nach Tiefe sortiert in _actors gezeichnet
        # Der Spinner selbst
        d = P["dir"] if P.get("leaving") else (1 if (P["bx"] - P["x"]) >= 0 else -1)
        self._spinner_body(p, e, sx, sy - 4, 2.4, d, t, True, True)
        # Scheinwerfer-Gondel unter dem Rumpf
        for q in (p, e):
            q.fillRect(QRectF(sx - 2, sy - 1, 4, 2), qc(WHITE))

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
    # Vordergrund je Zone: (Art, Gewicht). Nur DÜNNE Dinge direkt vor der Kamera - Kabel,
    # Masten, Rohre, Lampionschnüre. Die dicken Säulen stehen auf der anderen Straßenseite.
    FG_KINDS = [
        (("cable", 4), ("cables", 4), ("pole", 2), ("pipe", 2), ("none", 1)),
        (("cable", 3), ("cables", 3), ("pole", 3), ("lanterns", 1), ("none", 1)),
        (("cables", 4), ("lanterns", 4), ("pole", 2), ("cable", 2), ("none", 1)),
        (("cable", 3), ("pipe", 3), ("pole", 2), ("cables", 3), ("none", 1)),
        (("pole", 2), ("cable", 2), ("none", 4)),
    ]
    FG_DEPTH = 1.9           # sehr nah an der Kamera -> zieht schnell vorbei
    FG_SPACING = 190.0
    FG_BLUR = 3              # Unschärfe: Faktor des Herunterskalierens

    def _foreground(self, p, cam):
        """Dünne Requisiten direkt vor der Kamera, außerhalb der Schärfeebene: Kabel mit
        losen, pendelnden Enden, Masten mit Ampel/Schild, Rohre, Lampionschnüre. Eigene
        Ebene, die vor dem Einsetzen weichgezeichnet wird (Tiefenunschärfe)."""
        fg = self._fg_img
        fg.fill(0)
        fp = QPainter(fg)
        drawn = self._fg_draw(fp, cam)
        fp.end()
        if not drawn:
            return
        b = self.FG_BLUR
        small = fg.scaled(W // b, H // b, Qt.AspectRatioMode.IgnoreAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
        p.save()
        p.resetTransform()
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.drawImage(QRectF(0, 0, W, H), small)
        p.restore()

    def _fg_draw(self, p, cam):
        d = self.FG_DEPTH
        k = persp.ppu(d)
        spacing = self.FG_SPACING
        t = self.t
        th = self.city.th
        z = self.city.zone % len(self.FG_KINDS)
        kinds = self.FG_KINDS[z]
        tot = sum(wt for _, wt in kinds)
        dark = (5, 7, 9)
        rim = mul(th["rim"], 0.3)
        e = self._fg_e
        drawn = False
        first = math.floor((cam - W / k) / spacing) - 1
        for i in range(first, first + 7):
            wx = i * spacing + 120 * _hash(i, 3)
            x = persp.screen_x(wx, d, cam)
            if x < -300 or x > W + 300:
                continue
            r = _hash(i, 9 + z) * tot
            kind = kinds[-1][0]
            for kk, wt in kinds:
                if r < wt:
                    kind = kk
                    break
                r -= wt
            if kind == "none":
                continue
            drawn = True
            sway = math.sin(t * 0.9 + i * 1.7) * 3.0
            if kind in ("cable", "cables", "lanterns"):
                n = 1 if kind == "cable" else (2 + int(_hash(i, 4) * 2))
                for j in range(n):
                    y0 = -4 + 40 * _hash(i, 5 + j)
                    y1 = -4 + 40 * _hash(i, 15 + j)
                    span = 320 + 200 * _hash(i, 25 + j)
                    sag = 18 + 34 * _hash(i, 35 + j)
                    xa, xb = x - span / 2, x + span / 2
                    pts = []
                    for s_ in range(17):
                        u = s_ / 16
                        pts.append(QPointF(xa + (xb - xa) * u,
                                           y0 + (y1 - y0) * u + (sag + sway) * 4 * u * (1 - u)))
                    pen = QPen(qc(dark))
                    pen.setWidth(5 if j == 0 else 3)
                    p.setPen(pen)
                    p.drawPolyline(QPolygonF(pts))
                    if kind == "lanterns" and j == 0:
                        p.setPen(Qt.PenStyle.NoPen)
                        neon = th["neon"]
                        for s_ in range(2, 15, 2):
                            q_ = pts[s_]
                            c = neon[int(_hash(i * 31 + s_, 2) * len(neon))]
                            lit = self.dark < 0.4 and _hash(int(t * 3) + s_, i) > 0.04
                            for q in ((e, p) if lit and e is not None else (p,)):
                                q.setPen(Qt.PenStyle.NoPen)
                                q.setBrush(qc(c if lit else mul(c, 0.3)))
                                q.drawEllipse(QRectF(q_.x() - 6, q_.y() + 2, 12, 15))
                    # loses Ende, pendelt im Wind
                    if j == 0 and _hash(i, 45) < 0.7:
                        q0 = pts[int(4 + 8 * _hash(i, 46))]
                        ln = 40 + 90 * _hash(i, 47)
                        ang = math.sin(t * 1.3 + i) * 0.14
                        pen = QPen(qc(dark))
                        pen.setWidth(3)
                        p.setPen(pen)
                        p.drawLine(q0, QPointF(q0.x() + math.sin(ang) * ln, q0.y() + math.cos(ang) * ln))
                p.setPen(Qt.PenStyle.NoPen)
            elif kind == "pole":
                pw = 10
                p.fillRect(QRectF(int(x), 0, pw, H), qc(dark))
                p.fillRect(QRectF(int(x) + pw - 2, 0, 2, H), qc(rim))
                hy = int(H * (0.14 + 0.14 * _hash(i, 6)))
                if _hash(i, 7) < 0.5:       # Ampelkopf
                    p.fillRect(QRectF(int(x) - 8, hy, 26, 50), qc((12, 12, 14)))
                    st = int((t + _hash(i, 8) * 9) / 3.0) % 3
                    pal = config.zone_look(self.city.zone)["pal"]
                    for kk_, c in enumerate((pal[6], th["neon"][0], th["neon"][-1])):
                        on = kk_ == st and self.dark < 0.4
                        for q in ((p, e) if on and e is not None else (p,)):
                            q.fillRect(QRectF(int(x) - 3, hy + 4 + kk_ * 15, 14, 11), qc(c if on else mul(c, 0.2)))
                else:                       # Straßenschild
                    word = ("NO STOPPING", "SECTOR 4", "DANGER", "ONE WAY", "CROSS NOW")[int(_hash(i, 10) * 5)]
                    tw = pixfont.text_width(word, 2)
                    p.fillRect(QRectF(int(x) - tw // 2 - 6, hy, tw + 12, 22), qc((14, 20, 24)))
                    pixfont.draw(p, int(x) - tw // 2, hy + 4, word, mul(th["neon"][0], 0.5), 2, None)
                pen = QPen(qc(dark))
                pen.setWidth(3)
                p.setPen(pen)
                p.drawLine(QPointF(x + 4, hy - 14), QPointF(x + 240, 10 + sway))
                p.setPen(Qt.PenStyle.NoPen)
            elif kind == "pipe":
                pw = 12
                bot = int(H * (0.22 + 0.18 * _hash(i, 11)))
                p.fillRect(QRectF(int(x), 0, pw, bot), qc((10, 12, 14)))
                p.fillRect(QRectF(int(x) + 2, 0, 2, bot), qc(rim))
                for yy in range(20, bot, 46):
                    p.fillRect(QRectF(int(x) - 4, yy, pw + 8, 6), qc((18, 20, 22)))
                p.fillRect(QRectF(int(x) - 5, bot, pw + 10, 8), qc((12, 14, 16)))
                ph = (t * 1.4 + _hash(i, 12)) % 1.0
                p.fillRect(QRectF(int(x) + 5, bot + 8 + ph * (H - bot), 2, 6), qc(mix(th["fog"], PALE, 0.6), 160))
        return drawn

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
