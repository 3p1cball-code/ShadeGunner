"""Prozedurale Bevölkerung und Straßenmöblierung einer Zone.

Authored macro (Zone: Länge, Dichte, Replikantenzahl, Tarnung), procedural micro
(wer läuft wo, wie sieht er aus). Das Aussehen korreliert bewusst NICHT mit dem
Replikanten-Status - sonst wäre das Erkennen trivial.
"""

import random

from . import config
from .detection import spawn_tells
from .entities import Actor
from .render.sprites import random_look

# Regen je Zone (mehr Schirme bei mehr Regen) - spiegelt render/city.THEMES
ZONE_RAIN = [0.55, 0.4, 1.0, 0.35, 0.3]

# Hindernisse: Art -> (halbe Breite u, halbe Tiefe, Höhe u)
OBSTACLE_KINDS = {
    "barrier": (11.0, 0.035, 9.0),     # Polizei-Absperrung (gestreift)
    "crates": (9.0, 0.05, 11.0),       # Kistenstapel
    "bins": (8.0, 0.045, 8.0),         # Müllsäcke / Tonne
    "barrel": (4.5, 0.03, 9.0),        # Feuertonne (leuchtet)
    "vending": (6.0, 0.03, 20.0),      # Getränkeautomat (leuchtet)
}
ZONE_OBSTACLES = [
    ["barrel", "barrel", "bins", "crates", "barrier"],
    ["bins", "bins", "vending", "barrier", "barrel"],
    ["vending", "vending", "bins", "barrier", "crates"],
    ["crates", "crates", "barrel", "barrier", "bins"],
    ["barrier", "barrier", "vending", "crates"],
]


def populate(rng, zone, x_from, x_to, uid_start, zone_index=0):
    """Liste neuer Aktoren zwischen x_from und x_to. Gibt (actors, next_uid)."""
    span = max(1.0, x_to - x_from)
    count = max(10, int(span / 100.0 * zone["density"]))
    n_rep = min(count - 4, zone["replicants"])
    # Replikanten gleichmäßig über die Strecke verteilen (nicht alle am Anfang)
    slots = sorted(rng.sample(range(count), n_rep))
    replicant_ids = set(slots)
    rain = ZONE_RAIN[zone_index % len(ZONE_RAIN)]

    actors = []
    xs = sorted(rng.uniform(x_from, x_to) for _ in range(count))
    order = list(range(count))
    rng.shuffle(order)
    for i in range(count):
        is_rep = i in replicant_ids
        uid = uid_start + i
        depth = rng.uniform(config.DEPTH_MIN + 0.02, 0.97)
        tells = spawn_tells(rng, is_rep, zone["camo"])
        look = random_look(rng, uid, rain)
        a = Actor(
            x=xs[order[i]],
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
        a.state = "walk" if rng.random() < 0.72 else "idle"
        a.timer = rng.uniform(2.0, 9.0)
        a.glint_next = rng.uniform(2.0, 9.0)
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
