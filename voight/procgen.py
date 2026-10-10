"""Prozedurale Bevölkerung einer Straße/Zone.

Authored macro (Zone), procedural micro (wer steht wo). Accent-Farbe korreliert
bewusst NICHT mit Replikant-Status - sonst wäre das Erkennen trivial.
"""

from . import config
from .detection import spawn_tells
from .entities import Actor

BODY_DARK = (24, 28, 46)
BODY_MID = (42, 48, 76)
BODY_LIGHT = (58, 66, 100)
ACCENTS = [config.NOIR16[i] for i in (12, 13, 14, 15, 11, 9, 8)]  # cyan/magenta/amber/violet/teal/pale/ash


def populate(rng, zone, x_from, x_to, uid_start):
    """Liste neuer Aktoren zwischen x_from und x_to. Gibt (actors, next_uid)."""
    span = max(1.0, x_to - x_from)
    count = max(8, int(span / 18.0 * zone["density"]))
    n_rep = int(round(count * zone["replicant_ratio"]))
    replicant_ids = set(rng.sample(range(count), n_rep)) if n_rep else set()

    actors = []
    for i in range(count):
        is_rep = i in replicant_ids
        depth = rng.uniform(0.18, 1.0)
        body = rng.choice((BODY_DARK, BODY_MID, BODY_LIGHT))
        accent = rng.choice(ACCENTS)
        a = Actor(
            x=rng.uniform(x_from, x_to),
            depth=depth,
            body=body,
            accent=accent,
            is_replicant=is_rep,
            tells=spawn_tells(rng, is_rep, zone["subtlety"]),
            phase=rng.uniform(0, 6.283),
            speed=rng.uniform(-4.0, 4.0),
            uid=uid_start + i,
        )
        actors.append(a)
    return actors, uid_start + count
