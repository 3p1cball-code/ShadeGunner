#!/usr/bin/env python3
"""Debug: Häuserfront einer Zone als Streifen (Ausschnitt, hochskaliert) -> PNG.

Aufruf: python3 tools/facadeshot.py out.png zone [seed] [start_anteil] [breite_px] [skala]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402

from shadegunner.render.city import City  # noqa: E402
from shadegunner.sim import ZONES  # noqa: E402


def main():
    app = QGuiApplication(sys.argv)  # noqa: F841
    out = sys.argv[1]
    zone = int(sys.argv[2])
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 11
    f0 = float(sys.argv[4]) if len(sys.argv) > 4 else 0.3
    bw = int(sys.argv[5]) if len(sys.argv) > 5 else 900
    sc = int(sys.argv[6]) if len(sys.argv) > 6 else 2
    c = City(zone, ZONES[zone]["length"], seed)
    img = c.facade.img
    x0 = int(img.width() * f0)
    crop = img.copy(x0, 0, bw, img.height())
    bg = QImage(crop.size(), QImage.Format.Format_RGB32)
    p = QPainter(bg)
    for x in range(0, bw, c.sky.width()):
        p.drawImage(x, 0, c.sky)
    p.drawImage(0, 0, crop)
    p.end()
    bg.scaled(bw * sc, img.height() * sc, Qt.AspectRatioMode.IgnoreAspectRatio,
              Qt.TransformationMode.FastTransformation).save(out)
    print(out, img.width(), "fires", len(c.fires), "walks", len(c.walks))


if __name__ == "__main__":
    main()
