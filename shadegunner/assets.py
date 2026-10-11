"""Pfade zu mitgelieferten Dateien (Icons) - im Repo wie im PyInstaller-Bundle.

Die Bilder erzeugt `tools/make_brand.py`; fehlen sie, läuft das Spiel ohne.
"""

import os
import sys

ICON_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)


def base_dir():
    """Repo-Wurzel bzw. das entpackte Bundle (sys._MEIPASS)."""
    return getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def icon_path(size):
    """Pfad zu assets/icons/shadegunner-<size>.png oder None, wenn nicht vorhanden."""
    f = os.path.join(base_dir(), "assets", "icons", f"shadegunner-{size}.png")
    return f if os.path.exists(f) else None


_CACHE = {}


def emblem(size, scale=1):
    """Emblem als QImage (nearest um `scale` vergrößert, gecacht) oder None."""
    key = (size, scale)
    if key not in _CACHE:
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QImage
        f = icon_path(size)
        img = None
        if f:
            img = QImage(f).convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
            if img.isNull():
                img = None
            elif scale != 1:
                img = img.scaled(size * scale, size * scale, Qt.AspectRatioMode.IgnoreAspectRatio,
                                 Qt.TransformationMode.FastTransformation)
        _CACHE[key] = img
    return _CACHE[key]
