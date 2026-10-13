#!/usr/bin/env python3
"""Headless-GL-Render: rendert die GPU-Pipeline (Szene + HUD -> Bayer -> CRT) offscreen nach PNG.

Zweck: den GPU-Pfad ohne Fenster verifizieren (läuft über SSH mit gesetztem DISPLAY).
Aufruf: python3 tools/glshot.py [out.png] [zone] [seed] [frames] [--raw] [--hud] [--aim] [--scan]
  --raw   zusätzlich die unbearbeitete Szene (vor Dither) als <out>_raw.png
  --hud   HUD wie im Spiel einblenden
  --aim   Spieler zielt in den letzten Frames (Laservisier)
  --scan  Spieler scannt in den letzten Frames
  --eye   Augenreflex bei einem Replikanten erkennen (HUD-Emblem überm Kopf)
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtGui import (QGuiApplication, QOffscreenSurface, QOpenGLContext,  # noqa: E402
                         QSurfaceFormat)
from PyQt6.QtOpenGL import QOpenGLFramebufferObject  # noqa: E402

from shadegunner import config, persp  # noqa: E402
from shadegunner.render.glrender import CRTRenderer, GLFuncs  # noqa: E402
from shadegunner.render.scene import Scene  # noqa: E402
from shadegunner.sim import World  # noqa: E402


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    lang = "de"
    for fl in sys.argv[1:]:
        if fl.startswith("--lang="):
            lang = fl[7:]
    out = args[0] if len(args) > 0 else "shots/sg_gl.png"
    zone = int(args[1]) if len(args) > 1 else 2
    seed = int(args[2]) if len(args) > 2 else 11
    frames = int(args[3]) if len(args) > 3 else 90
    w, h = 1280, 720
    for fl in flags:
        if fl.startswith("--size="):
            w, h = (int(v) for v in fl[7:].lower().split("x"))

    app = QGuiApplication(sys.argv)  # noqa: F841
    from shadegunner import i18n
    i18n.set_lang(lang)
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

    gl = GLFuncs(ctx)
    renderer = CRTRenderer(gl)
    renderer.force_dt = 1 / 60
    fbo = QOpenGLFramebufferObject(w, h)

    world = World(seed=seed, zone_index=zone)
    world.player.x = world.length * 0.3
    for fl in flags:
        if fl == "--at=ramen" and getattr(world, "ramen", None):
            world.player.x = world.ramen[0]["x"] - 60
        elif fl == "--at=steam" and getattr(world, "manholes", None):
            m = sorted(world.manholes, key=lambda m: (not m["stack"], m["x"]))[0]
            world.player.x = m["x"] - 60
            for mm in world.manholes:
                mm["base"] = max(mm["base"], 0.8)
        elif fl == "--at=steam2" and getattr(world, "manholes", None):
            m = sorted(world.manholes, key=lambda m: (m["stack"], m["x"]))[0]
            world.player.x = m["x"] - 60
            for mm in world.manholes:
                mm["base"] = max(mm["base"], 0.8)
        elif fl == "--at=origami" and getattr(world, "origami", None):
            world.player.x = world.origami[0]["x"] - 70
            world.player.depth = world.origami[0]["depth"]
        elif fl == "--at=holo":
            from shadegunner.render.city import City
            c = City(zone, world.length, seed)
            st = [h for h in c.holos if h["kind"] == "street"]
            if st:
                world.player.x = st[0]["L"] / c.facade.factor - 40
        elif fl in ("--at=bridge", "--at=overhang"):
            from shadegunner.render.city import City
            c = City(zone, world.length, seed)
            sp = [s for s in c.spans if s["kind"] == fl[5:]]
            if sp:
                world.player.x = (sp[0]["x0"] + sp[0]["x1"]) / 2 - 40
        elif fl == "--at=sebastian":         # ROY steht vor Sebastians Haus und wartet
            world.player.x = world.length - config.ROY_STAND - 200
            world.stats["reps"] = world.quota
        elif fl.startswith("--at="):
            world.player.x = world.length * float(fl[5:])
    for fl in flags:
        if fl.startswith("--dx="):            # Kamera/Spieler relativ verschieben (z. B. vor/unter/nach Brücke)
            world.player.x += float(fl[5:])
    world.camera_x = world.player.x + 40
    for fl in flags:
        # --veh=car,police,...: Fahrzeuge stehen still im Bild (Beauty-Shot der Modelle)
        if fl.startswith("--veh="):
            from shadegunner.sim import VEHICLES
            for i, kind in enumerate(fl[6:].split(",")):
                L, hh, _sp = VEHICLES[kind]
                lane, dr = config.LANES[i % len(config.LANES)]
                world.vehicles.append(dict(x=world.player.x - 200 + i * 150, depth=lane, dir=dr, speed=0.0,
                                           kind=kind, L=L, h=hh, seed=i * 7, honk=True, uid=-5000 - i))
    sc = Scene(config.RENDER_W, config.RENDER_H)
    sc.ensure_zone(zone, seed, world.length)
    if "--bikes" in flags:               # Radfahrer-Pulk mitten im Bild (Kulisse zeigen)
        import random as _r
        rr = _r.Random(3)
        for j in range(5):
            sc.bikes.append(dict(x=world.player.x - 60 + j * 30 + rr.uniform(-6, 6), d=(0.12, 0.44)[j % 2],
                                 v=(48 if j % 2 else -50) * 0.02, ph=rr.uniform(0, 6), poncho=rr.choice(sc.PONCHO),
                                 hat=j != 2, umb=j in (1, 3), glow=j == 3, seed=j))
    hud = None
    if "--hud" in flags:
        from shadegunner.hud import HUD
        hud = HUD()

    dt = 1 / 60
    t_scene = 0.0
    img = None
    if "--patrol" in flags or "--land" in flags:
        world.patrol_cd = 0.5
    if "--land" in flags:            # Patrouille landet garantiert (Spinner-Landung zeigen)
        config.SPINNER_LAND_CHANCE = 1.0
    if "--dark" in flags:
        world.blackout_at = frames * dt * 0.5
    if "--roy" in flags:                 # ROY lässt ab: Monolog bis zur Taube (frames ~ 1700)
        world.player.x = world.length - config.ROY_TRIGGER + 5
        world.stats["reps"] = world.quota
        world.update(dt, {})
        world.player.x = world.boss.x - 90
        world.update(dt, {})
        world.boss_speak_t = 0.0
        world.player.hp = 1
    for i in range(frames):
        if "--traffic" in flags and i == frames - 120:
            world.traffic_cd = 0.0
        if "--kill" in flags and i == int(frames * 0.5):
            for a in sorted(world.living(), key=lambda a: abs(a.x - world.player.x))[:3]:
                world._kill(a)
        late = i > frames * 0.6
        mv = 0.0 if ("--still" in flags or "--roy" in flags) else (0.6 if not late else 0.0)
        if "--shout" in flags and i == int(frames * 0.6):
            world.shout_crowd()
        if "--eye" in flags and i == frames - 30:
            # Augenreflex beim nächsten Replikanten mit Pupillen-Tell (HUD-Emblem zeigen)
            cand = [a for a in world.living() if a.tells.get("pupils") and "pupils" not in a.revealed
                    and 60 < persp.screen_x(a.x, a.depth, world.camera_x) < config.RENDER_W - 60]
            if cand:
                a = min(cand, key=lambda a: abs(a.x - world.player.x))
                world.target = a
                world._glint_seen(a, "AUGENREFLEX!", 1e9)
        inp = dict(move=(mv, 0.0),
                   aim=late and "--aim" in flags,
                   scan=(i == int(frames * 0.6) + 1) and "--scan" in flags)
        world.update(dt, inp)
        if "--gust" in flags and i == frames - 50:      # Windböe mit Papier (Kulisse)
            sc._gust = 0.0
        t0 = time.perf_counter()
        img = sc.frame(world, dt)
        sc.consume(world, world.events)
        world.events.clear()
        t_scene += time.perf_counter() - t0
        ui = dict(mode="play")
        for fl in flags:
            if fl.startswith("--ui="):
                ui = dict(mode=fl[5:], t=i / 60.0 if fl[5:] == "intro" else 1.0, best=dict(best=4200, rank="A", runs=3),
                          options=world.run.offer(__import__("random").Random(1)) if fl[5:] == "clear" else [],
                          sel=1, help=False, settings={**__import__("shadegunner.settings").settings.DEFAULTS,
                                                       "lang": lang},
                          settings_sel=6)
        if "--help" in flags:
            ui["help"] = True

        himg = hud.render(world, sc, dt, ui) if hud else None
        renderer.render(fbo.handle(), w, h, img, config.RENDER_W, config.RENDER_H,
                        gamma=0.9, dt=dt, dpr=1.0, hud=himg)

    fbo.toImage().save(out)
    if "--raw" in flags:
        img.save(out.replace(".png", "_raw.png"))
    print(f"geschrieben: {out}  ({w}x{h}, {frames} Frames)  Zone '{world.zone['name']}'  "
          f"Szene Ø {t_scene / frames * 1000:.1f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
