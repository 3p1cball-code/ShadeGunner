"""Spiel-Einstellungen (Grafik/Sound), persistiert als JSON neben dem Spielstand."""

import json
import os

from .save import _base_dir

# renderer: "auto" (OpenGL, sonst Software) | "software" (immer CPU)
DEFAULTS = dict(music=0.7, sfx=1.0, fullscreen=False, resolution=[1280, 720],
                scanlines=True, renderer="auto", difficulty="normal", lang="de")


def _path():
    return os.path.join(_base_dir(), "shadegunner", "settings.json")


def load():
    d = dict(DEFAULTS)
    try:
        with open(_path(), encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            d.update({k: v for k, v in data.items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    r = d.get("resolution")
    if not (isinstance(r, (list, tuple)) and len(r) == 2 and all(isinstance(v, int) for v in r)):
        d["resolution"] = list(DEFAULTS["resolution"])
    if d.get("difficulty") not in ("leicht", "normal", "schwer"):
        d["difficulty"] = "normal"
    if d.get("lang") not in ("de", "en"):
        d["lang"] = "de"
    return d


def save(d):
    try:
        os.makedirs(os.path.dirname(_path()), exist_ok=True)
        tmp = _path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=1)
        os.replace(tmp, _path())
    except OSError:
        pass
