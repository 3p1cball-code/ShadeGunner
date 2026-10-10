#!/usr/bin/env python3
"""Headless-GL-Render: rendert die GPU-Pipeline (Bayer + CRT) offscreen nach PNG.

Zweck: den GPU-Pfad ohne Fenster verifizieren (läuft über SSH mit gesetztem DISPLAY).
Aufruf: python3 tools/glshot.py [out.png] [zone] [seed] [frames]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtGui import (QGuiApplication, QOffscreenSurface, QOpenGLContext,  # noqa: E402
                         QSurfaceFormat)
from PyQt6.QtOpenGL import QOpenGLFramebufferObject  # noqa: E402

from shadegunner import config  # noqa: E402
from shadegunner.render.glrender import CRTRenderer, GLFuncs  # noqa: E402
from shadegunner.render.scene import Scene  # noqa: E402
from shadegunner.sim import World  # noqa: E402


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/opencode/sg_gl.png"
    zone = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 11
    frames = int(sys.argv[4]) if len(sys.argv) > 4 else 24
    w, h = 1152, 648

    app = QGuiApplication(sys.argv)  # noqa: F841
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
    ctx = QOpenGLContext()
    ctx.setFormat(fmt)
    if not ctx.create():
        print("FEHLER: GL-Kontext konnte nicht erstellt werden", file=sys.stderr)
        return 2
    surf = QOffscreenSurface()
    surf.setFormat(fmt)
    surf.create()
    if not ctx.makeCurrent(surf):
        print("FEHLER: Kontext nicht current", file=sys.stderr)
        return 2
    f = ctx.format()
    print(f"[info] GL {f.majorVersion()}.{f.minorVersion()} "
          f"{'ES' if ctx.isOpenGLES() else 'desktop'}")

    gl = GLFuncs(ctx)
    renderer = CRTRenderer(gl)
    fbo = QOpenGLFramebufferObject(w, h)

    world = World(seed=seed, zone_index=zone)
    world.player.x = world.length * 0.35
    world.camera_x = world.player.x
    sc = Scene(config.RENDER_W, config.RENDER_H)
    sc.ensure_zone(zone, seed)

    dt = 1 / 60
    for i in range(frames):
        world.update(dt, (0.4, 0.0))
        cav = sc.frame(world, dt)
        renderer.render(fbo.handle(), w, h, cav.buf, config.RENDER_W, config.RENDER_H,
                        gamma=0.9, dt=dt, dpr=1.0)

    img = fbo.toImage()
    img.save(out)
    print(f"geschrieben: {out}  ({w}x{h}, {frames} Frames)  Zone '{world.zone['name']}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
