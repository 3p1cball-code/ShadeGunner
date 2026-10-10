"""Anwendungseinstieg.  Start:  python3 -m shadegunner [--fullscreen]"""

import sys

from PyQt6.QtGui import QSurfaceFormat
from PyQt6.QtWidgets import QApplication

from .game import GameWidget


def _set_gl_format():
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
    fmt.setSwapInterval(1)
    QSurfaceFormat.setDefaultFormat(fmt)


def main():
    # Im gepackten .exe-Build (PyInstaller) ruft sich das Spiel selbst auf, um den
    # Soundtrack zu erzeugen - dann ohne Qt/Fenster.
    if len(sys.argv) >= 3 and sys.argv[1] == "--build-audio":
        from . import audio
        audio.build(sys.argv[2])
        return
    _set_gl_format()
    fullscreen = "--fullscreen" in sys.argv
    app = QApplication(sys.argv)
    widget = GameWidget()
    if fullscreen:
        widget.showFullScreen()
    else:
        widget.showMaximized()
    widget.raise_()
    widget.activateWindow()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
