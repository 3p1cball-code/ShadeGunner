"""HUD und Bildschirm-Overlays in einer eigenen Textur (HUD_SCALE x Dither-Auflösung).

Die HUD-Textur wird im Bayer-Shader *nach* dem Dithern über das Bild gelegt und
läuft dann mit durch die CRT-Kette: Schrift bleibt lesbar (kein Dither-Rauschen),
bekommt aber Wölbung, Scanlines, Maske und Bloom wie alles andere.
"""

import datetime
import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen

from . import assets, config, i18n, persp
from .detection import ORDER, TELLS
from .i18n import tr
from .render import pixfont

S = config.HUD_SCALE
HW, HH = config.RENDER_W * S, config.RENDER_H * S
C = config.NOIR16_OLD   # HUD liegt über dem Dither: alte Farben bleiben
VOID, NIGHT, NAVY, INDIGO, BLUE, STEEL = C[0], C[1], C[2], C[3], C[4], C[5]
CRIMSON, SLATE, ASH, PALE, WHITE = C[6], C[7], C[8], C[9], C[10]
TEAL, CYAN, MAGENTA, AMBER, VIOLET = C[11], C[12], C[13], C[14], C[15]
SLATE = (112, 118, 132)   # HUD-Grau (Palette 7 ist jetzt Natrium-Orange)
RED = (240, 70, 90)
GREEN = (90, 230, 140)

# Augenreflex-Emblem über dem Kopf: 32er Icon, nearest x HUD_SCALE (= Spielpixelraster)
EYE_ICON = 32
EYE_PX = EYE_ICON * S
EYE_LIFE = 2.4             # Sekunden sichtbar


def conf_color(c):
    return CYAN if c >= 0.66 else (AMBER if c >= 0.33 else ASH)


def rank_of(score, civs, won):
    if won and civs == 0 and score >= 2600:
        return "S"
    if score >= 2000 and civs <= 1:
        return "A"
    if score >= 1200:
        return "B"
    if score >= 500:
        return "C"
    return "D"


def wrap(text, width_chars):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + (1 if cur else 0) > width_chars:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w) if cur else w
    if cur:
        lines.append(cur)
    return lines


class HUD:
    def __init__(self):
        self.img = QImage(HW, HH, QImage.Format.Format_ARGB32_Premultiplied)
        self.t = 0.0
        self._msg = ""
        self._msg_t = 0.0
        self._log_len = 0
        self._log_ref = None
        self._dt = 1 / 60
        self._eye_seen = {}        # uid -> HUD-Zeit, als der Augenreflex erkannt wurde
        self._eye_world = None

    # ------------------------------------------------------------------ Grundformen
    def _box(self, p, x, y, w, h, border=STEEL, fill=(6, 8, 14), alpha=215):
        p.fillRect(QRectF(x, y, w, h), QColor(fill[0], fill[1], fill[2], alpha))
        pen = QPen(QColor(*border))
        pen.setWidth(2)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(x + 1, y + 1, w - 2, h - 2))
        # Ecken-Akzente
        for cx, cy, dx, dy in ((x, y, 1, 1), (x + w, y, -1, 1), (x, y + h, 1, -1), (x + w, y + h, -1, -1)):
            p.fillRect(QRectF(cx if dx > 0 else cx - 8, cy if dy > 0 else cy - 3, 8, 3), QColor(*CYAN))

    def _bar(self, p, x, y, w, h, frac, col, back=(30, 34, 50)):
        p.fillRect(QRectF(x, y, w, h), QColor(*back))
        p.fillRect(QRectF(x, y, w * max(0.0, min(1.0, frac)), h), QColor(*col))
        for k in range(1, 10):
            p.fillRect(QRectF(x + w * k / 10, y, 2, h), QColor(6, 8, 14, 160))

    def _t(self, p, x, y, s, col, scale=2, align="left", opacity=1.0):
        return pixfont.draw(p, x, y, tr(s), col, scale, VOID, align, opacity)

    # ------------------------------------------------------------------ Haupt
    def render(self, world, scene, dt, ui=None):
        ui = ui or dict(mode="play")
        self.t += dt
        self._dt = dt
        self.img.fill(0)
        p = QPainter(self.img)
        mode = ui.get("mode", "play")
        if world is not None and mode in ("play", "intro", "pause"):
            self._world_marks(p, world, scene)
            self._panels(p, world, ui)
            if mode == "play":
                self._events(p, world)
                self._reticle(p, ui.get("mouse"), world)
                self._boss(p, world)
        if getattr(getattr(world, "run", None), "cheat", False) and mode in ("play", "pause", "intro"):
            self._t(p, HW - 16, HH - 56, "GIVEALL", MAGENTA, 2, "right")
        if mode == "title":
            self._title(p, ui)
        elif mode == "intro":
            self._intro(p, world, ui)
        elif mode == "pause":
            self._pause(p)
        elif mode == "settings":
            self._settings(p, ui)
        elif mode == "clear":
            self._clear(p, world, ui)
        elif mode in ("over", "victory"):
            self._end(p, world, ui, mode == "victory")
        if ui.get("help"):
            self._help(p)
        p.end()
        return self.img

    # ------------------------------------------------------------------ Welt-Markierungen
    def _scr(self, scene, a, world):
        sc = scene.screen.get(a.uid)
        if sc is None:
            cx = persp.screen_x(a.x, a.depth, world.camera_x)
            gy = persp.ground_y(a.depth)
            h = persp.figure_h(a.depth)
        else:
            cx, gy, h, _m = sc
        return cx * S, gy * S, h * S

    def _world_marks(self, p, world, scene):
        t = self.t
        # Gescannte NPCs behalten einen kleinen Konfidenz-Strich überm Kopf
        for a in world.actors:
            if a.player or not a.alive or a.escaped or a is world.target:
                continue
            if not a.revealed:
                continue
            cx, gy, h = self._scr(scene, a, world)
            if cx < -20 or cx > HW + 20:
                continue
            c = world.confidence_of(a)
            col = conf_color(c)
            y = gy - h * 1.08
            w = max(10, h * 0.28)
            p.fillRect(QRectF(cx - w / 2, y, w, 4), QColor(10, 12, 20, 200))
            p.fillRect(QRectF(cx - w / 2, y, w * c, 4), QColor(*col))
            if a.state == "flee":
                self._t(p, cx, y - 18, "FLÜCHTET", AMBER, 2, "center")
            elif a.state in ("attack", "punch"):
                self._t(p, cx, y - 18, "ANGRIFF!", RED, 2, "center")
        # Ziel-Klammern
        tg = world.target
        if tg is not None and tg.alive:
            cx, gy, h = self._scr(scene, tg, world)
            c = world.confidence_of(tg)
            col = conf_color(c) if tg.revealed else PALE
            if tg.state in ("attack", "punch"):
                col = RED
            bw = h * 0.5 + 10
            top = gy - h * 1.02 - 6
            bot = gy + 6
            pulse = 3 + 2 * math.sin(t * 6)
            if world.aiming:
                pulse = 1 + 6 * max(0.0, 1 - world.aim_t / max(0.05, world.run.mods["aim_min"] + 0.05))
            L = 12
            p.setPen(Qt.PenStyle.NoPen)
            for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                x = cx + sx * (bw / 2 + pulse)
                y = (top - pulse) if sy < 0 else (bot + pulse)
                p.fillRect(QRectF(x - (L if sx > 0 else 0), y - (3 if sy > 0 else 0), L, 3), QColor(*col))
                p.fillRect(QRectF(x - (3 if sx > 0 else 0), y - (L if sy > 0 else 0), 3, L), QColor(*col))
            if tg is not getattr(world, "boss", None):          # ROY trägt sein eigenes Label
                label = f"#{tg.uid:04d}"
                if tg.revealed:
                    label += f"  {int(round(c * 100))}%"
                self._t(p, cx, top - pulse - 22, label, col, 2, "center")
            if tg.state == "flee":
                self._t(p, cx, top - pulse - 40, "FLÜCHTET", AMBER, 2, "center")
            elif tg.state in ("attack", "punch"):
                self._t(p, cx, top - pulse - 40, "ANGRIFF!", RED, 2, "center")
            elif tg.state == "cower":
                self._t(p, cx, top - pulse - 40, "ERGIBT SICH", ASH, 2, "center")
        # Endboss-Label über dem Kopf
        bo = getattr(world, "boss", None)
        if bo is not None and bo.alive:
            bx, bgy, bh = self._scr(scene, bo, world)
            col = AMBER if bo.boss_invuln else WHITE
            if getattr(world, "roy_mercy", False):
                col = PALE
            self._t(p, bx, bgy - bh * 1.12 - 22, "ROY", col, 3, "center")
            if bo.boss_invuln and not getattr(world, "roy_mercy", False):
                self._t(p, bx, bgy - bh * 1.12 - 48, "(REDET)", ASH, 2, "center")
        # Blocker in der Schusslinie
        b = world.blocker if world.aiming else None
        if b is not None and b is not tg:
            cx, gy, h = self._scr(scene, b, world)
            self._t(p, cx, gy - h * 1.05 - 26, "IN DER LINIE!", AMBER, 2, "center")
        # Augenreflex erkannt -> Emblem taucht über dem Kopf auf
        eyes = self._eye_marks(p, world, scene)
        # Schwebende Texte (über einem aktiven Emblem nach oben ausweichen)
        for f in world.floaters:
            k = f["t"] / f["life"]
            cx = persp.screen_x(f["x"], f["depth"], world.camera_x) * S
            gy = persp.ground_y(f["depth"]) * S
            h = persp.figure_h(f["depth"]) * S
            y = gy - h * 1.15 - 40 - 36 * k - 20 * f.get("slot", 0)
            if f["uid"] in eyes:
                y -= EYE_PX + 8
            op = 1.0 if k < 0.7 else max(0.0, 1 - (k - 0.7) / 0.3)
            self._t(p, cx, y, f["text"], f["color"], 2, "center", op)

    def _eye_marks(self, p, world, scene):
        """Spiel-Emblem (Auge im Fadenkreuz) über Personen, bei denen gerade ein
        Augenreflex erkannt wurde - egal auf welchem Weg (Beobachtung, Scan,
        Suchlicht, Stromausfall). Es zeigt den *Tell*, nicht die Wahrheit: auch ein
        Mensch kann einen falschen Augenreflex haben, die Konfidenz bleibt ehrlich.

        Ablauf: einblitzen (CRT-Flackern), stehen, ausflackern. Gibt die uids mit
        sichtbarem Emblem zurück."""
        if self._eye_world is not world:          # neue Zone / neuer Run
            self._eye_world = world
            self._eye_seen = {a.uid: -EYE_LIFE for a in world.actors
                              if "pupils" in a.revealed and a.tells.get("pupils")}
        img = assets.emblem(EYE_ICON, S)
        shown = set()
        for a in world.actors:
            if a.player or not a.alive or a.escaped:
                continue
            if "pupils" not in a.revealed or not a.tells.get("pupils"):
                continue
            t0 = self._eye_seen.setdefault(a.uid, self.t)
            age = self.t - t0
            if age >= EYE_LIFE or img is None:
                continue
            cx, gy, h = self._scr(scene, a, world)
            if cx < -EYE_PX or cx > HW + EYE_PX:
                continue
            shown.add(a.uid)
            # einblitzen / ausflackern wie eine Röhre, die zündet bzw. verlischt
            if age < 0.16 and int(age * 40) % 2:
                continue
            out = age - (EYE_LIFE - 0.45)
            if out > 0 and int(out * 24) % 3 == 0:
                continue
            x = int(cx - EYE_PX / 2)
            y = int(gy - h * 1.02 - 38 - EYE_PX)
            if age < 0.05:                        # Zündblitz: kurz weiß hinterlegt
                p.fillRect(QRectF(x + 6, y + 6, EYE_PX - 12, EYE_PX - 12), QColor(*WHITE))
            p.drawImage(x, y, img)
        return shown

    # ------------------------------------------------------------------ Ereignisse / Warnungen
    def _events(self, p, world):
        t = self.t
        pl = world.player
        # Fahrzeuge, die noch außerhalb des Bildes heranrasen
        for v in getattr(world, "vehicles", ()):
            sx = persp.screen_x(v["x"], v["depth"], world.camera_x)
            ahead = (pl.x - v["x"]) * v["dir"]
            if (sx < 0 and v["dir"] > 0) or (sx > persp.W and v["dir"] < 0):
                if ahead > 0 and ahead < v["speed"] * 3.0:
                    in_lane = abs(pl.depth - v["depth"]) < 0.11
                    col = RED if in_lane else AMBER
                    if in_lane and int(t * 8) % 2:
                        col = WHITE
                    y = persp.ground_y(v["depth"]) * S - 30
                    if v["dir"] > 0:
                        self._t(p, 16, y, "→ FAHRZEUG", col, 2)
                    else:
                        self._t(p, HW - 16, y, "FAHRZEUG ←", col, 2, "right")
        P = getattr(world, "patrol", None)
        if P is not None and P.get("phase") in ("descend", "landed"):
            txt = "SPINNER LANDET - ABSTAND HALTEN" if P["phase"] == "descend" else "POLIZEIKONTROLLE AM BODEN"
            self._t(p, HW // 2, HH - 176, txt, (90, 140, 255) if int(t * 4) % 2 else MAGENTA, 2, "center")
        if getattr(world, "watched", False):
            col = RED if int(t * 3) % 2 else AMBER
            self._t(p, HW // 2, HH - 150, "IM SUCHLICHT - DIE POLIZEI SIEHT ZU", col, 2, "center")
        elif getattr(world, "patrol", None) is not None and world.patrol["on"] > 0.5:
            self._t(p, HW // 2, HH - 150, "SUCHLICHT: AUGENREFLEXE WERDEN SICHTBAR", PALE, 2, "center")
        if getattr(world, "blackout_t", 0) > 0:
            if int(t * 2.5) % 2 == 0:
                self._t(p, HW // 2, 196, "STROMAUSFALL", AMBER, 4, "center")
            self._t(p, HW // 2, 236, "IM DUNKELN LEUCHTEN REPLIKANTENAUGEN", ASH, 2, "center")
        # Nudelstand: Herz auffüllen
        if pl.hp < world.run.max_hp:
            for r in getattr(world, "ramen", ()):
                if r["used"] or abs(pl.x - r["x"]) >= config.RAMEN_RANGE + 8 or pl.depth >= 0.6:
                    continue
                cx = persp.screen_x(r["x"], 0.16, world.camera_x) * S
                cy = persp.ground_y(0.16) * S
                self._t(p, cx, cy - 168, "RAMEN", AMBER, 3, "center")
                k = min(1.0, r["t"] / config.RAMEN_TIME)
                bw = 170
                p.fillRect(QRectF(cx - bw / 2, cy - 132, bw, 9), QColor(10, 12, 20, 210))
                p.fillRect(QRectF(cx - bw / 2, cy - 132, bw * k, 9), QColor(*AMBER))
                if k <= 0.02:
                    self._t(p, cx, cy - 108, "STEHEN BLEIBEN", PALE, 2, "center")
                break

    def _boss(self, p, world):
        b = getattr(world, "boss", None)
        if b is None or not b.alive:
            return
        text = getattr(world, "boss_text", None)
        if getattr(world, "roy_waiting", False):
            return                                    # er steht nur da - noch kein Kampf
        if getattr(world, "roy_mercy", False):
            # Kein Lebensbalken mehr - nur er, der Regen und was er sagt
            if text:
                k = 1.0 - world.boss_speak_t / max(0.1, world.boss_text_dur)
                line = tr(text)
                n = int(len(line) * min(1.0, k * 1.8))
                for i, part in enumerate(wrap(line[:n], 56)):
                    self._t(p, HW // 2, HH - 190 + i * 24, part, PALE, 2, "center")
            return
        w2, h2 = 384, 30
        x2 = (HW - w2) // 2
        y2 = 64
        p.fillRect(QRectF(x2, y2, w2, h2), QColor(6, 8, 14, 225))
        pen = QPen(QColor(*CRIMSON))
        pen.setWidth(2)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(x2, y2, w2, h2)
        p.setPen(Qt.PenStyle.NoPen)
        self._t(p, x2 + 12, y2 + 6, "ROY", WHITE, 2)
        segs, bx, bw = config.ROY_HP, x2 + 80, w2 - 94
        segw = bw / segs
        for i in range(segs):
            on = i < b.hp
            p.fillRect(QRectF(bx + i * segw, y2 + 10, segw - 2, 11),
                       QColor(*(RED if on else (42, 22, 28))))
        if getattr(world, "boss_speak_t", 0.0) > 0.0 and text:
            line = tr(text)
            k = 1.0 - world.boss_speak_t / max(0.1, world.boss_text_dur)
            n = int(len(line) * min(1.0, k * 1.35))
            self._t(p, HW // 2, HH - 172, "ROY: " + line[:n], PALE, 2, "center")

    def _reticle(self, p, mouse, world):
        if mouse is None:
            return
        x, y = mouse[0] * S, mouse[1] * S
        col = RED if world.aiming else PALE
        for dx, dy, w, h in ((-14, -1, 9, 2), (5, -1, 9, 2), (-1, -14, 2, 9), (-1, 5, 2, 9)):
            p.fillRect(QRectF(x + dx, y + dy, w, h), QColor(4, 5, 10, 200))
            p.fillRect(QRectF(x + dx, y + dy - 1, w, h), QColor(*col))

    # ------------------------------------------------------------------ Panels
    def _panels(self, p, world, ui):
        t = self.t
        run = world.run
        z = world.zone
        # oben links
        ox, oy = 34, 24
        self._box(p, ox, oy, 410, 88)
        self._t(p, ox + 14, oy + 12, tr("SEKTOR {}/5", world.zone_index + 1), ASH)
        self._t(p, ox + 146, oy + 12, tr(z["name"]).upper(), WHITE)
        self._t(p, ox + 14, oy + 34, "AUFTRAG", ASH)
        x = ox + 116
        for i in range(max(world.quota, world.stats["reps"])):
            done = i < world.stats["reps"]
            col = (CYAN if i < world.quota else AMBER) if done else SLATE
            pixfont.draw(p, x, oy + 34, "▮" if done else "▯", col, 2, VOID)
            x += 16
        self._t(p, x + 8, oy + 34, f"{world.stats['reps']}/{world.quota}", PALE)
        self._t(p, ox + 300, oy + 34, tr("REST {}", world.reps_remaining()), SLATE)
        self._t(p, ox + 14, oy + 58, "PUNKTE", ASH)
        self._t(p, ox + 116, oy + 58, f"{max(0, run.score):06d}", WHITE)
        if world.combo > 1:
            self._t(p, ox + 236, oy + 58, tr("KETTE X{}", world.combo), AMBER if int(t * 4) % 2 else WHITE, 2)
        # Kopfgeld-Akte
        b = getattr(world, "bounty", None)
        if b is not None and world.bounty_desc:
            done = world.stats.get("bounty")
            gone = not done and (not b.alive or b.escaped)
            line1 = tr("KOPFGELD  {}", b.name)
            line2 = ", ".join(world.bounty_desc)
            status = "KASSIERT ✓" if done else ("ENTKOMMEN ✗" if b.escaped else ("" if not gone else "✗"))
            bw = max(pixfont.text_width(line2, 2), pixfont.text_width(line1 + "  " + status, 2)) + 28
            self._box(p, ox, oy + 96, bw, 58, border=AMBER if not done else TEAL, alpha=190)
            self._t(p, ox + 14, oy + 106, line1, AMBER if not done else TEAL)
            if status:
                self._t(p, ox + bw - 14, oy + 106, status, GREEN if done else RED, 2, "right")
            self._t(p, ox + 14, oy + 128, line2, PALE if not done else SLATE)
        # oben rechts
        rx = HW - 34 - 410
        self._box(p, rx, oy, 410, 136)
        self._t(p, rx + 14, oy + 12, "INTEGRITÄT", ASH)
        hx = rx + 160
        for i in range(run.max_hp):
            full = i < world.player.hp
            pixfont.draw(p, hx + i * 18, oy + 12, "♥" if full else "♡", RED if full else SLATE, 2, VOID)
        self._t(p, rx + 14, oy + 34, "SCAN", ASH)
        cx_ = rx + 160
        full = int(world.scan_charges)
        for i in range(world.scan_max):
            if i < full:
                pixfont.draw(p, cx_ + i * 16, oy + 34, "▮", CYAN, 2, VOID)
            else:
                pixfont.draw(p, cx_ + i * 16, oy + 34, "▯", SLATE, 2, VOID)
                if i == full:
                    frac = world.scan_charges - full
                    p.fillRect(QRectF(cx_ + i * 16 + 2, oy + 34 + 12 - 10 * frac, 6, 10 * frac), QColor(*TEAL))
        self._t(p, rx + 14, oy + 58, "VERDACHT", ASH)
        sus = world.suspicion
        col = AMBER if sus < 0.66 else (RED if int(t * 4) % 2 == 0 else CRIMSON)
        self._bar(p, rx + 160, oy + 60, 230, 10, sus, col)
        # Ruf (V): bereit / lädt
        cd = getattr(world, "shout_cd", 0.0)
        full = config.SHOUT_CD * world.run.mods.get("shout_cd", 1.0)
        self._t(p, rx + 14, oy + 82, "RUF  V", ASH)
        if cd <= 0:
            self._t(p, rx + 160, oy + 82, "BEREIT", CYAN)
            self._t(p, rx + 390, oy + 82, "HALTEN", SLATE, 2, "right")
        else:
            self._bar(p, rx + 160, oy + 84, 230, 10, 1.0 - cd / max(0.1, full), TEAL)
        un = getattr(world, "unrest", 0.0)
        self._t(p, rx + 14, oy + 106, "UNRUHE", ASH)
        self._bar(p, rx + 160, oy + 108, 230, 10, un, AMBER if un < 0.6 else RED)
        # Fortschritt (Mitte oben)
        px0, pw = HW // 2 - 160, 320
        py = oy + 22
        p.fillRect(QRectF(px0, py, pw, 2), QColor(*SLATE))
        f = max(0.0, min(1.0, world.player.x / world.length))
        open_ = world.exit_open()
        p.fillRect(QRectF(px0, py, pw * f, 2), QColor(*CYAN))
        pixfont.draw(p, px0 + pw * f - 4, py - 14, "▼", CYAN, 2, VOID)
        ecol = GREEN if open_ else RED
        p.fillRect(QRectF(px0 + pw - 2, py - 6, 4, 14), QColor(*ecol))
        self._t(p, HW // 2, py + 12, "AUSGANG OFFEN" if open_ else "AUSGANG GESPERRT", ecol, 2, "center")
        # Ziel-Panel
        self._target_panel(p, world)
        # Status / Meldungen
        if world.log is not self._log_ref or len(world.log) != self._log_len:
            if world.log and len(world.log) != self._log_len:
                self._msg = world.log[-1]
                self._msg_t = 3.0
            self._log_ref = world.log
            self._log_len = len(world.log)
        self._msg_t = max(0.0, self._msg_t - self._dt)
        if self._msg_t > 0 and self._msg:
            col = RED if ("MENSCH" in self._msg or "entkommen" in self._msg) else PALE
            self._t(p, HW // 2, HH - 120, self._msg.upper(), col, 2, "center", min(1.0, self._msg_t))
        hold = getattr(world, "shout_hold", -1.0)
        if hold >= config.SHOUT_TAP:
            if world.shout_cd > 0:
                self._t(p, HW // 2, HH - 92, "RUF LÄDT NOCH - LOSLASSEN BRICHT AB", SLATE, 2, "center")
            else:
                k = min(1.0, (hold - config.SHOUT_TAP) / config.SHOUT_CHARGE)
                self._t(p, HW // 2, HH - 92, tr("LOSLASSEN: ALLE RUNTER!   RADIUS {:3d}%", int(k * 100)), AMBER, 2, "center")
        elif hold >= 0.0:
            self._t(p, HW // 2, HH - 92, "TIPPEN = ZIEL ANSPRECHEN   HALTEN = MENGE", SLATE, 2, "center")
        if world.aiming:
            b, tg = world.blocker, world.target
            hint = "      C / RMT = ABBRECHEN"
            if b is not None and b is not tg:
                self._t(p, HW // 2, HH - 92, "SCHUSSLINIE BLOCKIERT" + hint, AMBER, 2, "center")
            elif tg is not None:
                ready = world.aim_t >= world.run.mods["aim_min"]
                self._t(p, HW // 2, HH - 92, ("ZIEL ERFASST - LOSLASSEN = FEUER" if ready else "ZIELEN...") + hint,
                        RED if ready else ASH, 2, "center")
            else:
                self._t(p, HW // 2, HH - 92, "KEIN ZIEL - SCHUSS GERADEAUS" + hint, ASH, 2, "center")
        self._t(p, HW - 48, HH - 44, "H HILFE  P PAUSE", SLATE, 2, "right")

    def _target_panel(self, p, world):
        tg = world.target
        x, y, w, h = 34, HH - 188, 306, 166
        if tg is None or not tg.alive:
            self._box(p, x, y + 120, w, 42, border=INDIGO, alpha=170)
            self._t(p, x + 12, y + 134, "KEIN ZIEL  (MAUS / Q / TAB)", SLATE)
            return
        c = world.confidence_of(tg)
        self._box(p, x, y, w, h, border=conf_color(c) if tg.revealed else STEEL)
        subj = tr("SUBJEKT #{:04d}", tg.uid)
        self._t(p, x + 12, y + 10, subj, WHITE)
        sx = x + 12 + pixfont.text_width(subj, 2) + 16
        if world.scan_t >= 0 and world.scan_target is tg:
            k = world.scan_t / max(0.01, config.SCAN_TIME * world.run.mods["scan_time"])
            self._t(p, sx, y + 10, tr("SCAN {:3d}%", int(k * 100)), CYAN)
        elif tg.scanned:
            self._t(p, sx, y + 10, "GESCANNT", TEAL)
        else:
            self._t(p, sx, y + 10, "BEOBACHTE", SLATE if int(self.t * 2) % 2 else ASH)
        yy = y + 30
        for name in ORDER:
            lbl = tr(TELLS[name][3])
            strong = TELLS[name][2]
            self._t(p, x + 12, yy, lbl, ASH)
            if name in tg.revealed:
                present = tg.tells.get(name)
                self._t(p, x + 104, yy, "AUFFÄLLIG" if present else "UNAUFFÄLLIG", AMBER if present else SLATE)
            else:
                hint = "SCAN" if strong else "BEOBACHTEN"
                if name == "serial":
                    hint = "NAHSCAN"
                self._t(p, x + 104, yy, f"? {hint}", INDIGO)
            yy += 17
        self._t(p, x + 12, yy + 4, "P(REP)", ASH)
        self._bar(p, x + 86, yy + 6, 150, 9, c, conf_color(c))
        self._t(p, x + 242, yy + 4, f"{int(round(c * 100)):3d}%", conf_color(c))
        ob = tg.exposure / config.OBSERVE_SECONDS
        if ob > 0.02 and len([n for n in tg.revealed if not TELLS[n][2]]) < 2:
            p.fillRect(QRectF(x + 12, y + h - 8, (w - 24) * min(1.0, ob), 3), QColor(*TEAL))

    # ------------------------------------------------------------------ Overlays
    def _dim(self, p, a=170):
        p.fillRect(0, 0, HW, HH, QColor(4, 5, 10, a))

    def _kana(self, p, rng, x, y, n, col, sc, t):
        """Pseudo-Kana-Reihe als Blade-Runner-Ornament (prozedural, kein Font nötig)."""
        from .render.city import _glyph
        adv = 8 * sc
        for i in range(n):
            g = _glyph(rng)
            on = int(t * 6 + i * 3) % 31 != 0
            c = col if on else (col[0] // 2, col[1] // 2, col[2] // 2)
            for (gx, gy) in g:
                p.fillRect(QRectF(x + i * adv + gx * sc, y + gy * sc, sc, sc), QColor(*c))

    def _title(self, p, ui):
        t = self.t
        import random as _r
        self._dim(p, 158)
        rng = _r.Random(7)
        # --- Pseudo-Kana streifen (Neon) ---
        self._kana(p, _r.Random(3), 470, 96, 20, VIOLET, 2, t)
        self._kana(p, _r.Random(9), 470, 600, 20, MAGENTA, 2, t + 1.3)

        # --- Titel mit RGB-Split, Doppelkontur und Glitch ---
        title = "SHADEGUNNER"
        sc = 9
        tw = pixfont.text_width(title, sc)
        x0 = (HW - tw) // 2
        y0 = 150
        glitch = (int(t * 9) % 47) == 0
        ox = 4 if glitch else 0
        pixfont.draw(p, x0 + 8 + ox, y0 + 7, title, MAGENTA, sc, None)      # Schatten
        pixfont.draw(p, x0 - 6 - ox, y0 - 5, title, (26, 52, 110), sc, None)  # Kante
        pixfont.draw(p, x0, y0, title, CYAN, sc, None)                        # Kern
        if not glitch:
            for i, ch in enumerate(title):
                if int(t * 3 + i) % 13 == 0:
                    pixfont.draw(p, x0 + i * pixfont.ADV * sc, y0, ch, WHITE, sc, None)
        # Neon-Leiste darunter
        uy = y0 + 7 * sc + 8
        p.fillRect(QRectF(x0 - 12, uy, tw + 24, 3), QColor(*CYAN))
        p.fillRect(QRectF(x0 - 4, uy + 4, tw + 8, 1), QColor(*MAGENTA))

        # --- Jahreszahl 2027 ---
        yr = str(datetime.date.today().year + 1)          # Jahreszahl im Titel: aktuelles Jahr + 1
        year = " ".join(yr)
        ysc = 7
        yw = pixfont.text_width(year, ysc)
        yx = (HW - yw) // 2
        yy = uy + 28
        pixfont.draw(p, yx + 6, yy + 5, year, MAGENTA, ysc, None)
        pixfont.draw(p, yx, yy, year, AMBER, ysc, None)
        if int(t * 3) % 17 == 0:
            pixfont.draw(p, yx, yy, year, (255, 230, 180), ysc, None)

        self._t(p, HW // 2, yy + 7 * ysc + 12, "BLADE RUNNER UNIT  ·  REPLICANT DETECTION  ·  LAPD",
                ASH, 2, "center")
        self._t(p, HW // 2, yy + 7 * ysc + 38, f"LOS ANGELES   ·   NOVEMBER {yr}", SLATE, 2, "center")

        if int(t * 1.6) % 2 == 0:
            self._t(p, HW // 2, 470, "ENTER  NEUER EINSATZ", WHITE, 3, "center")
        self._t(p, HW // 2, 514, "H  STEUERUNG      S  EINSTELLUNGEN      ESC  ENDE", ASH, 2, "center")
        best = ui.get("best")
        if best:
            self._t(p, HW // 2, 554, tr("BESTWERT {:06d}  RANG {}  EINSÄTZE {}",
                                        best.get("best", 0), best.get("rank", "-"), best.get("runs", 0)),
                    TEAL, 2, "center")
        self._t(p, HW // 2, HH - 54, "REPLIKANTEN SIND WIE JEDE ANDERE MASCHINE.", SLATE, 2, "center")

    def _intro(self, p, world, ui):
        k = ui.get("t", 0.0)
        z = world.zone
        w, h = 820, 280
        x, y = (HW - w) // 2, 190
        self._box(p, x, y, w, h, border=CYAN, alpha=225)
        self._t(p, HW // 2, y + 20, tr("SEKTOR {} / 5", world.zone_index + 1), ASH, 2, "center")
        name = tr(z["name"]).upper()
        n = int(len(name) * min(1.0, k * 2.5))
        self._t(p, HW // 2, y + 46, name[:n], WHITE, 6, "center")
        line = tr("AUFTRAG: {} VON {} REPLIKANTEN DEAKTIVIEREN", world.quota, world.replicants_total)
        n2 = int(len(line) * min(1.0, max(0.0, k - 0.3) * 1.6))
        self._t(p, HW // 2, y + 112, line[:n2], CYAN, 2, "center")
        if k > 0.9:
            tarn = int(round(z["camo"] * 4))
            agg = int(round(z["aggression"] * 4))
            self._t(p, x + 120, y + 146, "TARNUNG", ASH)
            self._t(p, x + 240, y + 146, "▮" * tarn + "▯" * (4 - tarn), AMBER)
            self._t(p, x + 420, y + 146, "AGGRESSION", ASH)
            self._t(p, x + 580, y + 146, "▮" * agg + "▯" * (4 - agg), RED)
            self._t(p, x + 120, y + 170, tr("PASSANTEN CA. {}", len(world.actors) - 1), ASH)
            self._t(p, x + 420, y + 170, tr("QUOTE {}%", int(world.prior * 100)), ASH)
            if getattr(world, "bounty", None) is not None and world.bounty_desc:
                b = world.bounty
                btxt = tr("KOPFGELD +{}: {}", config.POINTS_BOUNTY, b.name)
                if b.hp > 1:
                    btxt += tr("  (ZÄH: 2 TREFFER)")
                self._t(p, HW // 2, y + 200, btxt, AMBER, 2, "center")
                self._t(p, HW // 2, y + 222, ", ".join(world.bounty_desc), PALE, 2, "center")
        if k > 1.3 and int(self.t * 2) % 2 == 0:
            self._t(p, HW // 2, y + h - 26, "BELIEBIGE TASTE", SLATE, 2, "center")

    # Zeilen des Einstellungsmenüs: (Label, Wert-Funktion, Art)
    SETTING_ROWS = [
        ("music", "MUSIK", lambda s: f"{int(round(s['music'] * 100)):3d}%", "range"),
        ("sfx", "EFFEKTE", lambda s: f"{int(round(s['sfx'] * 100)):3d}%", "range"),
        ("quality", "QUALITÄT", lambda s: {"hoch": "HOCH", "mittel": "MITTEL", "niedrig": "NIEDRIG"}.get(
            s.get("quality", "hoch"), "HOCH"), "cycle"),
        ("reflections", "REFLEXIONEN", lambda s: "AN" if s.get("reflections", True) else "AUS", "toggle"),
        ("rain", "REGEN", lambda s: {"viel": "VIEL", "wenig": "WENIG", "aus": "AUS"}.get(s.get("rain", "viel"), "VIEL"),
         "cycle"),
        ("fog", "NEBEL", lambda s: "AN" if s.get("fog", True) else "AUS", "toggle"),
        ("fx", "FX", lambda s: "AN" if s.get("fx", True) else "AUS", "toggle"),
        ("fullscreen", "VOLLBILD", lambda s: "AN" if s["fullscreen"] else "AUS", "toggle"),
        ("resolution", "AUFLÖSUNG", lambda s: f"{s['resolution'][0]} x {s['resolution'][1]}", "cycle"),
        ("scanlines", "SCANLINES", lambda s: "AN" if s["scanlines"] else "AUS", "toggle"),
        ("lang", "SPRACHE", lambda s: i18n.lang_name(s.get("lang", "de")), "cycle"),
        ("difficulty", "SCHWIERIGKEIT", lambda s: config.DIFFICULTY.get(s.get("difficulty", "normal"),
                                                                        config.DIFFICULTY["normal"])["label"], "cycle"),
        ("renderer", "RENDERER", lambda s: "GPU" if s.get("renderer") != "software" else "SOFTWARE", "toggle"),
    ]

    # Geometrie der Einstellungsliste (scrollt, wenn nicht alle Zeilen passen - wie im Port)
    SET_W, SET_ROWH, SET_GAP, SET_Y, SET_MAXROWS = 720, 42, 10, 176, 8

    def _settings(self, p, ui):
        self._dim(p, 200)
        s = ui.get("settings", {})
        sel = ui.get("settings_sel", 0)
        self._t(p, HW // 2, 120, "EINSTELLUNGEN", WHITE, 5, "center")
        w, rowh, gap, maxrows = self.SET_W, self.SET_ROWH, self.SET_GAP, self.SET_MAXROWS
        x = (HW - w) // 2
        y = self.SET_Y
        n = len(self.SETTING_ROWS)
        first = max(0, min(sel - maxrows // 2, max(0, n - maxrows)))
        last = min(first + maxrows, n)
        if first > 0:
            self._t(p, HW // 2, y - 22, "▲ MEHR", SLATE, 2, "center")
        for i in range(first, last):
            key, label, val, kind = self.SETTING_ROWS[i]
            on = i == sel
            y0 = y + (i - first) * (rowh + gap)
            self._box(p, x, y0, w, rowh, border=CYAN if on else INDIGO, alpha=225)
            self._t(p, x + 24, y0 + 13, label, WHITE if on else ASH, 3)
            self._t(p, x + w - 24, y0 + 13, val(s), CYAN if on else PALE, 3, "right")
            if kind == "range" and on:
                self._t(p, x + w // 2 + 60, y0 + 15, "←  →", AMBER, 2, "center")
        if first + maxrows < n:
            self._t(p, HW // 2, y + maxrows * (rowh + gap) - 6, "▼ MEHR", SLATE, 2, "center")
        note = y + maxrows * (rowh + gap) + 16
        if s.get("renderer") == "software":
            self._t(p, HW // 2, note, "RENDERER WECHSELT MIT DEM NÄCHSTEN START", SLATE, 2, "center")
            note += 22
        key = self.SETTING_ROWS[sel][0]
        if key == "difficulty":
            self._t(p, HW // 2, note, "MEHR MENSCHEN JE VIERTEL - GILT AB DEM NÄCHSTEN EINSATZ", SLATE, 2, "center")
            note += 22
        elif key in ("quality", "reflections", "rain", "fog", "fx"):
            self._t(p, HW // 2, note, "WENIGER EFFEKTE = MEHR BILDER PRO SEKUNDE", SLATE, 2, "center")
            note += 22
        self._t(p, HW // 2, max(HH - 70, note + 2), "▲▼  WÄHLEN      ← →  ÄNDERN      ESC / S  ZURÜCK", ASH, 2, "center")

    def _pause(self, p):
        self._dim(p, 150)
        self._t(p, HW // 2, 230, "PAUSE", WHITE, 6, "center")
        self._t(p, HW // 2, 330, "P / ESC  WEITER      S  EINSTELLUNGEN      H  HILFE      Q  ZUM TITEL", ASH, 2, "center")

    def _clear(self, p, world, ui):
        self._dim(p, 175)
        st = world.stats
        missed = getattr(world, "mission_failed", False)
        head = "AUFTRAG VERFEHLT" if missed else "SEKTOR GESÄUBERT"
        self._t(p, HW // 2, 70, head, RED if missed else GREEN, 5, "center")
        rows = [("REPLIKANTEN DEAKTIVIERT", f"{st['reps']}/{world.replicants_total}", CYAN),
                ("MENSCHEN GETÖTET", str(st["civs"]), RED if st["civs"] else ASH),
                ("ENTKOMMEN", str(st["escaped"]), AMBER if st["escaped"] else ASH),
                ("SCANS / SCHÜSSE", f"{st['scans']} / {st['shots']}", ASH),
                ("ZEIT", f"{int(st['time']) // 60}:{int(st['time']) % 60:02d}", ASH),
                ("ORIGAMI", tr(world.origami[0]["name"]) if (world.origami and st.get("origami"))
                 else "NICHT GEFUNDEN", PALE if st.get("origami") else SLATE),
                ("PUNKTE (SEKTOR)", f"{st['score']:+d}", WHITE)]
        y = 150
        for lbl, val, col in rows:
            self._t(p, HW // 2 - 300, y, lbl, ASH)
            self._t(p, HW // 2 + 300, y, val, col, 2, "right")
            y += 26
        opts = ui.get("options") or []
        if not opts:
            if int(self.t * 2) % 2 == 0:
                self._t(p, HW // 2, 560, "ENTER  WEITER", WHITE, 3, "center")
            return
        self._t(p, HW // 2, 330, "AUSRÜSTUNG WÄHLEN", PALE, 3, "center")
        sel = ui.get("sel", 0)
        cw, ch = 360, 190
        gap = 30
        x0 = (HW - (3 * cw + 2 * gap)) // 2
        for i, (key, title, desc) in enumerate(opts):
            x = x0 + i * (cw + gap)
            y = 380
            on = i == sel
            lift = -8 if on else 0
            self._box(p, x, y + lift, cw, ch, border=CYAN if on else INDIGO, alpha=235)
            self._t(p, x + 16, y + lift + 16, str(i + 1), AMBER if on else SLATE, 3)
            self._t(p, x + 52, y + lift + 22, tr(title), WHITE if on else ASH, 2)
            yy = y + lift + 70
            for line in wrap(tr(desc), 26):
                self._t(p, x + 16, yy, line, PALE if on else SLATE, 2)
                yy += 22
        self._t(p, HW // 2, HH - 50, "1-3 / PFEILE + ENTER", SLATE, 2, "center")

    def _end(self, p, world, ui, won):
        self._dim(p, 185)
        run = world.run
        if won and getattr(run, "roy_spared", False):
            self._t(p, HW // 2, 90, "ROY HAT DICH VERSCHONT", PALE, 5, "center")
            self._t(p, HW // 2, 160, "SCHADE, DASS ER NICHT LEBEN WIRD.", ASH, 2, "center")
            self._t(p, HW // 2, 184, "ABER WER LEBT SCHON?", ASH, 2, "center")
        elif won:
            self._t(p, HW // 2, 90, "TYRELL HQ ERREICHT", GREEN, 5, "center")
            self._t(p, HW // 2, 160, "SIE HABEN GANZE ARBEIT GELEISTET, SIR.", ASH, 2, "center")
        else:
            self._t(p, HW // 2, 90, "EINSATZ BEENDET", RED, 5, "center")
            reason = ("VERDACHT ZU HOCH - DIENSTMARKE ENTZOGEN" if world.fail_reason == "suspicion"
                      else "INTEGRITÄT VERLOREN")
            self._t(p, HW // 2, 170, reason, AMBER, 2, "center")
        tot = run.totals
        rank = ui.get("rank") or rank_of(run.score, tot["civs"], won)
        rows = [("SEKTOR ERREICHT", f"{world.zone_index + 1}/5"),
                ("REPLIKANTEN", str(tot["reps"])), ("MENSCHEN", str(tot["civs"])),
                ("ENTKOMMEN", str(tot["escaped"])), ("UPGRADES", str(len(run.upgrades))),
                ("ORIGAMI", f"{len(getattr(run, 'origami', []))}/5"),
                ("PUNKTE", f"{max(0, run.score):06d}")]
        y = 240
        for lbl, val in rows:
            self._t(p, HW // 2 - 260, y, lbl, ASH)
            self._t(p, HW // 2 + 260, y, val, WHITE, 2, "right")
            y += 28
        self._t(p, HW // 2, y + 20, tr("RANG {}", rank), CYAN if rank in "SA" else AMBER, 6, "center")
        if ui.get("new_best"):
            self._t(p, HW // 2, y + 90, "NEUER BESTWERT!", AMBER if int(self.t * 3) % 2 else WHITE, 3, "center")
        if int(self.t * 1.6) % 2 == 0:
            self._t(p, HW // 2, HH - 60, "ENTER  ZUM TITEL     R  SOFORT NEU", WHITE, 2, "center")

    def _help(self, p):
        lines = [
            ("STEUERUNG", WHITE),
            ("A D / PFEILE        GEHEN            SHIFT  SPRINTEN", ASH),
            ("W S / PFEILE        TIEFE (VOR / ZURÜCK IN DER STRASSE)", ASH),
            ("SPACE               SPRINGEN (ÜBER HINDERNISSE, SCHLÄGEN AUSWEICHEN)", ASH),
            ("V / MITTLERE MT     TIPPEN: ZIEL ANSPRECHEN   HALTEN+LOSLASSEN: \"ALLE RUNTER!\"", ASH),
            ("MAUS ZEIGEN/KLICKEN ZIEL WÄHLEN    Q / TAB / RAD  ZIEL WECHSELN", ASH),
            ("R / RECHTE MT       GEWÄHLTES ZIEL SCANNEN (1 LADUNG)", ASH),
            ("E / LINKE MT        HALTEN = ZIELEN, LOSLASSEN = SCHIESSEN", ASH),
            ("C / RECHTE MT       SCHUSS ABBRECHEN (WAFFE SENKEN, KEIN SCHUSS)", ASH),
            ("P / ESC  PAUSE    F  VOLLBILD    M  TON    H  HILFE", ASH),
            ("", ASH),
            ("REGELN", WHITE),
            ("REPLIKANTEN SEHEN AUS WIE MENSCHEN. KEIN TELL BEWEIST ETWAS.", PALE),
            ("BEOBACHTEN (ZIEL HALTEN) DECKT GANG UND DETAIL AUF.", PALE),
            ("AUGENREFLEX IM BLICK = PUPILLEN-TELL. SCAN ZEIGT DIE STARKEN TELLS,", PALE),
            ("DIE SERIENNUMMER NUR AUS DER NÄHE. P(REP) IST EHRLICH KALIBRIERT.", PALE),
            ("WER FLIEHT ODER ANGREIFT, VERRÄT SICH - MENSCHEN GREIFEN NIE AN.", PALE),
            ("PASSANTEN IN DER SCHUSSLINIE FANGEN DIE KUGEL. TIEFE WECHSELN!", PALE),
            ("MENSCH GETÖTET = VERDACHT. BEI 100% IST DER EINSATZ VORBEI.", PALE),
            ("AUFTRAG ERFÜLLEN -> AUSGANG AM STRASSENENDE ÖFFNET SICH.", PALE),
            ("KOPFGELD: DER BESCHRIEBENE NEXUS-6 BRINGT EXTRA - VORSICHT, DOPPELGÄNGER.", PALE),
            ("FAHRZEUGE AUF DEN SPUREN AUSWEICHEN. SUCHLICHT UND STROMAUSFALL", PALE),
            ("MACHEN AUGENREFLEXE SICHTBAR - ABER IM SUCHLICHT SIEHT DIE POLIZEI ZU.", PALE),
            ("RUF: WER REGLOS STEHEN BLEIBT, ZEIGT DEN REIZ-TELL. GEDUCKTE: DIE KUGEL GEHT DRÜBER.", PALE),
            ("JEDER RUF MACHT DIE STRASSE UNRUHIGER: MEHR LEUTE RENNEN, REPLIKANTEN WERDEN NERVÖS.", PALE),
            ("LANDET EIN SPINNER: ABWIND SCHIEBT ALLE WEG, DANN KONTROLLE VOM BODEN AUS.", PALE),
            ("NUDELBAR: KURZ AN DER THEKE STEHEN = +1 HERZ.  GAFFS ORIGAMI: SCANNER VOLL.", PALE),
        ]
        lh = 23
        w, h = 1160, len(lines) * lh + 40
        x, y = (HW - w) // 2, (HH - h) // 2
        self._box(p, x, y, w, h, border=CYAN, alpha=240)
        yy = y + 20
        for s, col in lines:
            self._t(p, x + 30, yy, s, col, 2)
            yy += lh
