#!/usr/bin/env python3
"""SimShot: baut eine World, simuliert kurz, komponiert die Szene und dithert sie auf der CPU nach PNG.

Reiner CPU-Pfad (kein GL): zeigt exakt, was der Bayer-Shader aus der Szene macht,
nur ohne CRT. Langsam (Python-Dither, ein paar Sekunden), dafür überall lauffähig.
Aufruf: python3 tools/simshot.py [out.png] [zone] [seed]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtGui import QImage  # noqa: E402

from shadegunner import config  # noqa: E402
from shadegunner.palette import dither  # noqa: E402
from shadegunner.render import pngmin  # noqa: E402
from shadegunner.render.scene import Scene  # noqa: E402
from shadegunner.sim import World  # noqa: E402


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "shots/simshot.png"
    zone = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 11
    w, h = config.RENDER_W, config.RENDER_H

    world = World(seed=seed, zone_index=zone)
    world.player.x = world.length * 0.35
    world.camera_x = world.player.x + 40
    sc = Scene(w, h)
    for _ in range(30):
        world.update(1 / 60, dict(move=(0.5, 0)))
        img = sc.frame(world, 1 / 60)
    rgb = img.convertToFormat(QImage.Format.Format_RGB888)
    buf = bytearray(w * h * 3)
    bits = rgb.constBits()
    bits.setsize(rgb.sizeInBytes())
    raw = bytes(bits)
    stride = rgb.bytesPerLine()
    for y in range(h):
        buf[y * w * 3:(y + 1) * w * 3] = raw[y * stride:y * stride + w * 3]
    pngmin.write_png(out, dither(buf, w, h), w, h)
    reps = sum(1 for a in world.actors if a.is_replicant)
    print(f"geschrieben: {out}  Zone '{world.zone['name']}'  Aktoren={len(world.actors) - 1}  Replikanten={reps}")


if __name__ == "__main__":
    main()
