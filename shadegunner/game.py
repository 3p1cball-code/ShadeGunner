"""Interaktives Spiel: QOpenGLWidget mit Spiel-Loop, Zuständen, Eingabe, HUD und Sound.

Rendering: Szene (CPU, render/scene.py) + HUD (hud.py) -> CRTRenderer (Bayer + CRT).
Zustände: title -> intro -> play <-> pause -> clear (Upgrade) -> intro ... -> victory | over
"""

import os
import random
import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtWidgets import QWidget

from . import config, save, settings
from .audio import Audio
from .hud import HUD, rank_of
from .render import sodither
from .render.glrender import CRTRenderer, GLFuncs
from .render.scene import Scene
from .sim import ZONES, Run, World

K = Qt.Key
MOVE_LEFT = {K.Key_A, K.Key_Left}
MOVE_RIGHT = {K.Key_D, K.Key_Right}
DEPTH_FAR = {K.Key_W, K.Key_Up}
DEPTH_NEAR = {K.Key_S, K.Key_Down}
AIM_KEYS = {K.Key_E, K.Key_Control}
SPRINT = {K.Key_Shift}
CONFIRM = {K.Key_Return, K.Key_Enter, K.Key_Space}
SCAN_KEYS = {K.Key_R}
JUMP_KEYS = {K.Key_Space}
CANCEL_KEYS = {K.Key_C}


class _GameMixin:
    """Gemeinsame Spiellogik (Zustände, Eingabe, HUD, Sound) für beide Renderpfade.

    Konkrete Widgets: GameWidget (QOpenGLWidget + CRTRenderer) und
    SoftwareGameWidget (QWidget + CPU-Dither). Nur die Darstellung unterscheidet sich.
    """

    _SETTING_KEYS = ["music", "sfx", "fullscreen", "resolution", "scanlines", "renderer"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.software = False
        self.setWindowTitle("ShadeGunner")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.resize(1280, 720)

        self.vc, self.vr = config.RENDER_W, config.RENDER_H
        self.scene = Scene(self.vc, self.vr)
        self.hud = HUD()
        self.audio = Audio()
        self.best = save.load()
        self.settings = settings.load()
        self.settings_sel = 0
        self._settings_back = "title"
        self.audio.set_volumes(self.settings["music"], self.settings["sfx"])

        self._gl = None
        self.renderer = None
        self.keys = set()
        self.mouse_aim = False
        self.mouse_scene = None     # Mausposition in Szenen-Pixeln (640x360), None = außerhalb
        self.mouse_t = 99.0         # Sekunden seit der letzten Mausbewegung
        self._mouse_moved = False
        self._edge = {}
        self._last = time.monotonic()
        self._dt = 1 / 60
        self.help = False
        self.mode = "title"
        self.mode_t = 0.0
        self.power = 0.0
        self.fade = 0.0
        self._trans = None          # (phase, callback): Abblende -> Callback -> Aufblende
        self.options = []
        self.sel = 0
        self.end_info = {}
        self._title_world()
        self._perf = dict(n=0, scene=0.0, hud=0.0, gl=0.0, t0=time.monotonic())
        self._perf_on = os.environ.get("SHADEGUNNER_FPS") == "1"
        if os.environ.get("SHADEGUNNER_AUTOSTART") == "1":
            self._start_run()
            self._set_mode("play")

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(15)
        self.timer.timeout.connect(self._tick)

    # ---------------------------------------------------------------- Aufbau
    def _title_world(self):
        seed = random.randrange(1 << 16)
        self.world = World(seed=seed, zone_index=2)
        self.scene.ensure_zone(2, seed, self.world.length)
        self.title_cam = self.world.length * 0.2
        self.mode = "title"
        self.mode_t = 0.0

    def _start_run(self):
        seed = random.randrange(1 << 16)
        self.run = Run(seed)
        self.world = World(self.run, seed=seed, zone_index=0)
        self.scene.ensure_zone(0, seed, self.world.length)
        self._set_mode("intro")

    def _set_mode(self, m):
        self.mode = m
        self.mode_t = 0.0

    def _transition(self, cb):
        if self._trans is None:
            self._trans = ["out", cb]

    def focusNextPrevChild(self, _next):   # Tab gehört dem Spiel
        return False

    # ---------------------------------------------------------------- Loop
    def _tick(self):
        now = time.monotonic()
        dt = min(0.05, now - self._last)
        self._last = now
        self._dt = dt
        self.mode_t += dt
        self.power = min(1.0, self.power + dt * 1.4)

        self.audio.poll()
        if self.audio._fx and not self.audio._started_loops and not self.audio.muted:
            self.audio.loops(True)

        if self._trans is not None:
            phase, cb = self._trans
            if phase == "out":
                self.fade = min(1.0, self.fade + dt * 3.0)
                if self.fade >= 1.0:
                    cb()
                    self._trans = ["in", None]
            else:
                self.fade = max(0.0, self.fade - dt * 2.5)
                if self.fade <= 0.0:
                    self._trans = None

        w = self.world
        paused = self.help or self.mode in ("pause", "settings")
        if not paused:
            if self.mode == "title":
                self.title_cam += 16.0 * dt
                if self.title_cam > w.length - 200:
                    self.title_cam = 200.0
                w.update(dt, {})
            elif self.mode == "intro":
                w.update(dt, {})
                if self.mode_t > 4.5:
                    self._set_mode("play")
            elif self.mode == "play":
                self._play_tick(dt)
            else:
                w.update(dt, {})
        events = list(w.events)
        w.events.clear()
        self.scene.consume(w, events)
        self.audio.handle_events(events, w)
        if self.scene.sfx:
            self.audio.handle_events(self.scene.sfx, w)
            self.scene.sfx.clear()
        self.audio.update(dt, w, self.mode)
        self._edge.clear()
        self.update()

    # ---------------------------------------------------------------- Maus -> Szene
    def _scene_pos(self, pos):
        """Widget-Pixel -> Szenen-Pixel, inkl. der CRT-Wölbung (gleiche Formel wie CRT_FRAG)."""
        from .render.shaders import CRT_LEVEL
        dpr = self.devicePixelRatioF()
        fw, fh = self.width() * dpr, self.height() * dpr
        cell = min(fw / self.vc, fh / self.vr)
        pw, ph = self.vc * cell, self.vr * cell
        ox, oy = (fw - pw) / 2, (fh - ph) / 2
        nx = (pos.x() * dpr - ox) / pw * 2 - 1
        ny = (pos.y() * dpr - oy) / ph * 2 - 1
        cv = 0.0 if getattr(self, "software", False) else CRT_LEVEL["curve"]
        sx, sy = nx * (1 + cv * ny * ny), ny * (1 + cv * nx * nx)
        if abs(sx) > 1 or abs(sy) > 1:
            return None
        return ((sx * 0.5 + 0.5) * self.vc, (sy * 0.5 + 0.5) * self.vr)

    def _pick(self, sp):
        """Figur unter dem Mauszeiger (vorderste gewinnt), sonst die nächste in 14 px."""
        if sp is None:
            return None
        mx, my = sp
        w = self.world
        best, bd = None, -1.0
        near, nd = None, 14.0
        for a in w.living():
            sc = self.scene.screen.get(a.uid)
            if sc is None:
                continue
            cx, gy, hgt, _m = sc
            if abs(mx - cx) <= max(4.0, hgt * 0.24) and gy - hgt * 1.05 <= my <= gy + 2:
                if a.depth > bd:
                    best, bd = a, a.depth
            else:
                d = ((mx - cx) ** 2 + (my - (gy - hgt * 0.55)) ** 2) ** 0.5
                if d < nd:
                    near, nd = a, d
        return best or near

    def _play_tick(self, dt):
        w = self.world
        ks = self.keys
        mx = (1 if ks & MOVE_RIGHT else 0) - (1 if ks & MOVE_LEFT else 0)
        md = (1 if ks & DEPTH_NEAR else 0) - (1 if ks & DEPTH_FAR else 0)
        self.mouse_t += dt
        if self._mouse_moved and not w.aiming and w.scan_t < 0:
            a = self._pick(self.mouse_scene)
            if a is not None:
                w.set_target(a)
        self._mouse_moved = False
        inp = dict(move=(mx, md), sprint=bool(ks & SPRINT), aim=bool(ks & AIM_KEYS) or self.mouse_aim,
                   scan=self._edge.get("scan", False), cycle=self._edge.get("cycle", 0),
                   jump=self._edge.get("jump", False), cancel=self._edge.get("cancel", False))
        w.update(dt, inp)
        if w.state == "zone_clear" and self.mode_t > 0:
            self._set_mode("cleared")
        elif w.state == "failed":
            self._set_mode("failing")

    def _after_states(self):
        """Verzögerte Übergänge nach Zonenende / Scheitern (im Paint-Takt geprüft)."""
        w = self.world
        if self.mode == "cleared" and self.mode_t > 1.4:
            if w.zone_index + 1 >= len(ZONES):
                self._finish(True)
            else:
                self.options = w.run.offer(random.Random(w.seed + w.zone_index))
                self.sel = 0
                self._set_mode("clear")
        elif self.mode == "failing" and self.mode_t > 2.2:
            self._finish(False)

    def _finish(self, won):
        run = self.world.run
        rank = rank_of(run.score, run.totals["civs"], won)
        self.best, new_best = save.record(max(0, run.score), rank, won)
        self.end_info = dict(rank=rank, new_best=new_best)
        self._set_mode("victory" if won else "over")

    def _choose(self, i):
        if not (0 <= i < len(self.options)):
            return
        key = self.options[i][0]
        self.world.run.apply(key)
        self.audio.play("ui")

        def go():
            nw = self.world.next_world()
            self.world = nw
            self.scene.ensure_zone(nw.zone_index, nw.seed, nw.length)
            self._set_mode("intro")
        self.options = []
        self._transition(go)

    # ---------------------------------------------------------------- Einstellungen
    def _open_settings(self, back):
        self._settings_back = back
        self.settings_sel = 0
        self._set_mode("settings")
        self.audio.play("ui")

    def _settings_adjust(self, d):
        key = self._SETTING_KEYS[self.settings_sel]
        s = self.settings
        if key == "music":
            s["music"] = max(0.0, min(1.0, s["music"] + 0.1 * d))
            self.audio.set_volumes(music=s["music"])
        elif key == "sfx":
            s["sfx"] = max(0.0, min(1.0, s["sfx"] + 0.1 * d))
            self.audio.set_volumes(sfx=s["sfx"])
        elif key == "fullscreen":
            s["fullscreen"] = not s["fullscreen"]
            self._apply_display()
        elif key == "resolution":
            res = config.RESOLUTIONS
            try:
                i = res.index(tuple(s["resolution"]))
            except ValueError:
                i = 0
            i = (i + (1 if d > 0 else -1)) % len(res)
            s["resolution"] = list(res[i])
            self._apply_display()
        elif key == "scanlines":
            s["scanlines"] = not s["scanlines"]
            self._apply_scanlines()
        elif key == "renderer":
            s["renderer"] = "software" if s.get("renderer") != "software" else "auto"
        settings.save(s)
        self.audio.play("target")

    def _apply_scanlines(self):
        if self.renderer is not None:
            self.renderer.scan_on = bool(self.settings.get("scanlines", True))

    def _apply_display(self):
        """Fenster/Vollbild gemäß Einstellungen setzen (Auflösung = Fenstergröße, zentriert)."""
        w, h = int(self.settings["resolution"][0]), int(self.settings["resolution"][1])
        if self.settings.get("fullscreen"):
            self.showFullScreen()
            return
        self.showNormal()
        scr = self.screen().availableGeometry() if self.screen() else None
        if scr is not None:
            w, h = min(w, scr.width()), min(h, scr.height())
        self.resize(w, h)
        if scr is not None:
            self.move(scr.center().x() - w // 2, scr.center().y() - h // 2)

    # ---------------------------------------------------------------- Input
    def keyPressEvent(self, e):
        k = e.key()
        rep = e.isAutoRepeat()
        self.keys.add(k)
        if rep:
            return
        if k == K.Key_F:
            self.settings["fullscreen"] = not self.isFullScreen()
            self._apply_display()
            settings.save(self.settings)
            return
        if k == K.Key_M:
            self.audio.toggle_mute()
            return
        if k == K.Key_H or k == K.Key_F1:
            self.help = not self.help
            self.audio.play("ui")
            return
        if self.help and k in (K.Key_Escape, *CONFIRM):
            self.help = False
            return
        m = self.mode
        if m == "title":
            if k in CONFIRM:
                self.audio.play("ui")
                self._transition(self._start_run)
            elif k == K.Key_S:
                self._open_settings("title")
            elif k == K.Key_Escape:
                self.close()
        elif m == "intro":
            if self.mode_t > 0.6:
                self._set_mode("play")
        elif m == "play":
            if k in SCAN_KEYS:
                self._edge["scan"] = True
            elif k in JUMP_KEYS:
                self._edge["jump"] = True
            elif k in CANCEL_KEYS:
                self._edge["cancel"] = True
            elif k in (K.Key_Q, K.Key_Tab):
                self._edge["cycle"] = -1 if (e.modifiers() & Qt.KeyboardModifier.ShiftModifier) else 1
            elif k in (K.Key_P, K.Key_Escape):
                self._set_mode("pause")
                self.audio.play("ui")
            elif k in (K.Key_Return, K.Key_Enter):
                self.keys.add(K.Key_E)
        elif m == "pause":
            if k in (K.Key_P, K.Key_Escape):
                self._set_mode("play")
            elif k == K.Key_S:
                self._open_settings("pause")
            elif k == K.Key_Q:
                self._transition(self._title_world)
        elif m == "settings":
            if k in (K.Key_Escape, K.Key_S):
                self._set_mode(self._settings_back)
                settings.save(self.settings)
                self.audio.play("ui")
            elif k in (K.Key_Up, K.Key_W):
                self.settings_sel = (self.settings_sel - 1) % len(self._SETTING_KEYS)
                self.audio.play("target")
            elif k == K.Key_Down:
                self.settings_sel = (self.settings_sel + 1) % len(self._SETTING_KEYS)
                self.audio.play("target")
            elif k in MOVE_LEFT:
                self._settings_adjust(-1)
            elif k in MOVE_RIGHT:
                self._settings_adjust(+1)
            elif k in CONFIRM:
                self._settings_adjust(+1)
        elif m == "clear":
            if k in (K.Key_1, K.Key_2, K.Key_3):
                self._choose(k - K.Key_1)
            elif k in MOVE_LEFT:
                self.sel = (self.sel - 1) % max(1, len(self.options))
                self.audio.play("target")
            elif k in MOVE_RIGHT:
                self.sel = (self.sel + 1) % max(1, len(self.options))
                self.audio.play("target")
            elif k in CONFIRM:
                self._choose(self.sel)
        elif m in ("over", "victory"):
            if self.mode_t > 1.0:
                if k == K.Key_R:
                    self._transition(self._start_run)
                elif k in CONFIRM or k == K.Key_Escape:
                    self._transition(self._title_world)
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if e.isAutoRepeat():
            return
        k = e.key()
        self.keys.discard(k)
        if k in (K.Key_Return, K.Key_Enter):
            self.keys.discard(K.Key_E)
        super().keyReleaseEvent(e)

    def mousePressEvent(self, e):
        if self.mode == "play":
            self.mouse_scene = self._scene_pos(e.position())
            self.mouse_t = 0.0
            a = self._pick(self.mouse_scene)
            if a is not None and not self.world.aiming:
                self.world.set_target(a)       # Klick auf eine Figur = genau die
            if e.button() == Qt.MouseButton.LeftButton:
                self.mouse_aim = True
            elif e.button() == Qt.MouseButton.RightButton:
                # Rechte Maustaste: bricht beim Zielen ab, sonst Scan
                if self.world.aiming or self.mouse_aim or (self.keys & AIM_KEYS):
                    self._edge["cancel"] = True
                else:
                    self._edge["scan"] = True
        elif self.mode == "title" and e.button() == Qt.MouseButton.LeftButton:
            self.audio.play("ui")
            self._transition(self._start_run)
        elif self.mode == "intro" and self.mode_t > 0.6:
            self._set_mode("play")
        elif self.mode == "clear" and self.options:
            self._choose(self.sel)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.mouse_aim = False

    def mouseMoveEvent(self, e):
        sp = self._scene_pos(e.position())
        if sp != self.mouse_scene:
            self.mouse_scene = sp
            self.mouse_t = 0.0
            self._mouse_moved = True
        want = Qt.CursorShape.BlankCursor if self.mode == "play" else Qt.CursorShape.ArrowCursor
        if self.cursor().shape() != want:
            self.setCursor(want)

    def wheelEvent(self, e):
        if self.mode == "play":
            self._edge["cycle"] = 1 if e.angleDelta().y() < 0 else -1

    def focusOutEvent(self, e):
        self.keys.clear()
        self.mouse_aim = False
        super().focusOutEvent(e)

    def _hud_ui(self):
        hud_mode = {"cleared": "play", "failing": "play"}.get(self.mode, self.mode)
        return dict(mode=hud_mode, help=self.help, t=self.mode_t, best=self.best,
                    options=self.options, sel=self.sel,
                    mouse=self.mouse_scene if self.mouse_t < 2.5 else None,
                    settings=self.settings, settings_sel=self.settings_sel, **self.end_info)


class GameWidget(_GameMixin, QOpenGLWidget):
    """GPU-Pfad: QOpenGLWidget + CRTRenderer (Bayer + CRT-Kette auf der GPU)."""

    def initializeGL(self):
        try:
            self._gl = GLFuncs(self.context())
            self.renderer = CRTRenderer(self._gl)
        except Exception as exc:  # noqa: BLE001
            print(f"[error] GL-Init fehlgeschlagen: {exc}")
        self.timer.start()

    def paintGL(self):
        if self.renderer is None:
            return
        self._after_states()
        dpr = self.devicePixelRatioF()
        fw = max(1, round(self.width() * dpr))
        fh = max(1, round(self.height() * dpr))
        m = self.mode
        dt = 0.0 if (self.help or m == "pause") else self._dt
        cam = self.title_cam if m == "title" else None
        t0 = time.perf_counter()
        img = self.scene.frame(self.world, dt, show_player=(m != "title"), fade=self.fade,
                               power=self.power, cam_override=cam)
        t1 = time.perf_counter()
        himg = self.hud.render(self.world, self.scene, self._dt, self._hud_ui())
        t2 = time.perf_counter()
        self.renderer.scan_on = bool(self.settings.get("scanlines", True))
        self.renderer.render(self.defaultFramebufferObject(), fw, fh, img, self.vc, self.vr,
                             gamma=0.9, dt=self._dt, dpr=dpr, hud=himg)
        t3 = time.perf_counter()
        if self._perf_on:
            pf = self._perf
            pf["n"] += 1
            pf["scene"] += t1 - t0
            pf["hud"] += t2 - t1
            pf["gl"] += t3 - t2
            el = time.monotonic() - pf["t0"]
            if el > 3.0:
                n = pf["n"]
                print(f"[perf] {n / el:5.1f} fps  szene {pf['scene'] / n * 1000:4.1f} ms  "
                      f"hud {pf['hud'] / n * 1000:4.1f} ms  gl {pf['gl'] / n * 1000:4.1f} ms  "
                      f"modus {self.mode}", flush=True)
                self._perf = dict(n=0, scene=0.0, hud=0.0, gl=0.0, t0=time.monotonic())


class SoftwareGameWidget(_GameMixin, QWidget):
    """CPU-Fallback ohne OpenGL 3.3: Dither + einfaches CRT direkt ins Fenster."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.software = True
        self._ov = None
        self._ov_size = None
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.timer.start()

    def _overlay(self, w, h):
        if self._ov_size != (w, h):
            cell = min(w / self.vc, h / self.vr)
            self._ov = sodither._scan_overlay(w, h, max(2, cell))
            self._ov_size = (w, h)
        return self._ov

    def paintEvent(self, _e):
        self._after_states()
        m = self.mode
        dt = 0.0 if (self.help or m == "pause") else self._dt
        cam = self.title_cam if m == "title" else None
        t0 = time.perf_counter()
        img = self.scene.frame(self.world, dt, show_player=(m != "title"), fade=self.fade,
                               power=self.power, cam_override=cam)
        W, H = max(1, self.width()), max(1, self.height())
        ov = self._overlay(W, H) if self.settings.get("scanlines", True) else None
        base = sodither.compose(img, W, H, ov)
        t1 = time.perf_counter()
        himg = self.hud.render(self.world, self.scene, self._dt, self._hud_ui())
        t2 = time.perf_counter()
        p = QPainter(self)
        p.drawImage(0, 0, base)
        p.drawImage(0, 0, himg.scaled(W, H, Qt.AspectRatioMode.IgnoreAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation))
        p.end()
        if self._perf_on:
            pf = self._perf
            pf["n"] += 1
            pf["scene"] += t1 - t0
            pf["hud"] += t2 - t1
            el = time.monotonic() - pf["t0"]
            if el > 3.0:
                n = pf["n"]
                print(f"[perf] {n / el:5.1f} fps  szene+dither {pf['scene'] / n * 1000:4.1f} ms  "
                      f"hud {pf['hud'] / n * 1000:4.1f} ms  modus {self.mode}", flush=True)
                self._perf = dict(n=0, scene=0.0, hud=0.0, gl=0.0, t0=time.monotonic())
