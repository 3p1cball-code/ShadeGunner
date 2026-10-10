"""Tell- und Konfidenz-System.

Ein Replikant ist ein *Sampling* aus Tells - kein einzelner Tell beweist etwas.
Die Konfidenz ist ein Naive-Bayes-Log-Odds-Score über die bereits aufgedeckten
Tells und bleibt bei wenigen Tells nahe der Prior-Wahrscheinlichkeit: das ist
die Restunsicherheit, die das Spiel tragen soll.

Kalibrierung: Spawn und Konfidenz benutzen dieselben, zonen-abhängigen
Likelihoods (`likelihoods(camo)`) und als Prior die echte Replikantenquote der
Zone. Die angezeigte Prozentzahl ist damit ehrlich - 70 % heißt 70 %.

`TELLS[name] = (p_replikant, p_mensch, braucht_scan, kurzname)`
"""

import math

TELLS = {
    # name        p(rep) p(hum) scan?  HUD-Label
    "pupils":   (0.60, 0.05, True, "PUPILLE"),    # verlangsamte Pupillenreaktion / Augenreflex
    "stimulus": (0.55, 0.06, True, "REIZ"),       # Reaktion auf Licht/Ansprache
    "serial":   (0.70, 0.01, True, "SERIE"),      # Seriennummer-Fragment (nur Nahscan)
    "gait":     (0.45, 0.10, False, "GANG"),      # zu gleichmäßiger Gang
    "anachron": (0.35, 0.07, False, "DETAIL"),    # anachronistisches Detail
}
ORDER = ["gait", "anachron", "pupils", "stimulus", "serial"]
WEAK_TELLS = [n for n in ORDER if not TELLS[n][2]]
STRONG_TELLS = [n for n in ORDER if TELLS[n][2]]

PRIOR = 0.30   # Fallback-Prior, falls keine Zonenquote übergeben wird


def likelihoods(camo):
    """(p_rep, p_hum) je Tell für eine Tarntiefe camo in [0, 1].

    camo 0: Replikanten offensichtlich (alle Tells deutlich), kaum Gegen-Tells.
    camo 1: Elite - Replikanten verbergen die Hälfte, Menschen zeigen dreifach
    so oft falsche Tells. Genau die Steigerung aus DESIGN.md §5.
    """
    out = {}
    for name, (rp, hp, _scan, _lbl) in TELLS.items():
        r = min(0.95, rp * (1.25 - 0.6 * camo))
        h = min(0.6, hp * (0.8 + 2.2 * camo))
        out[name] = (r, h)
    return out


def spawn_tells(rng, is_replicant, camo):
    lk = likelihoods(camo)
    tells = {}
    for name in ORDER:
        r, h = lk[name]
        tells[name] = rng.random() < (r if is_replicant else h)
    return tells


def confidence(revealed, tells, camo=0.5, prior=PRIOR):
    """P(Replikant | aufgedeckte Tells) als 0..1 (Naive Bayes, Log-Odds)."""
    lk = likelihoods(camo)
    prior = min(max(prior, 0.01), 0.99)
    lo = math.log(prior / (1 - prior))
    for name in revealed:
        rp, hp = lk[name]
        present = bool(tells.get(name))
        r = rp if present else (1 - rp)
        h = hp if present else (1 - hp)
        r = min(max(r, 1e-3), 1 - 1e-3)
        h = min(max(h, 1e-3), 1 - 1e-3)
        lo += math.log(r / h)
    return 1.0 / (1.0 + math.exp(-lo))


def tell_present_count(revealed, tells):
    return sum(1 for n in revealed if tells.get(n))
