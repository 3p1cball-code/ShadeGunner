#!/usr/bin/env python3
"""SimShot: baut eine World, simuliert kurz, rendert + dithert nach PNG.

Aufruf: python3 tools/simshot.py [out.png] [zone] [seed]
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shadegunner import config  # noqa: E402
from shadegunner.palette import dither  # noqa: E402
from shadegunner.render import pngmin  # noqa: E402
from shadegunner.render.scene import render_world  # noqa: E402
from shadegunner.sim import World  # noqa: E402


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/opencode/shadegunner_sim.png"
    zone = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 11
    w, h = config.RENDER_W, config.RENDER_H

    world = World(seed=seed, zone_index=zone)
    # Spieler etwas in die Straße bewegen + ein paar Scans setzen
    world.player.x = world.length * 0.35
    world.camera_x = world.player.x
    for a in world.actors:
        if a is not world.player and abs(a.x - world.player.x) < config.SCAN_RANGE:
            world.player.x = a.x
            world.scan()

    cav = render_world(world, w, h, random.Random(seed + 99))
    framed = dither(cav.buf, w, h)
    pngmin.write_png(out, framed, w, h)
    reps = sum(1 for a in world.actors if a.is_replicant)
    print(f"geschrieben: {out}  Zone '{world.zone['name']}'  "
          f"Aktoren={len(world.actors) - 1}  Replikanten={reps}  Punkte={world.points}")


if __name__ == "__main__":
    main()
