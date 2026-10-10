"""Bayer-Ordered-Dithering gegen eine feste Palette (CPU-Zwilling des GPU-Shaders).

Dient der Software-Preview und als Fallback. Die Matrizen- und Distanz-Logik ist
bewusst identisch zu `asciiplay` (BAYER_FRAG / nearest_pal), damit Preview und
späteres GPU-Bild denselben Look ergeben.
"""

from . import config


def bayer_matrix(order):
    """Rekursive Bayer-Matrix der Seitenlänge 2**order, Werte 0..n^2-1."""
    if order <= 0:
        return [[0]]
    smaller = bayer_matrix(order - 1)
    n = len(smaller)
    out = [[0] * (2 * n) for _ in range(2 * n)]
    for y in range(n):
        for x in range(n):
            v = 4 * smaller[y][x]
            out[y][x] = v + 0
            out[y][x + n] = v + 2
            out[y + n][x] = v + 3
            out[y + n][x + n] = v + 1
    return out


def _nearest(pr, pg, pb, palette, weights):
    """Nächster Paletteneintrag; Gewichtung wie im Auge (Grün zählt am meisten)."""
    wr, wg, wb = weights
    best = 0
    bd = 1e18
    for i, (qr, qg, qb) in enumerate(palette):
        dr = (pr - qr) * wr
        dg = (pg - qg) * wg
        db = (pb - qb) * wb
        dd = dr * dr + dg * dg + db * db
        if dd < bd:
            bd = dd
            best = i
    return best


def dither(rgb, w, h, palette_name=None, spread=None, order=None):
    """RGB-Bytearray (Länge w*h*3) -> gedithertes RGB-Bytearray mit Palettenfarben."""
    palette_name = palette_name or config.DEFAULT_PALETTE
    spread = config.DITHER_SPREAD if spread is None else spread
    order = config.DITHER_ORDER if order is None else order

    pal = config.PALETTES[palette_name]
    paln = [(r / 255.0, g / 255.0, b / 255.0) for (r, g, b) in pal]
    n = 1 << order
    mat = bayer_matrix(order)
    denom = float(n * n)
    weights = (0.9, 1.1, 0.8)

    out = bytearray(len(rgb))
    for y in range(h):
        row = mat[y % n]
        base = y * w * 3
        for x in range(w):
            t = (row[x % n] + 0.5) / denom
            i = base + x * 3
            nr = rgb[i] / 255.0 + (t - 0.5) * spread
            ng = rgb[i + 1] / 255.0 + (t - 0.5) * spread
            nb = rgb[i + 2] / 255.0 + (t - 0.5) * spread
            nr = 0.0 if nr < 0 else (1.0 if nr > 1 else nr)
            ng = 0.0 if ng < 0 else (1.0 if ng > 1 else ng)
            nb = 0.0 if nb < 0 else (1.0 if nb > 1 else nb)
            qr, qg, qb = pal[_nearest(nr, ng, nb, paln, weights)]
            out[i] = qr
            out[i + 1] = qg
            out[i + 2] = qb
    return out
