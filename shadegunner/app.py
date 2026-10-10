"""Anwendungseinstieg.  Start:  python3 -m shadegunner [--fullscreen] [--software]"""

import os
import sys

from PyQt6.QtGui import QSurfaceFormat
from PyQt6.QtWidgets import QApplication

from . import settings
from .game import GameWidget, SoftwareGameWidget


def _set_gl_format():
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
    fmt.setSwapInterval(1)
    QSurfaceFormat.setDefaultFormat(fmt)


def _probe_gl():
    """Kurzer Test, ob ein OpenGL-3.3-Kontext möglich ist (sonst Software-Fallback)."""
    try:
        from PyQt6.QtGui import QOffscreenSurface, QOpenGLContext
        ctx = QOpenGLContext()
        if not ctx.create():
            return False
        surf = QOffscreenSurface()
        surf.setFormat(ctx.format())
        surf.create()
        ok = surf.isValid() and ctx.makeCurrent(surf)
        if ok:
            f = ctx.format()
            ok = (f.majorVersion(), f.minorVersion()) >= (3, 3)
        ctx.doneCurrent()
        return ok
    except Exception:  # noqa: BLE001
        return False


def _want_software():
    if "--software" in sys.argv:
        return True
    return os.environ.get("SHADEGUNNER_SOFTWARE", "").lower() in ("1", "true", "yes")


def main():
    # Im gepackten .exe-Build ruft sich das Spiel selbst auf, um den Soundtrack zu
    # erzeugen - dann ohne Qt/Fenster.
    if len(sys.argv) >= 3 and sys.argv[1] == "--build-audio":
        from . import audio
        audio.build(sys.argv[2])
        return

    _set_gl_format()
    cfg = settings.load()
    fullscreen = ("--fullscreen" in sys.argv) or bool(cfg.get("fullscreen"))
    app = QApplication(sys.argv)

    software = _want_software() or cfg.get("renderer") == "software" or not _probe_gl()
    if software:
        print("[info] Software-Renderer (kein OpenGL 3.3 / per Schalter aktiviert)")
    widget = SoftwareGameWidget() if software else GameWidget()
    if fullscreen:
        widget.showFullScreen()
    else:
        widget.showMaximized()
    widget.raise_()
    widget.activateWindow()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
