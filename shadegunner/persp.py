"""Perspektive der Belt-Ebene (Welt -> Bildschirm), geteilt von Sim und Renderer.

Tiefe d: 0 = hintere Bordsteinkante, 1 = vorne. Skala und Bild-y sind beide
linear in d - das ist exakt eine Zentralperspektive mit Horizont bei
`horizon_px()`. Damit scrollen Boden, Häuserfront und Figuren konsistent.
"""

from . import config

W, H = config.RENDER_W, config.RENDER_H
_Y0 = config.FLOOR_TOP_Y * H
_Y1 = config.FLOOR_BOTTOM_Y * H
_S0 = config.SCALE_FAR
PPU_NEAR = W / config.VIEW_SPAN_NEAR


def scale(d):
    return _S0 + (1.0 - _S0) * d


def ground_y(d):
    return _Y0 + (_Y1 - _Y0) * d


def depth_at_y(y):
    return (y - _Y0) / (_Y1 - _Y0)


def ppu(d):
    """Bildschirm-Pixel pro Welt-Einheit in Tiefe d."""
    return PPU_NEAR * scale(d)


def screen_x(x, d, cam_x):
    return W * 0.5 + (x - cam_x) * ppu(d)


def world_x(sx, d, cam_x):
    return cam_x + (sx - W * 0.5) / ppu(d)


def figure_h(d):
    return config.FIGURE_H_NEAR * H * scale(d)


def horizon_px():
    k = (_Y1 - _Y0) / (1.0 - _S0)
    return _Y0 - _S0 * k


FACADE_Y = ground_y(config.FACADE_DEPTH)
FACADE_PPU = ppu(config.FACADE_DEPTH)
