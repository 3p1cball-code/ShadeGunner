"""Zentrale Konstanten: Paletten, Dither-Parameter, Layout der Spielebene, Balancing.

Alles, was Balancing oder Look betrifft, lebt hier - nicht verstreut im Code.
"""

# ----------------------------------------------------------------------------------
# Paletten (je 16 RGB-Tripel, 0-255)
# ----------------------------------------------------------------------------------

# noir16: Cyberpunk-Noir. Blau-Rampe für die Nacht, Grau-Rampe für Regen/Beton,
# vier Neon-Akzente (Cyan, Magenta, Amber, Violett), Tief-Türkis und ein Karmin
# (Blut, Rost, Tyrell-Fackeln - ohne ihn ließe sich Wärme nur mit Amber dithern).
NOIR16 = [
    (6, 8, 14),        # 0  void
    (18, 22, 38),      # 1  night
    (34, 40, 66),      # 2  navy
    (52, 60, 96),      # 3  indigo
    (74, 92, 138),     # 4  blue
    (104, 132, 178),   # 5  steel
    (138, 32, 56),     # 6  crimson
    (156, 84, 40),     # 7  sodium (dunkles Natrium-Orange: Laternen, Rost, Tyrell-Gold)
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

# Fenster-Auflösungen im Einstellungsmenü (im Vollbild gilt die Bildschirmauflösung).
RESOLUTIONS = [(1280, 720), (1366, 768), (1600, 900), (1920, 1080), (2560, 1440), (3840, 2160)]

# Wie weit der Bayer-Schwellwert eine Farbe verschiebt, bevor sie auf den nächsten
# Paletteneintrag schnappt. Größer = sichtbareres Dithering zwischen Nachbarfarben.
DITHER_SPREAD = 0.24

# Bayer-Matrix-Ordnung: 3 -> 8x8 (feine Muster), 2 -> 4x4 (gröber), 1 -> 2x2.
DITHER_ORDER = 3

# Farbkorrektur vor dem Dither (GPU): tiefe Schwärzen, satte Neon-Lichter
# (Referenz: The Last Night). Contrast = Anteil S-Kurve, Lift < 0 drückt den Schwarzpunkt.
GRADE_CONTRAST = 0.3
GRADE_SATURATION = 1.22
GRADE_LIFT = -0.012

# ----------------------------------------------------------------------------------
# Bildschirm / Render
# ----------------------------------------------------------------------------------

# Interne (Dither-)Auflösung. Wird per CRT/Anzeige hochskaliert.
RENDER_W = 640
RENDER_H = 360

# HUD-Textur: Vielfaches der Dither-Auflösung (schärfere Schrift, kein Dither).
HUD_SCALE = 2

# ----------------------------------------------------------------------------------
# Spielebene (Belt-Scroller) - eine echte Zentralperspektive
# ----------------------------------------------------------------------------------
#
# Tiefe d in [0, 1]: 0 = hintere Bordsteinkante, 1 = vorne an der Kamera.
# Skala s(d) = SCALE_FAR + (1 - SCALE_FAR) * d;   Bild-y = HORIZON_PX + K * s.
# Weil y und Skala beide linear in d sind, ist alles (Figuren, Boden, Fassade)
# perspektivisch konsistent - auch die Parallaxe der Häuserfront.

FLOOR_TOP_Y = 0.50      # Bild-y (Anteil) der Tiefe 0
FLOOR_BOTTOM_Y = 0.985  # Bild-y (Anteil) der Tiefe 1
SCALE_FAR = 0.42        # Figuren-Skala bei Tiefe 0
FACADE_DEPTH = -0.075   # Tiefe der Häuserfront hinter dem Gehweg
FIGURE_H_NEAR = 0.215   # Figurenhöhe (Anteil Bildhöhe) bei Tiefe 1

# Waagerechter Sichtbereich in Welt-Einheiten bei Tiefe 1.
VIEW_SPAN_NEAR = 300.0

DEPTH_MIN = 0.10
DEPTH_MAX = 1.0
DEPTH_UNITS = 160.0     # wie viele Welt-Einheiten die volle Tiefe für Distanzen zählt

# ----------------------------------------------------------------------------------
# Spieler
# ----------------------------------------------------------------------------------

PLAYER_WALK_SPEED = 58.0
PLAYER_SPRINT_SPEED = 100.0
PLAYER_DEPTH_SPEED = 0.75
PLAYER_HP = 3
STRIDE_UNITS = 30.0      # Welt-Einheiten pro vollem Schrittzyklus (gegen Fußrutschen)

# Sprung (Höhe z in Welt-Einheiten; eine Figur ist ~36 u groß)
JUMP_V = 132.0
GRAVITY = 640.0
JUMP_SAFE_Z = 5.0        # ab dieser Höhe gehen Schläge/Sprungangriffe ins Leere

# Ramen-Stand: kurz stehen bleiben füllt ein Herz auf (einmal pro Stand)
RAMEN_TIME = 1.2
RAMEN_RANGE = 26.0

# ----------------------------------------------------------------------------------
# Endboss ROY (letzte Zone, Tyrell)
# ----------------------------------------------------------------------------------

# Er redet - währenddessen unverwundbar - und verträgt zwischen den Sprüchen Treffer.
ROY_LINES = [
    "Ich habe Dinge gesehen, von denen ihr Menschen nicht einmal träumt.",
    "Angriffsschiffe in Flammen vor der Schulter des Orion.",
    "Ich sah C-Strahlen glitzern im Dunkeln am Tannhäuser Tor.",
    "All diese Momente werden verloren sein in der Zeit - wie Tränen im Regen.",
]
ROY_PER_LINE = 2          # Treffer pro Spruch (danach der nächste Satz)
ROY_HP = len(ROY_LINES) * ROY_PER_LINE
ROY_SPEAK_S = 2.6         # Redezeit je Satz
ROY_TRIGGER = 320.0       # Abstand zum Zonenende, ab dem er auftritt

# ----------------------------------------------------------------------------------
# Straße: Fahrspuren, Verkehr, Hindernisse
# ----------------------------------------------------------------------------------

LANES = ((0.32, -1), (0.74, 1))   # (Tiefe, Fahrtrichtung)
LANE_HALF = 0.085                 # halbe Spurbreite in Tiefe
OBSTACLE_BANDS = ((0.12, 0.20), (0.45, 0.60), (0.88, 0.97))  # freie Streifen neben den Spuren

# ----------------------------------------------------------------------------------
# Aktionen
# ----------------------------------------------------------------------------------

TARGET_RANGE = 190.0       # Lock-on-Reichweite
OBSERVE_RANGE = 150.0      # Beobachtung deckt schwache Tells auf
OBSERVE_SECONDS = 2.4      # Beobachtungsdauer pro schwachem Tell (gelocktes Ziel)
SCAN_RANGE = 125.0
SCAN_TIME = 0.85           # Kanalzeit eines Scans
SHOOT_RANGE = 210.0
AIM_MIN = 0.18             # minimale Zielzeit vor dem Schuss
SHOT_COOLDOWN = 0.45
PANIC_RADIUS = 170.0

SCAN_CHARGES = 5
SCAN_RECHARGE_S = 5.0

# Suspicion: ein getöteter Mensch kostet so viel; ab 1.0 ist der Run verloren.
SUSPICION_PER_CIVILIAN = 0.34
SUSPICION_PER_ESCAPE = 0.06

# Punkte
POINTS_REPLICANT = 100
POINTS_INSTINCT = 60       # Bonus: Replikant ohne Scan erkannt
POINTS_CIVILIAN = -250
POINTS_ESCAPE = -40
POINTS_BOUNTY = 400        # Kopfgeld-Bonus (zusätzlich zum Replikanten)
COMBO_MAX = 5
SUSPICION_WATCHED = 1.5    # Faktor, wenn die Polizei-Patrouille dich im Suchlicht hat
