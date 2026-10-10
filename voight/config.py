"""Zentrale Konstanten: Paletten, Dither-Parameter, Layout der Spielebene.

Alles, was Balancing oder Look betrifft, lebt hier - nicht verstreut im Code.
"""

# ----------------------------------------------------------------------------------
# Paletten (je 16 RGB-Tripel, 0-255)
# ----------------------------------------------------------------------------------

# noir16: Cyberpunk-Noir. Neutrale von Schwarz bis Weiß (tragen das Dithering der
# Szene) plus vier Neon-Akzente (Cyan, Magenta, Amber, Violett) und ein Tief-Türkis.
NOIR16 = [
    (6, 8, 14),        # 0  void
    (18, 22, 38),      # 1  night
    (34, 40, 66),      # 2  navy
    (52, 60, 96),      # 3  indigo
    (74, 92, 138),     # 4  blue
    (104, 132, 178),   # 5  steel
    (74, 78, 88),      # 6  graphite
    (112, 118, 132),   # 7  slate
    (162, 168, 180),   # 8  ash
    (214, 220, 226),   # 9  pale
    (255, 255, 255),   # 10 white
    (34, 96, 104),     # 11 deep teal
    (64, 210, 220),    # 12 cyan neon
    (224, 72, 150),    # 13 magenta neon
    (255, 138, 44),    # 14 amber
    (122, 74, 168),    # 15 violet
]

# cga16: die klassische CGA/EGA-Textmodus-Palette (wie asciiplay "pal16").
CGA16 = [
    (0, 0, 0), (0, 0, 170), (0, 170, 0), (0, 170, 170),
    (170, 0, 0), (170, 0, 170), (170, 85, 0), (170, 170, 170),
    (85, 85, 85), (85, 85, 255), (85, 255, 85), (85, 255, 255),
    (255, 85, 85), (255, 85, 255), (255, 255, 85), (255, 255, 255),
]

PALETTES = {"noir16": NOIR16, "cga16": CGA16}
DEFAULT_PALETTE = "noir16"

# Wie weit der Bayer-Schwellwert eine Farbe verschiebt, bevor sie auf den nächsten
# Paletteneintrag schnappt. Größer = sichtbareres Dithering zwischen Nachbarfarben.
DITHER_SPREAD = 0.42

# Bayer-Matrix-Ordnung: 3 -> 8x8 (feine Muster), 2 -> 4x4 (gröber), 1 -> 2x2.
DITHER_ORDER = 3

# ----------------------------------------------------------------------------------
# Bildschirm / Render
# ----------------------------------------------------------------------------------

# Interne (Dither-)Auflösung. Wird per CRT/Anzeige hochskaliert.
RENDER_W = 512
RENDER_H = 288

# ----------------------------------------------------------------------------------
# Spielebene (Belt-Scroller)
# ----------------------------------------------------------------------------------

# Horizont (Anteil der Höhe von oben), darunter liegt die Straße.
HORIZON_Y = 0.42

# Die begehbare Straßentiefe wird als Perspektive abgebildet: y_depth in [0, 1]
# (0 = hinten am Horizont, 1 = vorne auf Höhe der Kamera).
FLOOR_TOP_Y = 0.44      # Bild-y der hintersten Bahn
FLOOR_BOTTOM_Y = 1.02   # Bild-y der vordersten Bahn (etwas aus dem Bild heraus)

# Prozedurale Streuung / Balances
CROWD_DENSITY = 0.55    # 0..1 Grunddichte der Passanten in Zone 2

# Spieler
PLAYER_WALK_SPEED = 62.0   # Einheiten/Sekunde auf X
PLAYER_DEPTH_SPEED = 26.0  # Tiefenbewegung (Y) Einheiten/Sekunde

# Aktions-Reichweiten (Welt-Einheiten)
OBSERVE_RANGE = 130.0      # ab hier werden schwache Tells über Zeit sichtbar
SCAN_RANGE = 110.0         # maximale Scan-Reichweite
DEACTIVATE_RANGE = 46.0    # maximale Deaktivierungs-Reichweite
OBSERVE_SECONDS = 2.6      # Beobachtungsdauer, bis ein schwacher Tell erscheint

# Scan-Ladungen (Basis, wird vom Skillbaum erhöht)
SCAN_CHARGES = 6
SCAN_RECHARGE_S = 4.0      # Ladung regeneriert nach so vielen Sekunden

# Suspicion: ein getöteter Mensch kostet so viel; ab 1.0 ist der Run verloren.
SUSPICION_PER_CIVILIAN = 0.34

# Waagerechter Sichtbereich in Welt-Einheiten, der die Bildschirmbreite füllt
# (bei Tiefe 1.0). Bestimmt die Kamera-Skalierung im Renderer.
VIEW_SPAN_NEAR = 260.0

