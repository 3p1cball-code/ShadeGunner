"""Prozedurale Stadt pro Zone: Himmel, Skyline-Layer, Häuserfront, Boden.

Alles Statische wird pro Zone einmal in große QImages gerendert (welt-verankert,
kein Wrappen - die Häuserfront scrollt exakt mit der Perspektive der Figuren).
Alles, was lebt (Neon-Flackern, Laternen, Billboards, Spinner, Fackeln,
Suchscheinwerfer, Warnlichter), wird als Objektliste gehalten und pro Frame
von render/scene.py gezeichnet.
"""

import bisect
import functools
import math
import random

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (QBrush, QColor, QImage, QLinearGradient, QPainter, QPen,
                         QPolygonF, QRadialGradient)

from .. import config, persp, procgen
from . import pixfont

C = config.NOIR16
VOID, NIGHT, NAVY, INDIGO, BLUE, STEEL = C[0], C[1], C[2], C[3], C[4], C[5]
CRIMSON, SODIUM, ASH, PALE, WHITE = C[6], C[7], C[8], C[9], C[10]
SLATE = (112, 118, 132)
TEAL, CYAN, MAGENTA, AMBER, VIOLET = C[11], C[12], C[13], C[14], C[15]

W, H = config.RENDER_W, config.RENDER_H
FAR_F = 0.10      # px Scroll pro Welt-Einheit Kamera
MID_F = 0.30
CLOUD_F = 0.035
TPU = 2.0         # Bodentextur: px pro Welt-Einheit


def mul(c, f):
    return (max(0, min(255, int(c[0] * f))), max(0, min(255, int(c[1] * f))), max(0, min(255, int(c[2] * f))))


def mix(a, b, t):
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


@functools.lru_cache(maxsize=4096)
def qc(c, a=255):
    return QColor(c[0], c[1], c[2], a)


def soft_reflection(img):
    """Nasse-Straße-Reflexion, progressiv: am Kontaktpunkt (oben im gespiegelten Bild)
    fast scharf und kräftig, mit zunehmender Tiefe immer weicher und blasser - wie
    Wasser auf Asphalt, nicht wie Glas. Aus mehreren Blur-Stufen zu EINEM Bild gebacken
    (gecacht, kostet zur Laufzeit nur einen einzigen drawImage)."""
    w, h = img.width(), img.height()
    if w < 2 or h < 2:
        return img
    mir = img.mirrored(False, True)
    layers = [mir]                                    # 0 = scharf
    for hf, wf in ((3, 2), (6, 3), (12, 5)):          # 1 mild, 2 mittel, 3 stark verwischt
        sm = mir.scaled(max(1, w // wf), max(1, h // hf), Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)
        sm = sm.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio,
                       Qt.TransformationMode.SmoothTransformation)
        layers.append(sm)
    out = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(0)
    op = QPainter(out)
    # von hinten (stark verwischt, tief) nach vorn (scharf, Kontaktpunkt)
    for idx, s, e, a in ((3, 0.32, 1.00, 0.55), (2, 0.05, 0.80, 0.78),
                         (1, 0.00, 0.52, 0.9), (0, 0.00, 0.26, 1.0)):
        tmp = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        tmp.fill(0)
        t = QPainter(tmp)
        t.drawImage(0, 0, layers[idx])
        t.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor(255, 255, 255, int(255 * a)))
        if s > 0:
            grad.setColorAt(s, QColor(255, 255, 255, int(255 * a)))
        grad.setColorAt(min(0.999, e), QColor(255, 255, 255, 0))
        grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        t.fillRect(0, 0, w, h, QBrush(grad))
        t.end()
        op.drawImage(0, 0, tmp)
    op.end()
    return out


# ------------------------------------------------------------------------- Zonen-Themen

THEMES = [
    dict(  # 0 Außenbezirk: Industrie, Natriumdampf, Raffinerie-Fackeln am Horizont
        name="Außenbezirk", style="industrial",
        sky_top=(8, 6, 14), sky_mid=(44, 22, 34), sky_hor=(140, 62, 46), cloud=(54, 30, 38), cloud_lit=(150, 74, 50),
        building=(28, 28, 40), building_hi=(52, 50, 64), far=(40, 24, 34), mid=(30, 24, 38),
        lit=0.16, win=[(AMBER, 3), ((170, 120, 70), 3), (STEEL, 1)],
        neon=[AMBER, TEAL, CRIMSON, CYAN], sign_rate=0.35,
        lamp=(255, 150, 60), lamp_every=(130, 180), street=(20, 18, 26), asphalt=(32, 30, 40),
        rain=0.55, fog=(44, 28, 36), fog_amt=0.45, flames=True, spinners=1, blimp=False,
        billboards=0, searchlights=0, pyramid=False, cranes=False, rim=(140, 90, 70),
        words=["REPARATUR", "SCHROTT", "24H", "PARTS", "TANKE", "LAGER", "MOTEL", "BAR"],
        h_range=(50, 115), mid_h=(70, 170), far_h=(40, 110),
    ),
    dict(  # 1 Vorstadt: Wohnblöcke, kaltes Neonröhrenlicht
        name="Vorstadt", style="blocks",
        sky_top=(6, 8, 16), sky_mid=(20, 20, 42), sky_hor=(66, 44, 92), cloud=(30, 28, 50), cloud_lit=(90, 66, 120),
        building=(18, 22, 36), building_hi=(34, 40, 62), far=(24, 22, 42), mid=(20, 22, 40),
        lit=0.24, win=[((170, 180, 200), 3), (AMBER, 2), (CYAN, 1), ((110, 120, 200), 2)],
        neon=[CYAN, VIOLET, MAGENTA, TEAL, AMBER], sign_rate=0.5,
        lamp=(170, 230, 240), lamp_every=(150, 210), street=(14, 16, 28), asphalt=(22, 24, 38),
        rain=0.4, fog=(34, 30, 56), fog_amt=0.35, flames=False, spinners=2, blimp=False,
        billboards=1, searchlights=1, pyramid=False, cranes=False, rim=(120, 140, 200),
        words=["KIOSK", "WASCHSALON", "NUDELN", "BLOCK 7", "APOTHEKE", "PFANDHAUS", "BAR", "LIVE"],
        h_range=(110, 210), mid_h=(80, 200), far_h=(30, 90),
    ),
    dict(  # 2 Innenstadt: Neonmarkt, Starkregen, Holo-Werbung
        name="Innenstadt", style="market",
        sky_top=(8, 6, 16), sky_mid=(30, 16, 44), sky_hor=(120, 50, 120), cloud=(40, 24, 56), cloud_lit=(150, 60, 140),
        building=(16, 18, 32), building_hi=(36, 34, 64), far=(32, 22, 52), mid=(24, 20, 44),
        lit=0.30, win=[(MAGENTA, 1), (CYAN, 2), (AMBER, 2), ((170, 170, 210), 2)],
        neon=[MAGENTA, CYAN, AMBER, VIOLET, TEAL, CRIMSON], sign_rate=1.0,
        lamp=(200, 140, 230), lamp_every=(130, 190), street=(14, 12, 26), asphalt=(22, 20, 36),
        rain=1.0, fog=(48, 26, 60), fog_amt=0.4, flames=False, spinners=4, blimp=True,
        billboards=3, searchlights=2, pyramid=False, cranes=False, rim=(200, 90, 180),
        words=["NUDELN", "SUSHI", "BAR", "HOTEL", "KARAOKE", "SNAKE PIT", "YUKON", "ESPER",
               "OPEN 24", "LIVE", "CLUB", "TAXI", "DRINK", "BRADBURY"],
        h_range=(90, 240), mid_h=(110, 260), far_h=(40, 110),
    ),
    dict(  # 3 Hafen: Container, Kräne, Nebel, Rost
        name="Hafen", style="harbor",
        sky_top=(6, 8, 12), sky_mid=(22, 28, 36), sky_hor=(70, 80, 84), cloud=(34, 40, 48), cloud_lit=(90, 96, 96),
        building=(18, 20, 26), building_hi=(40, 40, 46), far=(34, 40, 48), mid=(26, 30, 38),
        lit=0.08, win=[(AMBER, 3), (TEAL, 1)],
        neon=[AMBER, TEAL, CRIMSON], sign_rate=0.3,
        lamp=(255, 150, 60), lamp_every=(160, 220), street=(14, 16, 20), asphalt=(24, 26, 30),
        rain=0.35, fog=(70, 78, 84), fog_amt=0.75, flames=True, spinners=2, blimp=False,
        billboards=0, searchlights=1, pyramid=False, cranes=True, rim=(170, 120, 80),
        words=["DOCK 9", "ZOLL", "FRACHT", "OFF-WORLD", "KAI 4", "BAR"],
        h_range=(50, 120), mid_h=(60, 160), far_h=(20, 60),
    ),
    dict(  # 4 Tyrell: Monolithe, weißes Licht, Pyramiden im Goldglühen
        name="Tyrell", style="tyrell",
        sky_top=(6, 6, 12), sky_mid=(36, 24, 30), sky_hor=(150, 90, 50), cloud=(46, 32, 34), cloud_lit=(170, 110, 60),
        building=(14, 16, 24), building_hi=(44, 44, 56), far=(40, 28, 30), mid=(24, 22, 30),
        lit=0.16, win=[(AMBER, 3), ((220, 200, 160), 2), (PALE, 1)],
        neon=[PALE, AMBER, CYAN], sign_rate=0.2,
        lamp=(230, 236, 255), lamp_every=(140, 180), street=(14, 14, 20), asphalt=(26, 26, 32),
        rain=0.3, fog=(60, 40, 36), fog_amt=0.35, flames=True, spinners=3, blimp=True,
        billboards=1, searchlights=3, pyramid=True, cranes=False, rim=(220, 180, 120),
        words=["TYRELL", "NEXUS", "SEKTOR T", "ZUTRITT"],
        h_range=(60, 140), mid_h=(50, 120), far_h=(30, 80),
    ),
]


# Ladenarten je Stil (gewichtet) und ihre Schilder
SHOP_KINDS = {
    "industrial": [("repair", 3), ("shutter", 3), ("bar", 2), ("kiosk", 2), ("diner", 2)],
    "blocks": [("kiosk", 3), ("pharmacy", 2), ("noodle", 2), ("pawn", 2), ("bar", 1), ("shutter", 2),
               ("video", 2), ("laundry", 2)],
    "market": [("noodle", 4), ("video", 3), ("bar", 2), ("kiosk", 2), ("eye", 2), ("animoid", 2), ("pawn", 1),
               ("diner", 1)],
    "harbor": [("shutter", 4), ("bar", 2), ("repair", 2), ("kiosk", 1), ("noodle", 1)],
    "tyrell": [("lobby", 4), ("shutter", 1), ("eye", 1)],
}
SHOP_WORDS = {
    "repair": ["REPARATUR", "PARTS", "SCHROTT", "MOTOREN"], "shutter": [""],
    "bar": ["BAR", "SNAKE PIT", "TAVERNE", "CLUB", "TOWS"], "kiosk": ["KIOSK", "24H", "SNACKS", "MARKT"],
    "diner": ["DINER", "IMBISS", "KAFFEE"], "pharmacy": ["APOTHEKE", "KLINIK"],
    "noodle": ["NUDELN", "RAMEN", "WHITE DRAGON", "SUSHI", "UDON"], "pawn": ["PFANDHAUS", "ANKAUF"],
    "video": ["VIDEO", "ELEKTRO", "HOLO", "ESPER"], "laundry": ["WASCHSALON"],
    "eye": ["EYE WORKS", "AUGEN"], "animoid": ["KUNSTTIERE", "ANIMOID"], "lobby": ["TYRELL", "NEXUS", "EMPFANG"],
}


def _wchoice(rng, items):
    tot = sum(w for _c, w in items)
    r = rng.random() * tot
    for c, w in items:
        r -= w
        if r <= 0:
            return c
    return items[-1][0]


# ------------------------------------------------------------------------- Bausteine

class Layer:
    """Welt-verankertes Bild: Layer-Koordinate L = Welt-x * factor."""

    def __init__(self, factor, cam_min, cam_max, height, y=0, fmt=QImage.Format.Format_ARGB32_Premultiplied):
        self.factor = factor
        self.lmin = int(cam_min * factor - W * 0.5 - 40)
        self.width = int((cam_max - cam_min) * factor + W + 80)
        self.y = y
        self.img = QImage(self.width, height, fmt)
        self.img.fill(0)

    def lx(self, L):
        """Layer-Koordinate -> Bildpixel."""
        return L - self.lmin

    def screen_x(self, L, cam):
        return L - cam * self.factor + W * 0.5

    def draw(self, p, cam, img=None, dy=0, opacity=1.0):
        img = img or self.img
        x = self.lmin - cam * self.factor + W * 0.5
        sx = max(0.0, -x)
        sw = min(img.width() - sx, W + 2)
        if sw <= 0:
            return
        if opacity < 1.0:
            p.setOpacity(opacity)
        p.drawImage(QRectF(int(x + sx), self.y + dy, int(sw), img.height()), img,
                    QRectF(int(sx), 0, int(sw), img.height()))
        if opacity < 1.0:
            p.setOpacity(1.0)


class Sign:
    """Neon-Schild mit Flacker-Verhalten. Bilder: an / aus / emit."""
    __slots__ = ("L", "y", "on", "off", "emit", "mode", "seed", "w", "h", "color")

    def __init__(self, L, y, on, off, emit, mode, seed, color):
        self.L, self.y, self.on, self.off, self.emit = L, y, on, off, emit
        self.mode, self.seed, self.color = mode, seed, color
        self.w, self.h = on.width(), on.height()

    def lit(self, t):
        k = int(t * 18.0)
        n = _hash(k, self.seed)
        if self.mode == "steady":
            return 1.0 if n > 0.004 else 0.0
        if self.mode == "buzz":
            burst = _hash(int(t * 0.7), self.seed + 7) < 0.25
            return 0.0 if (burst and n < 0.45) else 1.0
        if self.mode == "blink":
            return 1.0 if int(t * 1.6 + self.seed % 7) % 2 == 0 else 0.0
        if self.mode == "dying":
            return 1.0 if n < 0.35 or _hash(int(t * 2.0), self.seed) < 0.2 else 0.0
        return 1.0


def _hash(i, s):
    h = (i * 374761393 + s * 668265263) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF) / 65535.0


def _glyph(rng):
    """Pseudo-Kanji 5x7 als Liste gesetzter Pixel."""
    px = set()
    strokes = rng.randint(3, 5)
    for _ in range(strokes):
        kind = rng.random()
        if kind < 0.4:
            y = rng.choice((0, 2, 3, 4, 6))
            x0, x1 = rng.choice(((0, 4), (0, 2), (2, 4), (1, 3)))
            for x in range(x0, x1 + 1):
                px.add((x, y))
        elif kind < 0.8:
            x = rng.choice((0, 2, 4, 1, 3))
            y0, y1 = rng.choice(((0, 6), (0, 3), (3, 6), (1, 5)))
            for y in range(y0, y1 + 1):
                px.add((x, y))
        else:
            d = rng.choice((1, -1))
            for i in range(4):
                px.add((2 + d * (i - 1), 2 + i))
    return px


def _make_sign(rng, color, kind, word=None):
    """Erzeugt (on, off, emit) Bilder für ein Neon-Schild."""
    if kind == "vertical":
        n = rng.randint(3, 6)
        w, h = 11, n * 9 + 4
        glyphs = [_glyph(rng) for _ in range(n)]
        pts = [(3 + x, 3 + i * 9 + y) for i, g in enumerate(glyphs) for (x, y) in g]
    elif kind == "text":
        word = word or "BAR"
        tw = pixfont.text_width(word)
        w, h = tw + 8, 13
        img = pixfont.render(word, (255, 255, 255), 1, shadow=None)
        pts = []
        for y in range(img.height()):
            for x in range(img.width()):
                if img.pixelColor(x, y).alpha() > 0:
                    pts.append((4 + x, 3 + y))
    else:  # arrow/chevrons
        w, h = 22, 11
        pts = []
        for k in range(3):
            for i in range(4):
                pts.append((3 + k * 6 + i, 1 + i + 1))
                pts.append((3 + k * 6 + i, 9 - i - 1))
    bw = rng.random() < 0.6

    def build(state):
        img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        if state != "emit":
            p.fillRect(0, 0, w, h, qc((8, 8, 14), 235))
            p.setPen(qc(mul(color, 0.25 if state == "off" else 0.45)))
            p.drawRect(0, 0, w - 1, h - 1)
        col = color if state != "off" else mul(color, 0.22)
        core = mix(color, WHITE, 0.55) if state != "off" else col
        for (x, y) in pts:
            img.setPixelColor(x, y, qc(core if state == "on" and (x + y) % 3 == 0 else col))
        if state != "off" and bw:
            p.setPen(qc(color, 255 if state == "emit" else 200))
            p.drawRect(1, 1, w - 3, h - 3)
        p.end()
        return img

    return build("on"), build("off"), build("emit")


class Lamp:
    __slots__ = ("x", "L", "y", "arm", "color", "seed", "flicker")

    def __init__(self, x, L, y, arm, color, seed, flicker):
        self.x, self.L, self.y, self.arm, self.color = x, L, y, arm, color
        self.seed, self.flicker = seed, flicker

    def level(self, t):
        if not self.flicker:
            return 1.0
        n = _hash(int(t * 14), self.seed)
        if _hash(int(t * 0.5), self.seed + 3) < 0.35:
            return 0.15 if n < 0.5 else 1.0
        return 1.0


# ------------------------------------------------------------------------- Stadt

class City:
    def __init__(self, zone_index, length, seed):
        self.zone = zone_index
        self.th = THEMES[zone_index % len(THEMES)]
        self.length = length
        self.seed = seed
        self.rng = random.Random(seed * 7919 + zone_index * 104729)
        self.cam_min, self.cam_max = -120.0, length + 220.0
        self.fy = int(persp.FACADE_Y)
        self.signs, self.lamps, self.vents, self.blinks = [], [], [], []
        self.billboards, self.flames, self.lanterns, self.tvs = [], [], [], []
        self.searchlights = []
        self.exit_x = length
        self._sky()
        self._clouds()
        self._far()
        self._mid()
        self._facade()
        self._ground()
        self._fog_tex()
        self._cloud_bank()
        self._cloud_tile()
        self._air()
        # Für schnelles Culling: nach Layer-x sortiert
        self.tvs.sort(key=lambda v: v[0])
        self._tv_x = [v[0] for v in self.tvs]
        self.signs.sort(key=lambda s: s.L)
        self._sign_x = [s.L for s in self.signs]
        self.lanterns.sort(key=lambda v: v[0])
        self._lan_x = [v[0] for v in self.lanterns]

    def visible(self, items, keys, lo, hi):
        """Ausschnitt einer nach keys sortierten Liste mit lo <= key <= hi."""
        return items[bisect.bisect_left(keys, lo):bisect.bisect_right(keys, hi)]

    # ---------------------------------------------------------------- Nebel / Luftverkehr
    def _cloud_bank(self):
        """Großflächige, dichtere Nebelwolken (eine Kachel): für ziehende Schwaden."""
        th, rng = self.th, self.rng
        w, h = W * 3, 260
        img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        p.setPen(Qt.PenStyle.NoPen)
        col = mix(mix(th["fog"], th["sky_hor"], 0.5), PALE, 0.28)
        for _ in range(46):
            cx, cy = rng.uniform(0, w), rng.uniform(h * 0.15, h * 0.9)
            r = rng.uniform(70, 180)
            a = int(rng.uniform(0.55, 1.0) * 150)
            for ox in (-w, 0, w):
                g = QRadialGradient(cx + ox, cy, r)
                g.setColorAt(0.0, qc(col, a))
                g.setColorAt(0.55, qc(col, int(a * 0.4)))
                g.setColorAt(1.0, qc(col, 0))
                p.setBrush(QBrush(g))
                p.save()
                p.translate(cx + ox, cy)
                p.scale(1.0, 0.5)
                p.translate(-(cx + ox), -cy)
                p.drawEllipse(QRectF(cx + ox - r, cy - r, 2 * r, 2 * r))
                p.restore()
        p.end()
        self.bank = img

    def _cloud_tile(self):
        """Eine einzelne, weiche Nebelwolke (mit hellem Kern) - Baustein für ziehende Schwaden."""
        th = self.th
        w, h = 260, 172
        img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        p.setPen(Qt.PenStyle.NoPen)
        col = mix(mix(th["fog"], th["sky_hor"], 0.45), PALE, 0.36)
        rng = random.Random(4242)
        for _ in range(8):
            cx, cy = rng.uniform(w * 0.22, w * 0.78), rng.uniform(h * 0.32, h * 0.72)
            r = rng.uniform(46, 96)
            g = QRadialGradient(cx, cy, r)
            g.setColorAt(0.0, qc(col, 130))
            g.setColorAt(0.5, qc(col, 58))
            g.setColorAt(1.0, qc(col, 0))
            p.setBrush(QBrush(g))
            p.save()
            p.translate(cx, cy)
            p.scale(1.0, 0.6)
            p.translate(-cx, -cy)
            p.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))
            p.restore()
        p.end()
        self.cloud = img

    def _fog_tex(self):
        """Kachelbare Nebelschwaden (weiche Flecken), zwei Dichten."""
        th, rng = self.th, self.rng
        self.fog_layers = []
        for (h, n, amax, rmin, rmax) in ((90, 70, 70, 20, 60), (60, 90, 90, 14, 44)):
            w = W * 2
            img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
            img.fill(0)
            p = QPainter(img)
            p.setPen(Qt.PenStyle.NoPen)
            col = mix(mix(th["fog"], th["sky_hor"], 0.45), PALE, 0.2)
            for _ in range(n):
                cx, cy = rng.uniform(0, w), rng.uniform(h * 0.25, h * 0.8)
                r = rng.uniform(rmin, rmax)
                a = int(rng.uniform(0.35, 1.0) * amax)
                for ox in (-w, 0, w):
                    g = QRadialGradient(cx + ox, cy, r)
                    g.setColorAt(0, qc(col, a))
                    g.setColorAt(1, qc(col, 0))
                    p.setBrush(QBrush(g))
                    p.save()
                    p.translate(cx + ox, cy)
                    p.scale(1.0, 0.38)
                    p.translate(-(cx + ox), -cy)
                    p.drawEllipse(QRectF(cx + ox - r, cy - r, 2 * r, 2 * r))
                    p.restore()
            p.end()
            self.fog_layers.append(img)

    def _air(self):
        """Luftstraßen: Ketten aus Spinner-Lichtern in mehreren Höhen (fern = langsam/klein)."""
        th, rng = self.th, self.rng
        n_lanes = 2 + th["spinners"]
        self.air = []
        for i in range(n_lanes):
            far = i % 2 == 0
            self.air.append(dict(
                y=rng.uniform(26, self.fy * (0.45 if far else 0.62)),
                speed=rng.uniform(8, 16) if far else rng.uniform(18, 34),
                dir=rng.choice((-1, 1)), fac=FAR_F if far else MID_F,
                n=rng.randint(5, 10), gap=rng.uniform(28, 70), ph=rng.uniform(0, 400),
                size=1 if far else 2, slope=rng.uniform(-0.03, 0.03)))

    # ---------------------------------------------------------------- Himmel
    def _sky(self):
        th = self.th
        img = QImage(W, self.fy + 4, QImage.Format.Format_RGB32)
        p = QPainter(img)
        g = QLinearGradient(0, 0, 0, self.fy)
        g.setColorAt(0.0, qc(th["sky_top"]))
        g.setColorAt(0.55, qc(th["sky_mid"]))
        g.setColorAt(1.0, qc(th["sky_hor"]))
        p.fillRect(0, 0, W, self.fy + 4, QBrush(g))
        p.end()
        self.sky = img

    def _clouds(self):
        th, rng = self.th, self.rng
        self.cloud_layers = []
        for li, (y0, y1, a) in enumerate(((8, 70, 150), (40, 120, 120))):
            cw = W * 2
            img = QImage(cw, 150, QImage.Format.Format_ARGB32_Premultiplied)
            img.fill(0)
            p = QPainter(img)
            p.setPen(Qt.PenStyle.NoPen)
            for _ in range(90):
                cx = rng.uniform(0, cw)
                cy = rng.uniform(y0, y1)
                rw, rh = rng.uniform(30, 120), rng.uniform(4, 14)
                lit = (cy - y0) / max(1, (y1 - y0))
                col = mix(th["cloud"], th["cloud_lit"], lit * 0.8 * rng.uniform(0.5, 1.0))
                for ox in (-cw, 0, cw):
                    p.setBrush(qc(col, int(a * rng.uniform(0.4, 1.0))))
                    p.drawEllipse(QRectF(cx + ox - rw / 2, cy - rh / 2, rw, rh))
            p.end()
            self.cloud_layers.append((img, 6.0 + li * 5.0, CLOUD_F * (1 + li)))

    # ---------------------------------------------------------------- ferne Skyline
    def _far(self):
        th, rng = self.th, self.rng
        lay = Layer(FAR_F, self.cam_min, self.cam_max, self.fy + 2)
        p = QPainter(lay.img)
        base = self.fy + 2
        x = 0
        fc = th["far"]
        while x < lay.width:
            bw = rng.randint(14, 46)
            bh = rng.randint(*th["far_h"])
            top = base - bh
            col = mul(fc, rng.uniform(0.75, 1.15))
            p.fillRect(x, top, bw, bh, qc(col))
            if rng.random() < 0.4:
                p.fillRect(x + bw // 4, top - rng.randint(3, 10), max(2, bw // 3), 10, qc(col))
            if rng.random() < 0.3:
                ax = x + rng.randint(2, bw - 2)
                ah = rng.randint(6, 20)
                p.fillRect(ax, top - ah, 1, ah, qc(col))
                self.blinks.append(("far", ax + lay.lmin, top - ah, CRIMSON, rng.random() * 3))
            for wy in range(top + 3, base - 2, 4):
                for wx in range(x + 2, x + bw - 1, 3):
                    if rng.random() < th["lit"] * 0.35:
                        p.fillRect(wx, wy, 1, 1, qc(mix(col, _wchoice(rng, th["win"]), 0.45)))
            x += bw + rng.randint(-4, 6)
        # Raffinerie-Schlote mit Fackeln (Hades-Landschaft)
        if th["flames"]:
            for _ in range(int(lay.width / 260) + 2):
                sx = rng.randint(0, lay.width)
                sh = rng.randint(70, 140)
                p.fillRect(sx, base - sh, 3, sh, qc(mul(fc, 0.7)))
                p.fillRect(sx - 1, base - sh, 5, 2, qc(mul(fc, 0.6)))
                self.flames.append((sx + 1 + lay.lmin, base - sh - 1, rng.random() * 10, rng.uniform(0.7, 1.4)))
        if th["pyramid"]:
            # Zwei Tyrell-Pyramiden; die große steht in Richtung Zonenende
            for (wx, size) in ((self.length * 0.85, 1.25), (self.length * 0.4, 0.8), (self.length * 0.05, 0.6)):
                L = int(wx * FAR_F) - lay.lmin + W // 4
                self._pyramid(p, rng, L, base, int(230 * size), int(150 * size))
        p.end()
        self.far = lay

    def _pyramid(self, p, rng, cx, base, half, hgt):
        th = self.th
        col = mul(th["far"], 1.25)
        poly = QPolygonF([QPointF(cx - half, base), QPointF(cx - half * 0.12, base - hgt),
                          QPointF(cx + half * 0.12, base - hgt), QPointF(cx + half, base)])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc(col))
        p.drawPolygon(poly)
        # Schattenseite
        p.setBrush(qc(mul(col, 0.65)))
        p.drawPolygon(QPolygonF([QPointF(cx + half * 0.12, base - hgt), QPointF(cx + half, base),
                                 QPointF(cx + half * 0.35, base)]))
        # Fensterreihen: goldene Punkte in den Terrassen
        for row in range(4, hgt - 2, 4):
            y = base - row
            f = row / hgt
            hw = half * (1 - f) + half * 0.12 * f
            for x in range(int(cx - hw) + 2, int(cx + hw) - 1, 3):
                if rng.random() < 0.35:
                    p.fillRect(x, y, 1, 1, qc(AMBER if rng.random() < 0.7 else PALE))
        self.blinks.append(("far", cx + self.far_lmin_hint(), base - hgt - 2, AMBER, 0.0))

    def far_lmin_hint(self):
        return int(self.cam_min * FAR_F - W * 0.5 - 40)

    # ---------------------------------------------------------------- mittlere Skyline
    def _mid(self):
        th, rng = self.th, self.rng
        lay = Layer(MID_F, self.cam_min, self.cam_max, self.fy + 2)
        p = QPainter(lay.img)
        base = self.fy + 2
        mc = th["mid"]
        x = 0
        tops = []
        while x < lay.width:
            bw = rng.randint(24, 70)
            bh = rng.randint(*th["mid_h"])
            top = base - bh
            col = mul(mc, rng.uniform(0.8, 1.25))
            p.fillRect(x, top, bw, bh, qc(col))
            p.fillRect(x, top, 1, bh, qc(mul(col, 1.35)))
            # Stufen (Wedding-cake)
            if rng.random() < 0.45:
                sw = int(bw * rng.uniform(0.4, 0.7))
                sh = rng.randint(10, 40)
                p.fillRect(x + (bw - sw) // 2, top - sh, sw, sh, qc(col))
                top2 = top - sh
            else:
                top2 = top
            # Fenster
            wc = _wchoice(rng, th["win"])
            for wy in range(top + 4, base - 2, 4):
                for wx in range(x + 3, x + bw - 2, 3):
                    r = rng.random()
                    if r < th["lit"] * 0.8:
                        p.fillRect(wx, wy, 1, 2, qc(mix(col, wc if rng.random() < 0.7 else _wchoice(rng, th["win"]), 0.6)))
            # Antenne + Warnlicht
            if rng.random() < 0.55:
                ax = x + rng.randint(3, bw - 3)
                ah = rng.randint(8, 26)
                p.fillRect(ax, top2 - ah, 1, ah, qc(mul(col, 0.9)))
                self.blinks.append(("mid", ax + lay.lmin, top2 - ah, CRIMSON if rng.random() < 0.7 else MAGENTA,
                                    rng.random() * 3))
            tops.append((x, top2, bw))
            # Holo-Billboards
            if th["billboards"] and rng.random() < 0.09 * th["billboards"] and bh > 80:
                bbw, bbh = rng.choice(((30, 40), (40, 28), (24, 52), (52, 30)))
                bbx = x + (bw - bbw) // 2
                bby = top + rng.randint(6, max(7, bh // 3))
                p.fillRect(bbx - 1, bby - 1, bbw + 2, bbh + 2, qc(VOID))
                self.billboards.append([bbx + lay.lmin, bby, bbw, bbh, rng.randint(0, 99)])
            x += bw + rng.randint(-6, 10)
        if th["cranes"]:
            for _ in range(int(lay.width / 220) + 1):
                cx = rng.randint(0, lay.width)
                self._crane(p, lay, rng, cx, base)
        # Suchscheinwerfer-Ursprünge (von Dächern, schwenken über den Himmel)
        for _ in range(max(1, th["searchlights"]) * int(lay.width / 520 + 1)):
            self.searchlights.append((rng.randint(0, lay.width) + lay.lmin, base - rng.randint(30, 110),
                                      rng.uniform(0.18, 0.45), rng.random() * 6.28))
        p.end()
        self.mid = lay

    def _crane(self, p, lay, rng, cx, base):
        col = qc(mul(self.th["mid"], 0.75))
        h = rng.randint(90, 140)
        p.fillRect(cx, base - h, 4, h, col)
        p.fillRect(cx - 50, base - h, 90, 3, col)
        p.fillRect(cx - 50, base - h + 3, 10, 6, col)
        pen = QPen(col)
        pen.setWidth(1)
        p.setPen(pen)
        for i in range(0, h, 8):
            p.drawLine(cx, base - i, cx + 4, base - i - 8)
        p.drawLine(cx + 2, base - h - 12, cx - 48, base - h)
        p.drawLine(cx + 2, base - h - 12, cx + 38, base - h)
        p.fillRect(cx + 1, base - h - 14, 2, 14, col)
        hook = rng.randint(cx - 40, cx + 30)
        p.drawLine(hook, base - h + 3, hook, base - h + rng.randint(20, 60))
        p.setPen(Qt.PenStyle.NoPen)
        self.blinks.append(("mid", cx + 2 + lay.lmin, base - h - 15, CRIMSON, rng.random() * 3))
        self.blinks.append(("mid", cx - 48 + lay.lmin, base - h - 1, CRIMSON, rng.random() * 3))

    # ---------------------------------------------------------------- Häuserfront
    def _facade(self):
        th, rng = self.th, self.rng
        fac = Layer(persp.FACADE_PPU, self.cam_min, self.cam_max, self.fy + 1)
        emit = QImage(fac.width, self.fy + 1, QImage.Format.Format_ARGB32_Premultiplied)
        emit.fill(0)
        p, e = QPainter(fac.img), QPainter(emit)
        base = self.fy + 1
        x = 0
        style = th["style"]
        self.exit_L = int(self.exit_x * fac.factor) - fac.lmin
        gate_l, gate_r = self.exit_L - 60, self.exit_L + 60
        gate_done = False
        while x < fac.width:
            r = rng.random()
            alley = r < 0.12
            bw = rng.randint(18, 40) if alley else (
                rng.randint(60, 150) if style != "harbor" else rng.randint(50, 110))
            # Ausgang/Tor am Zonenende frei halten
            if not gate_done and x + bw > gate_l:
                bw = gate_l - x
                if bw >= 12:
                    self._building(p, e, fac, rng, x, bw, rng.randint(*th["h_range"]), base)
                self._exit_gate(p, e, fac, gate_l, base)
                gate_done = True
                x = gate_r
                continue
            if alley:
                self._alley(p, e, fac, rng, x, bw, base)
            else:
                bh = rng.randint(*th["h_range"])
                if style == "harbor" and rng.random() < 0.5:
                    self._containers(p, e, fac, rng, x, bw, base)
                else:
                    self._building(p, e, fac, rng, x, bw, bh, base)
            x += bw
        # Laternen
        lx = self.cam_min + rng.uniform(20, 80)
        while lx < self.cam_max:
            L = lx * fac.factor
            arm = rng.randint(10, 18)
            y = base - rng.randint(46, 60)
            self._lamp_post(p, fac.lx(L), y, base, arm)
            self.lamps.append(Lamp(lx, L, y, arm, th["lamp"], rng.randint(0, 9999), rng.random() < 0.18))
            lx += rng.uniform(*th["lamp_every"])
        self._street_props(p, e, fac, rng, base)
        # Nudelstände an den deterministischen Positionen (Herzen auffüllen)
        for rx in procgen.ramen_positions(self.length, self.seed, self.zone):
            lx = fac.lx(rx * fac.factor)
            if 8 <= lx <= fac.width - 150:
                self._ramen_booth(p, e, fac, int(lx), base)
        p.end()
        e.end()
        self.facade = fac
        self.facade_emit = emit
        # Nasse Fahrbahn reflektiert progressiv: am Kontaktpunkt fast scharf, nach unten
        # zunehmend verwischt und blasser. Körper (Fenster/Fassade) und Neon getrennt.
        self.facade_refl_body = soft_reflection(fac.img)
        self.facade_refl = soft_reflection(emit)

    def _win_grid(self, p, e, rng, x, top, bw, bot, fh, ww, wh, gap, dark, col_hint=None):
        th = self.th
        lit_p = th["lit"]
        wc = col_hint or _wchoice(rng, th["win"])
        y = top + 6
        while y + wh < bot - 4:
            xx = x + gap
            while xx + ww < x + bw - gap + 1:
                r = rng.random()
                if r < lit_p:
                    c = wc if rng.random() < 0.75 else _wchoice(rng, th["win"])
                    c = mul(c, rng.uniform(0.55, 0.95))
                    p.fillRect(xx, y, ww, wh, qc(c))
                    e.fillRect(xx, y, ww, wh, qc(mul(c, 0.55)))
                    if rng.random() < 0.3:   # Jalousie / Silhouette
                        p.fillRect(xx, y + wh // 2, ww, 1, qc(mul(c, 0.5)))
                    if rng.random() < 0.04:
                        self.tvs.append((xx, y, ww, wh, rng.randint(0, 999)))
                else:
                    p.fillRect(xx, y, ww, wh, qc(dark))
                    p.fillRect(xx, y, ww, 1, qc(mul(dark, 1.6)))
                xx += ww + gap
            y += fh

    def _building(self, p, e, fac, rng, x, bw, bh, base):
        th = self.th
        style = th["style"]
        top = base - bh
        col = mul(th["building"], rng.uniform(0.8, 1.2))
        hi = mul(th["building_hi"], rng.uniform(0.85, 1.1))
        g = QLinearGradient(0, top, 0, base)
        g.setColorAt(0, qc(mul(col, 0.8)))
        g.setColorAt(1, qc(mix(col, hi, 0.6)))
        p.fillRect(x, top, bw, bh, QBrush(g))
        # Kanten / Gesims
        p.fillRect(x, top, bw, 2, qc(hi))
        p.fillRect(x, top, 1, bh, qc(mul(hi, 0.9)))
        p.fillRect(x + bw - 1, top, 1, bh, qc(mul(col, 0.5)))
        dark = mul(col, 0.55)
        shop_h = rng.randint(32, 40) if style != "tyrell" else rng.randint(36, 46)
        if style == "industrial":
            self._win_grid(p, e, rng, x, top, bw, base - shop_h, 14, 6, 3, 5, dark)
            # Rolltor
            dw = int(bw * rng.uniform(0.35, 0.55))
            dx = x + rng.randint(4, bw - dw - 4)
            p.fillRect(dx, base - shop_h + 4, dw, shop_h - 4, qc(mul(hi, 0.8)))
            for yy in range(base - shop_h + 5, base, 2):
                p.fillRect(dx, yy, dw, 1, qc(mul(hi, 0.55)))
            if rng.random() < 0.5:
                p.fillRect(dx, base - shop_h + 2, dw, 2, qc(AMBER if rng.random() < 0.5 else (90, 80, 30)))
        elif style == "blocks":
            self._win_grid(p, e, rng, x, top, bw, base - shop_h, 11, 4, 5, 3, dark)
            # Balkone
            for yy in range(top + 14, base - shop_h - 6, 22):
                if rng.random() < 0.6:
                    p.fillRect(x + 3, yy, bw - 6, 2, qc(mul(hi, 1.1)))
                    for bx in range(x + 4, x + bw - 4, 3):
                        p.fillRect(bx, yy - 4, 1, 4, qc(mul(hi, 0.9)))
                    if rng.random() < 0.3:  # Wäscheleine
                        for bx in range(x + 6, x + bw - 6, 5):
                            p.fillRect(bx, yy - 7, 2, 3, qc(rng.choice((ASH, CRIMSON, BLUE, PALE))))
            # Satellitenschüsseln
            sd_lo, sd_hi = top + 8, base - shop_h - 10
            for _ in range(rng.randint(0, 3) if sd_hi > sd_lo and bw > 10 else 0):
                sx = x + rng.randint(4, bw - 6)
                sy = rng.randint(sd_lo, sd_hi)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(qc(SLATE))
                p.drawEllipse(QRectF(sx, sy, 5, 5))
        elif style == "tyrell":
            # Monolith: Lichtschlitze statt Fenster
            for xx in range(x + 8, x + bw - 8, rng.randint(18, 30)):
                p.fillRect(xx, top + 10, 1, bh - shop_h - 16, qc(mul(PALE, 0.28)))
                e.fillRect(xx, top + 10, 1, bh - shop_h - 16, qc(mul(PALE, 0.15)))
            yy = top + rng.randint(14, 30)
            p.fillRect(x + 2, yy, bw - 4, 1, qc(mul(AMBER, 0.55)))
            e.fillRect(x + 2, yy, bw - 4, 1, qc(mul(AMBER, 0.35)))
        else:
            self._win_grid(p, e, rng, x, top, bw, base - shop_h, rng.choice((12, 14, 16)), rng.randint(4, 6),
                           rng.randint(4, 7), rng.randint(3, 5), dark)
        # Feuerleiter
        if style in ("market", "blocks", "industrial") and rng.random() < 0.35 and bh > 90:
            fx = x + rng.randint(6, max(7, bw - 30))
            fw = 22
            pen = QPen(qc(mul(hi, 0.75)))
            p.setPen(pen)
            for yy in range(top + 16, base - shop_h - 4, 18):
                p.drawLine(fx, yy, fx + fw, yy)
                p.drawLine(fx, yy, fx, yy - 6)
                p.drawLine(fx + fw, yy, fx + fw, yy - 6)
                p.drawLine(fx + 2, yy, fx + fw - 2, yy + 18)
            p.setPen(Qt.PenStyle.NoPen)
        # Klimageräte, Rohre
        ay_lo, ay_hi = top + 6, base - shop_h - 8
        for _ in range(rng.randint(0, 3) if ay_hi > ay_lo and bw > 12 else 0):
            ax = x + rng.randint(2, bw - 10)
            ay = rng.randint(ay_lo, ay_hi)
            p.fillRect(ax, ay, 8, 6, qc(mul(hi, 0.9)))
            p.fillRect(ax + 1, ay + 1, 6, 4, qc(mul(col, 0.7)))
            for gx in range(ax + 2, ax + 7, 2):
                p.fillRect(gx, ay + 1, 1, 4, qc(mul(hi, 0.6)))
            if rng.random() < 0.35:
                self.vents.append((fac.lmin + ax + 4, ay - 1))
        if rng.random() < 0.4:
            px_ = x + rng.randint(2, bw - 4)
            p.fillRect(px_, top + 4, 2, bh - 6, qc(mul(hi, 0.7)))
        # Erdgeschoss
        self._shopfront(p, e, fac, rng, x, bw, base, shop_h, col, hi)
        # Dach: Tank / Antenne / Schild
        if rng.random() < 0.3 and top > 10:
            tx = x + rng.randint(4, max(5, bw - 20))
            p.fillRect(tx, top - 12, 14, 12, qc(mul(col, 0.9)))
            p.fillRect(tx + 2, top - 2, 2, 2, qc(mul(col, 0.6)))
            p.fillRect(tx + 10, top - 2, 2, 2, qc(mul(col, 0.6)))
        # Neon-Schilder
        n_signs = 0
        rate = th["sign_rate"]
        while rng.random() < rate * (0.85 if n_signs == 0 else 0.45) and n_signs < 4:
            n_signs += 1
            color = rng.choice(th["neon"])
            kind = rng.choice(("vertical", "vertical", "text", "text", "arrow")) if style == "market" else \
                rng.choice(("text", "text", "vertical", "arrow"))
            word = rng.choice(th["words"])
            on, off, em = _make_sign(rng, color, kind, word)
            if on.width() > bw + 30:
                continue
            sx = x + rng.randint(-6, max(-5, bw - on.width() + 6))
            sy_min, sy_max = max(top + 4, 4), base - shop_h - on.height() - 2
            if sy_max <= sy_min:
                sy = base - shop_h - on.height() + 2
            else:
                sy = rng.randint(sy_min, sy_max)
            mode = rng.choice(("steady", "steady", "steady", "buzz", "blink", "dying")) if style != "tyrell" \
                else "steady"
            # Halterung
            p.fillRect(sx + on.width() // 2, sy - 3, 1, 3, qc(SLATE))
            self.signs.append(Sign(fac.lmin + sx, sy, on, off, em, mode, rng.randint(0, 99999), color))
        # Lampions (Markt)
        if style == "market" and rng.random() < 0.4:
            ly = base - shop_h - rng.randint(2, 8)
            pen = QPen(qc(SLATE))
            p.setPen(pen)
            p.drawLine(x, ly - 3, x + bw, ly - 1)
            p.setPen(Qt.PenStyle.NoPen)
            for k in range(x + 4, x + bw - 2, rng.randint(8, 14)):
                self.lanterns.append((fac.lmin + k, ly + 1, rng.choice((CRIMSON, AMBER, MAGENTA)), rng.random() * 6))

    def _shopfront(self, p, e, fac, rng, x, bw, base, sh, col, hi):
        th = self.th
        top = base - sh
        p.fillRect(x, top, bw, sh, qc(mul(col, 0.7)))
        p.fillRect(x, top, bw, 2, qc(mul(hi, 1.2)))
        style = th["style"]
        kinds = SHOP_KINDS.get(style)
        if kinds:
            # Mehrere Läden nebeneinander, wenn das Haus breit genug ist
            xx = x
            while xx < x + bw - 24:
                sw = min(x + bw - xx, rng.randint(46, 84))
                if x + bw - (xx + sw) < 24:
                    sw = x + bw - xx
                self._shop(p, e, fac, rng, xx, sw, base, sh, col, hi, _wchoice(rng, kinds))
                xx += sw
            return
        if style == "industrial":
            return
        # Schaufenster
        if rng.random() < 0.85:
            ww = int(bw * rng.uniform(0.35, 0.6))
            wx = x + rng.randint(3, max(4, bw - ww - 14))
            wc = mul(_wchoice(rng, th["win"]), rng.uniform(0.45, 0.8)) if rng.random() < 0.75 else mul(col, 0.4)
            p.fillRect(wx, top + 6, ww, sh - 8, qc(wc))
            e.fillRect(wx, top + 6, ww, sh - 8, qc(mul(wc, 0.7)))
            # Ware / Silhouetten
            for k in range(wx + 2, wx + ww - 2, rng.randint(3, 6)):
                hgt = rng.randint(2, 8)
                p.fillRect(k, base - 2 - hgt, 2, hgt, qc(mul(wc, 0.35)))
            if rng.random() < 0.5:
                for k in range(wx + 3, wx + ww - 3, 5):
                    p.fillRect(k, top + 7, 1, rng.randint(2, 5), qc(mul(wc, 0.5)))
            # Tür
            dx = wx + ww + 3
            if dx + 8 < x + bw:
                p.fillRect(dx, top + 8, 8, sh - 8, qc(mul(col, 0.35)))
                p.fillRect(dx, top + 8, 8, 1, qc(mul(wc, 1.2)))
        else:
            # Rolladen
            for yy in range(top + 4, base, 2):
                p.fillRect(x + 4, yy, bw - 8, 1, qc(mul(hi, 0.7 if yy % 4 else 0.5)))
        # Markise
        if rng.random() < (0.55 if style == "market" else 0.25):
            ac = rng.choice(th["neon"] + [SLATE, CRIMSON])
            aw = int(bw * rng.uniform(0.5, 0.9))
            ax = x + (bw - aw) // 2
            poly = QPolygonF([QPointF(ax, top), QPointF(ax + aw, top), QPointF(ax + aw + 3, top + 7),
                              QPointF(ax - 3, top + 7)])
            p.setBrush(qc(mul(ac, 0.45)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPolygon(poly)
            for k in range(ax, ax + aw, 6):
                p.fillRect(k, top + 1, 3, 6, qc(mul(ac, 0.3)))
            p.fillRect(ax - 3, top + 6, aw + 6, 1, qc(mul(ac, 0.8)))

    def _shop(self, p, e, fac, rng, x, w, base, sh, col, hi, kind):
        """Ein Laden im Erdgeschoss: Schild, Schaufenster mit Innenleben, Tür."""
        th = self.th
        top = base - sh
        neon = rng.choice(th["neon"])
        frame = mul(col, 0.45)
        p.fillRect(x, top + 2, w, sh - 2, qc(frame))
        p.fillRect(x, top + 2, 1, sh - 2, qc(mul(hi, 0.8)))
        word = rng.choice(SHOP_WORDS.get(kind, [""]))
        board_h = 0
        if word and kind != "shutter":
            tw = pixfont.text_width(word)
            if tw + 6 <= w - 2:
                board_h = 10
                bx = x + (w - tw - 6) // 2
                p.fillRect(bx, top + 3, tw + 6, 9, qc((10, 10, 16)))
                p.setPen(qc(mul(neon, 0.5)))
                p.drawRect(bx, top + 3, tw + 5, 8)
                p.setPen(Qt.PenStyle.NoPen)
                pixfont.draw(p, bx + 3, top + 4, word, neon, 1, None)
                pixfont.draw(e, bx + 3, top + 4, word, neon, 1, None)
        wy = top + 4 + board_h
        wh = base - 2 - wy
        if wh < 8:
            return
        door_w = 8 if w > 40 else 0
        wx0, wx1 = x + 3, x + w - 3 - (door_w + 3 if door_w else 0)
        ww = wx1 - wx0

        def lit(xx, yy, ww_, hh_, c, k=0.7):
            p.fillRect(xx, yy, ww_, hh_, qc(c))
            e.fillRect(xx, yy, ww_, hh_, qc(mul(c, k)))

        if kind == "shutter":
            for yy in range(top + 4, base, 2):
                p.fillRect(x + 2, yy, w - 4, 1, qc(mul(hi, 0.65 if yy % 4 else 0.45)))
            # Graffiti
            gc = rng.choice((MAGENTA, CYAN, AMBER, VIOLET, CRIMSON))
            pen = QPen(qc(mul(gc, 0.7)))
            pen.setWidth(2)
            p.setPen(pen)
            gx = x + rng.randint(4, max(5, w - 30))
            pts = [QPointF(gx + i * 4, base - 10 - rng.randint(0, 9)) for i in range(rng.randint(4, 7))]
            p.drawPolyline(QPolygonF(pts))
            p.setPen(Qt.PenStyle.NoPen)
            if rng.random() < 0.4:   # Lichtspalt unten
                lit(x + 3, base - 2, w - 6, 1, AMBER, 0.6)
            return
        if kind == "lobby":
            g = QLinearGradient(0, wy, 0, base)
            g.setColorAt(0, qc(mul(PALE, 0.55)))
            g.setColorAt(1, qc(mul(AMBER, 0.45)))
            p.fillRect(x + 2, wy, w - 4, wh, QBrush(g))
            e.fillRect(x + 2, wy, w - 4, wh, qc(mul(PALE, 0.25)))
            for xx in range(x + 2, x + w - 2, 12):
                p.fillRect(xx, wy, 1, wh, qc(mul(col, 0.6)))
            p.fillRect(x + w // 2 - 10, base - 8, 20, 6, qc((20, 18, 22)))   # Empfang
            p.fillRect(x + w // 2 - 10, base - 8, 20, 1, qc(AMBER))
            return
        interior = {
            "noodle": mix(AMBER, CRIMSON, 0.3), "kiosk": (190, 196, 200), "video": (20, 24, 40),
            "pawn": mul(AMBER, 0.45), "bar": (34, 14, 34), "pharmacy": (150, 210, 200),
            "laundry": (160, 180, 200), "eye": mul(CYAN, 0.6), "animoid": (40, 30, 60),
            "diner": mix(AMBER, PALE, 0.4), "repair": mul(AMBER, 0.5),
        }.get(kind, (120, 120, 140))
        k_int = rng.uniform(0.55, 0.85)
        lit(wx0, wy, ww, wh, mul(interior, k_int), 0.6)
        if kind == "noodle":
            p.fillRect(wx0, base - 9, ww, 3, qc((26, 16, 18)))           # Theke
            p.fillRect(wx0, base - 9, ww, 1, qc(mul(AMBER, 0.9)))
            for sx in range(wx0 + 3, wx1 - 2, 7):                         # Hocker
                p.fillRect(sx, base - 5, 3, 1, qc((40, 30, 30)))
                p.fillRect(sx + 1, base - 4, 1, 4, qc((40, 30, 30)))
            for k in range(rng.randint(1, 3)):                            # Gäste
                gx = rng.randint(wx0 + 2, max(wx0 + 3, wx1 - 6))
                p.fillRect(gx, base - 15, 4, 6, qc((22, 14, 18)))
                p.fillRect(gx + 1, base - 18, 3, 3, qc((22, 14, 18)))
            self.vents.append((fac.lmin + wx0 + ww // 2, base - 12))
            for k in range(x + 4, x + w - 2, rng.randint(7, 11)):
                self.lanterns.append((fac.lmin + k, top + board_h + 2, rng.choice((CRIMSON, AMBER)), rng.random() * 6))
        elif kind == "kiosk":
            for yy in range(wy + 3, base - 3, 4):
                p.fillRect(wx0 + 1, yy + 2, ww - 2, 1, qc(mul(interior, 0.45)))
                for xx in range(wx0 + 2, wx1 - 2, 2):
                    if rng.random() < 0.7:
                        c = rng.choice((CRIMSON, AMBER, CYAN, MAGENTA, PALE, TEAL))
                        p.fillRect(xx, yy, 1, 2, qc(mul(c, 0.85)))
        elif kind == "video":
            for yy in range(wy + 2, base - 6, 7):
                for xx in range(wx0 + 2, wx1 - 6, 8):
                    self.tvs.append((xx, yy, 6, 5, rng.randint(0, 999)))
        elif kind == "pawn":
            for xx in range(wx0, wx1, 3):
                p.fillRect(xx, wy, 1, wh, qc(mul(hi, 0.5)))
            for k in range(3):
                gx = rng.randint(wx0 + 2, max(wx0 + 3, wx1 - 5))
                lit(gx, base - 8, 3, 3, rng.choice((AMBER, PALE)), 0.7)
        elif kind == "bar":
            sc_ = rng.choice((MAGENTA, CYAN, AMBER))
            cx_ = wx0 + ww // 2
            for q in (p, e):
                q.setPen(qc(sc_))
                q.setBrush(Qt.BrushStyle.NoBrush)
                q.drawEllipse(QRectF(cx_ - 5, wy + 3, 10, 7))
                q.drawLine(cx_ - 2, wy + 10, cx_ + 2, wy + 10)
                q.setPen(Qt.PenStyle.NoPen)
        elif kind == "pharmacy":
            cx_, cy_ = wx0 + ww // 2, wy + wh // 2
            for q in (p, e):
                q.fillRect(cx_ - 1, cy_ - 4, 3, 9, qc(TEAL if q is p else mul(TEAL, 1.6)))
                q.fillRect(cx_ - 4, cy_ - 1, 9, 3, qc(TEAL if q is p else mul(TEAL, 1.6)))
        elif kind == "laundry":
            for xx in range(wx0 + 3, wx1 - 6, 9):
                p.setBrush(qc((40, 44, 60)))
                p.setPen(qc(mul(PALE, 0.8)))
                p.drawEllipse(QRectF(xx, base - 9, 6, 6))
                p.setPen(Qt.PenStyle.NoPen)
        elif kind == "eye":
            cx_, cy_ = wx0 + ww // 2, wy + wh // 2
            for q in (p, e):
                q.setBrush(Qt.BrushStyle.NoBrush)
                q.setPen(qc(PALE))
                q.drawEllipse(QRectF(cx_ - 7, cy_ - 3, 14, 6))
                q.setPen(Qt.PenStyle.NoPen)
                q.fillRect(cx_ - 1, cy_ - 1, 3, 3, qc(CRIMSON if q is p else AMBER))
        elif kind == "animoid":
            for k in range(rng.randint(2, 4)):
                gx = rng.randint(wx0 + 2, max(wx0 + 3, wx1 - 8))
                p.setPen(qc(mul(hi, 0.7)))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(gx, base - 12, 7, 9)
                p.setPen(Qt.PenStyle.NoPen)
                lit(gx + 2, base - 9, 1, 1, AMBER, 1.0)
                lit(gx + 4, base - 9, 1, 1, AMBER, 1.0)
        elif kind == "diner":
            p.fillRect(wx0, base - 8, ww, 2, qc(mul(interior, 0.4)))
            for k in range(rng.randint(1, 4)):
                gx = rng.randint(wx0 + 2, max(wx0 + 3, wx1 - 6))
                p.fillRect(gx, base - 14, 4, 6, qc(mul(interior, 0.25)))
                p.fillRect(gx + 1, base - 17, 3, 3, qc(mul(interior, 0.25)))
        elif kind == "repair":
            p.fillRect(wx0 + 2, base - 7, ww - 4, 2, qc((30, 24, 20)))
            for k in range(4):
                gx = rng.randint(wx0 + 2, max(wx0 + 3, wx1 - 4))
                p.fillRect(gx, wy + 2, 1, rng.randint(3, 7), qc((30, 24, 20)))
            lit(wx0 + ww // 2, wy + 1, 3, 2, (255, 230, 180), 1.0)
        # Fensterrahmen
        p.fillRect(wx0, wy, ww, 1, qc(mul(hi, 1.1)))
        # Tür mit Lichtschein
        if door_w:
            dx = wx1 + 3
            p.fillRect(dx, base - 22, door_w, 22, qc(mul(col, 0.3)))
            if rng.random() < 0.6:
                lit(dx + 1, base - 21, door_w - 2, 20, mul(interior, 0.5), 0.5)
            lit(dx, base - 24, door_w, 1, neon, 0.8)
        # Markise
        if kind in ("noodle", "kiosk", "diner", "pawn", "laundry") and rng.random() < 0.6:
            ac = rng.choice(th["neon"] + [CRIMSON, SLATE])
            ay = top + board_h + 3
            poly = QPolygonF([QPointF(x + 1, ay), QPointF(x + w - 1, ay), QPointF(x + w + 2, ay + 6),
                              QPointF(x - 2, ay + 6)])
            p.setBrush(qc(mul(ac, 0.45)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPolygon(poly)
            for k in range(x, x + w, 6):
                p.fillRect(k, ay + 1, 3, 5, qc(mul(ac, 0.28)))
            p.fillRect(x - 2, ay + 5, w + 4, 1, qc(mul(ac, 0.85)))

    def _street_props(self, p, e, fac, rng, base):
        """Gehweg-Möbel auf Fassadenebene: Vidphon-Zellen, Zeitungsautomaten, Imbisskarren."""
        th = self.th
        x = rng.randint(30, 120)
        while x < fac.width - 40:
            kind = rng.choice(("phone", "news", "cart", "hydrant", "none", "none"))
            if abs(x + 10 - self.exit_L) < 90:
                kind = "none"
            if kind == "phone":
                p.fillRect(x, base - 30, 12, 30, qc((26, 30, 40)))
                p.fillRect(x + 2, base - 27, 8, 16, qc(mul(CYAN, 0.4)))
                e.fillRect(x + 2, base - 27, 8, 16, qc(mul(CYAN, 0.35)))
                p.fillRect(x, base - 31, 12, 2, qc(mul(th["building_hi"], 1.3)))
                pixfont.draw(p, x + 1, base - 9, "TEL", PALE, 1, None)
            elif kind == "news":
                for k in range(2):
                    c = rng.choice((CRIMSON, BLUE, AMBER))
                    p.fillRect(x + k * 7, base - 9, 6, 9, qc(mul(c, 0.6)))
                    p.fillRect(x + k * 7 + 1, base - 8, 4, 3, qc(mul(PALE, 0.6)))
            elif kind == "cart":
                c = rng.choice(th["neon"])
                p.fillRect(x, base - 12, 22, 9, qc((40, 34, 36)))
                p.fillRect(x + 1, base - 3, 3, 3, qc(VOID))
                p.fillRect(x + 18, base - 3, 3, 3, qc(VOID))
                p.fillRect(x - 2, base - 22, 26, 2, qc(mul(c, 0.6)))
                p.fillRect(x + 1, base - 20, 1, 8, qc(SLATE))
                p.fillRect(x + 20, base - 20, 1, 8, qc(SLATE))
                for q in (p, e):
                    q.fillRect(x + 2, base - 12, 18, 1, qc(c))
                self.vents.append((fac.lmin + x + 11, base - 13))
            elif kind == "hydrant":
                p.fillRect(x, base - 6, 4, 6, qc((120, 30, 40)))
                p.fillRect(x - 1, base - 5, 6, 1, qc((150, 40, 50)))
            x += rng.randint(90, 220)

    def _ramen_booth(self, p, e, fac, x, base):
        """Nudelstand: warm erleuchtete Bude, Neon-RAMEN-Schild, Banner, Noren, Lampions."""
        rng = self.rng
        w = 156
        top = base - 58
        wood_hi = (112, 78, 48)
        warm = (196, 116, 42)
        p.fillRect(x, top, w, 54, qc((26, 16, 14)))
        p.fillRect(x, top, w, 3, qc(wood_hi))
        # warmes Innenlicht (kräftig, leuchtet mit)
        for q, a in ((p, 255), (e, 235)):
            q.fillRect(x + 8, top + 15, w - 16, 30, qc(warm, a))
        # Flaschenregal (Silhouetten vor dem Licht)
        for i in range(9):
            p.fillRect(x + 12 + i * 13, top + 16, 3, rng.randint(5, 10), qc((40, 24, 18)))
        # Theke + dampfender Suppentopf
        p.fillRect(x, base - 14, w, 14, qc((32, 20, 16)))
        p.fillRect(x, base - 14, w, 2, qc(wood_hi))
        p.setBrush(qc((12, 12, 14)))
        p.drawEllipse(QRectF(x + 24, base - 22, 24, 10))
        p.setBrush(qc((200, 202, 208)))
        p.drawEllipse(QRectF(x + 26, base - 21, 20, 7))
        # Noren-Vorhang
        for i in range(6):
            c = (132, 32, 58) if i % 2 == 0 else (186, 190, 200)
            p.fillRect(x + 5 + i * 25, top + 3, 21, 13, qc(c))
        p.fillRect(x + 5, top + 3, 6 * 25 - 4, 1, qc(wood_hi))
        # Neon-RAMEN-Schild (flackert + Lichthof wie die anderen Schilder)
        on, off, em = _make_sign(rng, AMBER, "text", "RAMEN")
        sx = x + (w - on.width()) // 2
        self.signs.append(Sign(fac.lmin + sx, top - 27, on, off, em, "buzz", rng.randint(0, 99999), AMBER))
        # dampfende Schale als Bildmarke
        bx = x + w + 8
        p.fillRect(bx, top - 6, 4, 62, qc((74, 52, 34)))              # Pfosten
        for q in (p, e):
            q.setPen(Qt.PenStyle.NoPen)
            q.setBrush(qc((206, 210, 214)))
            q.drawPolygon(QPolygonF([QPointF(bx - 6, top - 30), QPointF(bx + 10, top - 30),
                                     QPointF(bx + 6, top - 20), QPointF(bx - 2, top - 20)]))
            q.setBrush(qc(AMBER))
            q.drawRect(QRectF(bx - 4, top - 32, 12, 2))
        # hohes Banner mit Kana
        p.fillRect(bx - 9, top - 6, 22, 68, qc((124, 28, 52)))
        for i in range(3):
            g = _glyph(rng)
            for (gx, gy) in g:
                p.fillRect(QRectF(bx - 7 + gx, top - 2 + i * 21 + gy, 1, 1), qc((228, 228, 234)))
        # Lampionkette über der Bude
        p.setPen(qc((90, 70, 46)))
        p.drawLine(x, top - 2, x + w, top - 2)
        p.setPen(Qt.PenStyle.NoPen)
        for k in range(5):
            lx2 = x + 16 + k * 31
            for q in (p, e):
                q.setPen(qc(CRIMSON))
                q.drawLine(lx2, top - 2, lx2, top + 3)
                q.setPen(Qt.PenStyle.NoPen)
                q.setBrush(qc(CRIMSON))
                q.drawEllipse(QRectF(lx2 - 3, top + 3, 6, 8))
        self.blinks.append(("fac", fac.lmin + x + w // 2, top - 20, AMBER, rng.random() * 3))

    def _alley(self, p, e, fac, rng, x, bw, base):
        th = self.th
        # Gasse: tiefer, dunkel, Dampf, evtl. Zaun
        p.fillRect(x, 0, bw, base, qc(mul(th["building"], 0.45)))
        p.fillRect(x + 2, base - 50, bw - 4, 50, qc(mul(th["building"], 0.3)))
        if rng.random() < 0.6:
            for k in range(x, x + bw, 3):
                p.fillRect(k, base - 22, 1, 22, qc(mul(th["building_hi"], 0.7)))
            p.fillRect(x, base - 22, bw, 1, qc(mul(th["building_hi"], 0.9)))
        self.vents.append((fac.lmin + x + bw // 2, base - 10))
        if rng.random() < 0.5:
            c = rng.choice(th["neon"])
            p.fillRect(x + bw // 2 - 1, base - 70, 2, 30, qc(mul(c, 0.6)))
            e.fillRect(x + bw // 2 - 1, base - 70, 2, 30, qc(mul(c, 0.6)))

    def _containers(self, p, e, fac, rng, x, bw, base):
        cols = [(110, 40, 40), (40, 70, 90), (90, 80, 50), (50, 60, 70), (30, 70, 70)]
        y = base
        for _ in range(rng.randint(2, 5)):
            ch = 22
            cw = bw - rng.randint(0, 20)
            c = mul(rng.choice(cols), 0.55)
            cx = x + rng.randint(0, bw - cw)
            p.fillRect(cx, y - ch, cw, ch, qc(c))
            for k in range(cx + 1, cx + cw - 1, 3):
                p.fillRect(k, y - ch + 2, 1, ch - 4, qc(mul(c, 0.7)))
            p.fillRect(cx, y - ch, cw, 1, qc(mul(c, 1.4)))
            if rng.random() < 0.3:
                txt = rng.choice(("TYRELL", "SHIMATA", "OFF-WORLD", "NEXUS"))
                img = pixfont.render(txt, mul(PALE, 0.5), 1, shadow=None)
                if img.width() < cw - 4:
                    p.drawImage(cx + 3, y - ch + 8, img)
            y -= ch
        if rng.random() < 0.5:
            self.blinks.append(("fac", fac.lmin + x + bw // 2, y - 2, AMBER, rng.random() * 3))

    def _exit_gate(self, p, e, fac, x, base):
        th = self.th
        col = mul(th["building"], 1.3)
        p.fillRect(x, 0, 120, base, qc(mul(col, 0.8)))
        p.fillRect(x + 20, base - 70, 80, 70, qc(VOID))
        p.fillRect(x + 18, base - 72, 84, 2, qc(mul(col, 1.6)))
        for k in range(base - 66, base, 6):
            p.fillRect(x + 24, k, 72, 1, qc(mul(col, 0.6)))
        label = "TYRELL CORP" if th["style"] == "tyrell" else "U-BAHN"
        self.gate = dict(L=fac.lmin + x, y=base - 92, w=120, label=label, door=(fac.lmin + x + 20, base - 70, 80, 70))

    def _lamp_post(self, p, x, y, base, arm):
        col = qc((30, 32, 44))
        p.fillRect(int(x), y, 2, base - y, col)
        p.fillRect(int(x), y, arm, 2, col)
        p.fillRect(int(x) + arm - 3, y + 2, 5, 2, qc((50, 52, 64)))

    # ---------------------------------------------------------------- Boden
    def _ground(self):
        th, rng = self.th, self.rng
        y0 = self.fy
        y1 = H
        rows = y1 - y0
        wmin = self.cam_min - config.VIEW_SPAN_NEAR / config.SCALE_FAR
        wmax = self.cam_max + config.VIEW_SPAN_NEAR / config.SCALE_FAR
        self.g_wmin = wmin
        gw = int((wmax - wmin) * TPU)
        img = QImage(gw, rows, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        asph = th["asphalt"]
        curb_row = int(persp.ground_y(0.0) - y0)

        def X(wx):
            return int((wx - wmin) * TPU)

        # Gehweg
        side = mix(asph, th["building_hi"], 0.5)
        p.fillRect(0, 0, gw, curb_row, qc(side, 235))
        for wx in range(int(wmin), int(wmax), 22):
            p.fillRect(X(wx), 0, 1, curb_row, qc(mul(side, 0.7), 235))
        p.fillRect(0, curb_row - 2, gw, 2, qc(mul(side, 1.5)))
        p.fillRect(0, curb_row, gw, 1, qc(mul(asph, 0.5)))
        # Asphalt mit Körnung
        p.fillRect(0, curb_row + 1, gw, rows - curb_row - 1, qc(asph, 205))
        for _ in range(int(gw * rows / 60)):
            gx, gy = rng.randrange(gw), rng.randrange(curb_row + 1, rows)
            p.fillRect(gx, gy, rng.choice((1, 2, 3)), 1, qc(mul(asph, rng.choice((0.6, 1.35, 1.6))), 220))
        # Rinnstein (nass)
        p.fillRect(0, curb_row + 1, gw, 2, qc(mul(asph, 0.5), 120))
        # Fahrbahnmarkierung
        lane = int(persp.ground_y(0.52) - y0)
        for wx in range(int(wmin), int(wmax), 70):
            p.fillRect(X(wx), lane, int(34 * TPU), 2, qc(mul(ASH, 0.55), 230))
        # Zebrastreifen
        cw_x = wmin + rng.uniform(200, 500)
        while cw_x < wmax:
            for k in range(7):
                sx = X(cw_x + k * 9)
                p.fillRect(sx, curb_row + 3, int(5 * TPU), rows - curb_row - 3, qc(mul(ASH, 0.3), 140))
            cw_x += rng.uniform(700, 1300)
        # Kanaldeckel (mit Dampf)
        self.manholes = []
        mx = wmin + rng.uniform(80, 200)
        while mx < wmax:
            d = rng.uniform(0.2, 0.85)
            r = int(persp.ground_y(d) - y0)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qc(mul(asph, 0.55)))
            p.drawEllipse(QRectF(X(mx) - 14, r - 3, 28, 6))
            p.setBrush(qc(mul(asph, 1.5)))
            p.drawEllipse(QRectF(X(mx) - 11, r - 2, 22, 4))
            self.manholes.append((mx, d))
            mx += rng.uniform(260, 520)
        # Pfützen: fast transparent -> Spiegelung kommt durch. Weltkoordinaten merken,
        # damit der Renderer die Reflexion darin verstärken kann (Pfützen spiegeln mehr).
        self.puddles = []
        for _ in range(int((wmax - wmin) / 11)):
            px_ = rng.uniform(0, gw)
            r = rng.randint(curb_row + 3, rows - 2)
            pw = rng.uniform(24, 92) * (0.5 + r / rows)
            ph = max(3, int(rng.uniform(3.0, 7.0) * (0.6 + r / rows)))
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            p.setBrush(qc((26, 34, 52), 70))
            p.drawEllipse(QRectF(px_, r, pw, ph))
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            # "Himmel" im Wasser: heller Schimmer oben auf der Pfütze
            p.fillRect(int(px_ + pw * 0.12), r, int(pw * 0.78), 1, qc((120, 150, 190), 150))
            p.fillRect(int(px_ + pw * 0.28), r + 1, int(pw * 0.5), 1, qc((70, 96, 130), 90))
            self.puddles.append((wmin + px_ / TPU + pw / (2 * TPU), persp.depth_at_y(y0 + r),
                                 pw / (2 * TPU), max(2.0, ph)))
        # Risse
        pen = QPen(qc(mul(asph, 0.55), 220))
        p.setPen(pen)
        for _ in range(int((wmax - wmin) / 40)):
            cx_, cy_ = rng.uniform(0, gw), rng.randint(curb_row + 3, rows - 2)
            for _k in range(rng.randint(2, 5)):
                nx, ny = cx_ + rng.uniform(-14, 14), cy_ + rng.uniform(-2, 2)
                p.drawLine(QPointF(cx_, cy_), QPointF(nx, ny))
                cx_, cy_ = nx, ny
        p.end()
        self.ground = img
        self.ground_y0 = y0

    def draw_ground(self, p, cam):
        """Mode-7-artiger Perspektivboden: pro Zeile ein Ausschnitt in Weltkoordinaten."""
        img = self.ground
        y0 = self.ground_y0
        rows = img.height()
        r = 0
        while r < rows:
            band = 2 if r < rows * 0.45 else 1     # nahe am Horizont ändert sich die Skala kaum
            band = min(band, rows - r)
            y = y0 + r
            d = persp.depth_at_y(y + band * 0.5)
            k = persp.ppu(d)
            wl = cam - (W * 0.5) / k
            sx = (wl - self.g_wmin) * TPU
            sw = W / k * TPU
            p.drawImage(QRectF(0, y, W, band), img, QRectF(sx, r, sw, band))
            r += band
