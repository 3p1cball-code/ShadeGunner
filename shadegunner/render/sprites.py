"""Prozedurale, skelett-animierte Pixel-Figuren.

Jede Figur ist ein kleiner Gliederpuppen-Rig (Hüfte, Knie, Knöchel, Schulter,
Ellbogen, Hand, Kopf) in Design-Einheiten (Figurhöhe = 48 u, Füße bei y = 0,
Blickrichtung +x). Pro Frame wird die Pose analytisch aus (Animation, Phase)
berechnet und mit QPainter ohne Antialiasing gezeichnet - direkt in der
Zielgröße, deshalb bleiben die Silhouetten bei jeder Tiefe pixelscharf.

Danach: 1-px-Umriss (dunkel) + Rimlight auf der Lichtseite + Tiefennebel. Das
Ergebnis wird pro (Look, Animation, Frame, Höhe, Lichtseite, Nebel, Richtung)
gecacht; Leuchtteile (Schirmstäbe, Scanner, Waffe) kommen als zweites Bild für
den Glow-Pass mit.
"""

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPolygonF

from .. import config

PI = math.pi
C = config.NOIR16

# Animationen: Name -> Frames (zyklisch, außer 'die')
ANIMS = {
    "idle": 4, "walk": 8, "run": 6, "panic": 6, "die": 9,
    "aim": 1, "shoot": 2, "scan": 2, "hurt": 1, "punch": 3, "cower": 2, "jump": 1,
}

# Mantelfarben mit deutschem Adjektiv (Kopfgeld-Beschreibung muss sagbar sein)
COATS = [
    ((44, 52, 86), "dunkelblau"), ((66, 80, 124), "blau"), ((78, 80, 94), "grau"),
    ((126, 32, 58), "rot"), ((34, 96, 106), "türkis"), ((100, 66, 150), "violett"),
    ((96, 120, 166), "hellblau"), ((24, 24, 32), "schwarz"), ((196, 150, 52), "gelb"),
    ((196, 200, 208), "weiß"), ((196, 70, 140), "pink"), ((200, 104, 44), "orange"),
]
COAT_W = [5, 5, 4, 3, 3, 2, 3, 5, 1, 1, 1, 1]
PANTS = [(22, 24, 38), (34, 40, 62), (52, 58, 80), (28, 30, 46), (16, 16, 22)]
SKINS = [(206, 176, 158), (164, 122, 100), (118, 84, 70), (226, 210, 200), (186, 150, 124), (92, 64, 54)]
HAIRS = [(14, 14, 20), (40, 30, 30), (170, 172, 180), (138, 32, 56), (122, 74, 168),
         (64, 210, 220), (226, 210, 160), (10, 10, 14), (224, 72, 150), (200, 104, 44)]
NEON = [C[12], C[13], C[14], C[15], C[11], C[9]]

OUTFITS = ["trench", "trench", "long", "jacket", "jacket", "dress", "cloak", "robe", "hoodie",
           "vest", "suit", "overall"]
HEADS = ["short", "short", "long", "bun", "fedora", "fedora", "cap", "hood", "conical", "conical",
         "mohawk", "bald", "beanie", "ponytail", "visor", "afro"]

# (Wort, Genus) für die Beschreibung: m/f/n
OUTFIT_NAME = dict(trench=("TRENCHCOAT", "m"), long=("LANGER MANTEL", "m"), jacket=("JACKE", "f"),
                   dress=("KLEID", "n"), cloak=("REGENCAPE", "n"), robe=("KUTTE", "f"),
                   hoodie=("KAPUZENPULLI", "m"), vest=("WESTE", "f"), suit=("ANZUG", "m"),
                   overall=("OVERALL", "m"))
HEAD_NAME = dict(short="KURZE HAARE", long="LANGE HAARE", bun="DUTT", fedora="HUT", cap="KAPPE",
                 hood="KAPUZE AUF", conical="STROHHUT", mohawk="IROKESE", bald="GLATZE",
                 beanie="MÜTZE", ponytail="PFERDESCHWANZ", visor="LEUCHTVISIER", afro="AFRO")


def _mul(c, f):
    return (max(0, min(255, int(c[0] * f))), max(0, min(255, int(c[1] * f))),
            max(0, min(255, int(c[2] * f))))


def _adj(word, genus):
    return word.upper() + {"m": "ER", "f": "E", "n": "ES"}[genus]


def describe(look):
    """Zwei sagbare Merkmale (Kleidung, Kopf) für Kopfgeld-Briefings."""
    out = look["outfit"]
    word, g = OUTFIT_NAME[out]
    if out == "cloak":
        cloth = "TRANSPARENTES REGENCAPE"
    elif out == "long":
        cloth = _adj(look["coat_name"], "m") + " LANGMANTEL"
    else:
        cloth = _adj(look["coat_name"], g) + " " + word
    head = HEAD_NAME[look["head"]]
    if look.get("umbrella"):
        head += ", LEUCHTSCHIRM"
    return cloth, head


def random_look(rng, uid, rain=0.6):
    outfit = rng.choice(OUTFITS)
    head = rng.choice(HEADS)
    if outfit == "hoodie" and rng.random() < 0.6:
        head = "hood"
    umbrella = rng.choice(NEON[:5] + [(220, 230, 255)]) if rng.random() < 0.18 + 0.22 * rain else None
    if head in ("conical", "afro"):
        umbrella = None if rng.random() < 0.7 else umbrella
    ci = rng.choices(range(len(COATS)), COAT_W)[0]
    coat, cname = COATS[ci]
    old = rng.random() < 0.07
    bag = rng.choice((None, None, None, None, "bag", "briefcase", "backpack"))
    return dict(
        id=uid, outfit=outfit, head=head, umbrella=umbrella,
        umb_style="bubble" if rng.random() < 0.3 else "flat",
        wf=rng.uniform(0.82, 1.28), hf=rng.uniform(0.88, 1.08) * (0.95 if old else 1.0),
        coat=coat, coat_name=cname, pants=rng.choice(PANTS), skin=rng.choice(SKINS),
        hair=(170, 172, 180) if old else rng.choice(HAIRS), accent=rng.choice(NEON),
        bag=bag, collar=rng.random() < 0.3,
        cig=rng.random() < 0.12, led=rng.random() < 0.16, mask=rng.random() < 0.1, old=old,
    )


PLAYER_LOOK = dict(
    id=-1, outfit="trench", head="short", umbrella=None, wf=1.06, hf=1.03,
    coat=(150, 146, 140), coat_name="beige", pants=(34, 38, 56), skin=(206, 176, 158), hair=(40, 30, 30),
    accent=(64, 210, 220), bag=None, collar=True, player=True, cig=False, led=False, mask=False, old=False,
)


# ---------------------------------------------------------------------------- Pose

def pose(anim, t):
    """Gelenkwinkel für Animation `anim` bei Zyklusphase t (0..1)."""
    phi = 2 * PI * t
    s, c = math.sin(phi), math.cos(phi)
    P = dict(lean=0.0, bob=0.0, crouch=0.0, rot=0.0,
             legs=[(0.0, 0.05), (0.0, 0.05)],     # (far, near): (Oberschenkel, Kniebeuge)
             arms=[(0.08, 0.15), (0.08, 0.15)],   # (far, near): (Oberarm, Unterarm)
             flutter=0.0, gun=False, scanner=False, muzzle=False)
    if anim == "walk":
        A = 0.42
        P["legs"] = [(-A * s, 0.12 + 0.8 * max(0.0, -c)), (A * s, 0.12 + 0.8 * max(0.0, c))]
        P["arms"] = [(0.36 * s + 0.05, 0.25), (-0.36 * s + 0.05, 0.25)]
        P["bob"] = -0.9 * (1 - abs(s))
        P["lean"] = 0.04
        P["flutter"] = 0.3
    elif anim in ("run", "panic"):
        A = 0.78
        P["legs"] = [(-A * s, 0.25 + 1.45 * max(0.0, -c)), (A * s, 0.25 + 1.45 * max(0.0, c))]
        P["bob"] = -1.6 * (1 - abs(s)) + 0.5
        P["lean"] = 0.24
        P["flutter"] = 1.0
        if anim == "run":
            P["arms"] = [(0.9 * s, 1.55), (-0.9 * s, 1.55)]
        else:
            P["arms"] = [(2.55 + 0.35 * math.sin(2 * phi), 0.35), (2.75 - 0.35 * math.sin(2 * phi), 0.3)]
            P["lean"] = 0.1
    elif anim == "idle":
        b = math.sin(phi)
        P["legs"] = [(-0.07, 0.06), (0.08, 0.05)]
        P["arms"] = [(0.06 + 0.03 * b, 0.18), (0.04 - 0.03 * b, 0.2)]
        P["bob"] = 0.25 * b
    elif anim in ("aim", "shoot"):
        P["legs"] = [(-0.2, 0.12), (0.22, 0.18)]
        rec = 0.28 if (anim == "shoot" and t < 0.5) else 0.0
        P["arms"] = [(1.25 + rec * 0.5, 0.32), (PI / 2 - 0.04 + rec, -rec * 0.4)]
        P["lean"] = -0.05 - rec * 0.25
        P["gun"] = True
        P["muzzle"] = anim == "shoot" and t < 0.5
    elif anim == "scan":
        P["legs"] = [(-0.12, 0.08), (0.14, 0.1)]
        P["arms"] = [(0.1, 0.25), (1.8 + 0.05 * s, -0.25)]
        P["scanner"] = True
    elif anim == "hurt":
        P["legs"] = [(-0.3, 0.3), (0.12, 0.4)]
        P["arms"] = [(0.9, 0.6), (-0.7, 0.4)]
        P["lean"] = -0.35
        P["crouch"] = 1.5
    elif anim == "cower":
        tr = 0.06 * s
        P["legs"] = [(-0.12, 0.35), (0.1, 0.4)]
        P["arms"] = [(2.7 + tr, 0.55), (2.85 - tr, 0.5)]
        P["lean"] = -0.1
        P["crouch"] = 1.2
    elif anim == "jump":
        P["legs"] = [(-0.55, 1.5), (0.85, 1.75)]
        P["arms"] = [(-0.9, 0.9), (1.9, 0.6)]
        P["lean"] = 0.18
        P["crouch"] = 2.0
        P["flutter"] = 1.4
    elif anim == "punch":
        k = math.sin(PI * t)
        P["legs"] = [(-0.3, 0.15), (0.32, 0.3)]
        P["arms"] = [(0.6, 1.2), (0.6 + 1.0 * k, 1.3 - 1.2 * k)]
        P["lean"] = 0.15 + 0.2 * k
    elif anim == "die":
        if t < 0.38:
            k = t / 0.38
            P["legs"] = [(-0.1 - 0.4 * k, 0.2 + 1.3 * k), (0.15 + 0.5 * k, 0.2 + 1.5 * k)]
            P["arms"] = [(0.2 + 0.6 * k, 0.3 + 0.4 * k), (0.4 + 0.9 * k, 0.5)]
            P["crouch"] = 7.0 * k
            P["lean"] = 0.35 * k
        else:
            k = min(1.0, (t - 0.38) / 0.5)
            ke = 1 - (1 - k) ** 2
            P["legs"] = [(-0.5 + 0.5 * ke, 1.5 - 1.35 * ke), (0.65 - 0.5 * ke, 1.7 - 1.5 * ke)]
            P["arms"] = [(0.8 + 1.6 * ke, 0.7), (1.3 + 1.5 * ke, 0.5)]
            P["crouch"] = 7.0 * (1 - ke)
            P["lean"] = 0.35 * (1 - ke)
            P["rot"] = -PI / 2 * ke
    return P


def _limb(origin, a, l):
    return QPointF(origin.x() + l * math.sin(a), origin.y() + l * math.cos(a))


# ---------------------------------------------------------------------------- Zeichnen

def _pen(p, col, w, alpha=255):
    pen = QPen(QColor(col[0], col[1], col[2], alpha))
    pen.setWidthF(w)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)


def _fill(p, col, alpha=255):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor(col[0], col[1], col[2], alpha)))


def _poly(p, pts, col, alpha=255):
    _fill(p, col, alpha)
    p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))


def _draw_figure(p, look, P, emit):
    """Zeichnet die Figur in Design-Einheiten (Füße bei 0,0). emit: Painter für Leuchtteile."""
    wf, hf = look["wf"], look["hf"]
    coat, pants, skin = look["coat"], look["pants"], look["skin"]
    outfit, head = look["outfit"], look["head"]
    if outfit == "overall":
        pants = _mul(coat, 0.9)
    far_coat, far_pants = _mul(coat, 0.62), _mul(pants, 0.7)
    leg_w = 3.9 * wf
    arm_w = 3.1 * wf
    old = look.get("old") and P["rot"] == 0.0

    hip = QPointF(0.0, -22.0 * hf + P["crouch"] + P["bob"] + (1.0 if old else 0.0))
    lean = P["lean"] + (0.2 if old else 0.0)
    sh = QPointF(hip.x() + 14.0 * hf * math.sin(lean), hip.y() - 14.0 * hf * math.cos(lean))
    hc = QPointF(sh.x() + 6.2 * hf * math.sin(lean * 1.3) + 0.6, sh.y() - 6.2 * hf * math.cos(lean * 1.3))

    def leg(i):
        th, bend = P["legs"][i]
        k = _limb(hip, th, 11.0 * hf)
        a = _limb(k, th - bend, 11.2 * hf)
        return k, a, th - bend

    def arm(i):
        al, be = P["arms"][i]
        e = _limb(sh, al, 8.0 * hf)
        h = _limb(e, al + be, 7.2 * hf)
        return e, h

    legs = [leg(0), leg(1)]
    arms = [arm(0), arm(1)]

    sleeve_far = _mul(skin, 0.7) if outfit == "vest" else far_coat
    sleeve = skin if outfit == "vest" else (coat if outfit != "cloak" else look["accent"])

    # --- Rucksack (hinter allem)
    if look.get("bag") == "backpack":
        _poly(p, [(sh.x() - 4.6 * wf, sh.y() + 0.5), (sh.x() - 1.5, sh.y() + 0.5), (hip.x() - 2.0, hip.y() - 2),
                  (hip.x() - 5.8 * wf, hip.y() - 2.5)], _mul(coat, 0.5))

    # --- ferner Arm
    e, h = arms[0]
    _pen(p, sleeve_far, arm_w)
    p.drawLine(sh, e)
    p.drawLine(e, h)
    _pen(p, _mul(skin, 0.7), arm_w * 0.9)
    p.drawPoint(h)

    # --- Beine (fern, nah)
    for i, (k, a, sa) in enumerate(legs):
        col = far_pants if i == 0 else pants
        _pen(p, col, leg_w)
        p.drawLine(hip, k)
        p.drawLine(k, a)
        shoe = _mul(col, 0.55)
        _pen(p, shoe, leg_w * 0.85)
        fx = a.x() + 2.4 * math.cos(sa)
        fy = a.y() - 2.4 * math.sin(sa) * 0.3
        p.drawLine(a, QPointF(fx, fy))
        if outfit == "overall":   # Reflexstreifen
            m = QPointF(k.x() * 0.5 + a.x() * 0.5, k.y() * 0.5 + a.y() * 0.5)
            _pen(p, (214, 220, 226) if i else (150, 156, 166), leg_w * 0.9)
            p.drawPoint(m)

    # --- Torso / Mantel
    kx = [legs[0][0].x(), legs[1][0].x()]
    ax = [legs[0][1].x(), legs[1][1].x()]
    w = 4.9 * wf * (1.12 if outfit in ("long", "suit") else 1.0)
    sx, sy, hx, hy = sh.x(), sh.y(), hip.x(), hip.y()
    if outfit in ("trench", "robe", "cloak", "dress", "long"):
        if outfit == "trench":
            hem_y = -6.0 * hf + P["crouch"] * 0.6
        elif outfit == "long":
            hem_y = -2.4 * hf + P["crouch"] * 0.6
        elif outfit == "robe":
            hem_y = -0.8
        elif outfit == "cloak":
            hem_y = -5.0 * hf + P["crouch"] * 0.6
        else:
            hem_y = -11.0 * hf + P["crouch"] * 0.5
        spread_f = max(3.8 * wf, max(kx + ax) * 0.75 + 1.8)
        spread_b = min(-3.6 * wf, min(kx + ax) * 0.75 - 1.8)
        if outfit == "dress":
            spread_f, spread_b = spread_f + 1.2, spread_b - 1.2
        fl = P["flutter"]
        hem_b_x = spread_b - 2.5 * fl
        hem_b_y = hem_y - 3.0 * fl
        if outfit == "cloak":
            # Unterkleid sichtbar unter der Klarsicht-Folie
            _poly(p, [(sx - w * 0.8, sy), (sx + w * 0.9, sy), (hx + w, hy), (hx - w * 0.9, hy)],
                  look["accent"])
            _poly(p, [(hx - w * 0.9, hy), (hx + w, hy), (spread_f * 0.8, hem_y + 4), (spread_b * 0.8, hem_y + 4)],
                  _mul(look["accent"], 0.6))
        body_col = (176, 200, 222) if outfit == "cloak" else coat
        alpha = 84 if outfit == "cloak" else 255
        pts = [(sx - w * 0.85, sy - 0.6), (sx + w * 0.75, sy - 0.6), (sx + w * 1.0, sy + 4.5),
               (hx + w * 0.9, hy - 1.0), (spread_f, hem_y), (hem_b_x, hem_b_y), (hx - w * 0.95, hy)]
        _poly(p, pts, body_col, alpha)
        if outfit == "cloak":
            _pen(p, (226, 236, 244), 0.8, 170)
            p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in pts] + [QPointF(*pts[0])]))
        else:
            # Schattenseite + Saum
            _poly(p, [(sx - w * 0.85, sy - 0.6), (sx - w * 0.2, sy), (hx - w * 0.3, hy),
                      (hem_b_x + 1.5, hem_b_y), (hem_b_x, hem_b_y), (hx - w * 0.95, hy)], _mul(body_col, 0.72))
        if outfit in ("trench", "long"):
            _pen(p, _mul(coat, 0.55), 1.2)
            p.drawLine(QPointF(hx - w * 0.9, hy + 1.2), QPointF(hx + w * 0.95, hy + 0.5))
            if look.get("collar") or outfit == "long":
                _poly(p, [(sx - w * 0.95, sy - 3.4), (sx + w * 0.5, sy - 1.0), (sx - w * 0.2, sy + 3.0)],
                      _mul(coat, 1.18))
        elif outfit == "robe":
            _pen(p, look["accent"], 1.0)
            p.drawLine(QPointF(sx + w * 0.7, sy + 1), QPointF(spread_f - 0.6, hem_y - 0.5))
    else:
        # Jacke / Hoodie / Weste / Anzug / Overall: kurzer Oberkörper, Hose sichtbar
        hem = hy + 2.2
        _poly(p, [(sx - w * 0.85, sy - 0.6), (sx + w * 0.8, sy - 0.6), (sx + w * 1.0, sy + 4.5),
                  (hx + w * 0.95, hem), (hx - w * 1.0, hem)], coat)
        _poly(p, [(sx - w * 0.85, sy - 0.6), (sx - w * 0.15, sy), (hx - w * 0.25, hem), (hx - w * 1.0, hem)],
              _mul(coat, 0.72))
        if outfit == "suit":
            _poly(p, [(sx + w * 0.35, sy - 0.4), (sx + w * 0.85, sy - 0.4), (sx + w * 0.75, sy + 4.0)],
                  (214, 220, 226))
            _pen(p, look["accent"], 0.9)
            p.drawLine(QPointF(sx + w * 0.72, sy + 0.4), QPointF(sx + w * 0.8, sy + 4.4))
        elif outfit == "overall":
            _pen(p, (214, 220, 226), 1.0)
            p.drawLine(QPointF(hx - w * 0.9, (sy + hy) / 2), QPointF(hx + w * 0.95, (sy + hy) / 2 - 0.3))
        else:
            _pen(p, look["accent"], 1.0)
            if outfit in ("jacket", "vest"):
                p.drawLine(QPointF(sx + w * 0.95, sy + 2.0), QPointF(hx + w * 0.9, hem - 0.5))
            else:
                p.drawLine(QPointF(hx - w * 0.9, hem - 0.3), QPointF(hx + w * 0.9, hem - 0.3))

    # Leuchtstreifen am Mantel (LED-Kleidung)
    if look.get("led") and outfit != "cloak":
        for q in (p, emit):
            _pen(q, look["accent"], 0.9)
            q.drawLine(QPointF(sx + w * 0.85, sy + 1.0), QPointF(hx + w * 0.92, hy - 0.5))

    bag = look.get("bag")
    if bag == "bag" or bag is True:
        _poly(p, [(hx - w * 1.3, hy - 3), (hx - w * 0.2, hy - 3), (hx - w * 0.3, hy + 3), (hx - w * 1.2, hy + 3)],
              _mul(coat, 0.45))
        _pen(p, _mul(coat, 0.4), 0.8)
        p.drawLine(QPointF(hx - w * 0.7, hy - 3), QPointF(sx + w * 0.4, sy + 0.5))

    # --- Kopf
    rx, ry = 3.5 * wf ** 0.3, 4.0
    hair = look["hair"]
    if head == "afro":
        _fill(p, hair)
        p.drawEllipse(QRectF(hc.x() - rx - 2.2, hc.y() - ry - 2.6, 2 * rx + 3.6, 2 * ry + 3.0))
    if head == "ponytail":
        _pen(p, hair, 1.8)
        p.drawLine(QPointF(hc.x() - rx * 0.8, hc.y() - ry * 0.6), QPointF(hc.x() - rx - 2.6 - P["flutter"],
                                                                         hc.y() + 2.5))
    if head == "long":
        _poly(p, [(hc.x() - rx - 0.6, hc.y() - 1), (hc.x() + 0.5, hc.y() - ry), (hc.x() - 0.2, sy + 4),
                  (hc.x() - rx - 1.6, sy + 3)], hair)
    if head == "hood":
        _fill(p, _mul(coat, 0.85))
        p.drawEllipse(QRectF(hc.x() - rx - 1.6, hc.y() - ry - 1.6, 2 * rx + 2.6, 2 * ry + 3.4))
    _fill(p, skin)
    p.drawEllipse(QRectF(hc.x() - rx, hc.y() - ry, 2 * rx, 2 * ry))
    # Kinn/Gesicht nach vorn + Schatten am Hinterkopf
    _fill(p, _mul(skin, 0.7))
    p.drawEllipse(QRectF(hc.x() - rx, hc.y() - ry * 0.4, rx * 0.9, ry * 1.2))
    _pen(p, _mul(skin, 0.35), 0.7)
    eye = QPointF(hc.x() + rx * 0.55, hc.y() - 0.5)
    p.drawPoint(eye)
    top = hc.y() - ry
    if head == "short":
        _poly(p, [(hc.x() - rx - 0.3, hc.y() + 0.5), (hc.x() - rx * 0.6, top - 0.6), (hc.x() + rx * 0.9, top - 0.3),
                  (hc.x() + rx * 0.3, top + 1.6), (hc.x() - rx * 0.3, hc.y() - 0.5)], hair)
    elif head == "long":
        _poly(p, [(hc.x() - rx - 0.6, hc.y()), (hc.x() - rx * 0.4, top - 0.7), (hc.x() + rx, top),
                  (hc.x() + rx * 0.2, top + 1.8)], hair)
    elif head == "bun":
        _poly(p, [(hc.x() - rx - 0.2, hc.y()), (hc.x() - rx * 0.5, top - 0.5), (hc.x() + rx * 0.9, top),
                  (hc.x() + rx * 0.2, top + 1.5)], hair)
        _fill(p, hair)
        p.drawEllipse(QRectF(hc.x() - rx - 2.4, top - 0.4, 2.8, 2.8))
    elif head == "fedora":
        _poly(p, [(hc.x() - rx * 0.9, top + 1.2), (hc.x() - rx * 0.7, top - 2.6), (hc.x() + rx * 0.8, top - 2.6),
                  (hc.x() + rx * 0.95, top + 1.2)], _mul(coat, 0.75))
        _pen(p, _mul(coat, 0.6), 1.3)
        p.drawLine(QPointF(hc.x() - rx - 2.4, top + 1.4), QPointF(hc.x() + rx + 2.4, top + 1.2))
        _pen(p, look["accent"], 0.7)
        p.drawLine(QPointF(hc.x() - rx * 0.75, top + 0.2), QPointF(hc.x() + rx * 0.85, top + 0.2))
    elif head == "cap":
        _poly(p, [(hc.x() - rx, top + 2), (hc.x() - rx * 0.6, top - 0.8), (hc.x() + rx * 0.8, top - 0.6),
                  (hc.x() + rx * 1.0, top + 1.6)], look["accent"])
        _pen(p, _mul(look["accent"], 0.6), 1.0)
        p.drawLine(QPointF(hc.x() + rx * 0.6, top + 1.7), QPointF(hc.x() + rx + 2.6, top + 2.1))
    elif head == "conical":
        _poly(p, [(hc.x() - rx - 4.6, top + 2.6), (hc.x() + 0.2, top - 3.2), (hc.x() + rx + 4.6, top + 2.6)],
              (150, 138, 104))
        _pen(p, (90, 80, 60), 0.8)
        p.drawLine(QPointF(hc.x() - rx - 4.6, top + 2.6), QPointF(hc.x() + rx + 4.6, top + 2.6))
    elif head == "mohawk":
        _pen(p, hair, 1.6)
        p.drawLine(QPointF(hc.x() - rx * 0.6, top - 0.3), QPointF(hc.x() + rx * 0.6, top - 1.8))
        p.drawLine(QPointF(hc.x() - rx * 0.9, top + 1), QPointF(hc.x() - rx * 0.2, top - 1.5))
    elif head == "hood":
        _poly(p, [(hc.x() - rx - 1.6, hc.y() + 1), (hc.x() - rx * 0.6, top - 1.6), (hc.x() + rx * 0.9, top - 1.0),
                  (hc.x() + rx * 0.4, top + 1.2), (hc.x() - rx * 0.4, hc.y() + 0.5)], _mul(coat, 0.85))
    elif head == "beanie":
        _poly(p, [(hc.x() - rx - 0.4, top + 2.4), (hc.x() - rx * 0.7, top - 1.2), (hc.x() + rx * 0.2, top - 1.8),
                  (hc.x() + rx * 0.95, top - 0.6), (hc.x() + rx * 1.05, top + 2.0)], _mul(look["accent"], 0.7))
        _pen(p, _mul(look["accent"], 0.45), 1.0)
        p.drawLine(QPointF(hc.x() - rx - 0.4, top + 2.2), QPointF(hc.x() + rx * 1.05, top + 1.9))
    elif head in ("ponytail", "visor"):
        _poly(p, [(hc.x() - rx - 0.3, hc.y() + 0.5), (hc.x() - rx * 0.6, top - 0.6), (hc.x() + rx * 0.9, top - 0.3),
                  (hc.x() + rx * 0.3, top + 1.6), (hc.x() - rx * 0.3, hc.y() - 0.5)], hair)
        if head == "visor":
            for q in (p, emit):
                _pen(q, look["accent"], 1.3)
                q.drawLine(QPointF(hc.x() - rx * 0.1, hc.y() - 0.8), QPointF(hc.x() + rx + 0.6, hc.y() - 0.8))
    elif head == "afro":
        _fill(p, _mul(hair, 1.2))
        p.drawEllipse(QRectF(hc.x() - rx - 1.2, top - 2.2, 2 * rx + 1.6, 3.4))
    if look.get("mask"):
        _poly(p, [(hc.x() + rx * 0.1, hc.y() + 0.6), (hc.x() + rx + 0.4, hc.y() + 0.4),
                  (hc.x() + rx + 0.2, hc.y() + 3.2), (hc.x() + rx * 0.2, hc.y() + 3.4)], (30, 32, 40))
        _pen(p, look["accent"], 0.8)
        p.drawPoint(QPointF(hc.x() + rx * 0.75, hc.y() + 2.0))
    if look.get("cig") and P["rot"] == 0.0:
        tip = QPointF(hc.x() + rx + 1.8, hc.y() + 1.6)
        _pen(p, (214, 220, 226), 0.7)
        p.drawLine(QPointF(hc.x() + rx + 0.2, hc.y() + 1.6), tip)
        for q in (p, emit):
            _pen(q, (255, 138, 44), 1.0)
            q.drawPoint(tip)

    # --- naher Arm
    e, h = arms[1]
    _pen(p, sleeve, arm_w)
    p.drawLine(sh, e)
    p.drawLine(e, h)
    if bag == "briefcase" and not (P["gun"] or P["scanner"]) and P["rot"] == 0.0:
        _poly(p, [(h.x() - 2.6, h.y() + 0.6), (h.x() + 2.8, h.y() + 0.6), (h.x() + 2.8, h.y() + 4.6),
                  (h.x() - 2.6, h.y() + 4.6)], (30, 24, 26))
    if old and not (P["gun"] or P["scanner"]):
        _pen(p, (60, 52, 50), 0.9)
        p.drawLine(h, QPointF(h.x() + 2.0, 0.0))
    if outfit == "cloak":
        _pen(p, (210, 222, 232), arm_w + 0.6, 80)
        p.drawLine(sh, e)
        p.drawLine(e, h)
    _pen(p, skin, arm_w * 0.9)
    p.drawPoint(h)

    if P["gun"]:
        al = P["arms"][1][0] + P["arms"][1][1]
        dx, dy = math.sin(al), math.cos(al)
        tip = QPointF(h.x() + dx * 4.4, h.y() + dy * 4.4)
        _pen(p, (24, 26, 34), 1.9)
        p.drawLine(h, tip)
        _pen(p, (24, 26, 34), 1.4)
        p.drawLine(h, QPointF(h.x() - dy * 1.6, h.y() + dx * 1.6 + 0.6))
        _pen(p, (64, 210, 220), 0.8)
        p.drawPoint(QPointF(h.x() + dx * 2.2, h.y() + dy * 2.2 - 0.5))
        if P["muzzle"]:
            mx, my = tip.x() + dx * 2.6, tip.y() + dy * 2.6
            for q in (p, emit):
                _fill(q, (255, 240, 200))
                q.drawEllipse(QRectF(mx - 2.4, my - 1.6, 4.8, 3.2))
                _fill(q, (255, 160, 60), 200)
                q.drawPolygon(QPolygonF([QPointF(mx - 1, my - 2.6), QPointF(mx + 6.5, my), QPointF(mx - 1, my + 2.6)]))
    if P["scanner"]:
        al = P["arms"][1][0] + P["arms"][1][1]
        dx, dy = math.sin(al), math.cos(al)
        _pen(p, (162, 168, 180), 2.2)
        p.drawLine(h, QPointF(h.x() + dx * 2.4, h.y() + dy * 2.4))
        for q in (p, emit):
            _pen(q, (64, 210, 220), 1.4)
            q.drawPoint(QPointF(h.x() + dx * 2.6, h.y() + dy * 2.6))

    if look.get("umbrella") and P["rot"] == 0.0:
        _umbrella(p, emit, look, hc)
    return eye, hc, arms[1][1]


def _umbrella(p, emit, look, hc):
    uc = look["umbrella"]
    hand = QPointF(hc.x() + 3.0, hc.y() + 10.5)
    apex = QPointF(hand.x() - 1.0, hc.y() - 15.0)
    R = 11.5
    pts = []
    for i in range(13):
        a = PI * i / 12
        x = apex.x() + R * math.cos(a)
        y = apex.y() + 7.0 - 7.0 * math.sin(a) ** 0.7
        pts.append(QPointF(x, y))
    # Wellenkante
    for i in range(7):
        x = apex.x() - R + 2 * R * i / 6
        pts.append(QPointF(x, apex.y() + 7.6 + (0.9 if i % 2 else 0.0)))
    canopy = QPolygonF(pts[:13] + list(reversed(pts[13:])))
    bubble = look.get("umb_style") == "bubble"
    core = (min(255, uc[0] + 120), min(255, uc[1] + 120), min(255, uc[2] + 120))
    if bubble:
        # Transparente Kuppel, vom Leuchtstab von innen angestrahlt
        _fill(p, (190, 210, 230), 70)
        p.drawPolygon(canopy)
        _fill(p, uc, 90)
        p.drawEllipse(QRectF(apex.x() - R * 0.5, apex.y() + 0.5, R, 6.0))
        _pen(p, (220, 232, 244), 0.8, 150)
        p.drawPolyline(QPolygonF(pts[:13]))
    else:
        _fill(p, _mul(uc, 0.32), 215)
        p.drawPolygon(canopy)
        # Innenseite um den Stab heller (Licht fällt aufs Tuch)
        _fill(p, _mul(uc, 0.75), 160)
        p.drawPolygon(QPolygonF([QPointF(apex.x() - R * 0.35, apex.y() + 7.4), apex,
                                 QPointF(apex.x() + R * 0.35, apex.y() + 7.4)]))
    for q in (p, emit):
        _pen(q, uc, 1.0)
        q.drawLine(QPointF(apex.x() - R, apex.y() + 7.4), QPointF(apex.x() + R, apex.y() + 7.4))
        # Leuchtender Schaft (wie im Film): heller Kern über die ganze Länge
        _pen(q, uc, 1.9)
        q.drawLine(apex, hand)
        _pen(q, core, 0.9)
        q.drawLine(apex, hand)
    _fill(emit, uc, 90)
    emit.drawPolygon(canopy)
    _pen(p, look["skin"], 2.2)
    p.drawPoint(hand)


def _fallen_umbrella(p, emit, look):
    """Liegender Schirm neben einem Körper; der Stab leuchtet weiter."""
    uc = look["umbrella"]
    core = (min(255, uc[0] + 120), min(255, uc[1] + 120), min(255, uc[2] + 120))
    x0, y0 = -26.0, 1.0
    _fill(p, _mul(uc, 0.32), 215)
    p.drawPolygon(QPolygonF([QPointF(x0, y0), QPointF(x0 + 6, y0 - 7), QPointF(x0 + 11, y0 - 8),
                             QPointF(x0 + 12, y0)]))
    for q in (p, emit):
        _pen(q, uc, 1.8)
        q.drawLine(QPointF(x0 - 10, y0 + 0.5), QPointF(x0 + 6, y0 - 3))
        _pen(q, core, 0.8)
        q.drawLine(QPointF(x0 - 10, y0 + 0.5), QPointF(x0 + 6, y0 - 3))


# ---------------------------------------------------------------------------- Cache / API

_CACHE = {}
_CACHE_MAX = 7000
_PAD = 26.0     # Design-Einheiten Rand links/rechts (Schirm, Sturz)
_TOP = 60.0
_BOT = 4.0


def _postprocess(img, rim_rgb, rim_side, fog_rgb, fog, outline=(4, 5, 10)):
    """Umriss + Rimlight + Nebel auf ein fertiges Figurenbild."""
    w, h = img.width(), img.height()

    def mask(rgb, alpha):
        m = QImage(img)
        q = QPainter(m)
        q.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        q.fillRect(0, 0, w, h, QColor(rgb[0], rgb[1], rgb[2], alpha))
        q.end()
        return m

    out = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(0)
    q = QPainter(out)
    dark = mask(outline, 255)
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        q.drawImage(dx, dy, dark)
    if rim_rgb is not None:
        rim = mask(rim_rgb, 235)
        q.drawImage(rim_side, 0, rim)
        q.drawImage(0, -1, mask(_mul(rim_rgb, 0.6), 160))
    q.drawImage(0, 0, img)
    if fog > 0.0:
        q.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
        q.fillRect(0, 0, w, h, QColor(fog_rgb[0], fog_rgb[1], fog_rgb[2], int(255 * fog)))
    q.end()
    return out


def frame_count(anim):
    return ANIMS.get(anim, 1)


def get(look, anim, frame, height_px, facing=1, rim=None, rim_side=1, fog_rgb=(0, 0, 0), fog=0.0,
        outline=(4, 5, 10)):
    """Fertiges Figurenbild. Rückgabe (QImage, QImage emit|None, anchor_x, anchor_y, meta).

    anchor = Fußpunkt im Bild. meta: eye (x,y) und hand (x,y) relativ zum Anker in px.
    """
    hpx = max(8, int(round(height_px)))
    fogq = round(fog * 8) / 8.0
    key = (look["id"], anim, frame, hpx, facing, rim, rim_side, fog_rgb, fogq, outline)
    hit = _CACHE.get(key)
    if hit is not None:
        return hit

    k = hpx / 48.0
    left = 60.0 if anim == "die" else _PAD
    right = 36.0 if anim == "die" else _PAD
    W = int(math.ceil((left + right) * k)) + 4
    H = int(math.ceil((_TOP + _BOT) * k)) + 4
    ax, ay = int(left * k) + 2, int(_TOP * k) + 2

    img = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    emit = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
    emit.fill(0)
    p = QPainter(img)
    pe = QPainter(emit)
    for q in (p, pe):
        q.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        q.translate(ax, ay)
        q.scale(k, k)
    n = frame_count(anim)
    t = (frame / max(1, n - 1)) if anim == "die" else (frame / n)
    P = pose(anim, t)
    if P["rot"] != 0.0:
        for q in (p, pe):
            q.translate(-3.0, 0.0)
            q.rotate(math.degrees(P["rot"]))
            q.translate(0.0, -2.5 * abs(P["rot"]) / (PI / 2))
    eye, hc, hand = _draw_figure(p, look, P, pe)
    tr = p.transform()
    fallen = anim == "die" and frame >= n - 3 and look.get("umbrella")
    if fallen:
        for q in (p, pe):
            q.resetTransform()
            q.translate(ax, ay)
            q.scale(k, k)
        _fallen_umbrella(p, pe, look)
    p.end()
    pe.end()

    emit_used = (P["muzzle"] or P["scanner"] or bool(fallen)
                 or (bool(look.get("umbrella")) and P["rot"] == 0.0)
                 or look.get("led") or look.get("head") == "visor" or (look.get("cig") and P["rot"] == 0.0))
    out = _postprocess(img, rim, rim_side, fog_rgb, fogq, outline)
    e_pt = tr.map(eye)
    h_pt = tr.map(hand)
    if facing < 0:
        out = out.mirrored(True, False)
        emit = emit.mirrored(True, False)
        e_pt = QPointF(W - 1 - e_pt.x(), e_pt.y())
        h_pt = QPointF(W - 1 - h_pt.x(), h_pt.y())
        ax = W - 1 - ax
    c_pt = tr.map(hc)
    if facing < 0:
        c_pt = QPointF(W - 1 - c_pt.x(), c_pt.y())
    meta = dict(eye=(e_pt.x() - ax, e_pt.y() - ay), hand=(h_pt.x() - ax, h_pt.y() - ay),
                head=(c_pt.x() - ax, c_pt.y() - ay),
                head_top=-(_TOP - 12) * k)
    res = (out, emit if emit_used else None, ax, ay, meta)
    if len(_CACHE) > _CACHE_MAX:
        _CACHE.clear()
    _CACHE[key] = res
    return res

