"""Requisiten der gegenüberliegenden Straßenseite (Referenz: reference/, Filmstills).

Alles hier wird einmal pro Zone in die Häuserfront gebacken (kostet zur Laufzeit
nichts). Was lebt - Feuer in Tonnen, Fußgängerampeln, Monitore, Warnlampen - wird
nur als Eintrag in eine Liste der Stadt gelegt und von render/scene.py gezeichnet.

- dicke Säulen: Beton-Monolithen mit Kreide-Graffiti, bauchig gedrehte
  Ornament-Säulen, Ampeltürme aus Kästen und Kabeln (rote Hand / grüner Pfeil)
- Verfall: Müllberge, ausgeschlachtete 60er-Wracks, Feuertonnen, Pollerkästen
- Fassaden: alt + verschnörkelt mit nachgerüsteten Kabeln, oder hypermodern

Eigener Zufallsgenerator, damit die Grundaufteilung der Stadt erhalten bleibt.
"""

import math
import random

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QLinearGradient, QPainterPath, QPen, QPolygonF

from .. import config, procgen

C = config.NOIR16
VOID, NIGHT, NAVY = C[0], C[1], C[2]
RED, SODIUM, NBLUE, PALE = C[6], C[7], C[8], C[9]
TEAL, CYAN, AMBER, GREEN = C[11], C[12], C[14], C[15]
CHALK = (196, 210, 206)

# Je Zone: wie oft welche Requisite (relative Gewichte) und wie dicht überhaupt.
# Außenbezirk abgeranzt, Innenstadt Chinatown-Säulen, Tyrell sauber.
ZONE_PROPS = [
    dict(step=(6, 30), w=dict(trash=8, wreck=5, barrel=4, bins=4, bollard=1, monolith=2, none=1)),
    dict(step=(10, 44), w=dict(trash=4, wreck=2, barrel=2, bins=4, bollard=2, monolith=3, ornate=3, none=2)),
    dict(step=(8, 40), w=dict(trash=3, barrel=1, bins=3, bollard=3, monolith=4, ornate=5, none=1)),
    dict(step=(8, 40), w=dict(trash=4, wreck=3, barrel=3, bins=3, bollard=2, monolith=3, ornate=2, none=2)),
    dict(step=(40, 90), w=dict(monolith=4, none=3)),
]
# Fassaden-Charakter je Zone: Anteil (verschnörkelt-alt, hypermodern)
ZONE_FACADE = [(0.35, 0.05), (0.3, 0.2), (0.45, 0.25), (0.25, 0.1), (0.1, 0.65)]

WIDTH = dict(trash=(30, 64), wreck=(86, 100), barrel=(9, 9), bollard=(8, 8), monolith=(36, 48),
             tower=(38, 46), ornate=(28, 38), bins=(14, 26), none=(0, 0))
# Tyrell, verlassenes Ende (Sebastians Straße): Verfall statt polierter Monolithen
DERELICT = dict(trash=4, bins=3, ornate=4, barrel=1, none=3)


def mul(c, f):
    return (max(0, min(255, int(c[0] * f))), max(0, min(255, int(c[1] * f))), max(0, min(255, int(c[2] * f))))


def mix(a, b, t):
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


def qc(c, a=255):
    return QColor(c[0], c[1], c[2], a)


def _poly(p, pts, col, a=255):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(qc(col, a))
    p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))


def _wire(p, x0, y0, x1, y1, sag, col, a=255, w=1):
    """Durchhängendes Kabel (Parabel)."""
    pen = QPen(qc(col, a))
    pen.setWidth(w)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath(QPointF(x0, y0))
    path.quadTo(QPointF((x0 + x1) / 2, max(y0, y1) + sag * 2), QPointF(x1, y1))
    p.drawPath(path)
    p.setPen(Qt.PenStyle.NoPen)


def _glyph(rng):
    """Pseudo-Schriftzeichen 5x7 (wie city._glyph, eigener Generator)."""
    px = set()
    for _ in range(rng.randint(3, 5)):
        k = rng.random()
        if k < 0.4:
            y = rng.choice((0, 2, 3, 4, 6))
            x0, x1 = rng.choice(((0, 4), (0, 2), (2, 4), (1, 3)))
            px.update((x, y) for x in range(x0, x1 + 1))
        elif k < 0.8:
            x = rng.choice((0, 2, 4, 1, 3))
            y0, y1 = rng.choice(((0, 6), (0, 3), (3, 6), (1, 5)))
            px.update((x, y) for y in range(y0, y1 + 1))
        else:
            d = rng.choice((1, -1))
            px.update((2 + d * (i - 1), 2 + i) for i in range(4))
    return px


# ============================================================================ Platzierung

def furnish(city, p, e, fac, base):
    """Verteilt die Requisiten über die Häuserfront der Zone."""
    th = city.th
    z = city.zone % len(ZONE_PROPS)
    cfg = ZONE_PROPS[z]
    rng = random.Random(city.seed * 7177 + z * 31 + 5)
    busy = []
    for rx in procgen.ramen_positions(city.length, city.seed, city.zone):
        lx = fac.lx(rx * fac.factor) - 88
        busy.append((lx - 14, lx + 190))
    busy.append((city.exit_L - 72, city.exit_L + 72))
    if getattr(city, "sebastian_span", None):
        busy.append(city.sebastian_span)
    # Unter den Brücken: Feuertonnen, Müll und Wracks - dort hausen die, die sonst nirgends sind
    for s in getattr(city, "spans", ()):
        if s["kind"] != "bridge" or z == 4:
            continue
        a = int(fac.lx(s["x0"] * fac.factor))
        b = int(fac.lx(s["x1"] * fac.factor))
        xx = a + rng.randint(0, 6)
        while xx < b - 10:
            kind = rng.choice(("barrel", "barrel", "trash", "wreck", "bins", "barrel"))
            w = rng.randint(*WIDTH[kind])
            if xx + w > b + 6:
                break
            if not any(p_ < xx + w and xx < q_ for p_, q_ in busy):
                _place(city, p, e, fac, rng, kind, xx, base, w)
            xx += w + rng.randint(2, 12)
        busy.append((a - 4, b + 4))
    kinds = list(cfg["w"].keys())
    weights = list(cfg["w"].values())
    x = rng.randint(10, 60)
    last = None
    der_k, der_w = list(DERELICT.keys()), list(DERELICT.values())
    der_from = city.length * (config.EMPTY_FROM - 0.04) * fac.factor - fac.lmin if z == 4 else 1e9
    while x < fac.width - 40:
        if x > der_from:
            kind = rng.choices(der_k, der_w)[0]
        else:
            kind = rng.choices(kinds, weights)[0]
        if kind == last and kind in ("wreck", "tower", "ornate"):
            kind = "none"
        w0, w1 = WIDTH[kind]
        w = rng.randint(w0, w1)
        if kind != "none" and not any(a < x + w and x < b for a, b in busy):
            _place(city, p, e, fac, rng, kind, x, base, w)
            last = kind
            # Säulen stehen oft in Reihe (Kolonnade wie im Chinatown-Set)
            if kind in ("monolith", "ornate") and rng.random() < 0.55:
                x += w + rng.randint(40, 70)
                if x < fac.width - 40 and not any(a < x + w and x < b for a, b in busy):
                    _place(city, p, e, fac, rng, kind, x, base, w)
        x += w + rng.randint(*cfg["step"])


# Silhouette, die das Leuchten der Läden dahinter verdeckt (x-Rand, Höhe über base)
OCCLUDE = dict(monolith=(4, None), ornate=(4, None), tower=(8, 92), trash=(2, 16), wreck=(2, 14),
               barrel=(1, 11), bollard=(1, 12), bins=(1, 11))


def _place(city, p, e, fac, rng, kind, x, base, w):
    mx, h = OCCLUDE[kind]
    top = 0 if h is None else base - h
    e.setCompositionMode(e.CompositionMode.CompositionMode_Clear)
    e.fillRect(QRectF(x + mx, top, w - 2 * mx, base - top), QColor(0, 0, 0, 0))
    e.setCompositionMode(e.CompositionMode.CompositionMode_SourceOver)
    DRAW[kind](city, p, e, fac, rng, x, base, w)


# ============================================================================ Säulen

def monolith(city, p, e, fac, rng, x, base, w):
    """Beton-Monolith, der oben im Dunkel verschwindet; Kreide-Graffiti (Schriftzeichen)."""
    th = city.th
    clean = th["style"] == "tyrell"
    sw = w - 8                                   # Schaftbreite unten
    cx = x + w / 2
    c = mix(th["building_hi"], (60, 64, 62), 0.5)
    c = mul(c, rng.uniform(0.8, 1.05) * (0.7 if clean else 1.0))
    ph = rng.randint(9, 14)
    top_w = sw - 4
    g = QLinearGradient(0, 0, 0, base)
    g.setColorAt(0.0, qc(mul(c, 0.25)))
    g.setColorAt(0.55, qc(mul(c, 0.6)))
    g.setColorAt(1.0, qc(c))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(g))
    p.drawPolygon(QPolygonF([QPointF(cx - top_w / 2, 0), QPointF(cx + top_w / 2, 0),
                             QPointF(cx + sw / 2, base - ph), QPointF(cx - sw / 2, base - ph)]))
    # Schattenseite + Streiflicht (Neon von der Straße)
    _poly(p, [(cx + top_w / 2 - 3, 0), (cx + top_w / 2, 0), (cx + sw / 2, base - ph), (cx + sw / 2 - 4, base - ph)],
          mul(c, 0.45), 200)
    rim = mul(th["rim"], 0.5)
    for y in range(int(base * 0.35), base - ph):
        k = (y - base * 0.35) / (base * 0.65)
        xl = cx - top_w / 2 + (sw - top_w) / 2 * (y / (base - ph))
        p.fillRect(QRectF(int(xl), y, 1, 1), qc(rim, int(60 + 120 * k)))
    # Sockel (Pyramidenstumpf)
    _poly(p, [(cx - sw / 2 - 1, base - ph), (cx + sw / 2 + 1, base - ph), (x + w, base), (x, base)], mul(c, 0.9))
    p.fillRect(QRectF(int(cx - sw / 2 - 1), base - ph, sw + 2, 1), qc(mul(c, 1.35)))
    _poly(p, [(cx + sw / 2 - 2, base - ph), (cx + sw / 2 + 1, base - ph), (x + w, base), (x + w - 5, base)],
          mul(c, 0.55))
    # Fugen
    y = base - ph - rng.randint(14, 22)
    while y > 20:
        xl = cx - top_w / 2 + (sw - top_w) / 2 * (y / (base - ph))
        p.fillRect(QRectF(int(xl) + 1, y, int(top_w + (sw - top_w) * y / (base - ph)) - 2, 1), qc(mul(c, 0.7)))
        y -= rng.randint(16, 26)
    if clean:
        # Tyrell: polierter Stein, eine bernsteinfarbene Lichtfuge
        for q, k in ((p, 0.7), (e, 0.45)):
            q.fillRect(QRectF(int(cx) - 1, 30, 1, base - ph - 34), qc(mul(AMBER, k)))
        return
    # Schmutzfahnen
    for _ in range(rng.randint(2, 5)):
        sx = int(cx - sw / 2 + rng.uniform(2, sw - 2))
        sy = rng.randint(int(base * 0.4), base - ph - 6)
        p.fillRect(QRectF(sx, sy, 1, rng.randint(6, 24)), qc(mul(c, 0.55), 160))
    # Kreide-Graffiti: Spalten aus Schriftzeichen, unregelmäßig, blass
    for col in range(rng.choice((1, 2, 2))):
        gx = int(cx - sw / 2 + 2 + col * (sw / 2 - 1))
        gy = base - ph - 10 - rng.randint(0, 8)
        for _ in range(rng.randint(3, 7)):
            a = rng.randint(70, 150)
            for (px, py) in _glyph(rng):
                if px < sw / 2 - 2:
                    p.fillRect(QRectF(gx + px, gy - 7 + py, 1, 1), qc(CHALK, a))
            gy -= 9
            if gy < base * 0.45:
                break
    if rng.random() < 0.4:        # Kritzelei
        pen = QPen(qc(CHALK, 90))
        p.setPen(pen)
        y0 = base - ph - rng.randint(4, 16)
        p.drawLine(QPointF(cx - sw / 2 + 2, y0), QPointF(cx + sw / 2 - 3, y0 - rng.randint(-3, 3)))
        p.setPen(Qt.PenStyle.NoPen)
    # Plakatfetzen
    if rng.random() < 0.35:
        px_ = int(cx - sw / 2 + rng.uniform(1, sw - 8))
        py_ = rng.randint(int(base * 0.6), base - ph - 12)
        pc = rng.choice(((170, 160, 130), (150, 60, 50), (90, 120, 120)))
        p.fillRect(QRectF(px_, py_, rng.randint(5, 8), rng.randint(6, 10)), qc(mul(pc, 0.55)))


def _bulb(p, cx, y, hseg, half_max, stone, tex, rng, min_r=0.55):
    """Ein bauchiger Säulenring von y nach oben (hseg Zeilen). tex: 'twist' (gedrehte
    Kanneluren), 'lobes' (große runde Wülste), 'carved' (geschnitzte Knollen)."""
    twist = rng.choice((0.8, -0.8, 1.0))
    n_lobe = rng.choice((5, 6))
    rows = []
    for j in range(hseg):
        t = j / max(1, hseg - 1)
        half = half_max * (min_r + (1.0 - min_r) * math.sin(math.pi * t) ** 0.8)
        yy = y - j - 1
        rows.append((yy, half))
        x0, x1 = int(cx - half), int(cx + half)
        vert = 0.72 + 0.28 * math.sin(math.pi * t)
        for xx in range(x0, x1 + 1):
            u = max(-1.0, min(1.0, (xx - cx) / max(1.0, half)))
            a = math.asin(u)
            light = (0.42 + 0.62 * max(0.0, 1.0 - (u + 0.38) ** 2)) * vert
            if tex == "twist":
                if ((xx - cx) + j * twist) % 4 < 1.4:
                    light *= 0.58
            elif tex == "lobes":
                lob = max(0.0, math.cos(a * n_lobe))
                light *= 0.32 + 0.95 * lob * (0.45 + 0.55 * math.sin(math.pi * t))
            else:  # carved
                rr = (t * 2.0) % 1.0
                off = 0.0 if t < 0.5 else math.pi / 7
                lump = max(0.0, math.cos(a * 7 + off)) * math.sin(math.pi * rr)
                light *= 0.3 + 0.95 * lump
            p.fillRect(QRectF(xx, yy, 1, 1), qc(mul(stone, light)))
    return y - hseg, rows


def ornate(city, p, e, fac, rng, x, base, w):
    """Ornament-Säule wie im Chinatown-Set: mehrere bauchige Ringe übereinander -
    unten gedreht und mit Plakatfetzen beklebt, darüber große runde Wülste, oben eine
    Krone aus geschnitzten Knollen; dann der schlanke Schaft ins Dunkel."""
    th = city.th
    stone = mul(rng.choice(((110, 84, 62), (100, 80, 64), (86, 76, 64))), rng.uniform(0.85, 1.05))
    rim = th["rim"]
    cx = x + w / 2
    half_max = w / 2 - 1
    u = w / 36.0
    plinth = max(4, int(5 * u))

    def collar(y, half):
        p.fillRect(QRectF(int(cx - half), y - 2, int(2 * half), 2), qc(mul(stone, 0.45)))
        for bx in range(int(cx - half) + 1, int(cx + half), 2):
            p.fillRect(QRectF(bx, y - 2, 1, 1), qc(mul(stone, 1.15)))
        return y - 2

    p.fillRect(QRectF(x + 1, base - plinth, w - 2, plinth), qc(mul(stone, 0.7)))
    p.fillRect(QRectF(x + 1, base - plinth, w - 2, 1), qc(mul(stone, 1.15)))
    y = base - plinth
    y, rows_a = _bulb(p, cx, y, int(rng.randint(20, 24) * u), half_max * 0.88, stone, "twist", rng, 0.6)
    # Plakatfetzen auf dem unteren Ring
    for _ in range(rng.randint(2, 4)):
        yy, half = rows_a[rng.randrange(len(rows_a) // 5, max(len(rows_a) // 5 + 1, len(rows_a) * 4 // 5))]
        pw, ph = rng.randint(3, 5), rng.randint(4, 7)
        px = cx + rng.uniform(-half * 0.8, half * 0.4)
        pc = mul(rng.choice(((190, 170, 150), (170, 110, 120), (120, 140, 160), (200, 190, 140))), 0.55)
        p.fillRect(QRectF(int(px), int(yy - ph / 2), pw, ph), qc(pc, 210))
        p.fillRect(QRectF(int(px), int(yy - ph / 2) + 1, 1, ph - 2), qc(mul(pc, 0.6), 200))
    y = collar(y, half_max * 0.62)
    y, _ = _bulb(p, cx, y, int(rng.randint(11, 14) * u), half_max * 0.95, stone, "lobes", rng, 0.6)
    y = collar(y, half_max * 0.7)
    y, _ = _bulb(p, cx, y, int(rng.randint(12, 15) * u), half_max, stone, "carved", rng, 0.72)
    # Kapitell
    p.fillRect(QRectF(int(cx - half_max * 0.9), y - 3, int(half_max * 1.8), 3), qc(mul(stone, 0.8)))
    p.fillRect(QRectF(int(cx - half_max * 0.9), y - 3, int(half_max * 1.8), 1), qc(mul(stone, 1.2)))
    y -= 3
    # Schaft ins Dunkel
    sw = int(w * 0.42)
    g = QLinearGradient(0, 0, 0, y)
    g.setColorAt(0.0, qc(mul(stone, 0.1)))
    g.setColorAt(1.0, qc(mul(stone, 0.5)))
    p.fillRect(QRectF(int(cx - sw / 2), 0, sw, y), QBrush(g))
    p.fillRect(QRectF(int(cx - sw / 2), int(y * 0.4), 1, int(y * 0.6)), qc(mul(rim, 0.4), 140))
    # Streiflicht (Neonseite)
    p.fillRect(QRectF(int(cx - half_max * 0.9), base - plinth - 16, 1, 10), qc(mul(rim, 0.55), 150))


def _hood_box(p, x, y, w, h, col, side, hood=True):
    """Kasten mit schräger Blende (Visier) zur Seite: wie die Ampelköpfe im Film."""
    p.fillRect(QRectF(x, y, w, h), qc(col))
    p.fillRect(QRectF(x, y, w, 1), qc(mul(col, 1.45)))
    p.fillRect(QRectF(x + (w - 1 if side < 0 else 0), y, 1, h), qc(mul(col, 1.25)))
    p.fillRect(QRectF(x + (0 if side < 0 else w - 1), y, 1, h), qc(mul(col, 0.55)))
    p.fillRect(QRectF(x + 1, y + h - 2, w - 2, 1), qc(mul(col, 0.6)))
    if hood:
        ex = x + (w if side > 0 else 0)
        _poly(p, [(ex, y - 1), (ex + side * 6, y - 4), (ex + side * 6, y), (ex, y + h * 0.6)], mul(col, 0.85))
        _poly(p, [(ex + side * 6, y - 4), (ex + side * 7, y - 4), (ex + side * 7, y + 1), (ex + side * 6, y)],
              mul(col, 0.5))


def tower(city, p, e, fac, rng, x, base, w):
    """Ampelturm (Syd Mead): massiver gerippter Sockel mit Aufklebern, darauf Kästen
    mit schrägen Blenden, ein Kasten mit runder Signallampe, ein Monitor, Kabel - und
    oben die Fußgängerampel (grüner Pfeil / rote Hand) mit eigener Blende."""
    th = city.th
    rim = th["rim"]
    cx = x + w // 2
    rust = [(96, 46, 32), (80, 44, 36), (70, 56, 46), (90, 62, 40)]

    def rc():
        return mul(rng.choice(rust), rng.uniform(0.75, 1.0))
    # Sockel: dick, mit Rippen und Aufkleber-Streifen
    pw = rng.randint(12, 15)
    ph = rng.randint(34, 42)
    px = cx - pw // 2
    col = mul((44, 30, 26), rng.uniform(0.8, 1.1))
    p.fillRect(QRectF(px, base - ph, pw, ph), qc(col))
    for xx in range(px + 1, px + pw - 1, 2):
        p.fillRect(QRectF(xx, base - ph + 2, 1, ph - 3), qc(mul(col, 0.6)))
    p.fillRect(QRectF(px, base - ph, 1, ph), qc(mul(rim, 0.35)))
    for _ in range(rng.randint(2, 4)):                    # Aufkleber mit Schriftzeichen
        sx = px + rng.randint(1, pw - 3)
        sy = base - rng.randint(6, ph - 4)
        sc = rng.choice(((170, 40, 40), (190, 180, 160), (200, 170, 60)))
        for j in range(rng.randint(3, 8)):
            if rng.random() < 0.7:
                p.fillRect(QRectF(sx, sy - j, rng.choice((1, 2)), 1), qc(mul(sc, 0.75)))
    p.fillRect(QRectF(px - 2, base - 3, pw + 4, 3), qc((24, 22, 22)))
    # unterer Kasten links am Sockel
    lb = (px - rng.randint(10, 13), base - ph + rng.randint(8, 14), rng.randint(10, 13), rng.randint(12, 15))
    _hood_box(p, lb[0], lb[1], lb[2], lb[3], rc(), -1, hood=False)
    p.fillRect(QRectF(lb[0] + 2, lb[1] + 3, lb[2] - 4, 1), qc((20, 18, 18)))
    # mittlere Ebene: links Blendenkasten, Mitte Kasten mit runder Lampe, rechts Blendenkasten
    my = base - ph - rng.randint(1, 3)
    cbw, cbh = rng.randint(11, 13), rng.randint(10, 12)
    cbx = cx - cbw // 2
    cc = rc()
    _hood_box(p, cbx, my - cbh, cbw, cbh, cc, 1, hood=False)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(qc(mul(cc, 0.6)))
    p.drawEllipse(QRectF(cx - 3.5, my - cbh + 2.5, 7, 7))
    lamp_c = rng.choice((RED, AMBER))
    city.blinks.append(("fac", fac.lmin + cx, my - cbh + 6, lamp_c, rng.random() * 3))
    for _ in range(2):                                     # rote Pinselzeichen
        p.fillRect(QRectF(cbx + rng.randint(1, cbw - 2), my - rng.randint(2, cbh - 1), 1, 2), qc((150, 40, 36)))
    bw_l, bh_l = rng.randint(11, 14), rng.randint(9, 12)
    _hood_box(p, cbx - bw_l, my - bh_l - rng.randint(2, 5), bw_l, bh_l, rc(), -1)
    bw_r, bh_r = rng.randint(11, 14), rng.randint(9, 12)
    ry = my - bh_r - rng.randint(0, 3)
    _hood_box(p, cbx + cbw, ry, bw_r, bh_r, rc(), 1)
    for (bx, by) in ((cbx + cbw + 3, ry + 3), (cbx + cbw + 6, ry + 3)):   # Schraubdeckel
        p.fillRect(QRectF(bx, by, 2, 2), qc((24, 20, 18)))
    # Mast + Fußgängerampel
    top = my - cbh - rng.randint(12, 18)
    p.fillRect(QRectF(cx - 1, top, 3, my - cbh - top), qc((30, 28, 28)))
    sw_, sh_ = 19, 11
    sx = cx - 7
    sy = top - sh_
    p.fillRect(QRectF(sx - 1, sy - 1, sw_ + 2, sh_ + 2), qc((30, 24, 22)))
    city.walks.append((fac.lmin + sx + 1, sy + 1, rng.uniform(0, 8), 8))
    _hood_box(p, sx + sw_ + 1, sy - 1, rng.randint(8, 11), sh_ + 2, rc(), 1)
    p.fillRect(QRectF(sx - 1, sy + sh_ + 1, sw_ + 2, 2), qc((22, 20, 20)))
    # Monitor in einem der Kästen
    if rng.random() < 0.6:
        mx, my2 = lb[0] + 2, lb[1] + 5
        p.fillRect(QRectF(mx - 1, my2 - 1, lb[2] - 2, 7), qc((18, 18, 22)))
        city.tvs.append((mx, my2, lb[2] - 4, 5, rng.randint(0, 999)))
    # Kabel hängen herab
    for _ in range(rng.randint(3, 5)):
        x0 = cx + rng.randint(-12, 14)
        y0 = my - rng.randint(2, 14)
        _wire(p, x0, y0, cx + rng.randint(-10, 10), base - rng.randint(0, 6), rng.uniform(2, 6), (14, 12, 12), 235)


# ============================================================================ Verfall

def trash(city, p, e, fac, rng, x, base, w):
    """Müllberg: Papier, Säcke, Kisten, Reifen, Paletten."""
    th = city.th
    items = []
    for _ in range(int(w * rng.uniform(1.0, 1.5))):
        u = rng.random()
        hx = rng.uniform(0, w)
        # Haufen: in der Mitte höher
        hmax = 3 + min(20, w * 0.36) * math.sin(math.pi * hx / w) ** 1.5
        hy = rng.uniform(0, hmax)
        items.append((hy, u, x + hx, base - hy))
    items.sort(key=lambda it: -it[0])                 # oben zuerst, vorne zuletzt
    for (_hy, u, ix, iy) in items:
        if u < 0.35:      # Säcke
            c = mul(rng.choice(((30, 32, 34), (40, 44, 40), (26, 30, 40))), rng.uniform(0.8, 1.2))
            r = rng.uniform(2.5, 4.5)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qc(c))
            p.drawEllipse(QRectF(ix - r, iy - r * 1.4, r * 2, r * 1.6))
            p.fillRect(QRectF(int(ix - r * 0.4), int(iy - r * 1.3), 1, 1), qc(mul(c, 2.0)))
        elif u < 0.7:     # Papier, Zeitungen
            c = mul(rng.choice(((180, 176, 160), (150, 154, 150), (120, 110, 90), (170, 120, 90))),
                    rng.uniform(0.5, 0.85))
            ww, hh = rng.randint(2, 5), rng.randint(1, 3)
            _poly(p, [(ix, iy - hh), (ix + ww, iy - hh - rng.uniform(-1, 1)), (ix + ww + 1, iy), (ix - 1, iy)], c)
        elif u < 0.82:    # Kiste
            c = mul((90, 70, 46), rng.uniform(0.5, 0.8))
            s = rng.randint(4, 6)
            p.fillRect(QRectF(int(ix), int(iy - s), s, s), qc(c))
            p.fillRect(QRectF(int(ix), int(iy - s), s, 1), qc(mul(c, 1.4)))
        elif u < 0.92:    # Reifen
            p.setBrush(Qt.BrushStyle.NoBrush)
            pen = QPen(qc((16, 16, 18)))
            pen.setWidth(2)
            p.setPen(pen)
            p.drawEllipse(QRectF(ix - 3, iy - 6, 6, 6))
            p.setPen(Qt.PenStyle.NoPen)
        else:             # Palette, schräg angelehnt
            c = mul((110, 92, 64), 0.5)
            for k in range(4):
                p.fillRect(QRectF(int(ix + k * 2), int(iy - 7 + k), 1, 7 - k), qc(c))
    # nasser Glanz obenauf (Neon)
    for _ in range(int(w / 6)):
        p.fillRect(QRectF(x + rng.uniform(2, w - 2), base - rng.uniform(2, 10), 1, 1),
                   qc(mul(rng.choice(th["neon"]), 0.5), 180))


# 60er-Jahre-Limousine (Heckflossen), in Zeichen-Einheiten: Länge 50, Höhe ~14
_CLASSIC = [(0, -4), (1, -7), (6, -8), (14, -8.6), (18, -13.4), (31, -13.6), (36, -9.0), (46, -8.4),
            (49.5, -9.6), (50, -6), (49, -3), (1, -3)]


def wreck(city, p, e, fac, rng, x, base, w):
    """Ausgeschlachtetes Wrack einer 60er-Limousine: aufgebockt, ohne Räder, Rost,
    zerbrochene Scheiben, Kabelgedärm aus dem Motorraum."""
    paint = mul(rng.choice(((70, 92, 96), (100, 80, 56), (62, 66, 84), (112, 92, 72), (88, 50, 44))),
                rng.uniform(0.45, 0.65))
    k = w / 50.0
    flip = rng.random() < 0.5
    tilt = rng.uniform(-1.5, 1.5)
    lift = rng.randint(0, 2)

    def P(px, py):
        xx = (50 - px) if flip else px
        return (x + xx * k, base - lift + py * k + tilt * (px / 50.0 - 0.5))

    # Blöcke statt Räder
    for px in (8, 40):
        bx, by = P(px, -2)
        p.fillRect(QRectF(int(bx) - 2, int(by), 5, base - int(by)), qc((40, 38, 36)))
    _poly(p, [P(*pt) for pt in _CLASSIC], paint)
    # Unterkante dunkel, Chromleiste
    _poly(p, [P(1, -5), P(49, -5), P(49, -3), P(1, -3)], mul(paint, 0.5))
    a, b = P(2, -6.2), P(48, -6.6)
    p.fillRect(QRectF(min(a[0], b[0]), a[1], abs(b[0] - a[0]), 1), qc((110, 112, 110), 160))
    # Fenster: dunkel, zersplittert
    win = [P(19, -12.6), P(30.5, -12.8), P(34.5, -9.2), P(15, -9.0)]
    _poly(p, win, (10, 12, 14))
    for _ in range(3):
        sx, sy = P(rng.uniform(17, 32), rng.uniform(-12, -9.5))
        p.fillRect(QRectF(int(sx), int(sy), 1, rng.randint(1, 2)), qc((150, 170, 170), 150))
    # Rostflecken
    for _ in range(rng.randint(4, 8)):
        sx, sy = P(rng.uniform(2, 48), rng.uniform(-8, -4))
        p.fillRect(QRectF(int(sx), int(sy), rng.randint(1, 4), rng.randint(1, 2)),
                   qc(mul(SODIUM, rng.uniform(0.45, 0.8))))
    # offene Haube, Kabel quellen heraus
    hx, hy = P(46, -8.4)
    hx2, hy2 = P(36, -9.0)
    _poly(p, [(hx2, hy2), (hx, hy), (hx + (-3 if flip else 3), hy - 7 * k)], mul(paint, 0.8))
    for _ in range(rng.randint(3, 6)):
        ex = hx + rng.uniform(-6, 6) * k
        _wire(p, (hx + hx2) / 2, hy - 1, ex, base - rng.randint(0, 3), rng.uniform(1, 3),
              rng.choice(((30, 30, 32), (90, 40, 30), (60, 70, 50))), 230)
    # zertrümmerte Scheinwerfer
    lx, ly = P(49, -7)
    p.fillRect(QRectF(int(lx) - 1, int(ly), 2, 2), qc((60, 62, 60)))


def barrel(city, p, e, fac, rng, x, base, w):
    """Feuertonne: rostiges Fass, oben die (lebende) Flamme."""
    c = mul((70, 44, 32), rng.uniform(0.7, 1.0))
    p.fillRect(QRectF(x + 1, base - 11, 7, 11), qc(c))
    for yy in (base - 9, base - 4):
        p.fillRect(QRectF(x + 1, yy, 7, 1), qc(mul(c, 1.4)))
    p.fillRect(QRectF(x + 1, base - 11, 7, 1), qc(mul(AMBER, 0.6)))
    p.fillRect(QRectF(x + 1, base - 11, 1, 11), qc(mul(AMBER, 0.35)))
    e.fillRect(QRectF(x + 1, base - 11, 7, 1), qc(mul(AMBER, 0.5)))
    city.fires.append((fac.lmin + x + 4.5, base - 11, rng.uniform(0.8, 1.2), rng.randint(0, 9999)))


def bollard(city, p, e, fac, rng, x, base, w):
    """Gelber Pollerkasten mit roter/grüner Lampe obenauf (Chinatown)."""
    c = mul((176, 150, 60), rng.uniform(0.5, 0.7))
    p.fillRect(QRectF(x + 1, base - 12, 6, 12), qc(c))
    p.fillRect(QRectF(x + 1, base - 12, 6, 1), qc(mul(c, 1.4)))
    p.fillRect(QRectF(x + 6, base - 12, 1, 12), qc(mul(c, 0.6)))
    p.fillRect(QRectF(x + 2, base - 8, 4, 2), qc((30, 28, 24)))
    col = rng.choice((RED, RED, GREEN))
    city.blinks.append(("fac", fac.lmin + x + 4, base - 14, col, rng.random() * 3))
    p.fillRect(QRectF(x + 3, base - 14, 2, 2), qc(mul(col, 0.4)))


def bins(city, p, e, fac, rng, x, base, w):
    """Zwei, drei Blechmülltonnen, manche mit schiefem Deckel, Müll daneben."""
    n = max(2, w // 8)
    xx = x
    for _ in range(n):
        c = mul(rng.choice(((70, 74, 72), (58, 66, 70), (76, 70, 60), (60, 56, 50))), rng.uniform(0.6, 0.9))
        h = rng.randint(8, 10)
        p.fillRect(QRectF(xx, base - h, 6, h), qc(c))
        for yy in range(base - h + 2, base, 3):
            p.fillRect(QRectF(xx, yy, 6, 1), qc(mul(c, 1.3)))
        p.fillRect(QRectF(xx + 5, base - h, 1, h), qc(mul(c, 0.55)))
        p.fillRect(QRectF(xx, base - h, 1, h), qc(mul(city.th["rim"], 0.35)))
        if rng.random() < 0.5:
            _poly(p, [(xx - 1, base - h), (xx + 7, base - h - 2), (xx + 7, base - h - 1), (xx - 1, base - h + 1)],
                  mul(c, 1.15))
        else:
            for _k in range(3):
                p.fillRect(QRectF(xx + rng.randint(0, 4), base - h - rng.randint(1, 2), 2, 1),
                           qc(mul(rng.choice(((170, 166, 150), (120, 108, 88), (40, 40, 44))), 0.7)))
        xx += 7 + rng.randint(0, 2)
    for _k in range(rng.randint(1, 4)):
        p.fillRect(QRectF(x + rng.uniform(-3, w), base - 1, rng.randint(2, 3), 1),
                   qc(mul((160, 156, 140), rng.uniform(0.4, 0.7))))


def sebastian(city, p, e, fac, base):
    """J. F. Sebastians Haus (Bradbury) am Ende der letzten Zone: alter Backsteinbau mit
    Rundbogenfenstern, Gesims, vergittertem Bogeneingang - und davor die dicken,
    gedrehten Ornament-Säulen. Hier steht ROY."""
    rx = int((city.length - config.ROY_STAND) * fac.factor) - fac.lmin     # Eingang = ROYs Platz
    x1 = city.exit_L - 62
    x0 = x1 - 240
    top = 12
    city.sebastian_span = (x0 - 4, x1 + 4)
    L0, L1 = fac.lmin + x0, fac.lmin + x1

    def inside(L, ww=0):
        return L + ww > L0 and L < L1
    city.signs = [s for s in city.signs if not inside(s.L, s.w)]
    city.tvs = [v for v in city.tvs if not inside(v[0] + fac.lmin, v[2])]
    city.lanterns = [v for v in city.lanterns if not inside(v[0])]
    city.blinks = [b for b in city.blinks if b[0] != "fac" or not inside(b[1])]
    city.vents = [v for v in city.vents if not inside(v[0])]
    city.lamps = [lp for lp in city.lamps if not inside(lp.L - 20, 40)]
    city.fires = [f for f in city.fires if not inside(f[0])]
    city.walks = [w_ for w_ in city.walks if not inside(w_[0], 14)]
    e.setCompositionMode(e.CompositionMode.CompositionMode_Clear)
    e.fillRect(QRectF(x0, 0, x1 - x0, base + 1), QColor(0, 0, 0, 0))
    e.setCompositionMode(e.CompositionMode.CompositionMode_SourceOver)
    rng = random.Random(city.seed * 17 + 1982)
    w = x1 - x0
    brick = (66, 40, 34)
    stone = (104, 90, 74)
    g = QLinearGradient(0, top, 0, base)
    g.setColorAt(0.0, qc(mul(brick, 0.45)))
    g.setColorAt(1.0, qc(brick))
    p.fillRect(QRectF(x0, top, w, base - top), QBrush(g))
    # Mauerwerk
    for i, y in enumerate(range(top + 2, base, 3)):
        p.fillRect(QRectF(x0, y, w, 1), qc(mul(brick, 0.62), 150))
        for x in range(x0 + (3 if i % 2 else 0), x1, 6):
            p.fillRect(QRectF(x, y - 2, 1, 2), qc(mul(brick, 0.7), 110))
    # Kranzgesims mit Zahnschnitt, Ecklisenen
    p.fillRect(QRectF(x0 - 3, top - 4, w + 6, 6), qc(mul(stone, 0.8)))
    p.fillRect(QRectF(x0 - 3, top - 4, w + 6, 1), qc(stone))
    for x in range(x0 - 2, x1 + 2, 3):
        p.fillRect(QRectF(x, top + 2, 1, 3), qc(mul(brick, 0.4)))
    for x in (x0, x1 - 5):
        p.fillRect(QRectF(x, top, 5, base - top), qc(mul(stone, 0.55)))
        p.fillRect(QRectF(x, top, 1, base - top), qc(mul(stone, 0.8)))
    # Rundbogenfenster, vier Geschosse
    ground = base - 46
    seb = (rng.randint(0, 3), rng.randint(2, 8))          # Sebastians Fenster: Licht, Spielzeug
    for row in range(4):
        y = top + 12 + row * 24
        if y + 16 > ground:
            break
        p.fillRect(QRectF(x0 + 4, y + 19, w - 8, 2), qc(mul(stone, 0.6)))         # Gurtgesims
        for col, x in enumerate(range(x0 + 12, x1 - 12, 14)):
            lit = (row, col) == seb
            dim = rng.random() < 0.12
            c = mul((255, 170, 90), 0.55) if lit else (mul((255, 160, 80), 0.18) if dim else (12, 10, 12))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qc(mul(stone, 0.7)))
            p.drawEllipse(QRectF(x - 1, y - 1, 10, 8))
            p.fillRect(QRectF(x - 1, y + 3, 10, 14), qc(mul(stone, 0.7)))
            for q, k in ((p, 1.0), (e, 0.6)) if lit else ((p, 1.0),):
                q.setPen(Qt.PenStyle.NoPen)
                q.setBrush(qc(mul(c, k)))
                q.drawEllipse(QRectF(x, y, 8, 7))
                q.fillRect(QRectF(x, y + 3, 8, 13), qc(mul(c, k)))
            p.fillRect(QRectF(x + 4, y + 2, 1, 14), qc(mul(stone, 0.45)))      # Sprosse
            if lit:                                       # Spielzeugsilhouetten im Fenster
                p.fillRect(QRectF(x + 1, y + 10, 2, 5), qc((40, 24, 20)))
                p.fillRect(QRectF(x + 1, y + 9, 2, 1), qc((40, 24, 20)))
                p.fillRect(QRectF(x + 5, y + 12, 2, 3), qc((40, 24, 20)))
                p.fillRect(QRectF(x + 5, y + 10, 1, 2), qc((40, 24, 20)))
            elif not dim and rng.random() < 0.2:          # zerbrochen
                p.fillRect(QRectF(x + 2, y + 6, 3, 1), qc((70, 80, 84), 160))
    # Steinband über dem Erdgeschoss mit eingemeißeltem Namen
    p.fillRect(QRectF(x0, ground - 6, w, 6), qc(mul(stone, 0.85)))
    p.fillRect(QRectF(x0, ground - 6, w, 1), qc(stone))
    word = "BRADBURY"
    from . import pixfont
    tw = pixfont.text_width(word)
    pixfont.draw(p, rx - tw // 2, ground - 5, word, mul(stone, 0.5), 1, None)
    # Erdgeschoss: vernagelte Schaufenster, Bogeneingang mit Gitter
    p.fillRect(QRectF(x0, ground, w, base - ground), qc(mul(brick, 0.7)))
    for x in list(range(x0 + 8, rx - 26, 30)) + list(range(rx + 26, x1 - 20, 30)):
        p.fillRect(QRectF(x, ground + 8, 22, 30), qc((24, 20, 18)))
        for k in range(4):
            y = ground + 10 + k * 7 + rng.randint(-1, 1)
            p.fillRect(QRectF(x - 1, y, 24, 3), qc(mul((92, 70, 50), rng.uniform(0.5, 0.8))))
    aw = 32
    ax = rx - aw // 2
    p.setBrush(qc(mul(stone, 0.75)))
    p.drawEllipse(QRectF(ax - 3, ground - 2, aw + 6, 22))
    p.fillRect(QRectF(ax - 3, ground + 9, aw + 6, base - ground - 9), qc(mul(stone, 0.75)))
    gi = QLinearGradient(0, ground, 0, base)
    gi.setColorAt(0, qc((40, 24, 16)))
    gi.setColorAt(1, qc((120, 70, 34)))
    for q, k in ((p, 1.0), (e, 0.35)):
        q.setPen(Qt.PenStyle.NoPen)
        q.setBrush(QBrush(gi) if q is p else qc((120, 70, 34), 90))
        q.drawEllipse(QRectF(ax, ground + 1, aw, 18))
        q.fillRect(QRectF(ax, ground + 10, aw, base - ground - 10), QBrush(gi) if q is p else qc((120, 70, 34), 90))
    for x in range(ax + 2, ax + aw, 3):                       # schmiedeeisernes Gitter
        p.fillRect(QRectF(x, ground + 4, 1, base - ground - 4), qc((16, 12, 10)))
    p.fillRect(QRectF(ax, ground + 16, aw, 1), qc((16, 12, 10)))
    # Wandleuchten neben dem Eingang
    for x in (ax - 8, ax + aw + 5):
        for q in (p, e):
            q.fillRect(QRectF(x, ground + 6, 3, 4), qc((255, 190, 120)))
        p.fillRect(QRectF(x + 1, ground + 10, 1, 3), qc((30, 26, 22)))
    # die dicken, gedrehten Säulen davor
    cw = 36
    for x in (rx - 24 - cw, rx + 24):
        _place(city, p, e, fac, rng, "ornate", x, base, cw)
    _place(city, p, e, fac, rng, "ornate", x0 + 4, base, 32)
    _place(city, p, e, fac, rng, "ornate", x1 - 36, base, 32)
    _place(city, p, e, fac, rng, "trash", rx - 26 - cw - 40, base, 34)
    _place(city, p, e, fac, rng, "barrel", rx + 26 + cw + 8, base, 9)


class _Collect:
    """Stellvertreter für Stadt/Fassade, wenn ein Turm als eigenes Objekt gezeichnet wird:
    sammelt die lebenden Teile (Ampel, Warnlampe) relativ zum Fußpunkt."""
    lmin = 0

    def __init__(self, th):
        self.th = th
        self.walks, self.blinks, self.tvs = [], [], []


def tower_sprite(seed, scale, th):
    """Ampelturm als freistehendes Objekt. scale = Pixel pro Fassaden-Pixel. Gibt
    (img, emit, ax, ay, walks, blinks) - walks/blinks in unskalierten Einheiten
    relativ zum Fußpunkt."""
    from PyQt6.QtGui import QImage, QPainter
    rng = random.Random(seed)
    cw, ch = 76, 116
    W_, H_ = int(cw * scale) + 4, int(ch * scale) + 4
    img = QImage(W_, H_, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    em = QImage(W_, H_, QImage.Format.Format_ARGB32_Premultiplied)
    em.fill(0)
    ax, ay = W_ // 2, H_ - 2
    col = _Collect(th)
    p, e = QPainter(img), QPainter(em)
    for q in (p, e):
        q.translate(ax, ay)
        q.scale(scale, scale)
    w = rng.randint(*WIDTH["tower"])
    tower(col, p, e, col, rng, -w // 2, 0, w)
    p.end()
    e.end()
    return img, em, ax, ay, col.walks, col.blinks


DRAW = dict(monolith=monolith, bins=bins, ornate=ornate, tower=tower, trash=trash, wreck=wreck, barrel=barrel,
            bollard=bollard)


# ============================================================================ Fassaden

def facade_look(city, rng):
    """Charakter eines Hauses: 'old' (verschnörkelt, nachgerüstet), 'modern' oder 'plain'."""
    po, pm = ZONE_FACADE[city.zone % len(ZONE_FACADE)]
    r = rng.random()
    return "old" if r < po else ("modern" if r < po + pm else "plain")


def old_stone(col):
    """Alte Häuser: wärmerer, dunklerer Stein."""
    return mix(col, (58, 46, 40), 0.45)


def ornament(p, e, rng, th, x, top, bw, bh, base, shop_h, col, hi):
    """Verschnörkelter Altbau: Kranzgesims mit Zahnschnitt, Pilaster, Gurtgesimse,
    Rosetten - und darüber, nachgerüstet, Kabel, Leitungen, Verteilerkästen."""
    stone_hi = mix(hi, (120, 100, 80), 0.35)
    dark = mul(col, 0.5)
    # Kranzgesims
    p.fillRect(QRectF(x - 2, top - 2, bw + 4, 4), qc(mul(stone_hi, 0.9)))
    p.fillRect(QRectF(x - 2, top - 2, bw + 4, 1), qc(mul(stone_hi, 1.3)))
    for k in range(x - 1, x + bw + 1, 3):
        p.fillRect(QRectF(k, top + 2, 1, 2), qc(dark))
    # Attika-Ornament
    if rng.random() < 0.6 and bw > 30:
        cx = x + bw // 2
        _poly(p, [(cx - 10, top - 2), (cx, top - 9), (cx + 10, top - 2)], mul(stone_hi, 0.8))
        p.fillRect(QRectF(cx - 1, top - 7, 2, 2), qc(mul(stone_hi, 1.3)))
    # Pilaster
    n = max(2, bw // 26)
    for i in range(n + 1):
        px = x + 1 + int(i * (bw - 4) / n)
        p.fillRect(QRectF(px, top + 4, 3, bh - shop_h - 4), qc(mul(col, 1.15)))
        p.fillRect(QRectF(px, top + 4, 1, bh - shop_h - 4), qc(mul(stone_hi, 0.9)))
        p.fillRect(QRectF(px - 1, top + 4, 5, 2), qc(mul(stone_hi, 1.1)))          # Kapitell
    # Gurtgesimse + Rosetten
    yy = top + rng.randint(18, 26)
    while yy < base - shop_h - 6:
        p.fillRect(QRectF(x, yy, bw, 1), qc(mul(stone_hi, 0.75)))
        p.fillRect(QRectF(x, yy + 1, bw, 1), qc(dark))
        yy += rng.randint(22, 34)
    for k in range(x + 6, x + bw - 4, 12):
        p.fillRect(QRectF(k, top + 6, 2, 2), qc(mul(stone_hi, 1.1)))
    # --- nachgerüstet: Kabel, Rohre, Kästen (die Zukunft hängt an der Vergangenheit)
    for _ in range(rng.randint(2, 5)):
        x0 = x + rng.uniform(0, bw * 0.4)
        x1 = x + rng.uniform(bw * 0.6, bw)
        y0 = rng.uniform(top + 8, base - shop_h - 4)
        y1 = y0 + rng.uniform(-10, 10)
        _wire(p, x0, y0, x1, y1, rng.uniform(1, 5), (12, 12, 14), 220)
    for _ in range(rng.randint(1, 3)):
        px = x + rng.randint(3, max(4, bw - 5))
        p.fillRect(QRectF(px, top + 6, 2, bh - 8), qc((40, 42, 44)))
        for yy in range(top + 10, base - 4, 12):
            p.fillRect(QRectF(px - 1, yy, 4, 1), qc((60, 62, 64)))
    for _ in range(rng.randint(1, 3)):
        bx = x + rng.randint(2, max(3, bw - 8))
        by = rng.randint(top + 10, max(top + 11, base - shop_h - 10))
        p.fillRect(QRectF(bx, by, 6, 7), qc((50, 52, 50)))
        p.fillRect(QRectF(bx, by, 6, 1), qc((86, 88, 86)))
        if rng.random() < 0.5:
            c = rng.choice((GREEN, RED, AMBER))
            for q in (p, e):
                q.fillRect(QRectF(bx + 4, by + 2, 1, 1), qc(c))


def modern(p, e, rng, th, x, top, bw, bh, base, shop_h, col, hi):
    """Hypermoderner Bau: Glasfassade mit feinen Sprossen, ganze Etagen hell,
    Lichtband an der Kante. Glatt, ohne Feuerleiter und Klimakästen."""
    glass_top = mul(mix(col, (20, 40, 54), 0.6), 0.9)
    glass_bot = mix(col, (40, 70, 84), 0.5)
    g = QLinearGradient(0, top, 0, base - shop_h)
    g.setColorAt(0.0, qc(glass_top))
    g.setColorAt(1.0, qc(glass_bot))
    p.fillRect(QRectF(x + 2, top + 3, bw - 4, bh - shop_h - 3), QBrush(g))
    fh = rng.choice((6, 7, 8))
    lit_floor = mix(PALE, rng.choice((CYAN, AMBER, PALE)), 0.3)
    yy = top + 4
    while yy < base - shop_h - 2:
        p.fillRect(QRectF(x + 2, yy, bw - 4, 1), qc(mul(glass_top, 0.6)))
        if rng.random() < th["lit"] * 0.9:
            c = mul(lit_floor, rng.uniform(0.35, 0.6))
            p.fillRect(QRectF(x + 3, yy + 1, bw - 6, fh - 2), qc(c))
            e.fillRect(QRectF(x + 3, yy + 1, bw - 6, fh - 2), qc(mul(c, 0.4)))
        yy += fh
    for k in range(x + 4, x + bw - 2, rng.choice((4, 5, 6))):
        p.fillRect(QRectF(k, top + 3, 1, bh - shop_h - 3), qc(mul(glass_top, 0.7), 200))
    # Spiegelung: diagonaler Lichtstreif
    s = rng.uniform(0, bw)
    _poly(p, [(x + s, top + 3), (x + s + 6, top + 3), (x + s - 14, base - shop_h), (x + s - 20, base - shop_h)],
          mix(glass_bot, PALE, 0.25), 60)
    # Lichtband
    c = rng.choice((CYAN, GREEN, NBLUE, PALE))
    for q, k in ((p, 0.85), (e, 0.8)):
        q.fillRect(QRectF(x + 1, top + 1, bw - 2, 1), qc(mul(c, k)))
        if rng.random() < 0.5:
            q.fillRect(QRectF(x + 1, top + 1, 1, bh - shop_h), qc(mul(c, k * 0.7)))
