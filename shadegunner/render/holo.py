"""Holografische Ballerinas (Blade Runner 2049): tanzende Werbe-Hologramme.

Die Tänzerin ist ein kleines 3D-Skelett (x seitlich, y nach unten, z zur Kamera),
das zwischen Ballett-Posen interpoliert und um die Hochachse dreht (Pirouette,
Promenade in der Arabeske). Projektion orthografisch mit leichter Aufsicht, damit
das Tutu als Scheibe lesbar bleibt.

Gezeichnet wird in eine kleine Zwischentextur (eine Farbe, vorn heller), darauf
Scanlines, Laufband und gelegentliche Aussetzer/Glitches, dann additiv in Szene
und Leuchtschicht. So bleibt sie durchscheinend wie im Film.
"""

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPolygonF, QRadialGradient

PLUS = QPainter.CompositionMode.CompositionMode_Plus
OVER = QPainter.CompositionMode.CompositionMode_SourceOver
DESIGN_H = 58.0          # Design-Einheiten von den Spitzen bis zu den gehobenen Händen

# Arme relativ zur Schulter, linke Seite (x < 0); rechts wird gespiegelt.
ARMS = {
    "bas": ((-1.0, 6.0, 2.0), (-0.6, 11.5, 3.5)),
    "first": ((-3.6, 4.6, 4.6), (-0.8, 7.6, 7.4)),
    "second": ((-7.0, 1.4, 1.0), (-13.6, 2.8, 1.2)),
    "haut": ((-4.6, -6.4, 1.6), (-1.3, -12.6, 2.0)),
    "fwd": ((-1.6, -2.6, 7.0), (-2.0, -5.2, 13.6)),
    "back": ((-7.0, 1.0, -1.6), (-13.2, 1.6, -3.4)),
}
# Spielbein relativ zur rechten Hüfte: (Knie, Fuß); "ground" = steht mit am Boden
LEGS = {
    "passe": ((8.6, 8.6, 2.6), (-0.4, 12.6, 1.6)),
    "seconde": ((9.6, -2.4, 0.6), (19.6, -6.2, 1.0)),
    "arabesque": ((0.6, 2.6, -10.6), (1.0, -1.2, -21.2)),
}

T4 = 4 * math.pi
T6 = 6 * math.pi
KEYS = [   # (Zeit s, Relevé, Plié, Neigung, Arme L, Arme R, Bein, Drehung)
    (0.0, 0.0, 0.0, 0.0, "bas", "bas", "ground", 0.0),
    (1.2, 0.0, 0.0, 0.0, "bas", "bas", "ground", 0.0),
    (1.8, 0.0, 1.0, 0.0, "second", "first", "ground", 0.0),
    (2.2, 1.0, 0.0, 0.0, "first", "first", "passe", 0.0),
    (3.8, 1.0, 0.0, 0.0, "first", "first", "passe", T4),        # doppelte Pirouette
    (4.3, 0.0, 0.6, 0.0, "second", "second", "ground", T4),
    (5.0, 1.0, 0.0, 0.0, "second", "second", "seconde", T4),
    (6.0, 1.0, 0.0, 0.0, "haut", "haut", "seconde", T4),
    (6.8, 1.0, 0.0, 0.45, "back", "fwd", "arabesque", T4),
    (10.0, 1.0, 0.0, 0.45, "back", "fwd", "arabesque", T6),     # Promenade
    (10.8, 0.0, 1.0, 0.1, "bas", "bas", "ground", T6),
    (11.6, 0.0, 0.3, 0.35, "second", "second", "ground", T6),   # Révérence
    (12.4, 0.0, 0.0, 0.0, "bas", "bas", "ground", T6),
]
CYCLE = KEYS[-1][0]


def _add(a, b, k=1.0):
    return (a[0] + b[0] * k, a[1] + b[1] * k, a[2] + b[2] * k)


def _lerp(a, b, u):
    return tuple(x + (y - x) * u for x, y in zip(a, b))


def _key_pose(key):
    """Konkrete Punkte (Körperkoordinaten, y nach unten negativ = oben) einer Schlüsselpose."""
    _t, r, pl, lean, al, ar, leg, _th = key
    hip_y = -(22.0 + 3.0 * r) + 6.0 * pl
    foot_y = -1.2 - 2.2 * r
    P = {}
    P["hip"] = (0.0, hip_y, 0.0)
    hs, hw = (-1.6, hip_y, 0.0), (1.6, hip_y, 0.0)
    # Standbein (links)
    ank = (-0.6, foot_y, 0.4)
    P["hip_s"], P["ank_s"] = hs, ank
    P["kn_s"] = ((hs[0] + ank[0]) / 2 - 3.2 * pl, (hs[1] + ank[1]) / 2, 0.8 + 1.6 * pl)
    P["toe_s"] = (-0.6 + 0.4 * (1 - r), 0.0 if r > 0.5 else -0.4, 0.8 + 2.4 * (1 - r))
    # Spielbein (rechts)
    P["hip_w"] = hw
    if leg == "ground":
        fw = (0.4, foot_y, 1.6)
        kw = ((hw[0] + fw[0]) / 2 + 3.2 * pl + 0.4, (hw[1] + fw[1]) / 2, 1.2 + 1.8 * pl)
        P["kn_w"], P["ank_w"] = kw, fw
        P["toe_w"] = (0.6 + 0.4 * (1 - r), 0.0 if r > 0.5 else -0.4, 2.0 + 2.2 * (1 - r))
    else:
        kn, ft = LEGS[leg]
        kw, fw = _add(hw, kn), _add(hw, ft)
        d = (fw[0] - kw[0], fw[1] - kw[1], fw[2] - kw[2])
        n = math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2) or 1.0
        P["kn_w"], P["ank_w"], P["toe_w"] = kw, fw, _add(fw, d, 3.0 / n)
    # Oberkörper (Neigung nach vorn = +z)
    cl, sl = math.cos(lean), math.sin(lean)
    sc = (0.0, hip_y - 14.0 * cl, 14.0 * sl)
    P["waist"] = (0.0, hip_y - 4.6 * cl, 4.6 * sl)
    P["sc"] = sc
    P["head"] = (0.0, sc[1] - 5.2 * cl, sc[2] + 5.2 * sl)
    P["bun"] = (0.0, sc[1] - 7.6 * cl, sc[2] + 7.6 * sl - 1.4)
    for side, name, s in (("l", al, 1.0), ("r", ar, -1.0)):
        sh = (sc[0] - 4.2 * s, sc[1], sc[2])
        el, ha = ARMS[name]
        P["sh_" + side] = sh
        P["el_" + side] = _add(sh, (el[0] * s, el[1], el[2]))
        P["ha_" + side] = _add(sh, (ha[0] * s, ha[1], ha[2]))
    return P


_KP = [_key_pose(k) for k in KEYS]


def pose_at(t):
    """(Punkte, Drehwinkel) zur Zeit t (s), zyklisch."""
    t %= CYCLE
    i = 0
    while i < len(KEYS) - 2 and KEYS[i + 1][0] <= t:
        i += 1
    t0, t1 = KEYS[i][0], KEYS[i + 1][0]
    u = 0.0 if t1 <= t0 else (t - t0) / (t1 - t0)
    us = u * u * (3 - 2 * u)
    a, b = _KP[i], _KP[i + 1]
    pts = {k: _lerp(a[k], b[k], us) for k in a}
    th = KEYS[i][7] + (KEYS[i + 1][7] - KEYS[i][7]) * (u if KEYS[i + 1][7] != KEYS[i][7] else us)
    return pts, th


def _proj(pt, c, s):
    x, y, z = pt
    X = x * c + z * s
    Z = -x * s + z * c
    return X, y + Z * 0.12, Z


def _shade(col, k):
    return QColor(max(0, min(255, int(col[0] * k))), max(0, min(255, int(col[1] * k))),
                  max(0, min(255, int(col[2] * k))))


def draw_dancer(p, t, col, wk=1.0):
    """Tänzerin in Design-Einheiten (Füße bei y = 0) auf Painter p zeichnen."""
    pts, th = pose_at(t)
    c, s = math.cos(th), math.sin(th)
    Q = {k: _proj(v, c, s) for k, v in pts.items()}
    items = []

    def seg(a, b, w):
        z = (Q[a][2] + Q[b][2]) * 0.5
        items.append((z, "line", (Q[a], Q[b], w * wk)))

    seg("hip_s", "kn_s", 2.4)
    seg("kn_s", "ank_s", 1.7)
    seg("ank_s", "toe_s", 1.2)
    seg("hip_w", "kn_w", 2.4)
    seg("kn_w", "ank_w", 1.7)
    seg("ank_w", "toe_w", 1.2)
    for sd in ("l", "r"):
        seg("sh_" + sd, "el_" + sd, 1.5)
        seg("el_" + sd, "ha_" + sd, 1.2)
    # Mieder: Schultern -> Taille (wird bei Seitenansicht schmal)
    zt = Q["sc"][2]
    items.append((zt, "poly", [Q["sh_l"], Q["sh_r"], _add(Q["waist"], (1.9 * c, 0, 0)), _add(Q["waist"], (-1.9 * c, 0, 0))]))
    items.append((zt, "line", (Q["sc"], Q["head"], 1.2)))
    items.append((Q["head"][2] + 0.5, "head", (Q["head"], Q["bun"])))
    # Tutu: hintere Hälfte hinter, vordere Hälfte vor den Beinen
    hip = Q["hip"]
    items.append((-6.0, "tutu", (hip, th, False)))
    items.append((6.0, "tutu", (hip, th, True)))
    items.sort(key=lambda it: it[0])
    p.setPen(Qt.PenStyle.NoPen)
    for z, kind, d in items:
        k = 0.72 + 0.28 * max(-1.0, min(1.0, z / 9.0))
        if kind == "line":
            a, b, w = d
            pen = QPen(_shade(col, k))
            pen.setWidthF(w)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(a[0], a[1]), QPointF(b[0], b[1]))
            p.setPen(Qt.PenStyle.NoPen)
        elif kind == "poly":
            p.setBrush(_shade(col, k))
            p.drawPolygon(QPolygonF([QPointF(x, y) for x, y, _z in d]))
        elif kind == "head":
            h, bun = d
            p.setBrush(_shade(col, 1.0))
            p.drawEllipse(QPointF(h[0], h[1]), 2.7, 3.0)
            p.drawEllipse(QPointF(bun[0], bun[1]), 1.4, 1.2)
        else:
            hp, ang, front = d
            R, yc = 10.5, hp[1] + 0.8
            a0, a1 = (0.0, math.pi) if front else (math.pi, 2 * math.pi)
            n = 14
            top = [(R * math.cos(a0 + (a1 - a0) * i / n), yc + 0.12 * R * math.sin(a0 + (a1 - a0) * i / n))
                   for i in range(n + 1)]
            bot = [(x * 0.9, y + 1.8) for x, y in reversed(top)]
            p.setBrush(_shade(col, 1.0 if front else 0.6))
            p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in top + bot]))
            # Falten drehen mit (zeigt die Pirouette)
            pen = QPen(_shade(col, 0.5 if front else 0.35))
            pen.setWidthF(0.7)
            p.setPen(pen)
            for i in range(12):
                a = ang + i * math.pi / 6
                if (math.sin(a) > 0) != front:
                    continue
                x, y = R * math.cos(a), yc + 0.12 * R * math.sin(a)
                p.drawLine(QPointF(x * 0.3, yc + 0.3 * (y - yc)), QPointF(x, y + 1.2))
            p.setPen(Qt.PenStyle.NoPen)


def _hash(i, s):
    h = (i * 374761393 + s * 668265263) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF) / 65535.0


_TMP = {}       # (seed, w, hh) -> [tick, QImage]   eigene Textur je Hologramm
_MASK = {}      # (w, hh, step) -> Scanline-Maske (Alpha je Zeile)
FPS = 20.0      # Hologramm-Bildrate (Projektor-Look, spart Zeichenzeit)


def _mask(w, hh, step):
    key = (w, hh, step)
    m = _MASK.get(key)
    if m is None:
        m = QImage(w, hh, QImage.Format.Format_ARGB32_Premultiplied)
        m.fill(QColor(0, 0, 0, 255))
        q = QPainter(m)
        q.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        for y in range(0, hh, step):
            q.fillRect(0, y, w, 1, QColor(0, 0, 0, 105))
        q.end()
        _MASK[key] = m
    return m


def render(p, e, x, base, h, col, t, seed, reflect=0.0, alpha=0.62, mirror=False):
    """Hologramm der Höhe h px mit Fußpunkt (x, base) additiv zeichnen."""
    s = h / DESIGN_H
    w = int(h * 1.05) + 6
    hh = int(h * 1.08) + 6
    key = (seed, w, hh, mirror)
    tick = int(t * FPS)
    ent = _TMP.get(key)
    if ent is None:
        if len(_TMP) > 32:
            _TMP.clear()
        ent = _TMP[key] = [None, QImage(w, hh, QImage.Format.Format_ARGB32_Premultiplied)]
    img = ent[1]
    if ent[0] != tick:
        ent[0] = tick
        img.fill(0)
        q = QPainter(img)
        q.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        q.translate(w / 2, hh - 3)
        q.scale(-s if mirror else s, s)
        draw_dancer(q, tick / FPS + seed * 0.37, col, wk=max(1.0, min(1.6, 150.0 / max(1.0, h))))
        q.resetTransform()
        # Scanlines (eine Maske, ein Blit) + wanderndes Helligkeitsband
        q.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        q.drawImage(0, 0, _mask(w, hh, 2 if h < 90 else 3))
        q.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
        band = (t * 38.0 + seed * 17) % (hh + 30) - 15
        q.fillRect(QRectF(0, band, w, max(2.0, h * 0.06)), QColor(255, 255, 255, 110))
        q.end()
    # Flackern, Aussetzer, Glitch
    a = alpha * (0.9 + 0.1 * math.sin(t * 23.0 + seed))
    if _hash(int(t * 9), seed) < 0.035:
        a *= 0.25
    glitch = _hash(int(t * 7), seed + 3) < 0.06
    x0, y0 = int(x - w / 2), int(base - hh + 3)
    p.setCompositionMode(PLUS)
    # Projektionslicht am Fußpunkt
    rg = QRadialGradient(x, base, h * 0.35)
    rg.setColorAt(0, QColor(col[0], col[1], col[2], int(70 * a)))
    rg.setColorAt(1, QColor(0, 0, 0, 0))
    p.save()
    p.translate(x, base)
    p.scale(1.0, 0.22)
    p.translate(-x, -base)
    p.fillRect(QRectF(x - h * 0.35, base - h * 0.35, h * 0.7, h * 0.7), rg)
    p.restore()
    for q, op in ((p, a), (e, a * 0.32)):
        q.setOpacity(op)
        if glitch:
            for row in range(0, hh, 4):
                off = int((_hash(row + int(t * 30), seed) - 0.5) * h * 0.08)
                q.drawImage(QRectF(x0 + off, y0 + row, w, 4), img, QRectF(0, row, w, 4))
        else:
            q.drawImage(x0, y0, img)
        q.setOpacity(1.0)
    if reflect > 0.0:
        p.setOpacity(a * reflect)
        p.drawImage(x0, int(base) - 3, img.mirrored(False, True))
        p.setOpacity(1.0)
    p.setCompositionMode(OVER)
