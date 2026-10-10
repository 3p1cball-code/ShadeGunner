"""Software-Pfad: Grading + Bayer-Dither + leichte CRT-Anmutung auf der CPU (numpy).

Fallback für Systeme ohne OpenGL 3.3 (VMs, schwache/ältere Rechner, manche
Compat-Umgebungen). Spiegelt Grading und Palette des GPU-Shaders
(render/shaders.py) und skaliert das Ergebnis auf die Fenstergröße. Kein
Fancy-CRT - nur Dither, Scanlines und Vignette, dafür überall lauffähig.
"""

import numpy as np
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QImage, QPainter, QRadialGradient, QColor

from .. import config
from ..palette import bayer_matrix

_PAL = None
_BAYER = None
_LUT = None
_LUT_BITS = 6
_WEIGHTS = np.array([0.9, 1.1, 0.8], np.float32)


def _pal():
    global _PAL
    if _PAL is None:
        _PAL = np.array(config.PALETTES[config.DEFAULT_PALETTE], np.float32) / 255.0
    return _PAL


def _bayer():
    global _BAYER
    if _BAYER is None:
        n = 1 << config.DITHER_ORDER
        _BAYER = (np.array(bayer_matrix(config.DITHER_ORDER), np.float32) + 0.5) / (n * n)
    return _BAYER


def _lut():
    """Nächste Palettenfarbe für jeden 6-Bit-RGB-Würfel, einmal vorberechnet (64^3, uint8)."""
    global _LUT
    if _LUT is None:
        n = 1 << _LUT_BITS
        v = np.linspace(0.0, 1.0, n, dtype=np.float32)
        g = np.stack(np.meshgrid(v, v, v, indexing="ij"), axis=-1).reshape(-1, 3)
        pal = _pal()
        d = ((g[:, None, :] - pal[None, :, :]) * _WEIGHTS) ** 2
        _LUT = d.sum(-1).argmin(-1).astype(np.uint8).reshape(n, n, n)
    return _LUT


def _to_rgb(img):
    """QImage -> numpy RGB (h, w, 3) uint8."""
    if img.format() != QImage.Format.Format_RGB32:
        img = img.convertToFormat(QImage.Format.Format_RGB32)
    w, h = img.width(), img.height()
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    arr = np.frombuffer(ptr, np.uint8).reshape(h, img.bytesPerLine() // 4, 4)
    return np.ascontiguousarray(arr[:, :w, :3][:, :, ::-1])


def dither_rgb(rgb):
    """RGB uint8 (h,w,3) -> geditherte Palettenfarben (h,w,3) uint8. Grading + Bayer."""
    h, w = rgb.shape[:2]
    c = rgb.astype(np.float32) / 255.0
    # Grading (wie im Shader): Sättigung, Schwarzpunkt, S-Kurve
    lum = (c * np.array([0.299, 0.587, 0.114], np.float32)).sum(-1, keepdims=True)
    c = np.clip(lum + (c - lum) * config.GRADE_SATURATION, 0.0, 1.0)
    c = np.clip((c + config.GRADE_LIFT) / (1.0 + config.GRADE_LIFT), 0.0, 1.0)
    s = c * c * (3.0 - 2.0 * c)
    c = c + (s - c) * config.GRADE_CONTRAST
    # Bayer-Schwelle
    n = _bayer().shape[0]
    th = np.tile(_bayer(), (h // n + 1, w // n + 1))[:h, :w]
    c += (th[..., None] - 0.5) * config.DITHER_SPREAD
    np.clip(c, 0.0, 1.0, out=c)
    # nächste Palettenfarbe über die vorberechnete LUT (schnell)
    bits = _LUT_BITS
    m = (1 << bits) - 1
    q = np.rint(c * m).astype(np.intp)
    np.clip(q, 0, m, out=q)
    best = _lut()[q[..., 0], q[..., 1], q[..., 2]]
    return (_pal()[best] * 255.0 + 0.5).astype(np.uint8)


def _scan_overlay(w, h, cell):
    """Schwarzes Overlay mit horizontalen Scanlines + Vignette (einmal bauen)."""
    ov = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    ov.fill(0)
    p = QPainter(ov)
    step = max(2, int(round(cell)))
    p.setPen(QColor(0, 0, 0, 70))
    y = 0
    while y < h:
        p.drawLine(0, y, w, y)
        y += step
    g = QRadialGradient(w / 2, h / 2, max(w, h) * 0.72)
    g.setColorAt(0.55, QColor(0, 0, 0, 0))
    g.setColorAt(1.0, QColor(0, 0, 0, 150))
    p.fillRect(0, 0, w, h, g)
    p.end()
    return ov


def compose(scene_img, out_w, out_h, overlay=None):
    """Szene -> gedithert + skaliert (16:9 letterboxed) als QImage in Fenstergröße."""
    rgb = _to_rgb(scene_img)
    dit = dither_rgb(rgb)
    h, w = dit.shape[:2]
    qi = QImage(dit.tobytes(), w, h, w * 3, QImage.Format.Format_RGB888).copy()

    aspect = w / h
    if out_w / out_h > aspect:
        th = out_h
        tw = max(1, int(round(out_h * aspect)))
    else:
        tw = out_w
        th = max(1, int(round(out_w / aspect)))
    ox, oy = (out_w - tw) // 2, (out_h - th) // 2

    canvas = QImage(out_w, out_h, QImage.Format.Format_RGB32)
    canvas.fill(0)
    p = QPainter(canvas)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
    p.drawImage(QRectF(ox, oy, tw, th), qi)
    if overlay is not None:
        p.drawImage(0, 0, overlay)
    p.end()
    return canvas
