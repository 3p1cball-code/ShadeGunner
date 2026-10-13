"""Bodenfahrzeuge und Straßen-Hindernisse als gecachte Pixelbilder (Seitenansicht).

Gezeichnet in Design-Einheiten (= Welt-Einheiten; Boden bei y = 0, Fahrtrichtung +x)
und direkt in Zielgröße gerastert. Jedes Bild kommt mit einer Leuchtschicht
(Scheinwerfer, Rücklichter, Neon-Unterboden, Automatenfront) für den Glow-Pass.
Lebende Teile (Blaulicht, Feuer, Blinklampen, Lichtkegel) zeichnet render/scene.py.
"""

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QImage, QLinearGradient, QPainter, QPen, QPolygonF

from .. import config
from . import pixfont

C = config.NOIR16
CYAN, MAGENTA, AMBER, GREEN, TEAL = C[12], C[13], C[14], C[15], C[11]
PALE, WHITE, RED, NBLUE = C[9], C[10], C[6], C[8]
CRIMSON = (150, 28, 40)

_CACHE = {}
VEH_SCALE = 1.5    # Zeichnung in 2/3-Einheiten, Welt-Maße in sim.VEHICLES

# Farbwelt im Stil von Syd Meads Blade-Runner-Fahrzeugen: gedeckte Metallics,
# überbaute Lichtleisten, verkleidete Räder, nachgerüstete Rohre und Lüftungen.
BODY = {
    "car": [(40, 46, 64), (64, 36, 46), (36, 58, 64), (78, 80, 92), (58, 50, 40),
            (52, 60, 96), (46, 66, 58), (70, 52, 74), (30, 36, 52), (86, 60, 52),
            (96, 84, 60), (58, 72, 84), (44, 40, 56), (72, 84, 68)],
    "taxi": [(196, 150, 52), (186, 120, 40), (206, 168, 74), (168, 132, 50), (120, 140, 150), (150, 158, 90)],
    "police": [(70, 82, 104)],
    "truck": [(70, 66, 62), (78, 52, 40), (52, 64, 76), (64, 72, 54), (84, 74, 58), (56, 58, 70)],
    "bike": [(30, 30, 40), (90, 20, 50), (24, 50, 60), (70, 58, 30), (40, 44, 66), (88, 44, 36)],
    "limo": [(14, 14, 20), (30, 16, 26)],
    "classic": [(70, 108, 106), (150, 140, 112), (90, 40, 44), (24, 24, 28), (96, 120, 140), (100, 136, 116),
                (120, 92, 60), (60, 64, 70)],
    "bus": [(54, 60, 78), (70, 52, 60), (40, 66, 70), (72, 66, 44), (58, 44, 64), (46, 54, 54), (84, 72, 52)],
}
UNDERGLOW = [CYAN, MAGENTA, NBLUE, TEAL, AMBER, GREEN, RED]
# Akzentfarbe für Zierlinien, Dächer, Schweller und Werbebanner
ACCENT = [(196, 150, 52), (224, 72, 150), (64, 210, 220), (255, 138, 44),
          (122, 74, 168), (34, 96, 104), (138, 32, 56), (162, 168, 180)]
_ZONE = [None]


def set_zone(zone_index):
    """Unterboden-Neon und Zierfarben aus der Zonenpalette (Farbkuratierung je Level)."""
    global UNDERGLOW, ACCENT
    if _ZONE[0] == zone_index:
        return
    _ZONE[0] = zone_index
    neon = config.zone_colors(zone_index, "people")
    UNDERGLOW = list(neon)
    pal = config.zone_look(zone_index)["pal"]
    ACCENT = list(neon) + [_mul(c, 0.7) for c in neon[:3]] + [pal[5]]
    _CACHE.clear()


LIVERY = ["TYRELL", "SHIMATA", "PAN AM", "OFF-WORLD", "NEXUS 6", "EYE WORKS",
          "DNA ROW", "KOBAYASHI", "WALLACE", "SECTOR 4", "HADES", "VOIGHT-KAMPFF"]
BUS_OP = ["OFF-WORLD", "SHIMATA", "TYRELL", "PAN AM", "KOBAYASHI"]
BUS_ROUTE = ["4 CHINATOWN", "12 HADES", "9 SECTOR 4", "7 DNA ROW", "2 OFF-WORLD", "11 TYRELL", "6 EYE WORKS"]
TAXI_SIGN = ["TAXI", "CAB", "TAXI", "METRO", "TAXI"]
VARIANTS = 32      # unterscheidbare Varianten je Fahrzeugart (Cache-Schlüssel)
HEAD = (255, 250, 230)
TAIL = (236, 34, 40)
WIN = (24, 34, 58)
CHROME = (128, 134, 148)


def _q(c, a=255):
    return QColor(int(c[0]), int(c[1]), int(c[2]), a)


def _tint(c, k):
    """Helligkeit leicht streuen (k = -3..3), damit gleiche Palettenfarben nicht gleich wirken."""
    return _mul(c, 1.0 + 0.10 * k)


def _mul(c, f):
    return (max(0, min(255, int(c[0] * f))), max(0, min(255, int(c[1] * f))), max(0, min(255, int(c[2] * f))))


def _poly(p, pts, col, a=255):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_q(col, a))
    p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))


def _rect(p, x, y, w, h, col, a=255):
    p.fillRect(QRectF(x, y, w, h), _q(col, a))


def _ell(p, x, y, w, h, col, a=255):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_q(col, a))
    p.drawEllipse(QRectF(x, y, w, h))


def _line(p, x0, y0, x1, y1, col, wd=0.6):
    pen = QPen(_q(col))
    pen.setWidthF(wd)
    p.setPen(pen)
    p.drawLine(QPointF(x0, y0), QPointF(x1, y1))
    p.setPen(Qt.PenStyle.NoPen)


def _wheel(p, x, r, skirt=None, cover=None):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_q((8, 8, 12)))
    p.drawEllipse(QRectF(x - r, -2 * r, 2 * r, 2 * r))
    if cover is not None:     # Radkappe/Scheibe (Mead: geschlossene Räder)
        p.setBrush(_q(cover))
        p.drawEllipse(QRectF(x - r * 0.72, -r * 1.72, r * 1.44, r * 1.44))
        p.setBrush(_q(_mul(cover, 1.5)))
        p.drawEllipse(QRectF(x - r * 0.2, -r * 1.2, r * 0.4, r * 0.4))
    else:
        p.setBrush(_q((60, 62, 72)))
        p.drawEllipse(QRectF(x - r * 0.45, -r * 1.45, r * 0.9, r * 0.9))
    if skirt is not None:
        _rect(p, x - r - 0.5, -2 * r - 0.5, 2 * r + 1, r * 1.15, skirt)
        _rect(p, x - r - 0.5, -r * 0.85 - 0.5, 2 * r + 1, 0.5, _mul(skirt, 0.5))


def _stencil(p, word, x, y, width, col, d, max_sc=1.0):
    """Schriftzug auf der Karosserie (wird bei d < 0 vorgespiegelt, weil das
    ganze Bild danach gespiegelt wird)."""
    img = pixfont.render(word, col, 1, shadow=None)
    sc = min(max_sc, width / max(1, img.width()))
    tot = abs(p.transform().m11()) or 1.0      # auf ganze Bildpunkte schnappen: scharfe Schrift
    if sc * tot >= 0.75:
        sc = max(1, round(sc * tot)) / tot
    p.save()
    if d < 0:
        p.translate(x + img.width() * sc, y)
        p.scale(-sc, sc)
    else:
        p.translate(x, y)
        p.scale(sc, sc)
    p.drawImage(0, 0, img)
    p.restore()


def _lamps(p, e, xs, y, w, h, col):
    for q in (p, e):
        for x in xs:
            _rect(q, x, y, w, h, col)


# ---------------------------------------------------------------------------- Spinner
SPIN_L = 62.0     # Länge in Zeichen-Einheiten
# Live-Lichtpunkte (Zeichen-Einheiten, Fahrtrichtung +x) für render/scene.py
SPIN_BAR = (-14.0, -18.8, 10.0, 2.0)     # Lichtbalken x, y, w, h
SPIN_NOSE = (27.6, -8.0)                 # Bug-Scheinwerfer
SPIN_TAIL = (-31.0, -10.5)


def _draw_spinner(p, e, police, rnd, rim, d=1, detail=True):
    """Spinner nach Syd Mead: geschlossenes Lift-Fahrzeug mit Kapsel-Kanzel über dem
    vorderen Viertel, zwei kugeligen Radgondeln vor dem Bug, verdecktem Heck."""
    body = (70, 82, 104) if police else ((44, 50, 62), (58, 44, 54), (40, 60, 66))[rnd % 3]
    dark, hi = _mul(body, 0.5), _mul(body, 1.5)
    glow = TAIL if police else UNDERGLOW[(rnd >> 8) % len(UNDERGLOW)]
    # Unterboden-Glühen (Polizei rot) + Turbinenauslässe
    for q in (p, e):
        _rect(q, -25, -3.4, 42, 1.0, glow)
        _rect(q, -27, -5.0, 3.0, 1.2, _mul(AMBER, 0.8))
    # verdecktes Hinterrad (nur ein Schlitz)
    _rect(p, -24, -4.2, 12, 1.4, (8, 8, 12))
    # Rumpf: hohes Heck mit Turbinendeck, Dach fällt zur Kanzel, Bug taucht ab
    hull = [(-31, -4.6), (-31.4, -12.8), (-29.5, -15.6), (-9, -16.6), (-4, -16.8), (16, -13.4), (23, -10.6),
            (27.2, -8.8), (27.6, -6.2), (22, -4.4), (-29, -3.6)]
    _poly(p, hull, body)
    # dunkle Seitenschürze
    _poly(p, [(-31, -8.2), (21, -8.2), (23.5, -5.6), (22, -4.4), (-29, -3.6), (-31, -4.6)], _mul(body, 0.62))
    # Kanzel (Kapsel über dem vorderen Viertel)
    can = [(-7, -16.6), (-1, -20.6), (8, -20.6), (15.5, -15.6), (22.4, -10.8), (12, -11.4), (-5, -12.8)]
    _poly(p, can, WIN)
    _line(p, -0.5, -20.2, 8, -20.2, _mul(rim, 0.95), 0.8)
    _line(p, 9, -19.6, 15.5, -15.0, _mul(rim, 0.7), 0.6)
    _line(p, 4.5, -20.4, 9.5, -11.6, _mul(body, 0.9), 0.9)        # Mittelstrebe
    _ell(p, 0.5, -18.6, 3.2, 3.4, (12, 14, 22))                     # Pilot
    for q in (p, e):
        _rect(q, 6.5, -14.4, 3.0, 0.8, _mul(CYAN, 0.6))           # HUD-Schimmer im Glas
    # Turbinen-Lamellen am Heck + Kantenlicht
    for i in range(6):
        _rect(p, -28 + i * 2.4, -14.4, 1.2, 3.8, dark)
    _rect(p, -29, -15.8, 21, 0.8, _mul(rim, 0.85))
    _rect(p, -31, -8.6, 52, 0.6, hi)
    # Radgondel vorn (kugelig, ragt vor den Bug)
    _rect(p, 17, -7.2, 7, 2.2, dark)
    _ell(p, 20.2, -9.4, 9.2, 9.0, _mul(body, 0.8))
    _ell(p, 21.0, -5.4, 7.6, 5.4, (8, 8, 12))
    _ell(p, 22.6, -8.6, 3.6, 2.0, _mul(rim, 0.6))
    # Lichtbalken + Mittelscheinwerfer (live: render/scene.py)
    bx, by, bw, bh = SPIN_BAR
    if police:
        _rect(p, bx, by, bw, bh, (20, 20, 30))
        _rect(p, bx + 3.5, by - 1.2, 3, 1.2, (30, 30, 40))
    for q in (p, e):
        _rect(q, SPIN_NOSE[0] - 1.2, -9.4, 1.4, 1.2, HEAD)            # überbaute Lichtleiste
        _rect(q, SPIN_NOSE[0] - 1.6, -7.8, 1.6, 0.9, HEAD)
        _rect(q, 24.5, -11.2, 1.4, 0.8, AMBER)
        _rect(q, -31.6, -12.0, 1.0, 3.2, TAIL)
        _rect(q, -31.6, -7.4, 1.0, 1.2, TAIL)
    if police and detail:
        _stencil(p, "POLICE", -26.5, -12.4, 15.0, (226, 230, 236), d, 0.5)
        _stencil(p, "44", 2.0, -7.6, 4.0, (226, 230, 236), d, 0.45)
        for i in range(5):                                              # Warnstreifen
            _poly(p, [(8 + i * 2, -5.0), (9 + i * 2, -7.6), (10 + i * 2, -7.6), (9 + i * 2, -5.0)],
                  (220, 180, 40) if i % 2 == 0 else (14, 14, 18))
        for q in (p, e):
            _rect(q, -20, -4.4, 1.6, 0.9, (90, 140, 255))
            _rect(q, 10, -4.4, 1.6, 0.9, TAIL)


def spinner_image(ppx, police, d=1, far=False):
    """Gecachtes Spinner-Sprite. ppx = Bildpunkte pro Zeichen-Einheit.
    Rückgabe (img, emit, ax, ay_mitte, ay_boden): Anker am Rumpfzentrum (y = -10)
    bzw. am Boden (y = 0)."""
    kpx = max(0.25, round(ppx * 8) / 8)
    key = ("s", kpx, police, d, far)
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    w = int(64 * kpx) + 8
    hh = int(24 * kpx) + 8
    ax, ayg = w // 2, hh - 3
    img = QImage(w, hh, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    em = QImage(w, hh, QImage.Format.Format_ARGB32_Premultiplied)
    em.fill(0)
    p, e = QPainter(img), QPainter(em)
    for q in (p, e):
        q.translate(ax, ayg)
        q.scale(kpx, kpx)
    _draw_spinner(p, e, police, 1 if not far else 2, (150, 160, 190) if not far else (70, 76, 100), d,
                  detail=kpx >= 0.9)
    p.end()
    e.end()
    if far:      # ferne Spinner: in den Dunst getaucht
        q = QPainter(img)
        q.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
        q.fillRect(0, 0, w, hh, QColor(16, 18, 30, 150))
        q.end()
    img = _outline(img)
    if d < 0:
        img = img.mirrored(True, False)
        em = em.mirrored(True, False)
        ax = w - 1 - ax
    res = (img, em, ax, ayg - 10 * kpx, ayg)
    if len(_CACHE) > 600:
        _CACHE.clear()
    _CACHE[key] = res
    return res


# ---------------------------------------------------------------------------- Bodenverkehr
def _sedan(p, e, body, glow, rim, accent, style, livery, d):
    """Deckard-Sedan: ausgemusterter Flug-Sedan, Klappen entfernt, Lichtmuster behalten."""
    for q in (p, e):
        _rect(q, -23, -2.6, 46, 1.0, glow)
    _poly(p, [(-29, -4), (-29.6, -10.6), (-27, -12.2), (-15.5, -12.8), (-11.5, -18.8), (5, -19.4), (9, -18.8),
              (15, -13.0), (26, -11.8), (29.2, -9.8), (29.6, -5.2), (27, -3.6), (-27, -3.6)], body)
    _poly(p, [(-13, -13.0), (-10.2, -18.0), (4.6, -18.5), (8.2, -17.8), (13.2, -13.0)], WIN)
    _rect(p, -2.4, -18.4, 1.3, 5.6, body)                                # B-Säule
    _line(p, 12.6, -13.4, 9.6, -16.6, (12, 12, 16), 0.5)                # überbaute Wischer
    _line(p, 8.4, -13.4, 5.6, -16.4, (12, 12, 16), 0.5)
    _rect(p, -10.6, -18.9, 15.4, 0.7, _mul(rim, 0.9))
    _rect(p, -28, -12.4, 13, 0.7, _mul(rim, 0.7))
    _rect(p, 14, -12.0, 12, 0.6, _mul(rim, 0.6))
    # Gullwing-Fuge + entfernte Luftleitklappen (Vertiefungen)
    _rect(p, -12.6, -12.6, 0.5, 7.6, _mul(body, 0.45))
    _rect(p, 6.4, -12.6, 0.5, 7.6, _mul(body, 0.45))
    for x0 in (-26.0, 16.5):
        _rect(p, x0, -10.4, 8.5, 2.6, _mul(body, 0.5))
        _rect(p, x0, -10.4, 8.5, 0.5, _mul(rim, 0.5))
    _rect(p, -29.4, -6.6, 59, 1.5, CHROME)                              # Stoßleiste
    _rect(p, -29.4, -6.6, 59, 0.5, _mul(rim, 1.0))
    # Variante: Zierlinie / Zweifarbdach / Schweller / Türdecal / Doppelstreifen
    if style == 0:
        _rect(p, -27, -8.8, 53.5, 1.1, accent)
    elif style == 1:
        _rect(p, -12.8, -18.9, 21.8, 1.0, accent)
        _rect(p, -27, -8.8, 53.5, 0.5, _mul(accent, 0.75))
    elif style == 2:
        _rect(p, -27.5, -5.3, 52.5, 1.5, accent)
    elif style == 3:
        _stencil(p, livery, -25.0, -11.2, 15.0, accent, d, 0.5)
    else:
        _rect(p, -27, -9.7, 53.5, 0.6, accent)
        _rect(p, -27, -7.9, 53.5, 0.6, accent)
    _wheel(p, -18, 3.6, skirt=body)
    _wheel(p, 18, 3.6, skirt=body)
    _lamps(p, e, (27.6, 28.4), -10.6, 0.7, 1.0, HEAD)                   # Lichtmuster vorn
    _lamps(p, e, (26.6, 27.6, 28.6), -8.8, 0.7, 0.8, HEAD)
    _lamps(p, e, (-29.8,), -11.2, 1.0, 3.0, TAIL)
    _lamps(p, e, (-29.4, -27.8, -26.2), -5.6, 0.9, 0.7, TAIL)
    for q in (p, e):
        _rect(q, 24, -11.4, 1.4, 0.6, AMBER)


def _classic(p, e, body, glow, rim, accent, style, d):
    """60er-Jahre-Straßenkreuzer wie im Film: lang und flach, Heckflossen, Chrom,
    runde Doppelscheinwerfer, Weißwandreifen - teils mit Gepäck auf dem Dach,
    nachgerüsteten Kabeln oder einem Neonstreifen darunter."""
    if style in (3, 4):
        for q in (p, e):
            _rect(q, -26, -2.6, 52, 0.9, glow)
    _poly(p, [(-31.6, -5), (-32.4, -9.2), (-31.2, -12.4), (-27, -10.8), (-14.5, -10.9), (-10.5, -16.4),
              (7.8, -16.8), (13.2, -11.2), (28.6, -10.4), (31.8, -8.8), (32.2, -5.2), (30, -3.6), (-30, -3.6)], body)
    if style == 2:                                                       # Zweifarb-Dach
        _poly(p, [(-10.5, -16.4), (7.8, -16.8), (8.6, -15.6), (-10.2, -15.4)], _mul(accent, 0.7))
    _poly(p, [(-9.4, -11.2), (-7.4, -15.6), (7.0, -15.9), (11.4, -11.2)], WIN)
    _rect(p, -1.2, -15.8, 1.2, 4.8, body)                               # B-Säule
    _rect(p, -10.2, -16.8, 18.6, 0.6, _mul(rim, 0.9))
    _rect(p, -30.5, -11.0, 17, 0.6, _mul(rim, 0.7))
    _rect(p, 13.5, -10.9, 15, 0.6, _mul(rim, 0.6))
    _rect(p, -30, -8.0, 60, 0.6, CHROME)                                # Zierleiste
    _rect(p, -33.2, -6.6, 4.4, 2.2, CHROME)                             # Stoßstangen
    _rect(p, 29.8, -6.6, 4.4, 2.2, CHROME)
    _rect(p, -33.2, -6.6, 4.4, 0.5, _mul(rim, 1.0))
    _rect(p, 29.8, -6.6, 4.4, 0.5, _mul(rim, 1.0))
    _rect(p, 29.6, -9.4, 2.2, 2.4, _mul(CHROME, 0.7))                   # Kühlergrill
    _line(p, 11.6, -11.4, 9.0, -15.0, (12, 12, 16), 0.5)                # Wischer
    if style in (0, 1):                                                  # Gepäck auf dem Dach
        _rect(p, -7.0, -19.2, 13.0, 2.4, _mul((96, 80, 60), 0.8 + 0.2 * style))
        _rect(p, -6.0, -20.6, 7.0, 1.6, _mul((80, 90, 84), 0.8))
        _line(p, -6.5, -19.4, -6.5, -16.8, (20, 20, 22), 0.4)
        _line(p, 5.5, -19.4, 5.5, -16.8, (20, 20, 22), 0.4)
    if style == 4:                                                       # nachgerüstete Kabel
        _line(p, 20, -10.8, 24, -13.0, (20, 20, 24), 0.5)
        _line(p, 24, -13.0, 27, -10.6, (20, 20, 24), 0.5)
    for x in (-19.0, 19.0):
        _wheel(p, x, 3.7, cover=(150, 152, 146))                        # Weißwand + Chromkappe
        _rect(p, x - 4.3, -7.9, 8.6, 1.0, _mul(body, 0.55))             # Radlauf
    _lamps(p, e, (31.2,), -9.4, 1.1, 1.1, HEAD)                         # runde Doppelscheinwerfer
    _lamps(p, e, (31.2,), -7.7, 1.1, 1.1, HEAD)
    _lamps(p, e, (-32.4,), -12.0, 0.9, 2.4, TAIL)                       # Flossenleuchten
    _lamps(p, e, (-32.6,), -8.2, 0.8, 1.2, TAIL)


def _metrokab(p, e, body, glow, rim, d, accent, style):
    """Metrokab: hoher Glas-Dom über kastigem Unterbau, Schachbrettband, Dachlampe."""
    for q in (p, e):
        _rect(q, -22, -2.6, 44, 1.0, glow)
    _poly(p, [(-28, -4), (-28.4, -11), (-25, -12.4), (22, -12.4), (27.4, -10.2), (28.2, -5.6), (26, -3.6),
              (-26, -3.6)], body)
    _poly(p, [(-20, -12.2), (-18.4, -19.4), (-12.6, -23.0), (6.2, -23.0), (14.4, -20.0), (21.6, -12.2)], WIN)
    _rect(p, -12.6, -24.0, 18.8, 1.2, (22, 22, 28))                    # Dach-Kappe
    _line(p, -12, -22.4, 6, -22.4, _mul(rim, 0.9), 0.7)
    _line(p, 6.4, -22.2, 14.4, -19.4, _mul(rim, 0.6), 0.6)
    _rect(p, -3.2, -23.0, 1.2, 10.6, (22, 22, 28))                     # Mittelstrebe
    _ell(p, -11.5, -19.6, 3.6, 3.8, (14, 14, 20))                      # Fahrgast
    _ell(p, 7.0, -19.4, 3.4, 3.6, (14, 14, 20))                        # Fahrer
    for q in (p, e):
        _rect(q, 10.5, -15.8, 3.0, 0.8, _mul(AMBER, 0.6))             # Taxameter-Schimmer
    if style != 3:                                                      # Schachbrettband (nicht immer)
        for i in range(20):
            x = -27 + i * 2.7
            _rect(p, x, -9.2 + (0 if i % 2 else 1.1), 1.35, 1.1, (14, 14, 18))
            _rect(p, x + 1.35, -9.2 + (1.1 if i % 2 else 0), 1.35, 1.1, (14, 14, 18))
    if style in (0, 2, 4):                                              # Zierlinie
        _rect(p, -28, -8.7, 53, 0.9, accent)
    _rect(p, -28, -12.6, 50, 0.6, _mul(rim, 0.8))
    _rect(p, -28.4, -6.0, 56.6, 1.2, (24, 24, 30))
    sign_col = accent if style in (1, 4) else AMBER                   # Dachschild
    _rect(p, -7, -27.0, 11, 3.0, (16, 16, 22))
    for q in (p, e):
        _rect(q, -6.2, -26.4, 9.4, 1.8, sign_col)
    _stencil(p, TAXI_SIGN[style % len(TAXI_SIGN)], -5.8, -26.5, 7.0, (30, 20, 10), d, 0.4)
    _wheel(p, -17, 3.4, skirt=body)
    _wheel(p, 17, 3.4, cover=_mul(body, 0.7))
    _lamps(p, e, (26.6, 27.4), -10.0, 0.8, 1.4, HEAD)
    _lamps(p, e, (-28.6,), -10.6, 1.0, 2.6, TAIL)


def _armadillo(p, e, body, rim, rnd, accent, livery, d):
    """Sebastians Laster: Panzer aus überlappenden, ausgemusterten Deflektorplatten."""
    hl = 46.0
    for q in (p, e):
        _rect(q, -hl + 4, -2.2, 2 * hl - 8, 1.0, AMBER)
    _rect(p, -hl, -8.0, 2 * hl, 3.6, (20, 20, 24))                     # Fahrgestell
    x0, x1, n = -hl, 21.0, 7
    pw = (x1 - x0) / n
    tints = [body, _mul(body, 0.85), (70, 54, 44), _mul(body, 1.12), (58, 62, 70), _mul(accent, 0.72),
             _mul(body, 1.25)]

    def top(x):
        u = (x - x0) / (x1 - x0)
        return -9.0 - 22.5 * max(0.0, math.sin(math.pi * min(1.0, max(0.0, u)))) ** 0.55

    for i in range(n):
        a, b = x0 + i * pw, x0 + (i + 1) * pw + 1.6
        c = tints[(rnd >> i) % len(tints)]
        pts = [(a, -7.6)] + [(a + (b - a) * k / 4, top(a + (b - a) * k / 4)) for k in range(5)] + [(b, -7.6)]
        _poly(p, pts, c)
        _rect(p, a, top(a + 0.5), 1.0, -7.6 - top(a + 0.5), _mul(c, 0.5))     # Überlappungsschatten
        _line(p, b - 0.6, top(b - 0.6) + 0.4, b - 0.6, -8.0, _mul(rim, 0.75), 0.6)   # Kantenlicht
        for yy in (-10.0, top((a + b) / 2) + 3.0):
            _rect(p, (a + b) / 2, yy, 0.6, 0.6, _mul(c, 1.6))                   # Nieten
    _stencil(p, livery, -hl + 8.0, -22.0, 34.0, _mul(PALE, 0.7), d, 0.9)   # Firmenaufschrift
    _rect(p, -42, -10.2, 20, 1.4, _mul(accent, 0.8))                  # Spanngurt
    _rect(p, -hl + 2, -9.0, 62, 0.8, (96, 96, 108))                    # nachgerüstetes Rohr
    for x in range(int(-hl) + 6, 18, 9):
        _rect(p, x, -9.4, 1.2, 1.6, (120, 120, 130))
    for i in range(6):                                                  # Warnstreifen
        _poly(p, [(-hl + i * 2, -4.6), (-hl + 1 + i * 2, -8.0), (-hl + 2 + i * 2, -8.0), (-hl + 1 + i * 2, -4.6)],
              (220, 180, 40) if i % 2 == 0 else (14, 14, 18))
    # Kabine
    cab = _mul(body, 1.15)
    _poly(p, [(20, -5), (20, -24.5), (30, -25.5), (40, -17), (46, -13.5), (46, -5)], cab)
    _poly(p, [(24, -23), (30, -24), (37.6, -17), (24, -16.4)], WIN)
    _rect(p, 20, -25.0, 10, 0.8, _mul(rim, 0.9))
    for y in (-12.0, -10.4, -8.8):
        _rect(p, 41, y, 5, 0.6, (24, 24, 28))                            # Kühlergrill
    _rect(p, 18.2, -31.0, 1.6, 24.0, (60, 60, 66))                    # Auspuff-Stack
    for q in (p, e):
        _rect(q, 18.2, -31.6, 1.6, 0.8, AMBER)
    for x in (-hl + 10, -hl + 21, 33):
        _wheel(p, x, 4.2, cover=(40, 40, 46))
    _lamps(p, e, (hl - 2,), -11.5, 2.0, 2.4, HEAD)
    _lamps(p, e, (-hl,), -11.0, 1.4, 3.4, TAIL)
    _lamps(p, e, (-30.0, -18.0, -6.0), top(-30.0) - 0.4, 1.2, 0.8, AMBER)
    _lamps(p, e, (22.0, 26.0), -26.2, 2.0, 0.8, AMBER)


def _limo(p, e, body, rim, d, accent):
    """Aerial-Limousine: lang, lackschwarz, Schlitzfenster, Radgondeln vorn, Goldlinie."""
    for q in (p, e):
        _rect(q, -36, -2.4, 64, 0.9, NBLUE)
    _poly(p, [(-42, -4), (-42.4, -10.4), (-38, -12.8), (-10, -13.6), (-4, -16.6), (18, -16.6), (28, -12.6),
              (38, -10.6), (42, -8.2), (42.2, -5.2), (37, -3.6), (-40, -3.6)], body)
    _poly(p, [(-3, -15.6), (17, -15.6), (24, -13.0), (-1, -13.0)], (30, 24, 50))
    _rect(p, -22, -12.4, 9, 1.3, (30, 24, 50))                          # Opernfenster
    _rect(p, -38, -13.0, 76, 0.6, _mul(rim, 0.9))
    _rect(p, -4, -16.8, 22, 0.6, _mul(rim, 1.0))
    _poly(p, [(-42, -10.4), (-41, -17.5), (-38.6, -17.5), (-37, -12.6)], _mul(body, 1.3))   # Heckflosse
    _rect(p, -42, -8.8, 80, 0.7, accent)                                # Zierlinie
    for q in (p, e):
        _rect(q, 2.0, -8.9, 18, 0.5, _mul(accent, 0.8))
    _poly(p, [(-27, -9.6), (-25.2, -12.0), (-23.4, -9.6)], _mul(accent, 1.05))   # Tyrell-Pyramide
    # Radgondel vorn, Hinterrad verkleidet
    _ell(p, 29.0, -9.0, 9.0, 8.6, _mul(body, 1.6))
    _ell(p, 29.8, -5.2, 7.4, 5.2, (8, 8, 12))
    _rect(p, -32, -4.4, 12, 1.2, (8, 8, 12))
    _lamps(p, e, (41.0,), -9.6, 1.2, 1.0, HEAD)
    _lamps(p, e, (40.0,), -7.4, 2.0, 0.6, HEAD)
    for q in (p, e):
        _rect(q, -42.4, -9.8, 1.2, 5.0, TAIL)
        _rect(q, -40, -5.0, 14, 0.6, TAIL)


def _bike(p, e, body, glow, rim, accent):
    for q in (p, e):
        _rect(q, -11, -1.6, 22, 0.9, glow)
    _wheel(p, -10, 4.0, cover=_mul(body, 1.3))
    _wheel(p, 10, 4.0, cover=_mul(body, 1.3))
    for q in (p, e):           # Leuchtring in der Radscheibe
        pen = QPen(_q(glow))
        pen.setWidthF(0.5)
        q.setPen(pen)
        q.setBrush(Qt.BrushStyle.NoBrush)
        for x in (-10, 10):
            q.drawEllipse(QRectF(x - 2.6, -6.6, 5.2, 5.2))
        q.setPen(Qt.PenStyle.NoPen)
    _poly(p, [(-15, -6), (-6, -11.4), (7, -12.6), (15.4, -8.4), (13, -5), (-12, -4.5)], body)
    _poly(p, [(-13, -6.0), (-5.5, -10.4), (6, -11.4), (12, -8.4), (10.5, -6.6), (-11, -5.6)], _mul(accent, 0.85))
    _rect(p, -6, -11.6, 13, 0.8, _mul(rim, 0.9))
    _poly(p, [(6, -12.4), (11, -15.4), (13.6, -11.2)], (40, 50, 80))     # Windschild
    # Fahrer, nach vorn gebeugt
    _poly(p, [(-6, -10.5), (-1, -19.5), (5, -18.5), (6, -12)], (24, 24, 32))
    _ell(p, 2.5, -24.0, 5.6, 5.2, (30, 30, 40))
    for q in (p, e):
        _rect(q, 5.5, -22.6, 2.4, 1.2, glow)          # Visier
        _rect(q, 14.2, -9, 1.6, 1.6, HEAD)
        _rect(q, -14.6, -7, 1.2, 1.4, TAIL)


def _bus(p, e, body, rim, rnd, d, accent, livery):
    """Stadtbus (aus Meads Formensprache extrapoliert): Fensterband voller Fahrgäste."""
    hl = 60.0
    for q in (p, e):
        _rect(q, -54, -2.4, 108, 1.0, TEAL)
    _poly(p, [(-60, -4), (-60.4, -33), (-57, -36), (50, -36), (56, -33.4), (60, -26), (60.4, -6), (58, -3.6),
              (-58, -3.6)], body)
    _rect(p, -40, -38.4, 22, 2.6, _mul(body, 0.7))                     # Dachaggregate
    _rect(p, 6, -38.0, 14, 2.2, _mul(body, 0.7))
    _rect(p, -57, -36.2, 107, 0.7, _mul(rim, 0.9))
    warm, cool = (196, 150, 92), (150, 176, 200)
    for i in range(10):
        x = -55 + i * 9.6
        lit = (rnd >> i) & 3
        c = warm if lit == 0 else (cool if lit == 1 else (40, 50, 70))
        _rect(p, x, -30, 8.2, 9.0, c)
        if lit != 2:
            _rect(e, x, -30, 8.2, 9.0, _mul(c, 0.4))
        if (rnd >> (i + 3)) & 1:                                       # Fahrgast-Silhouetten
            _ell(p, x + 2.0, -26.6, 3.2, 3.4, (16, 16, 22))
            _rect(p, x + 1.2, -23.4, 4.8, 2.6, (16, 16, 22))
    _rect(p, -57, -31.0, 107, 1.0, _mul(body, 0.6))
    _poly(p, [(50, -33.6), (55.6, -33), (59.2, -26), (59.2, -20), (50, -20)], WIN)   # Front
    _rect(p, 34, -19.4, 8, 15.0, (34, 40, 56))                         # Tür
    for q in (p, e):
        _rect(q, 34.6, -18.8, 6.8, 0.8, _mul(PALE, 0.7))
    _rect(p, -52, -18.6, 70, 7.0, _mul(accent, 0.45))                  # Werbeband
    for q in (p, e):
        _rect(q, -52, -18.6, 70, 0.8, _mul(accent, 1.0))
    _rect(p, -52, -12.0, 70, 0.7, _mul(accent, 0.8))
    _stencil(p, livery, -48, -17.4, 40.0, _mul(PALE, 0.85), d, 0.9)
    _rect(p, 30, -35.4, 18, 3.4, (12, 12, 16))                          # Linienanzeige
    route = BUS_ROUTE[(rnd >> 5) % len(BUS_ROUTE)]
    _stencil(p, route, 31, -34.8, 16.0, AMBER, d, 0.45)
    _stencil(e, route, 31, -34.8, 16.0, AMBER, d, 0.45)
    _rect(p, -60, -8.0, 120, 1.2, (24, 24, 30))
    _wheel(p, -44, 4.6, skirt=body)
    _wheel(p, 40, 4.6, skirt=body)
    _lamps(p, e, (58.6,), -12.0, 1.6, 2.2, HEAD)
    _lamps(p, e, (-60.8,), -12.0, 1.2, 4.0, TAIL)
    _lamps(p, e, (-56.0, -20.0, 16.0, 46.0), -37.0, 1.4, 0.8, AMBER)


def _draw_vehicle(p, e, kind, seed, rim, d=1):
    rnd = (seed * 2654435761) & 0xFFFFFFFF
    pal = BODY[kind]
    body = _tint(pal[rnd % len(pal)], ((rnd >> 4) % 7) - 3)
    glow = UNDERGLOW[(rnd >> 8) % len(UNDERGLOW)]
    accent = ACCENT[(rnd >> 13) % len(ACCENT)]
    style = (rnd >> 17) % 5
    livery = LIVERY[(rnd >> 3) % len(LIVERY)]
    if kind == "police":
        p.save()
        e.save()
        for q in (p, e):
            q.scale(60.0 / SPIN_L, 1.0)
        _draw_spinner(p, e, True, rnd, rim, d)
        p.restore()
        e.restore()
    elif kind == "car":
        _sedan(p, e, body, glow, rim, accent, style, livery, d)
    elif kind == "classic":
        _classic(p, e, body, glow, rim, accent, style, d)
    elif kind == "taxi":
        _metrokab(p, e, body, glow, rim, d, accent, style)
    elif kind == "truck":
        _armadillo(p, e, body, rim, rnd, accent, livery, d)
    elif kind == "limo":
        _limo(p, e, body, rim, d, accent)
    elif kind == "bike":
        _bike(p, e, body, glow, rim, accent)
    elif kind == "bus":
        _bus(p, e, body, rim, rnd, d, accent, livery)


def vehicle_image(kind, seed, ppu, rim, d=1):
    """(img, emit, ax, ay, length_px): Anker = Boden-Mitte des Fahrzeugs (Fahrtrichtung d)."""
    kpx = round(ppu * 8) / 8
    key = ("v", kind, seed % VARIANTS, kpx, rim, d)
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
    _draw_vehicle(p, e, kind, seed % VARIANTS, rim, d)
    p.end()
    e.end()
    img = _outline(img)
    if d < 0:
        img = img.mirrored(True, False)
        em = em.mirrored(True, False)
        ax = w - 1 - ax
    res = (img, em, ax, ay, L * kpx)
    if len(_CACHE) > 1000:
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
        col = (CYAN, GREEN, AMBER, RED, NBLUE)[rnd % 5]
        _rect(p, -6, -20, 12, 20, (30, 32, 44))
        _rect(p, -6, -20, 12, 0.8, _mul(rim, 0.8))
        for q, a in ((p, 255), (e, 200)):
            _rect(q, -5, -19, 7, 12, _mul(col, 0.55), a)
            for y in (-18, -15, -12):
                _rect(q, -4.5, y, 6, 1.4, _mul(col, 1.1), a)
            _rect(q, 3, -17, 2, 2, (255, 250, 230), a)
        _rect(p, -5, -5, 7, 2.4, (10, 10, 14))
    elif kind == "dustbin":
        # Blechmülltonne mit Rippen; Deckel schief oder daneben, Müll quillt raus
        c = ((70, 74, 72), (58, 66, 70), (76, 70, 60))[rnd % 3]
        _rect(p, -3.4, -8, 6.8, 8, c)
        for y in (-6.4, -3.6, -1.2):
            _rect(p, -3.4, y, 6.8, 0.6, _mul(c, 1.35))
        _rect(p, -3.4, -8, 0.8, 8, _mul(rim, 0.6))
        _rect(p, 2.6, -8, 0.8, 8, _mul(c, 0.55))
        if rnd % 2:
            _poly(p, [(-4.2, -8.8), (3.6, -10.6), (3.9, -9.6), (-4.0, -7.8)], _mul(c, 1.15))
        else:
            _ell(p, 3.0, -2.2, 6.4, 2.2, _mul(c, 1.1))                 # Deckel liegt daneben
            for (x, y, w_, h_, col) in ((-3, -9.4, 3, 1.4, (150, 146, 132)), (0, -9.0, 3, 1.2, (40, 40, 44)),
                                        (-1.5, -10.0, 2, 1.0, (120, 100, 70))):
                _rect(p, x, y, w_, h_, col)
    elif kind == "wreck":
        # ausgeschlachteter 60er-Straßenkreuzer, aufgebockt; Länge ~48, Höhe ~12
        paint = _mul(((70, 92, 96), (100, 80, 56), (62, 66, 84), (112, 92, 72), (88, 50, 44))[rnd % 5], 0.55)
        s_ = 0.75
        for x in (-15, 15):
            _rect(p, x - 2, -3.2, 4, 3.2, (40, 38, 36))                 # Blöcke statt Räder
        body = [(-31.6, -5), (-32.4, -9.2), (-31.2, -12.4), (-27, -10.8), (-14.5, -10.9), (-10.5, -16.4),
                (7.8, -16.8), (13.2, -11.2), (28.6, -10.4), (31.8, -8.8), (32.2, -5.2), (30, -3.6), (-30, -3.6)]
        flip = -1 if rnd % 2 else 1
        _poly(p, [(x * s_ * flip, y * s_ - 0.6) for x, y in body], paint)
        _poly(p, [(x * s_ * flip, y * s_ - 0.6) for x, y in ((-9.4, -11.2), (-7.4, -15.6), (7.0, -15.9),
                                                             (11.4, -11.2))], (10, 12, 14))
        _rect(p, -23, -6.6, 46, 0.5, (100, 102, 100))                    # Chromleiste
        for (x, y, w_, h_) in ((-18, -8.4, 3, 1.4), (-6, -9.0, 2, 1.0), (9, -8.2, 4, 1.2), (16, -7.0, 2, 1.6)):
            _rect(p, x, y, w_, h_, _mul((156, 84, 40), 0.75))              # Rost
        hx = 21.0 * flip
        _poly(p, [(hx - 6 * flip, -8.6), (hx + 2 * flip, -8.2), (hx + 4 * flip, -14.0)], _mul(paint, 0.85))
        for k in range(4):                                               # Kabelgedärm
            _line(p, hx, -8.0, hx + (k - 1.5) * 2.4 * flip, -0.4, ((30, 30, 32), (90, 40, 30), (60, 70, 50))[k % 3],
                  0.5)
        _rect(p, -6, -12.4, 1.0, 1.0, (150, 170, 170))                  # Scherben


_OB_W = {"wreck": 66}
# Zeichenmaßstab je Hindernis (Welt-Einheiten; eine Figur ist ~36 u groß). Baken, Tonnen
# und Wracks waren neben den Leuten zu klein.
OB_SCALE = {"barrier": 1.8, "wreck": 2.3, "barrel": 1.4, "dustbin": 1.4, "crates": 1.3, "bins": 1.25}


def obstacle_image(kind, seed, ppu, rim):
    kpx = round(ppu * 8) / 8
    key = ("o", kind, seed % 5, kpx, rim)
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    sc = OB_SCALE.get(kind, 1.0)
    w = int(_OB_W.get(kind, 30) * sc * kpx) + 6
    hh = int(26 * sc * kpx) + 6
    ax, ay = w // 2, hh - 3
    img = QImage(w, hh, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    em = QImage(w, hh, QImage.Format.Format_ARGB32_Premultiplied)
    em.fill(0)
    p, e = QPainter(img), QPainter(em)
    for q in (p, e):
        q.translate(ax, ay)
        q.scale(kpx * sc, kpx * sc)
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
