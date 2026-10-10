#!/usr/bin/env python3
"""End-to-End-Test des echten GameWidget: Skript-Eingaben + Framegrabs, auch ohne sichtbares Fenster.

Simuliert Tastendrücke über die echten Event-Handler, rendert per grabFramebuffer()
(ruft paintGL auch dann auf, wenn das Fenster nicht exponiert ist, z. B. bei
gesperrtem Bildschirm) und speichert ausgewählte Frames.

Aufruf: python3 tools/playtest.py [ausgabe_präfix]
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SHADEGUNNER_NOSOUND", "1")

from PyQt6.QtCore import QEvent, Qt  # noqa: E402
from PyQt6.QtGui import QKeyEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from shadegunner import game  # noqa: E402
from shadegunner.app import _set_gl_format  # noqa: E402

K = Qt.Key


def key(w, k, down=True):
    ev = QKeyEvent(QEvent.Type.KeyPress if down else QEvent.Type.KeyRelease, k, Qt.KeyboardModifier.NoModifier)
    (w.keyPressEvent if down else w.keyReleaseEvent)(ev)


def main():
    prefix = sys.argv[1] if len(sys.argv) > 1 else "shots/play"
    _set_gl_format()
    app = QApplication(sys.argv)
    w = game.GameWidget()
    w.resize(1280, 720)
    w.show()
    app.processEvents()
    w.timer.stop()                 # wir takten selbst
    w.grabFramebuffer()            # initialisiert GL
    w.timer.stop()

    script = [
        (0.8, None, "title"),
        (0.1, ("tap", K.Key_Return), None),
        (1.2, None, "intro"),
        (0.1, ("tap", K.Key_Space), None),
        (3.0, ("hold", K.Key_D), "walk"),
        (0.1, ("tap", K.Key_Space), None),
        (0.2, None, "jump"),
        (0.6, None, None),
        (0.1, ("click", None), None),
        (0.1, ("tap", K.Key_R), None),
        (0.5, None, "scan"),
        (0.6, ("hold", K.Key_E), "aim"),
        (0.1, ("release", K.Key_E), None),
        (0.15, None, "shot"),
        (2.0, ("hold", K.Key_D), None),
        (0.1, ("tap", K.Key_H), None),
        (0.3, None, "help"),
        (0.1, ("tap", K.Key_H), None),
    ]
    dt = 1 / 60
    frame_times = []
    for dur, act, shot in script:
        if act:
            kind, k = act
            if kind == "tap":
                key(w, k, True)
                key(w, k, False)
            elif kind == "hold":
                key(w, k, True)
            elif kind == "release":
                key(w, k, False)
            elif kind == "click":
                # Rechtsklick auf die zweitnächste Figur: Zielwahl per Maus + Scan
                from PyQt6.QtCore import QPointF
                from PyQt6.QtGui import QMouseEvent
                pl = w.world.player
                cands = sorted(w.world.living(), key=lambda a: abs(a.x - pl.x) + abs(a.depth - pl.depth) * 160)
                cands = [a for a in cands if a.uid in w.scene.screen]
                if len(cands) > 1:
                    a = cands[1]
                    cx, gy, hgt, _m = w.scene.screen[a.uid]
                    wx = (cx / w.vc) * w.width()
                    wy = ((gy - hgt * 0.5) / w.vr) * w.height()
                    ev = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(wx, wy), QPointF(wx, wy),
                                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
                    w.mousePressEvent(ev)
                    w.mouse_aim = False
                    print("Mausklick auf #%04d -> Ziel #%s" % (a.uid, w.world.target.uid if w.world.target else None))
        n = max(1, int(dur / dt))
        for i in range(n):
            w._last = time.monotonic() - dt
            w._tick()
            t0 = time.perf_counter()
            img = w.grabFramebuffer()
            frame_times.append(time.perf_counter() - t0)
        if act and act[0] == "hold":
            key(w, act[1], False)
        if shot:
            img.save(f"{prefix}_{shot}.png")
            print("frame:", f"{prefix}_{shot}.png", "modus", w.mode)
    avg = sum(frame_times) / len(frame_times) * 1000
    print(f"Frames {len(frame_times)}  Ø Render {avg:.1f} ms  Modus {w.mode}  "
          f"Punkte {w.world.run.score if hasattr(w.world, 'run') else '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
