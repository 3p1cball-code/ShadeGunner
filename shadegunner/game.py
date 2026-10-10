"""Interaktives Spiel: QOpenGLWidget mit Spiel-Loop, Eingabe und HUD.

Rendering: Szene (CPU, render/scene.py) -> CRTRenderer (Bayer + CRT) -> Widget.
Der HUD wird per QPainter über das fertige Bild gelegt.
"""

import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtOpenGLWidgets import QOpenGLWidget

from . import config
from .render.glrender import CRTRenderer, GLFuncs
from .render.scene import Scene
from .sim import ZONES, World

C = config.NOIR16
WHITE, CYAN, AMBER, MAGENTA, ASH, SLATE, RED = C[10], C[12], C[14], C[13], C[8], C[7], C[13]

MOVE_LEFT = {Qt.Key.Key_A, Qt.Key.Key_Left}
MOVE_RIGHT = {Qt.Key.Key_D, Qt.Key.Key_Right}
DEPTH_FAR = {Qt.Key.Key_W, Qt.Key.Key_Up}
DEPTH_NEAR = {Qt.Key.Key_S, Qt.Key.Key_Down}


class GameWidget(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ShadeGunner")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.resize(1152, 648)

        self.vc, self.vr = config.RENDER_W, config.RENDER_H
        seed = int(time.time()) & 0xFFFF
        self.world = World(seed=seed, zone_index=0)
        self.scene = Scene(self.vc, self.vr)
        self.scene.ensure_zone(0, seed)

        self._gl = None
        self.renderer = None
        self.keys = set()
        self._last = time.monotonic()
        self._dt = 1 / 60
        self._flash = ("", 0.0)
        self._zone_hold = 0.0
        self._finished_hold = 0.0

        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)

    # ---------------------------------------------------------------- GL
    def initializeGL(self):
        try:
            self._gl = GLFuncs(self.context())
            self.renderer = CRTRenderer(self._gl)
            self.timer.start()
        except Exception as exc:  # noqa: BLE001
            print(f"[error] GL-Init fehlgeschlagen: {exc}")

    # ---------------------------------------------------------------- Loop
    def _tick(self):
        now = time.monotonic()
        self._dt = min(0.05, now - self._last)
        self._last = now
        w = self.world

        if w.state == "playing":
            mx = (1 if (self.keys & MOVE_RIGHT) else 0) - (1 if (self.keys & MOVE_LEFT) else 0)
            md = (1 if (self.keys & DEPTH_NEAR) else 0) - (1 if (self.keys & DEPTH_FAR) else 0)
            w.update(self._dt, (mx, md))
        elif w.state == "zone_clear":
            self._zone_hold += self._dt
            if self._zone_hold > 1.6:
                self._zone_hold = 0.0
                if not w.advance_zone():
                    self.world.state = "finished"
                else:
                    self.scene.ensure_zone(w.zone_index, w.zone_index * 31)
        elif w.state == "failed":
            self._finished_hold += self._dt
            if self._finished_hold > 2.4 and (self.keys & {Qt.Key.Key_R}):
                self._restart()

        self._flash_tick(self._dt)
        self.update()

    def _restart(self):
        seed = int(time.time()) & 0xFFFF
        self.world = World(seed=seed, zone_index=0)
        self.scene.ensure_zone(0, seed)
        self._finished_hold = 0.0

    def _flash_tick(self, dt):
        if self._flash[1] > 0:
            self._flash = (self._flash[0], max(0.0, self._flash[1] - dt))

    # ---------------------------------------------------------------- Input
    def keyPressEvent(self, e):
        self.keys.add(e.key())
        if e.key() == Qt.Key.Key_Space:
            res, a = self.world.scan()
            self._say_scan(res)
        elif e.key() in (Qt.Key.Key_E, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            res, a = self.world.neutralize()
            self._say_action(res)
        elif e.key() == Qt.Key.Key_R and self.world.state in ("failed", "finished"):
            self._restart()
        elif e.key() == Qt.Key.Key_Escape:
            self.close()
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        self.keys.discard(e.key())
        super().keyReleaseEvent(e)

    def _say_scan(self, res):
        msg = {"no_charge": "Keine Scan-Ladung!",
               "no_target": "Kein Ziel in Reichweite.",
               "ok": "Scan läuft..."}.get(res, res)
        self._flash = (msg, 1.2)

    def _say_action(self, res):
        msg = {"no_target": "Niemand in Reichweite.",
               "replicant": "Replikant deaktiviert.",
               "civilian": "MENSCH getötet!"}.get(res, res)
        self._flash = (msg, 1.4)

    # ---------------------------------------------------------------- Draw
    def paintGL(self):
        if self.renderer is None:
            return
        dpr = self.devicePixelRatioF()
        fw = max(1, round(self.width() * dpr))
        fh = max(1, round(self.height() * dpr))
        cav = self.scene.frame(self.world, self._dt)
        self.renderer.render(self.defaultFramebufferObject(), fw, fh, cav.buf,
                             self.vc, self.vr, gamma=0.9, dt=self._dt, dpr=dpr)
        self._hud(dpr, fw, fh)

    def _cell_map(self, dpr, fw, fh):
        cell = min(fw / self.vc, fh / self.vr)
        ox = (fw - self.vc * cell) / 2.0
        oy = (fh - self.vr * cell) / 2.0
        return cell, ox, oy

    def _hud(self, dpr, fw, fh):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        f = QFont("monospace")
        f.setPixelSize(15)
        p.setFont(f)

        w = self.world
        # Konfidenz-Meter über gescannten Aktoren
        cell, ox, oy = self._cell_map(dpr, fw, fh)
        for a in w.actors:
            if a.player or a.deactivated or not a.scanned or not a.alive:
                continue
            gx, gy, hgt = w.project(a, self.vc, self.vr)
            if gx < -20 or gx > self.vc + 20:
                continue
            sx = (ox + gx * cell) / dpr
            sy = (oy + (gy - hgt) * cell) / dpr
            conf = w.confidence_of(a)
            self._meter(p, sx, sy - 14, conf)

        # linkes Panel
        zone = f"ZONE {w.zone_index + 1}/{len(ZONES)}  {w.zone['name'].upper()}"
        self._text(p, 16, 30, zone, WHITE)
        self._text(p, 16, 52, f"PUNKTE {w.points}   REPLIKANTEN {w.replicants_total}", ASH)

        # rechtes Panel: Scan-Ladungen + Suspicion
        rx = self.width() - 260
        self._text(p, rx, 30, "SCAN", ASH)
        full = int(w.scan_charges)
        charges = "|" * full + "." * max(0, w.scan_max - full)
        self._text(p, rx + 60, 30, charges, CYAN)
        self._text(p, rx, 52, "SUSPICION", ASH)
        self._bar(p, rx + 110, 42, 140, 10, w.suspicion)

        # Meldungs-Flash
        if self._flash[1] > 0:
            col = [WHITE, CYAN, AMBER, MAGENTA][0]
            if "MENSCH" in self._flash[0] or "getötet" in self._flash[0]:
                col = (255, 90, 70)
            self._text(p, 16, self.height() - 60, self._flash[0], col)

        # Log
        y = self.height() - 34
        for line in w.log[-2:]:
            self._text(p, 16, y, line, SLATE)
            y += 18

        # Steuerung
        self._text(p, self.width() - 300, self.height() - 24,
                   "A/D bewegen  W/S tiefe  SPACE scan  E deaktivieren", SLATE)

        if w.state == "zone_clear":
            self._center(p, "ZONE GESCHAFFT")
        elif w.state == "finished":
            self._center(p, "TYRELL HQ ERREICHT — R für neuen Run")
        elif w.state == "failed":
            self._center(p, "SUSPICION ZU HOCH — R für neuen Run")
        p.end()

    # ---- HUD-Helfer
    def _text(self, p, x, y, s, col):
        p.setPen(QPen(QColor(col[0], col[1], col[2])))
        p.drawText(int(x), int(y), s)

    def _center(self, p, s):
        p.setPen(QPen(QColor(255, 255, 255)))
        fm = p.fontMetrics()
        f = p.font()
        f.setPixelSize(34)
        p.setFont(f)
        p.drawText(int((self.width() - fm.horizontalAdvance(s)) / 2), int(self.height() / 2), s)
        f.setPixelSize(15)
        p.setFont(f)

    def _bar(self, p, x, y, w, h, frac):
        p.fillRect(int(x), int(y), int(w), int(h), QColor(30, 34, 46))
        col = (255, 138, 44) if frac < 0.5 else (224, 72, 90)
        p.fillRect(int(x), int(y), int(w * min(1.0, frac)), int(h), QColor(*col))

    def _meter(self, p, x, y, conf):
        h = 26
        p.fillRect(int(x), int(y - h), 6, h, QColor(20, 24, 34))
        col = (64, 210, 220) if conf >= 0.66 else ((255, 138, 44) if conf >= 0.4 else (120, 126, 140))
        p.fillRect(int(x), int(y - h * conf), 6, int(h * conf), QColor(*col))
