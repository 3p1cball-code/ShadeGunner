"""Tell- und Konfidenz-System.

Ein Replikant ist ein *Sampling* aus Tells - kein einzelner Tell beweist etwas.
Die Konfidenz ist ein Naive-Bayes-Log-Odds-Score über die bereits aufgedeckten
Tells und bleibt bei wenigen Tells nahe der Prior-Wahrscheinlichkeit: das ist
die Restunsicherheit, die das Spiel tragen soll.

`TELLS[name] = (p_replikant, p_mensch, braucht_scan, gewicht)`
"""

import math

TELLS = {
    # name        p(rep) p(hum) scan?  Gewicht
    "pupils":   (0.55, 0.04, True, 0.90),   # verlangsamte Pupillenreaktion
    "stimulus": (0.50, 0.05, True, 0.85),   # Reaktion auf Licht/Ansprache
    "serial":   (0.70, 0.01, True, 1.00),   # Seriennummer-Fragment (nah)
    "gait":     (0.40, 0.10, False, 0.70),  # zu gleichmäßiger Gang
    "anachron": (0.30, 0.06, False, 0.60),  # anachronistisches Detail
}
WEAK_TELLS = [n for n, (_r, _h, scan, _w) in TELLS.items() if not scan]
STRONG_TELLS = [n for n, (_r, _h, scan, _w) in TELLS.items() if scan]

PRIOR = 0.30   # Grundquote Replikanten unter Passanten


def spawn_tells(rng, is_replicant, subtlety):
    """Latente Tells eines Aktors.

    subtlety < 1: Replikanten sind besser getarnt, Menschen zeigen mehr falsche
    Gegen-Tells - genau die Steigerung aus DESIGN.md §5.
    """
    tells = {}
    for name, (rp, hp, _scan, _w) in TELLS.items():
        if is_replicant:
            p = rp * subtlety
        else:
            p = min(0.9, hp / max(0.25, subtlety))
        tells[name] = rng.random() < p
    return tells


def confidence(revealed, tells):
    """P(Replikant | aufgedeckte Tells) als 0..1 (Naive Bayes, Log-Odds)."""
    lo = math.log(PRIOR / (1 - PRIOR))
    for name in revealed:
        rp, hp, _scan, _w = TELLS[name]
        present = bool(tells.get(name))
        r = rp if present else (1 - rp)
        h = hp if present else (1 - hp)
        r = min(max(r, 1e-3), 1 - 1e-3)
        h = min(max(h, 1e-3), 1 - 1e-3)
        lo += math.log(r / h)
    return 1.0 / (1.0 + math.exp(-lo))


def tell_present_count(revealed, tells):
    return sum(1 for n in revealed if tells.get(n))
