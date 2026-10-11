#!/usr/bin/env python3
"""Erzeugt Spiel-Icon, Logo und GitHub-Social-Preview - reproduzierbar aus dem Code.

Alles läuft durch die Bildkette des Spiels: Vektor-Motiv -> Grading + Bayer-Dither
gegen `noir16` (render/sodither.py) -> Nearest-Upscale. Logo und Social Preview
gehen zusätzlich durch den echten GPU-Pfad (Szene + Dither + CRT, wie tools/glshot.py),
der Hintergrund ist eine echte Spielszene.

Motiv: ein Auge im Scanner-Fadenkreuz. Die Pupille trägt den bernsteinfarbenen
Augenreflex - im Spiel der Tell, an dem man Replikanten erkennt.

Aufruf (aus dem Repo-Wurzelverzeichnis):
    python3 tools/make_brand.py            # alles
    python3 tools/make_brand.py icons      # nur Icons (CPU, kein OpenGL nötig)
    python3 tools/make_brand.py logo       # Logo + Social Preview (braucht OpenGL 3.3)
Unter KDE/Wayland für den GL-Teil:  QT_QPA_PLATFORM=xcb python3 tools/make_brand.py

Ausgabe:
    assets/icons/shadegunner-<n>.png   n = 16 24 32 48 64 128 256 512
    assets/icons/shadegunner.ico       Windows (16..128 als DIB, 256 als PNG)
    assets/logo.png                    README-Banner 1280x400 (mit Szene + CRT)
    assets/logo-transparent.png        freistehend, transparent 1280x360 (Steam, Presse)
    assets/social-preview.jpg          GitHub Social Preview 1280x640 (< 1 MB)
"""

import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402  (nur das Werkzeug braucht numpy, das Spiel nicht)
from PyQt6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PyQt6.QtGui import (QColor, QGuiApplication, QImage, QLinearGradient,  # noqa: E402
                         QPainter, QPainterPath, QPen, QRadialGradient)

from shadegunner import config  # noqa: E402
from shadegunner.render import sodither  # noqa: E402

OUT_ICONS = os.path.join(ROOT, "assets", "icons")
OUT_ASSETS = os.path.join(ROOT, "assets")
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)

P = config.NOIR16
VOID, NIGHT, NAVY, INDIGO, BLUE, STEEL = P[0], P[1], P[2], P[3], P[4], P[5]
CRIMSON, SODIUM, ASH, PALE, WHITE = P[6], P[7], P[8], P[9], P[10]
TEAL, CYAN, MAGENTA, AMBER, VIOLET = P[11], P[12], P[13], P[14], P[15]


def _c(rgb, a=255):
    return QColor(rgb[0], rgb[1], rgb[2], a)


# ----------------------------------------------------------------------------------
# Motiv
# ----------------------------------------------------------------------------------

def paint_emblem(p, x, y, s, detail=2, plate=True, layer="all"):
    """Emblem in das Quadrat (x, y, s) zeichnen.

    detail: 0 = nur Auge (16 px), 1 = + Fadenkreuz (24-48 px), 2 = + Regen/Scanlinie.
    plate:  dunkle Bildschirmplatte als Hintergrund (Icon) oder freistehend (Logo).
    layer:  "fill" = Flächen und Verläufe (werden gedithert), "line" = Konturen in
            exakten Palettenfarben ohne Kantenglättung (kommen nach dem Dither drauf,
            damit sie nicht zerkrümeln), "all" = beides.
    """
    fill = layer in ("all", "fill")
    line = layer in ("all", "line")
    def X(u):
        return x + u * s

    def Y(v):
        return y + v * s

    def W(u):
        return u * s

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, layer != "line")

    # --- Platte: dunkler Röhrenbildschirm mit Neon-Rand -----------------------------
    r = W(0.2)
    plate_path = QPainterPath()
    plate_path.addRoundedRect(QRectF(X(0), Y(0), W(1), W(1)), r, r)
    if plate and fill:
        g = QLinearGradient(0, Y(0), 0, Y(1))
        g.setColorAt(0.0, _c(NAVY))
        g.setColorAt(0.55, _c(NIGHT))
        g.setColorAt(1.0, _c(VOID))
        p.fillPath(plate_path, g)
        # Lichthof hinter dem Auge (Neon im Regen)
        halo = QRadialGradient(X(0.5), Y(0.5), W(0.5))
        halo.setColorAt(0.0, _c(VIOLET, 150))
        halo.setColorAt(0.55, _c(INDIGO, 70))
        halo.setColorAt(1.0, _c(NIGHT, 0))
        p.fillPath(plate_path, halo)
        if detail >= 2:
            # Regen: feine Schrägen (fest gesetzt, damit das Icon reproduzierbar ist)
            p.setClipPath(plate_path)
            pen = QPen(_c(STEEL, 120))
            pen.setWidthF(max(1.0, W(0.012)))
            p.setPen(pen)
            for (u, v, ln) in ((0.10, 0.05, 0.16), (0.30, 0.70, 0.14), (0.62, 0.02, 0.12),
                               (0.84, 0.60, 0.18), (0.18, 0.84, 0.10), (0.92, 0.18, 0.12),
                               (0.48, 0.86, 0.12), (0.74, 0.30, 0.08), (0.04, 0.40, 0.12)):
                p.drawLine(QPointF(X(u), Y(v)), QPointF(X(u - ln * 0.25), Y(v + ln)))
            p.setClipping(False)
    if plate and line and detail >= 1:
        pen = QPen(_c(TEAL))
        pen.setWidthF(max(1.0, round(W(0.025))))
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        inset = pen.widthF() / 2
        p.drawRoundedRect(QRectF(X(0) + inset, Y(0) + inset, W(1) - 2 * inset, W(1) - 2 * inset),
                          r - inset, r - inset)

    # --- Fadenkreuz: Scanner-Ecken + Striche ------------------------------------------
    if line and detail >= 1:
        pen = QPen(_c(CYAN))
        pen.setWidthF(max(1.0, round(W(0.045))))
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        p.setPen(pen)
        a, b, k = 0.14, 0.86, 0.15          # Rahmen und Schenkellänge
        for (cx, cy, dx, dy) in ((a, a, 1, 1), (b, a, -1, 1), (a, b, 1, -1), (b, b, -1, -1)):
            path = QPainterPath(QPointF(X(cx), Y(cy + dy * k)))
            path.lineTo(X(cx), Y(cy))
            path.lineTo(X(cx + dx * k), Y(cy))
            p.drawPath(path)
        pen.setWidthF(max(1.0, round(W(0.03))))
        p.setPen(pen)
        for (u0, v0, u1, v1) in ((0.5, 0.06, 0.5, 0.2), (0.5, 0.8, 0.5, 0.94)):
            p.drawLine(QPointF(X(u0), Y(v0)), QPointF(X(u1), Y(v1)))

    # --- Auge -----------------------------------------------------------------------
    lx, rx, cy = 0.08, 0.92, 0.5
    lid = 0.25 if detail >= 1 else 0.20      # Lidbogen (Abstand Kontrollpunkt zur Mitte)
    eye = QPainterPath(QPointF(X(lx), Y(cy)))
    eye.quadTo(QPointF(X(0.5), Y(cy - 2 * lid)), QPointF(X(rx), Y(cy)))
    eye.quadTo(QPointF(X(0.5), Y(cy + 2 * lid)), QPointF(X(lx), Y(cy)))
    ir = 0.2 if detail >= 1 else 0.22         # Iris-Radius
    pr = ir * 0.46                            # Pupille inkl. Reflex-Ring

    if fill:
        sclera = QLinearGradient(0, Y(cy - lid), 0, Y(cy + lid))
        sclera.setColorAt(0.0, _c(INDIGO))
        sclera.setColorAt(1.0, _c(NIGHT))
        p.fillPath(eye, sclera)
        p.save()
        p.setClipPath(eye)
        iris = QRadialGradient(X(0.5), Y(cy), W(ir))
        iris.setColorAt(0.0, _c(AMBER))
        iris.setColorAt(0.35, _c(MAGENTA))
        iris.setColorAt(0.8, _c(VIOLET))
        iris.setColorAt(1.0, _c(NAVY))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(iris)
        p.drawEllipse(QPointF(X(0.5), Y(cy)), W(ir), W(ir))
        # Voight-Kampff-Scanlinie quer durchs Auge
        if detail >= 2:
            p.fillRect(QRectF(X(0), Y(cy + 0.075), W(1), max(1.0, W(0.018))), _c(CYAN, 170))
        p.restore()

    if line:
        p.setPen(Qt.PenStyle.NoPen)
        # Pupille mit Replikanten-Reflex (bernsteinfarbener Ring)
        p.setBrush(_c(AMBER))
        p.drawEllipse(QPointF(X(0.5), Y(cy)), W(pr), W(pr))
        p.setBrush(_c(VOID))
        p.drawEllipse(QPointF(X(0.5), Y(cy)), W(pr * 0.72), W(pr * 0.72))
        # Glanzlicht
        p.setBrush(_c(WHITE))
        gr = max(W(0.035), 0.75)
        p.drawEllipse(QPointF(X(0.5 - ir * 0.42), Y(cy - ir * 0.42)), gr, gr)
        # Lidkontur in Neon-Cyan
        pen = QPen(_c(CYAN))
        pen.setWidthF(max(1.0, round(W(0.05 if detail >= 1 else 0.075))))
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(eye)
    p.restore()


# ----------------------------------------------------------------------------------
# Bildkette (CPU): QImage <-> numpy, Dither, Alpha hart schneiden
# ----------------------------------------------------------------------------------

def _rgba(img):
    img = img.convertToFormat(QImage.Format.Format_RGBA8888)
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    a = np.frombuffer(ptr, np.uint8).reshape(img.height(), img.bytesPerLine() // 4, 4)
    return a[:, :img.width()].copy()


def _qimage(arr):
    h, w = arr.shape[:2]
    return QImage(np.ascontiguousarray(arr).tobytes(), w, h, w * 4,
                  QImage.Format.Format_RGBA8888).copy()


def quantize(arr, dither=True):
    """RGBA -> Palettenfarben (Grading + Bayer wie im Spiel), Alpha hart (Pixel-Art)."""
    old = config.DITHER_SPREAD
    if not dither:
        config.DITHER_SPREAD = 0.0
    try:
        q = sodither.dither_rgb(np.ascontiguousarray(arr[..., :3]))
    finally:
        config.DITHER_SPREAD = old
    out = np.zeros_like(arr)
    out[..., :3] = q
    out[..., 3] = np.where(arr[..., 3] >= 128, 255, 0)
    return out


def render_icon(size):
    """Icon in Endgröße. Große Größen: 128er Pixelraster, nearest hochskaliert."""
    logical = min(size, 128)
    detail = 0 if logical <= 16 else (1 if logical <= 48 else 2)
    img = QImage(logical, logical, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    paint_emblem(p, 0, 0, logical, detail=detail, layer="fill")
    p.end()
    q = _qimage(quantize(_rgba(img), dither=logical >= 48))
    p = QPainter(q)
    paint_emblem(p, 0, 0, logical, detail=detail, layer="line")
    p.end()
    if logical != size:
        q = q.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio,
                     Qt.TransformationMode.FastTransformation)
    return q


def _png_bytes(img):
    from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def _dib_bytes(img):
    """Klassischer ICO-Eintrag: BITMAPINFOHEADER + 32-bit BGRA (bottom-up) + AND-Maske."""
    a = _rgba(img)
    h, w = a.shape[:2]
    bgra = a[::-1, :, [2, 1, 0, 3]].tobytes()
    stride = ((w + 31) // 32) * 4                     # 1-bit-Zeilen auf 32 Bit gepolstert
    mask = bytearray(stride * h)
    for y in range(h):
        row = a[h - 1 - y, :, 3]
        for x in range(w):
            if row[x] < 128:
                mask[y * stride + x // 8] |= 0x80 >> (x % 8)
    head = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, len(bgra) + len(mask), 0, 0, 0, 0)
    return head + bgra + bytes(mask)


def write_ico(path, images):
    """Windows-ICO: kleine Größen als DIB (überall lesbar), 256 px als PNG (Standard seit Vista).

    Qt kann nur Einzelbild-ICOs schreiben, deshalb von Hand."""
    blobs = [(img.width(), _png_bytes(img) if img.width() >= 256 else _dib_bytes(img)) for img in images]
    head = struct.pack("<HHH", 0, 1, len(blobs))
    off = 6 + 16 * len(blobs)
    dirs, data = b"", b""
    for (s, blob) in blobs:
        dirs += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(blob), off + len(data))
        data += blob
    with open(path, "wb") as f:
        f.write(head + dirs + data)


def make_icons():
    os.makedirs(OUT_ICONS, exist_ok=True)
    imgs = {}
    for s in ICON_SIZES:
        imgs[s] = render_icon(s)
        imgs[s].save(os.path.join(OUT_ICONS, f"shadegunner-{s}.png"))
    write_ico(os.path.join(OUT_ICONS, "shadegunner.ico"), [imgs[s] for s in ICO_SIZES])
    print(f"Icons: {', '.join(map(str, ICON_SIZES))} px + shadegunner.ico -> {OUT_ICONS}")


# ----------------------------------------------------------------------------------
# Logo + Social Preview (GPU-Pfad mit echter Spielszene)
# ----------------------------------------------------------------------------------

def _scene_frame(zone=2, seed=11, frames=90, at=0.3):
    """Eine echte Spielszene (640x360) - ohne Bewegung, wie `glshot --still`.

    Ohne die Vordergrund-Masten: die würden quer durch Emblem und Schrift laufen."""
    from shadegunner.render.scene import Scene
    from shadegunner.sim import World
    world = World(seed=seed, zone_index=zone)
    world.player.x = world.length * at
    world.camera_x = world.player.x + 40
    sc = Scene(config.RENDER_W, config.RENDER_H)
    sc.ensure_zone(zone, seed, world.length)
    sc._foreground = lambda p, cam: None
    img = None
    for _ in range(frames):
        world.update(1 / 60, dict(move=(0.0, 0.0), aim=False, scan=False))
        img = sc.frame(world, 1 / 60, show_player=False)
        sc.consume(world, world.events)
        world.events.clear()
    return img


def _wordmark(p, cx, y, sc, t_sub=None, sub_sc=2, sub_shadow=VOID):
    """SHADEGUNNER wie im Titelbildschirm: Magenta-Schatten, Navy-Kante, Cyan-Kern."""
    from shadegunner.render import pixfont
    title = "SHADEGUNNER"
    tw = pixfont.text_width(title, sc)
    x0 = int(cx - tw / 2)
    o = max(1, sc // 9)
    pixfont.draw(p, x0 + 8 * o, y + 7 * o, title, MAGENTA, sc, None)
    pixfont.draw(p, x0 - 6 * o, y - 5 * o, title, (26, 52, 110), sc, None)
    pixfont.draw(p, x0, y, title, CYAN, sc, None)
    uy = y + 7 * sc + 8 * o
    p.fillRect(QRectF(x0 - 12 * o, uy, tw + 24 * o, 3 * o), _c(CYAN))
    p.fillRect(QRectF(x0 - 4 * o, uy + 4 * o, tw + 8 * o, o), _c(MAGENTA))
    if t_sub:
        for i, (s, col) in enumerate(t_sub):
            pixfont.draw(p, cx, uy + 18 * o + i * (9 * sub_sc + 6 * o), s, col, sub_sc, sub_shadow, "center")
    return tw


def _gl_render(scene_img, hud_img, out_w, out_h, curve=0.03, frames=24):
    """Szene + HUD durch Dither + CRT (echte Spiel-Shader) -> QImage in Ausgabegröße."""
    from PyQt6.QtGui import QOffscreenSurface, QOpenGLContext, QSurfaceFormat
    from PyQt6.QtOpenGL import QOpenGLFramebufferObject
    from shadegunner.render import shaders
    from shadegunner.render.glrender import CRTRenderer, GLFuncs

    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
    ctx = QOpenGLContext()
    ctx.setFormat(fmt)
    surf = QOffscreenSurface()
    surf.setFormat(fmt)
    surf.create()
    if not ctx.create() or not ctx.makeCurrent(surf):
        raise RuntimeError("Kein OpenGL-3.3-Kontext (unter Wayland: QT_QPA_PLATFORM=xcb)")
    gl = GLFuncs(ctx)
    r = CRTRenderer(gl)
    r.force_dt = 1 / 60
    fbo = QOpenGLFramebufferObject(out_w, out_h)
    lvl = dict(shaders.CRT_LEVEL, curve=curve, hum=0.0, grain=0.02)
    for _ in range(frames):            # Nachleuchten einschwingen lassen
        r.render(fbo.handle(), out_w, out_h, scene_img, scene_img.width(), scene_img.height(),
                 gamma=0.9, dt=1 / 60, dpr=1.0, level=lvl, hud=hud_img)
    out = fbo.toImage()
    ctx.doneCurrent()
    return out


def _dim(img, alpha, band=None):
    p = QPainter(img)
    p.fillRect(img.rect(), QColor(4, 5, 10, alpha))
    if band is not None:            # zusätzlich abgedunkelter Streifen hinter der Schrift
        y0, y1, a = band
        g = QLinearGradient(0, y0, 0, y1)
        g.setColorAt(0.0, QColor(4, 5, 10, 0))
        g.setColorAt(0.25, QColor(4, 5, 10, a))
        g.setColorAt(0.75, QColor(4, 5, 10, a))
        g.setColorAt(1.0, QColor(4, 5, 10, 0))
        p.fillRect(QRectF(0, y0, img.width(), y1 - y0), g)
    p.end()


def _emblem_layers(bg, hud, x, y, s):
    """Emblem ins Logo: Flächen in die Szene (GPU-Dither), Konturen pixelgenau ins HUD.

    Die Konturen werden im Dither-Raster (logisch) gezeichnet und nearest auf HUD-Größe
    hochskaliert - so sieht das Emblem aus wie das Icon und wie Spielgrafik."""
    p = QPainter(bg)
    paint_emblem(p, x, y, s, detail=2, layer="fill")
    p.end()
    lines = QImage(bg.width(), bg.height(), QImage.Format.Format_ARGB32_Premultiplied)
    lines.fill(0)
    p = QPainter(lines)
    paint_emblem(p, x, y, s, detail=2, layer="line")
    p.end()
    p = QPainter(hud)
    p.drawImage(0, 0, lines.scaled(hud.width(), hud.height(), Qt.AspectRatioMode.IgnoreAspectRatio,
                                   Qt.TransformationMode.FastTransformation))
    p.end()


def _new_hud(w, h):
    hud = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    hud.fill(0)
    return hud


def make_logo():
    from shadegunner import i18n
    i18n.set_lang("en")
    full = _scene_frame(zone=2).convertToFormat(QImage.Format.Format_RGB32)

    # --- README-Banner: 640x200 logisch -> 1280x400 --------------------------------
    w, h = 640, 200
    bg = full.copy(0, 40, w, h)
    _dim(bg, 120, band=(30, 175, 90))
    hud = _new_hud(w * 2, h * 2)
    _emblem_layers(bg, hud, 44, 32, 136)
    p = QPainter(hud)
    _wordmark(p, 800, 132, 10, [("BLADE RUNNER UNIT  ·  REPLICANT DETECTION", ASH),
                                ("A 16-COLOR CYBERPUNK SIDE-SCROLLER", STEEL)], sub_sc=2)
    p.end()
    _gl_render(bg, hud, w * 2, h * 2).save(os.path.join(OUT_ASSETS, "logo.png"))

    # --- Social Preview: 640x320 logisch -> 1280x640 (GitHub-Format 2:1) -----------
    # GitHub nimmt nur Dateien < 1 MB an -> JPEG.
    w, h = 640, 320
    bg = full.copy(0, 20, w, h)
    _dim(bg, 110, band=(170, 300, 110))
    hud = _new_hud(w * 2, h * 2)
    _emblem_layers(bg, hud, 320 - 64, 26, 128)
    p = QPainter(hud)
    _wordmark(p, 640, 360, 11, [("BLADE RUNNER UNIT  ·  REPLICANT DETECTION  ·  LAPD", ASH),
                                ("A 16-COLOR CYBERPUNK SIDE-SCROLLER  ·  PYTHON + PYQT6", STEEL)],
              sub_sc=3)
    p.end()
    _gl_render(bg, hud, w * 2, h * 2).save(os.path.join(OUT_ASSETS, "social-preview.jpg"), "JPG", 90)
    print(f"Logo + Social Preview -> {OUT_ASSETS}")


def make_wordmark():
    """Freistehendes Logo (transparent, ohne CRT) - z. B. Steam-Bibliothekslogo, Presse."""
    from shadegunner.render import pixfont
    w, h = 1280, 360
    emb = render_icon(256)
    sc, gap = 12, 48
    tw = pixfont.text_width("SHADEGUNNER", sc)
    x0 = (w - (256 + gap + tw)) // 2              # Emblem + Schrift als Gruppe zentriert
    img = _new_hud(w, h)
    p = QPainter(img)
    p.drawImage(x0, (h - 256) // 2, emb)
    # Unterzeile in Stahlblau ohne Schatten: lesbar auf dunklem wie hellem Grund
    _wordmark(p, x0 + 256 + gap + tw // 2, 130, sc, [("BLADE RUNNER UNIT  ·  REPLICANT DETECTION", STEEL)],
              sub_sc=3, sub_shadow=None)
    p.end()
    img.save(os.path.join(OUT_ASSETS, "logo-transparent.png"))
    print(f"Logo (transparent) -> {OUT_ASSETS}")


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    app = QGuiApplication(sys.argv[:1])  # noqa: F841
    if what in ("all", "icons"):
        make_icons()
        make_wordmark()
    if what in ("all", "logo"):
        make_logo()
    return 0


if __name__ == "__main__":
    sys.exit(main())
