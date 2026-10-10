"""Bodenfahrzeuge und Straßen-Hindernisse als gecachte Pixelbilder (Seitenansicht).

Gezeichnet in Design-Einheiten (= Welt-Einheiten; Boden bei y = 0, Fahrtrichtung +x)
und direkt in Zielgröße gerastert. Jedes Bild kommt mit einer Leuchtschicht
(Scheinwerfer, Rücklichter, Neon-Unterboden, Automatenfront) für den Glow-Pass.
Lebende Teile (Blaulicht, Feuer, Blinklampen, Lichtkegel) zeichnet render/scene.py.
"""

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QImage, QLinearGradient, QPainter, QPen, QPolygonF

from .. import config
from . import pixfont

C = config.NOIR16
CYAN, MAGENTA, AMBER, VIOLET, TEAL = C[12], C[13], C[14], C[15], C[11]
PALE, WHITE, CRIMSON = C[9], C[10], C[6]

_CACHE = {}
VEH_SCALE = 1.5    # Zeichnung in 2/3-Einheiten, Welt-Maße in sim.VEHICLES

BODY = {
    "car": [(34, 38, 58), (58, 30, 44), (30, 52, 60), (70, 72, 86)],
    "taxi": [(196, 150, 52)],
    "police": [(26, 30, 52)],
    "truck": [(60, 58, 64), (70, 44, 36), (40, 56, 70)],
    "bike": [(30, 30, 40), (90, 20, 50)],
    "limo": [(14, 14, 20)],
}
UNDERGLOW = [CYAN, MAGENTA, VIOLET, TEAL, AMBER]


def _q(c, a=255):
    return QColor(int(c[0]), int(c[1]), int(c[2]), a)


def _mul(c, f):
    return (max(0, min(255, int(c[0] * f))), max(0, min(255, int(c[1] * f))), max(0, min(255, int(c[2] * f))))


def _poly(p, pts, col, a=255):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_q(col, a))
    p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))


def _rect(p, x, y, w, h, col, a=255):
    p.fillRect(QRectF(x, y, w, h), _q(col, a))


def _wheel(p, x, r, skirt=None):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_q((8, 8, 12)))
    p.drawEllipse(QRectF(x - r, -2 * r, 2 * r, 2 * r))
    p.setBrush(_q((60, 62, 72)))
    p.drawEllipse(QRectF(x - r * 0.45, -r * 1.45, r * 0.9, r * 0.9))
    if skirt is not None:
        _rect(p, x - r - 0.5, -2 * r - 0.5, 2 * r + 1, r * 1.1, skirt)


def _draw_vehicle(p, e, kind, seed, rim, d=1):
    rnd = (seed * 2654435761) & 0xFFFFFFFF
    body = BODY[kind][rnd % len(BODY[kind])]
    glow = UNDERGLOW[(rnd >> 8) % len(UNDERGLOW)]
    hi = _mul(body, 1.6)
    win = (30, 44, 70)
    if kind in ("car", "taxi", "police", "limo"):
        L = {"car": 58.0, "taxi": 56.0, "police": 60.0, "limo": 84.0}[kind]
        hl = L / 2
        cab0, cab1 = (-hl * 0.55, hl * 0.42) if kind != "limo" else (-hl * 0.5, hl * 0.25)
        top = -15.5 if kind != "limo" else -13.0
        # Unterboden-Neon
        for q in (p, e):
            _rect(q, -hl + 6, -2.2, L - 12, 1.2, glow)
        # Karosserie (kantig, 2019-Retro-Futur)
        _poly(p, [(-hl, -4), (-hl, -9.5), (-hl + 4, -10.5), (cab0, -10.5), (cab0 + 5, top), (cab1 - 2, top),
                  (cab1 + 6, -10.5), (hl - 3, -10), (hl, -8), (hl, -4), (hl - 2, -3), (-hl + 2, -3)], body)
        # Fenster
        _poly(p, [(cab0 + 2, -10.8), (cab0 + 6, top + 1.4), (cab1 - 2.6, top + 1.4), (cab1 + 3.6, -10.8)], win)
        _rect(p, (cab0 + cab1) / 2 + 1, top + 1.2, 1.2, 5, body)
        if kind == "limo":
            _rect(p, cab0 + 8, top + 1.2, 1.2, 5, body)
        # Kante/Rimlight oben + Zierlinie
        _rect(p, -hl + 3, -10.6, L - 6, 0.9, _mul(rim, 0.8))
        _rect(p, cab0 + 5, top - 0.2, cab1 - cab0 - 7, 0.8, _mul(rim, 0.9))
        _rect(p, -hl + 1, -7.0, L - 2, 0.7, _mul(body, 0.55) if kind != "limo" else AMBER)
        # Räder (halb verkleidet)
        r = 3.4
        _wheel(p, -hl + 11, r, skirt=body if kind != "taxi" else None)
        _wheel(p, hl - 11, r, skirt=body if kind == "limo" else None)
        # Lichter
        for q in (p, e):
            _rect(q, hl - 2.4, -9.0, 2.4, 1.6, (255, 250, 230))
            _rect(q, -hl, -9.0, 1.6, 2.4, (240, 40, 70))
            _rect(q, -hl, -6.0, 1.2, 1.0, (240, 40, 70))
        if kind == "taxi":
            _rect(p, -3, top - 3.2, 9, 3.2, (20, 20, 26))
            for q in (p, e):
                _rect(q, -2, top - 2.6, 7, 2, AMBER)
            _rect(p, -hl + 4, -8.4, L - 8, 1.0, (30, 30, 30))
        if kind == "police":
            _rect(p, -hl + 4, -8.2, L - 8, 1.6, (214, 220, 226))
            _rect(p, -6, top - 2.0, 12, 2.0, (20, 20, 30))   # Lichtbalken (leuchtet live)
    elif kind == "truck":
        L, hl = 92.0, 46.0
        for q in (p, e):
            _rect(q, -hl + 4, -2.2, L - 8, 1.0, AMBER)
        # Koffer
        _rect(p, -hl, -30, 66, 25, body)
        _rect(p, -hl, -30, 66, 1.2, _mul(rim, 0.8))
        for x in range(int(-hl) + 4, 18, 6):
            _rect(p, x, -29, 0.8, 23, _mul(body, 0.7))
        words = ("OFF-WORLD", "TYRELL", "SHIMATA", "FRACHT")
        img = pixfont.render(words[rnd % len(words)], _mul(PALE, 0.55), 1, shadow=None)
        p.save()
        sc = min(1.0, 50.0 / max(1, img.width()))
        if d < 0:     # das Bild wird später gespiegelt -> Schrift hier vorspiegeln
            p.translate(-hl + 6 + img.width() * sc, -22)
            p.scale(-sc, sc)
        else:
            p.translate(-hl + 6, -22)
            p.scale(sc, sc)
        p.drawImage(0, 0, img)
        p.restore()
        # Kabine
        _poly(p, [(21, -5), (21, -24), (34, -24), (44, -14), (46, -12), (46, -5)], _mul(body, 1.15))
        _poly(p, [(25, -22.5), (33, -22.5), (41, -14.5), (25, -14.5)], win)
        _rect(p, 21, -24, 13, 1.0, _mul(rim, 0.9))
        _rect(p, -hl, -6, L, 1.6, (16, 16, 20))
        for x in (-hl + 10, -hl + 20, 34):
            _wheel(p, x, 4.2)
        for q in (p, e):
            _rect(q, hl - 2, -11, 2, 2.4, (255, 250, 230))
            _rect(q, -hl, -9, 1.4, 3, (240, 40, 70))
            _rect(q, 22, -25.4, 10, 1.0, AMBER)       # Positionslampen
    elif kind == "bike":
        hl = 15.0
        for q in (p, e):
            _rect(q, -hl + 4, -1.6, 2 * hl - 8, 0.9, glow)
        _wheel(p, -10, 4.0)
        _wheel(p, 10, 4.0)
        _poly(p, [(-13, -6), (-4, -10), (8, -11), (14, -8), (12, -5), (-10, -4.5)], body)
        _rect(p, -6, -11, 12, 0.8, _mul(rim, 0.9))
        # Fahrer
        _poly(p, [(-5, -10), (-2, -20), (3, -20), (5, -11)], (24, 24, 32))
        p.setBrush(_q((30, 30, 40)))
        p.drawEllipse(QRectF(-1.5, -25, 5.5, 5.2))
        for q in (p, e):
            _rect(q, 1.5, -23.5, 2.6, 1.2, glow)          # Visier
            _rect(q, 13.6, -9, 1.6, 1.6, (255, 250, 230))
            _rect(q, -14, -7, 1.2, 1.4, (240, 40, 70))


def vehicle_image(kind, seed, ppu, rim, d=1):
    """(img, emit, ax, ay, length_px): Anker = Boden-Mitte des Fahrzeugs (Fahrtrichtung d)."""
    kpx = round(ppu * 8) / 8
    key = ("v", kind, seed % 6, kpx, rim, d)
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    from ..sim import VEHICLES
    L, h, _sp = VEHICLES[kind]
    w = int(L * kpx) + 8
    hh = int((h + 8) * kpx) + 6
    ax, ay = w // 2, hh - 3
    img = QImage(w, hh, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    em = QImage(w, hh, QImage.Format.Format_ARGB32_Premultiplied)
    em.fill(0)
    p, e = QPainter(img), QPainter(em)
    for q in (p, e):
        q.translate(ax, ay)
        q.scale(kpx * VEH_SCALE, kpx * VEH_SCALE)
    _draw_vehicle(p, e, kind, seed % 6, rim, d)
    p.end()
    e.end()
    img = _outline(img)
    if d < 0:
        img = img.mirrored(True, False)
        em = em.mirrored(True, False)
        ax = w - 1 - ax
    res = (img, em, ax, ay, L * kpx)
    if len(_CACHE) > 600:
        _CACHE.clear()
    _CACHE[key] = res
    return res


def _outline(img):
    w, h = img.width(), img.height()
    m = QImage(img)
    q = QPainter(m)
    q.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    q.fillRect(0, 0, w, h, QColor(4, 5, 10))
    q.end()
    out = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(0)
    q = QPainter(out)
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        q.drawImage(dx, dy, m)
    q.drawImage(0, 0, img)
    q.end()
    return out


# ---------------------------------------------------------------------------- Hindernisse

def _draw_obstacle(p, e, kind, seed, rim):
    rnd = (seed * 2246822519) & 0xFFFFFFFF
    if kind == "barrier":
        for x in (-9, 9):
            _poly(p, [(x - 3, 0), (x - 0.6, -9), (x + 0.6, -9), (x + 3, 0), (x + 2, 0), (x, -7), (x - 2, 0)],
                  (60, 60, 70))
        _rect(p, -11, -9.5, 22, 3.6, (214, 220, 226))
        for i in range(-11, 11, 4):
            _poly(p, [(i, -5.9), (i + 2, -9.5), (i + 4, -9.5), (i + 2, -5.9)], (200, 40, 60))
        _rect(p, -11, -9.5, 22, 0.8, _mul(rim, 1.0))
        _rect(p, -1, -12, 2, 2.4, (40, 40, 40))      # Blinklampe (leuchtet live)
    elif kind == "crates":
        cols = [(92, 70, 52), (60, 70, 90), (50, 80, 70)]
        c = cols[rnd % 3]
        _rect(p, -9, -6, 18, 6, c)
        _rect(p, -7, -11, 12, 5, _mul(c, 1.15))
        for (x, y, w, h) in ((-9, -6, 18, 6), (-7, -11, 12, 5)):
            _rect(p, x, y, w, 0.7, _mul(rim, 0.8))
            _rect(p, x + 0.5, y + h * 0.5, w - 1, 0.6, _mul(c, 0.6))
        img = pixfont.render(("OFF", "TYR", "XX")[rnd % 3], _mul(PALE, 0.5), 1, shadow=None)
        p.save()
        p.translate(-5, -5)
        p.scale(0.5, 0.5)
        p.drawImage(0, 0, img)
        p.restore()
    elif kind == "bins":
        _rect(p, 1, -8, 7, 8, (40, 60, 56))
        _rect(p, 0.5, -8.6, 8, 1.2, _mul(rim, 0.7))
        p.setPen(Qt.PenStyle.NoPen)
        for (x, y, r) in ((-6, -2.6, 3.0), (-2, -3.0, 3.4), (-4, -5.2, 2.6)):
            p.setBrush(_q((22, 22, 28)))
            p.drawEllipse(QRectF(x - r, y - r * 0.8, 2 * r, r * 1.7))
            p.setBrush(_q(_mul(rim, 0.6)))
            p.drawEllipse(QRectF(x - r * 0.4, y - r * 0.7, r * 0.5, r * 0.4))
    elif kind == "barrel":
        _rect(p, -4, -9, 8, 9, (66, 44, 36))
        for y in (-7.5, -3.5):
            _rect(p, -4, y, 8, 0.8, (90, 60, 46))
        _rect(p, -4, -9, 1.0, 9, _mul(rim, 0.7))
        for q in (p, e):
            _rect(q, -3.4, -9.4, 6.8, 1.0, AMBER)   # Glut am Rand
    elif kind == "vending":
        col = (CYAN, MAGENTA, AMBER, CRIMSON)[rnd % 4]
        _rect(p, -6, -20, 12, 20, (30, 32, 44))
        _rect(p, -6, -20, 12, 0.8, _mul(rim, 0.8))
        for q, a in ((p, 255), (e, 200)):
            _rect(q, -5, -19, 7, 12, _mul(col, 0.55), a)
            for y in (-18, -15, -12):
                _rect(q, -4.5, y, 6, 1.4, _mul(col, 1.1), a)
            _rect(q, 3, -17, 2, 2, (255, 250, 230), a)
        _rect(p, -5, -5, 7, 2.4, (10, 10, 14))


def obstacle_image(kind, seed, ppu, rim):
    kpx = round(ppu * 8) / 8
    key = ("o", kind, seed % 5, kpx, rim)
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    w = int(30 * kpx) + 6
    hh = int(26 * kpx) + 6
    ax, ay = w // 2, hh - 3
    img = QImage(w, hh, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    em = QImage(w, hh, QImage.Format.Format_ARGB32_Premultiplied)
    em.fill(0)
    p, e = QPainter(img), QPainter(em)
    for q in (p, e):
        q.translate(ax, ay)
        q.scale(kpx, kpx)
    _draw_obstacle(p, e, kind, seed % 5, rim)
    p.end()
    e.end()
    res = (_outline(img), em, ax, ay)
    _CACHE[key] = res
    return res


def headlight(p, x, y, d, ppu, gy, length=150.0, col=(255, 240, 210), a=70):
    """Lichtkegel vor dem Fahrzeug: Strahl in der Luft + Lichtfleck auf der Fahrbahn."""
    tip = x + d * length * ppu
    g = QLinearGradient(x, y, tip, y)
    g.setColorAt(0, QColor(col[0], col[1], col[2], a))
    g.setColorAt(1, QColor(col[0], col[1], col[2], 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(g))
    p.drawPolygon(QPolygonF([QPointF(x, y - 1), QPointF(tip, y - 10 * ppu), QPointF(tip, gy + 4 * ppu),
                             QPointF(x, y + 1)]))
