"""Prozedurale Bevölkerung und Straßenmöblierung einer Zone.

Authored macro (Zone: Länge, Dichte, Replikantenzahl, Tarnung), procedural micro
(wer läuft wo, wie sieht er aus). Das Aussehen korreliert bewusst NICHT mit dem
Replikanten-Status - sonst wäre das Erkennen trivial.
"""

import math
import random

from . import config
from .detection import spawn_tells
from .entities import Actor
from .render.sprites import random_look

# Regen je Zone (mehr Schirme bei mehr Regen) - spiegelt render/city.THEMES
ZONE_RAIN = [0.55, 0.4, 1.0, 0.35, 0.3]

# Hindernisse: Art -> (halbe Breite u, halbe Tiefe, Höhe u)
OBSTACLE_KINDS = {
    "barrier": (20.0, 0.04, 14.0),     # Polizei-Absperrung (gestreift, springbar)
    "crates": (12.0, 0.055, 14.0),     # Kistenstapel
    "bins": (10.0, 0.05, 10.0),        # Müllsäcke / Tonne
    "barrel": (6.3, 0.035, 12.6),      # Feuertonne (leuchtet)
    "vending": (6.0, 0.03, 20.0),      # Getränkeautomat (leuchtet)
    "wreck": (55.0, 0.07, 29.0),       # ausgeschlachteter 60er-Straßenkreuzer (aufgebockt), größer als ein Auto
    "dustbin": (5.6, 0.035, 12.6),     # Blechmülltonne, oft überquellend
}
ZONE_OBSTACLES = [
    ["barrel", "barrel", "bins", "crates", "wreck", "wreck", "dustbin", "dustbin"],
    ["bins", "dustbin", "vending", "barrier", "barrel", "wreck", "dustbin"],
    ["vending", "vending", "bins", "barrier", "crates", "dustbin", "dustbin"],
    ["crates", "crates", "barrel", "barrier", "bins", "wreck", "dustbin"],
    ["barrier", "barrier", "vending", "crates"],
]


def populate(rng, zone, x_from, x_to, uid_start, zone_index=0):
    """Liste neuer Aktoren zwischen x_from und x_to. Gibt (actors, next_uid).

    Drei Sorten, alle gleichwertig Teil der Simulation (scanbar, beobachtbar):
    Passanten auf der ganzen Straße, Flaneure auf dem hinteren Gehweg und Gruppen,
    die herumstehen und reden. Replikanten werden über alle drei verteilt - wer in
    einer Gruppe steht, ist weder verdächtiger noch unverdächtiger."""
    span = max(1.0, x_to - x_from)
    rain = ZONE_RAIN[zone_index % len(ZONE_RAIN)]
    specs = []                                   # (x, depth, kind, gruppe, gx)
    for _ in range(max(10, int(span / 100.0 * zone["density"]))):
        specs.append((rng.uniform(x_from, x_to), rng.uniform(config.DEPTH_MIN + 0.02, 0.97), "street", -1, 0.0))
    lo, hi = config.SIDEWALK
    for _ in range(int(span / 100.0 * zone.get("sidewalk", 0.0))):
        specs.append((rng.uniform(x_from, x_to), rng.uniform(lo, hi), "sidewalk", -1, 0.0))
    gid = 0
    for _ in range(int(span / 100.0 * zone.get("groups", 0.0))):
        gx = rng.uniform(x_from + 40, x_to - 40)
        back = rng.random() < 0.6
        gd = rng.uniform(lo + 0.01, hi) if back else rng.uniform(0.22, 0.9)
        n = rng.choice((2, 2, 3, 3, 4))
        for k in range(n):
            ang = 2 * math.pi * k / n + rng.uniform(-0.3, 0.3)
            specs.append((gx + math.cos(ang) * rng.uniform(6, 9), max(config.NPC_DEPTH_MIN, gd + math.sin(ang) * 0.035),
                          "group", gid, gx))
        gid += 1
    fade = zone.get("fade")
    if fade:                                     # Stadt leert sich zum Ende hin
        f0, f1 = fade
        specs = [s for s in specs if s[0] < f0 or (s[0] < f1 and rng.random() > ((s[0] - f0) / (f1 - f0)) ** 0.8)]
    count = len(specs)
    n_rep = min(count - 4, zone["replicants"])
    replicant_ids = set(rng.sample(range(count), n_rep))

    actors = []
    for i, (x, depth, kind, grp, gx) in enumerate(specs):
        is_rep = i in replicant_ids
        uid = uid_start + i
        tells = spawn_tells(rng, is_rep, zone["camo"])
        look = random_look(rng, uid, rain, config.zone_colors(zone_index, "people"))
        a = Actor(
            x=x,
            depth=depth,
            look=look,
            uid=uid,
            is_replicant=is_rep,
            tells=tells,
            facing=rng.choice((-1, 1)),
            speed=rng.uniform(11.0, 26.0) * (0.55 if look.get("old") else 1.0),
            phase=rng.random(),
            target_depth=depth,
        )
        a.react_t = rng.uniform(0.12, 0.5) + (0.45 if look.get("old") else 0.0)
        a.glint_next = rng.uniform(2.0, 9.0)
        if kind == "group":
            a.group, a.gx = grp, gx
            a.state = "loiter"
            a.timer = rng.uniform(25.0, 70.0)
            a.facing = 1 if gx >= x else -1
            if look.get("umbrella") and rng.random() < 0.5:
                look["umbrella"] = None              # unterm Vordach braucht's keinen Schirm
        else:
            if kind == "sidewalk":
                a.home = (lo, hi)
                a.speed *= 0.8                       # Flaneure bummeln
            a.state = "walk" if rng.random() < 0.72 else "idle"
            a.timer = rng.uniform(2.0, 9.0)
            # Gang-Tell sichtbar machen: auffällig gleichmäßige Geher bleiben nie stehen
            if tells.get("gait"):
                a.state = "walk"
                a.speed = 19.0
        if is_rep:
            a.aggressive = rng.random() < zone["aggression"]
        actors.append(a)
    return actors, uid_start + count


def ramen_positions(length, seed, zone_index):
    """Deterministische x-Positionen der Nudelstände (Sim und Renderer nutzen dieselben)."""
    rng = random.Random(seed * 131 + zone_index * 17 + 9)
    out = []
    for k in range(2):
        x = length * (0.28 + 0.44 * k) + rng.uniform(-120, 120)
        out.append(min(length - 160, max(180, x)))
    return out


# Überbauten je Zone (Brücken / überhängende Gebäude). Breite in Welt-Einheiten.
SPAN_PLAN = [("bridge", "bridge", "overhang"), ("bridge", "overhang", "bridge"),
             ("overhang", "bridge", "overhang", "bridge"), ("bridge", "bridge", "overhang"), ("overhang", "bridge")]
BRIDGE_W = (70.0, 210.0)
OVERHANG_W = (150.0, 260.0)


def span_layout(length, seed, zone_index, exit_x=None):
    """Deterministische Lage der Überbauten - Renderer und Sim (Tonnen/Wracks darunter)
    nutzen dieselbe Liste. Gibt [dict(kind, x0, x1, seed)] nach x sortiert."""
    rng = random.Random(seed * 911 + zone_index * 13 + 2)
    exit_x = length if exit_x is None else exit_x
    busy = [(r - 170, r + 190) for r in ramen_positions(length, seed, zone_index)]
    busy.append((exit_x - 260, exit_x + 200))
    out = []
    for kind in SPAN_PLAN[zone_index % len(SPAN_PLAN)]:
        for _ in range(80):
            w = rng.uniform(*(BRIDGE_W if kind == "bridge" else OVERHANG_W))
            x0 = rng.uniform(length * 0.08, length * 0.9 - w)
            if any(a < x0 + w and x0 < b for a, b in busy):
                continue
            busy.append((x0 - 220, x0 + w + 220))
            out.append(dict(kind=kind, x0=x0, x1=x0 + w, seed=rng.randint(0, 99999)))
            break
    out.sort(key=lambda s: s["x0"])
    return out


def under_spans(zone_index, spans):
    """Hindernisse unter den Brücken: Feuertonnen (Obdachlose wärmen sich) und Wracks.
    Eigener Zufall je Überbau, damit die übrige Straße unverändert bleibt."""
    out = []
    clean = zone_index == 4
    for s in spans:
        r = random.Random(s["seed"] + 17)
        n = 0 if clean else (2 + r.randint(0, 2) if s["kind"] == "bridge" else r.randint(0, 2))
        xs = []
        for _ in range(n * 4):
            if len(xs) >= n:
                break
            x = r.uniform(s["x0"] + 8, s["x1"] - 8)
            if any(abs(x - q) < 30 for q in xs):
                continue
            xs.append(x)
            band = r.choice(config.OBSTACLE_BANDS)
            kind = "barrel" if r.random() < 0.6 else "wreck"
            w, dd, h = OBSTACLE_KINDS[kind]
            d = r.uniform(band[0] + dd, band[1] - dd) if band[1] - band[0] > 2 * dd else (band[0] + band[1]) / 2
            out.append(dict(x=x, d=d, w=w, dd=dd, h=h, kind=kind, seed=r.randint(0, 9999)))
    return out


# Ampeltürme je 1000 u: (hinterer Gehweg, nah vor der Kamera)
TOWER_RATE = [(1.4, 0.6), (2.2, 0.8), (3.0, 1.2), (1.6, 0.6), (0.8, 0.4)]


def towers(seed, zone_index, length, ramen=(), existing=()):
    """Ampeltürme als eigene Objekte (wie Autos/Menschen nach Tiefe sortiert): am
    hinteren Gehweg vor der Häuserfront und vereinzelt ganz vorn vor der Kamera
    (dort außerhalb der Spielebene - sie verdecken, was dahinter passiert).
    Eigener Zufall, damit der Rest der Straße unverändert bleibt."""
    rng = random.Random(seed * 409 + zone_index * 3 + 11)
    back, near = TOWER_RATE[zone_index % len(TOWER_RATE)]
    out = []
    for rate, (d0, d1) in ((back, (0.04, 0.06)), (near, (1.12, 1.2))):
        n = int(length / 1000.0 * rate + rng.random())
        for _ in range(n * 8):
            if sum(1 for o in out if (o["d"] > 1.0) == (d0 > 1.0)) >= n:
                break
            x = rng.uniform(180.0, length - 160.0)
            d = rng.uniform(d0, d1)
            if any(abs(x - rx) < 120 for rx in ramen) or any(abs(x - o["x"]) < 90 for o in out):
                continue
            if any(abs(x - o["x"]) < o["w"] + 14 and abs(d - o["d"]) < o["dd"] + 0.05 for o in existing):
                continue
            sd = rng.randint(0, 99999)
            # hintere Türme 35-45 % kleiner (aus dem Seed, damit die Zufallsfolge gleich bleibt)
            size = 1.0 if d0 > 1.0 else 0.55 + (sd % 1000) / 1000.0 * 0.10
            out.append(dict(x=x, d=d, w=7.0 * size, dd=0.025, h=999.0, kind="tower", seed=sd, size=size))
    return out


def obstacles(rng, zone_index, length, ramen=()):
    """Hindernisse neben den Fahrspuren: man springt drüber oder geht außen herum."""
    kinds = ZONE_OBSTACLES[zone_index % len(ZONE_OBSTACLES)]
    out = []
    x = 220.0 + rng.uniform(0, 120)
    while x < length - 140:
        band = rng.choice(config.OBSTACLE_BANDS)
        kind = rng.choice(kinds)
        w, dd, h = OBSTACLE_KINDS[kind]
        d = rng.uniform(band[0] + dd, band[1] - dd) if band[1] - band[0] > 2 * dd else (band[0] + band[1]) / 2
        # Nudelstände frei halten (sonst kommt man nicht heran)
        if not any(abs(x - rx) < 80 for rx in ramen):
            out.append(dict(x=x, d=d, w=w, dd=dd, h=h, kind=kind, seed=rng.randint(0, 9999)))
        x += rng.uniform(170, 330)
    return out


def parked(rng, zone, kinds, dims, length, ramen=(), existing=()):
    """Parkende Fahrzeuge am Fahrbahnrand: hinten an der Bordsteinkante, vereinzelt vorn
    (die vorderen verdecken, was dahinter passiert). Feste Hindernisse - nicht springbar."""
    out = []
    n = int(length / 1000.0 * zone.get("parked", 0.0) + rng.random())
    for _ in range(n * 6):
        if len(out) >= n:
            break
        kind = rng.choice(kinds)
        L, h, _sp = dims[kind]
        d = config.PARK_BANDS[0][0] if rng.random() < config.PARK_BANDS[0][1] else config.PARK_BANDS[1][0]
        d += rng.uniform(-0.008, 0.008)
        x = rng.uniform(260.0, length - 220.0)
        if any(abs(x - rx) < 110 for rx in ramen):
            continue
        if any(abs(x - o["x"]) < o["w"] + L * 0.5 + 14 and abs(d - o["d"]) < o["dd"] + 0.06 for o in list(existing) + out):
            continue
        out.append(dict(x=x, d=d, w=L * 0.5, dd=0.035, h=h, kind="parked", veh=kind, dir=rng.choice((-1, 1)),
                        seed=rng.randint(0, 9999), hazard=rng.random() < 0.25))
    return out


def manholes(rng, zone, length, ramen=(), existing=()):
    """Dampfende Gullis (New York): auf und zwischen den Spuren; ein Teil mit gestreiftem
    Dampfschlot am Rand (ist ein kleines Hindernis). Gibt (gullis, schlot-hindernisse)."""
    holes, stacks = [], []
    n = int(length / 1000.0 * zone.get("steam", 0.0) + rng.random())
    for _ in range(n * 6):
        if len(holes) >= n:
            break
        x = rng.uniform(240.0, length - 200.0)
        stack = rng.random() < 0.3
        d = rng.choice((0.17, 0.53, 0.94)) if stack else rng.choice((0.3, 0.34, 0.53, 0.72, 0.77, 0.9))
        if any(abs(x - h["x"]) < 90 for h in holes) or any(abs(x - rx) < 90 for rx in ramen):
            continue
        if any(abs(x - o["x"]) < o["w"] + 14 and abs(d - o["d"]) < o["dd"] + 0.04 for o in existing):
            continue
        m = dict(x=x, d=d, stack=stack, base=rng.uniform(0.35, 0.8) if not stack else rng.uniform(0.7, 1.0),
                 every=rng.uniform(9.0, 22.0), burst=0.0, ph=rng.uniform(0, 6.28), t=0.0, s=0.5, drift=0.0,
                 seed=rng.randint(0, 9999))
        holes.append(m)
        if stack:
            stacks.append(dict(x=x, d=d, w=3.0, dd=0.02, h=14.0, kind="stack", seed=m["seed"]))
    return holes, stacks
