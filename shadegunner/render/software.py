"""Software-Renderer (reines Python): Canvas + Zeichenprimitiven.

Nur für Preview/Look-Validierung und als Fallback gedacht. Der echte Renderer ist
der QtOpenGL-Pfad mit den asciiplay-Shadern. Beide konsumieren dieselbe Szenen-
beschreibung, damit Preview und GPU-Bild zusammenpassen.
"""


class Canvas:
    """RGB8-Framebuffer (Bytearray) mit Painter's-Algorithm-Zeichenoperationen."""

    __slots__ = ("w", "h", "buf")

    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.buf = bytearray(w * h * 3)

    # ---- Basisfüllung ----------------------------------------------------------
    def fill(self, c):
        self.buf[:] = bytes(c) * (self.w * self.h)

    def row(self, y, c):
        if 0 <= y < self.h:
            s = y * self.w * 3
            self.buf[s:s + self.w * 3] = bytes(c) * self.w

    def set(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.buf[i] = c[0]
            self.buf[i + 1] = c[1]
            self.buf[i + 2] = c[2]

    def get(self, x, y):
        i = (y * self.w + x) * 3
        return (self.buf[i], self.buf[i + 1], self.buf[i + 2])

    def rect(self, x, y, w, h, c):
        x0, x1 = max(0, x), min(self.w, x + w)
        if x1 <= x0:
            return
        band = bytes(c) * (x1 - x0)
        for yy in range(max(0, y), min(self.h, y + h)):
            s = (yy * self.w + x0) * 3
            self.buf[s:s + (x1 - x0) * 3] = band

    # ---- Verläufe --------------------------------------------------------------
    def vgrad(self, y0, y1, c0, c1):
        """Vertikaler Verlauf c0 (oben, bei y0) -> c1 (unten, bei y1), volle Breite."""
        if y1 <= y0:
            return
        span = y1 - y0
        for y in range(max(0, y0), min(self.h, y1)):
            f = (y - y0) / span
            c = (int(c0[0] + (c1[0] - c0[0]) * f + 0.5),
                 int(c0[1] + (c1[1] - c0[1]) * f + 0.5),
                 int(c0[2] + (c1[2] - c0[2]) * f + 0.5))
            self.row(y, c)

    def hline(self, x0, x1, y, c):
        x0, x1 = max(0, x0), min(self.w, x1)
        if x1 <= x0 or not (0 <= y < self.h):
            return
        s = (y * self.w + x0) * 3
        self.buf[s:s + (x1 - x0) * 3] = bytes(c) * (x1 - x0)

    def vline(self, x, y0, y1, c):
        if not (0 <= x < self.w):
            return
        for y in range(max(0, y0), min(self.h, y1)):
            i = (y * self.w + x) * 3
            self.buf[i] = c[0]
            self.buf[i + 1] = c[1]
            self.buf[i + 2] = c[2]

    # ---- Sprites (Bitmap-Muster) ----------------------------------------------
    def blit(self, pattern, px, py, out_h, cmap):
        """Zeichnet ein Zeichen-Muster skaliert auf `out_h` Pixel Höhe.

        `pattern`: Liste von Strings, ein Zeichen pro Pixel; '.' = transparent.
        `cmap`: Zeichen -> RGB-Farbe. Die Breite skaliert im selben Faktor.
        """
        rows = len(pattern)
        if rows == 0 or out_h <= 0:
            return
        cols = max(len(r) for r in pattern)
        scale = out_h / rows
        out_w = max(1, int(round(cols * scale)))
        for oy in range(out_h):
            sy = int(oy / scale)
            if sy >= rows:
                sy = rows - 1
            line = pattern[sy]
            run_char = None
            run_start = 0
            for ox in range(out_w + 1):
                sx = int(ox / scale)
                ch = line[sx] if (ox <= out_w and sx < len(line)) else None
                if ch != run_char:
                    if run_char is not None and run_char != '.' and run_char in cmap and ox > run_start:
                        c = cmap[run_char]
                        self.hline(px + run_start, px + ox, py + oy, c)
                    run_char = ch
                    run_start = ox


# Passanten-Silhouetten, mehrere Varianten. '#' = Körper, 'A' = Akzent (Augen),
# '.' = ebenfalls Körper, ' ' = transparent. Bei kleiner Ausgabe zählt die Kontur,
# nicht das Detail - die Varianten unterscheiden sich bewusst in Umriss und Breite.
PEDESTRIANS = [
    [  # schlank
        "  .  ",
        " ### ",
        "#A#A#",
        " ### ",
        "#####",
        " ### ",
        " # # ",
        " # # ",
        " # # ",
    ],
    [  # breit, mit Schultern + Hut
        "  ###  ",
        " ##### ",
        "##A#A##",
        " ##### ",
        " ##### ",
        "  ###  ",
        "  # #  ",
        "  # #  ",
        "  # #  ",
        " #   # ",
    ],
    [  # schmal, langer Mantel
        "  #  ",
        " #A# ",
        "  #  ",
        " ### ",
        "#####",
        "#####",
        " ### ",
        " ### ",
        "  #  ",
        "  #  ",
        "  #  ",
    ],
]

# Spieler: eigene Figur (etwas breiter, klare Kontur)
PLAYER_SPRITE = [
    "  ###  ",
    " ##### ",
    "##A#A##",
    " ##### ",
    " ##### ",
    " ##### ",
    "  ###  ",
    "  # #  ",
    "  # #  ",
    " #   # ",
]


def _blit_sprite(cav, pattern, x, y_top, out_h, body, accent):
    cols = max(len(r) for r in pattern)
    half = int(out_h * cols / len(pattern) / 2)
    cav.blit(pattern, x - half, y_top, out_h, {"#": body, "A": accent, ".": body})


def draw_pedestrian(cav, x, y_ground, out_h, body, accent, variant=0):
    pat = PEDESTRIANS[variant % len(PEDESTRIANS)]
    _blit_sprite(cav, pat, x, y_ground - out_h, out_h, body, accent)


def draw_player(cav, x, y_ground, out_h, body, accent):
    _blit_sprite(cav, PLAYER_SPRITE, x, y_ground - out_h, out_h, body, accent)

