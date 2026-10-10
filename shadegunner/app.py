"""Anwendungseinstieg.  Start:  python3 -m shadegunner   (oder tools/run.sh)"""

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
    _set_gl_format()
    app = QApplication(sys.argv)
    widget = GameWidget()
    widget.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
