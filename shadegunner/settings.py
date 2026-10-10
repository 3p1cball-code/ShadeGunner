"""Spiel-Einstellungen (Grafik/Sound), persistiert als JSON neben dem Spielstand."""

import json
import os

from .save import _base_dir

# renderer: "auto" (OpenGL, sonst Software) | "software" (immer CPU)
DEFAULTS = dict(music=0.7, sfx=1.0, fullscreen=False, scanlines=True, renderer="auto")


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
