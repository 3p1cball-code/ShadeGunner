"""Persistenter Spielstand: Bestwert, Rang, Zahl der Einsätze (global, nicht pro Run)."""

import json
import os


def _base_dir():
    if os.name == "nt":   # Windows: %APPDATA%
        return os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    return os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")


def _path():
    return os.path.join(_base_dir(), "shadegunner", "save.json")


RANKS = "DCBAS"


def load():
    try:
        with open(_path(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def record(score, rank, won):
    """Ergebnis eintragen. Gibt (daten, neuer_bestwert) zurück."""
    d = load()
    d["runs"] = int(d.get("runs", 0)) + 1
    d["wins"] = int(d.get("wins", 0)) + (1 if won else 0)
    new_best = score > int(d.get("best", 0))
    if new_best:
        d["best"] = int(score)
    if RANKS.index(rank) > RANKS.index(d.get("rank", "D")) or "rank" not in d:
        d["rank"] = rank
    try:
        os.makedirs(os.path.dirname(_path()), exist_ok=True)
        tmp = _path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=1)
        os.replace(tmp, _path())
    except OSError:
        pass
    return d, new_best
