"""Zentrale Konstanten: Paletten, Dither-Parameter, Layout der Spielebene, Balancing.

Alles, was Balancing oder Look betrifft, lebt hier - nicht verstreut im Code.
"""

# ----------------------------------------------------------------------------------
# Paletten (je 16 RGB-Tripel, 0-255)
# ----------------------------------------------------------------------------------

# noir16: Cyberpunk-Noir nach den Filmstills (reference/): teal-grüner Dunst statt
# Blau-Violett. Dunkle Rampe Richtung Petrol, dazu die Neonfarben des Films -
# Cyan/Türkis (Röhren), Grün (Ampelpfeil), Signalrot (rote Hand, Rücklichter),
# Neon-Blau, Amber (Feuer, Natrium), selten Magenta. Kein Violett, kein Mittelgrau
# mehr (Grau dithert aus Stahl + Pale). Index-Semantik 6/8/15 hat sich geändert
# (13.10.2026): 6 Karmin -> Signalrot, 8 Ash -> Neon-Blau, 15 Violett -> Neon-Grün.
NOIR16 = [
    (5, 8, 10),        # 0  void
    (12, 22, 28),      # 1  night
    (22, 38, 48),      # 2  navy (Petrol)
    (34, 58, 70),      # 3  slate-teal
    (52, 86, 104),     # 4  blue
    (92, 128, 144),    # 5  steel
    (226, 38, 46),     # 6  signal red (rote Hand, Rücklichter, RAMEN)
    (156, 84, 40),     # 7  sodium (dunkles Natrium-Orange: Laternen, Rost, Tyrell-Gold)
    (46, 104, 250),    # 8  neon blue
    (148, 172, 170),   # 9  pale (helles Grau-Teal; Weiß übernimmt die Spitzlichter)
    (255, 255, 255),   # 10 white
    (30, 104, 104),    # 11 deep teal
    (70, 220, 214),    # 12 cyan neon
    (224, 72, 150),    # 13 magenta neon
    (255, 148, 48),    # 14 amber (Feuer)
    (80, 226, 110),    # 15 neon green
]

# Die alte Palette (bis 13.10.2026). Das HUD wird nach dem Dither unverändert
# darübergelegt und behält deshalb seine bisherigen Farben.
NOIR16_OLD = [
    (6, 8, 14), (18, 22, 38), (34, 40, 66), (52, 60, 96), (74, 92, 138), (104, 132, 178),
    (138, 32, 56), (156, 84, 40), (162, 168, 180), (214, 220, 226), (255, 255, 255),
    (34, 96, 104), (64, 210, 220), (224, 72, 150), (255, 138, 44), (122, 74, 168),
]

# cga16: die klassische CGA/EGA-Textmodus-Palette (wie asciiplay "pal16").
CGA16 = [
    (0, 0, 0), (0, 0, 170), (0, 170, 0), (0, 170, 170),
    (170, 0, 0), (170, 0, 170), (170, 85, 0), (170, 170, 170),
    (85, 85, 85), (85, 85, 255), (85, 255, 85), (85, 255, 255),
    (255, 85, 85), (255, 85, 255), (255, 255, 85), (255, 255, 255),
]

# ----------------------------------------------------------------------------------
# Paletten je Zone (14.10.2026): der Film kuratiert von Szene zu Szene, also auch wir.
# Jede Zone hat EIN komplementäres Farbpaar statt aller Neonfarben auf einmal, und
# zu beiden Seiten ein paar nahe Abstufungen (dunkel / Neon / Spitzlicht), damit
# Lichter auf Figuren modelliert werden können statt hart umzuschnappen.
# Aufbau: 0-5 dunkle Rampe (zur kühlen Seite getönt), dann Blut, Hautton,
# Pale/Weiß und die beiden Farbfamilien. 'neon' / 'people' = Indizes für
# Schilder bzw. Schirme und Leuchtakzente der Passanten.
# ----------------------------------------------------------------------------------
ZONE_LOOK = [
    dict(  # 0 Außenbezirk: Natrium/Amber gegen Blau/Violett (der ursprüngliche Look)
        name="hades16", pal=[
            (6, 6, 12), (16, 16, 28), (28, 28, 48), (44, 44, 72), (64, 66, 102), (100, 104, 142),
            (140, 34, 44),     # 6  Blut / Rücklicht
            (120, 64, 36),     # 7  Rost / dunkles Natrium
            (196, 104, 44),    # 8  Natrium
            (255, 156, 56),    # 9  Amber
            (255, 216, 140),   # 10 Amber-Spitzlicht
            (226, 214, 200),   # 11 Pale (warm)
            (255, 255, 255),   # 12 Weiß
            (96, 60, 140),     # 13 Violett tief
            (150, 104, 220),   # 14 Violett-Neon
            (84, 128, 255),    # 15 Blau-Neon
        ], neon=[9, 9, 8, 14, 15, 10], people=[9, 10, 14, 15, 8, 11]),
    dict(  # 1 Vorstadt: kaltes Grün/Cyan der Leuchtröhren gegen ein wenig Pink
        name="blocks16", pal=[
            (5, 9, 10), (12, 22, 26), (20, 38, 44), (32, 58, 64), (50, 86, 92), (90, 128, 130),
            (160, 34, 64),     # 6  Blut / tiefes Magenta
            (236, 86, 150),    # 7  Pink-Neon
            (156, 118, 98),    # 8  Hautton / warmes Neutral
            (36, 120, 84),     # 9  Grün tief
            (70, 214, 120),    # 10 Grün-Neon
            (176, 242, 196),   # 11 Leuchtröhren-Spitzlicht
            (60, 190, 214),    # 12 Cyan
            (196, 218, 212),   # 13 Pale
            (255, 255, 255),   # 14 Weiß
            (255, 170, 210),   # 15 Pink-Spitzlicht
        ], neon=[10, 10, 12, 11, 7, 12], people=[10, 11, 12, 7, 15, 13]),
    dict(  # 2 Innenstadt (Chinatown): Teal-Dunst gegen Signalrot und Lampion-Amber
        name="china16", pal=[
            (5, 8, 10), (12, 22, 28), (22, 38, 48), (34, 58, 70), (52, 86, 104), (92, 128, 144),
            (150, 26, 36),     # 6  Blut / dunkles Rot
            (230, 40, 48),     # 7  Signalrot
            (250, 146, 52),    # 8  Lampion-Amber
            (148, 172, 170),   # 9  Pale (Grau-Teal)
            (255, 255, 255),   # 10 Weiß
            (30, 104, 104),    # 11 Teal tief
            (70, 220, 214),    # 12 Cyan-Neon
            (176, 246, 236),   # 13 Cyan-Spitzlicht
            (160, 110, 82),    # 14 Hautton
            (255, 196, 150),   # 15 warmes Spitzlicht
        ], neon=[12, 12, 7, 7, 13, 8], people=[12, 13, 7, 8, 15, 9]),
    dict(  # 3 Hafen: Asch-Blau im Nebel gegen Natrium
        name="harbor16", pal=[
            (6, 8, 10), (16, 20, 26), (28, 34, 42), (44, 52, 62), (66, 78, 90), (100, 114, 126),
            (140, 152, 162),   # 6  Asche
            (190, 198, 204),   # 7  helle Asche
            (255, 255, 255),   # 8  Weiß
            (120, 40, 34),     # 9  Rost / Blut
            (110, 62, 34),     # 10 dunkles Natrium
            (196, 108, 46),    # 11 Natrium
            (255, 162, 66),    # 12 Amber
            (255, 214, 152),   # 13 Amber-Spitzlicht
            (70, 120, 150),    # 14 kaltes Blau
            (128, 180, 208),   # 15 Asch-Blau-Spitzlicht
        ], neon=[12, 12, 11, 15, 13], people=[12, 13, 15, 14, 7]),
    dict(  # 4 Tyrell: Gold gegen tiefes Blau (das Büro im Abendlicht)
        name="tyrell16", pal=[
            (4, 5, 10), (12, 14, 24), (22, 26, 42), (36, 40, 62), (56, 64, 94), (96, 106, 140),
            (130, 30, 30),     # 6  Blut
            (100, 62, 30),     # 7  Bronze dunkel
            (170, 110, 46),    # 8  Bronze
            (240, 170, 70),    # 9  Gold
            (255, 222, 150),   # 10 Gold-Spitzlicht
            (220, 214, 200),   # 11 Pale
            (255, 255, 255),   # 12 Weiß
            (60, 110, 200),    # 13 Blau
            (130, 180, 255),   # 14 Blau-Spitzlicht
            (100, 190, 220),   # 15 Eis-Cyan
        ], neon=[9, 10, 11, 14, 9], people=[9, 10, 14, 15, 11]),
]

PALETTES = {"noir16": NOIR16, "cga16": CGA16}
for _z in ZONE_LOOK:
    PALETTES[_z["name"]] = _z["pal"]
DEFAULT_PALETTE = "noir16"

# Aktive Dither-Palette; die Szene setzt sie beim Zonenwechsel (render/scene.py),
# GPU- und Software-Pfad lesen sie pro Frame.
ACTIVE = {"palette": DEFAULT_PALETTE}


def zone_look(zone_index):
    return ZONE_LOOK[zone_index % len(ZONE_LOOK)]


def zone_colors(zone_index, key):
    z = zone_look(zone_index)
    return [z["pal"][i] for i in z[key]]

# Fenster-Auflösungen im Einstellungsmenü (im Vollbild gilt die Bildschirmauflösung).
RESOLUTIONS = [(1280, 720), (1366, 768), (1600, 900), (1920, 1080), (2560, 1440), (3840, 2160)]

# Wie weit der Bayer-Schwellwert eine Farbe verschiebt, bevor sie auf den nächsten
# Paletteneintrag schnappt. Größer = sichtbareres Dithering zwischen Nachbarfarben.
DITHER_SPREAD = 0.24

# Bayer-Matrix-Ordnung: 3 -> 8x8 (feine Muster), 2 -> 4x4 (gröber), 1 -> 2x2.
DITHER_ORDER = 3

# Farbkorrektur vor dem Dither (GPU): tiefe Schwärzen, satte Neon-Lichter
# (Referenz: The Last Night). Contrast = Anteil S-Kurve, Lift < 0 drückt den Schwarzpunkt.
GRADE_CONTRAST = 0.36
GRADE_SATURATION = 1.22
GRADE_LIFT = -0.025

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
NPC_DEPTH_MIN = 0.02    # Passanten dürfen bis an die Hauswand (hinterer Gehweg)
SIDEWALK = (0.02, 0.09) # hinterer Gehweg: Flaneure und Gruppen vor den Läden
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
JUMP_V = 150.0           # Scheitel ~17.6 u: über Baken und Tonnen, nicht über Wracks
GRAVITY = 640.0
JUMP_SAFE_Z = 5.0        # ab dieser Höhe gehen Schläge/Sprungangriffe ins Leere

# Ruf (V): „LAPD! Alle runter!“ - Menge geht in Deckung, Schüsse gehen über Geduckte
# V tippen = Ansprache (nur das Ziel), V halten = Ruf an die Menge (Radius wächst).
SHOUT_TAP = 0.3           # kürzer gedrückt = Ansprache
SHOUT_CHARGE = 1.0        # so lange bis zum vollen Radius
SHOUT_RADIUS = (70.0, 160.0)   # Radius beim Loslassen: min .. max (u, Tiefe zählt mit)
SHOUT_SPEED = 240.0       # Ausbreitung der Rufwelle u/s (wer weiter weg ist, reagiert später)
SHOUT_CD = 10.0           # Abklingzeit Menge s
SHOUT_DUCK = (3.2, 4.6)   # so lange bleiben sie unten / reglos
SHOUT_SCATTER = 0.15      # Anteil Menschen, die lieber wegrennen (+ Unruhe)
SHOUT_ALERT = 0.3         # x Zonen-Fluchtrate: Replikant fühlt sich ertappt (Menge)
TALK_RANGE = 110.0        # Ansprache: Reichweite
TALK_CD = 2.5
TALK_ALERT = 0.45         # Ansprache ist direkter: Replikanten fühlen sich eher ertappt
UNREST_PER_SHOUT = 0.34   # jeder Ruf macht die Straße unruhiger ...
UNREST_DECAY = 0.025      # ... und sie beruhigt sich langsam (pro s)

# Schwierigkeit: mehr Menschen je Viertel (Prior sinkt, Schusslinien voller)
DIFFICULTY = {
    "leicht": dict(density=0.7, label="LEICHT"),
    "normal": dict(density=1.0, label="NORMAL"),
    "schwer": dict(density=1.4, label="SCHWER"),
}
DIFFICULTY_ORDER = ["leicht", "normal", "schwer"]

# Ramen-Stand: kurz stehen bleiben füllt ein Herz auf (einmal pro Stand)
RAMEN_TIME = 1.2
RAMEN_RANGE = 26.0

# ----------------------------------------------------------------------------------
# Endboss ROY (letzte Zone, Tyrell)
# ----------------------------------------------------------------------------------

# Er redet - währenddessen unverwundbar - und verträgt zwischen den Sprüchen Treffer.
# Im Kampf: Sticheleien (während er redet, ist er unverwundbar).
ROY_TAUNTS = [
    "Nicht sehr sportlich, auf einen unbewaffneten Gegner zu schießen.",
    "Ich dachte, du wärst gut. Bist du nicht der Gute?",
    "Komm schon. Zeig mir, was du drauf hast!",
    "Stolz auf dich, kleiner Mann?",
]
# Nur wenn man ihn leben lässt: Hat er dich bis auf ein Herz geschlagen, lässt er ab.
# Schießt man dann nicht, spricht er - und stirbt von selbst. Eine Taube fliegt auf.
ROY_LINES = [
    "Ganz schön, in Angst zu leben, nicht wahr? Das heißt es, ein Sklave zu sein.",
    "Ich habe Dinge gesehen, von denen ihr Menschen nicht einmal träumt.",
    "Angriffsschiffe in Flammen vor der Schulter des Orion.",
    "Ich sah C-Strahlen glitzern im Dunkeln am Tannhäuser Tor.",
    "All diese Momente werden verloren sein in der Zeit - wie Tränen im Regen.",
    "Zeit zu sterben.",
]
ROY_PER_LINE = 2          # Treffer pro Stichelei (danach die nächste)
ROY_HP = len(ROY_TAUNTS) * ROY_PER_LINE
ROY_SPEAK_S = 2.6         # Redezeit je Stichelei
ROY_MONO_S = 4.2          # Redezeit je Satz des Monologs (er spricht langsam)
ROY_MERCY_HP = 1          # bei so vielen Herzen lässt er von dir ab
ROY_TRIGGER = 480.0       # Abstand zum Zonenende, ab dem er da steht
ROY_STAND = 240.0         # er steht so weit vor dem Zonenende (vor Sebastians Haus)
ROY_WAKE = 150.0          # kommt man ihm so nah, beginnt er
EMPTY_FROM = 0.72         # Tyrell: ab hier (Anteil der Länge) werden es immer weniger Menschen
EMPTY_TO = 560.0          # ... bis so weit vor dem Ende niemand mehr da ist

# ----------------------------------------------------------------------------------
# Straße: Fahrspuren, Verkehr, Hindernisse
# ----------------------------------------------------------------------------------

# Polizei-Spinner landen ab und zu auf dem Mittelstreifen (Kontrolle vom Boden aus)
SPINNER_LAND_CHANCE = 0.45
LAND_DEPTH = 0.525
LAND_DESCENT_S = 2.6
LAND_ASCENT_S = 2.2
LAND_TIME = (7.0, 10.0)
LAND_PUSH = 55.0          # Abwind: u/s am Landeplatz
LANES = ((0.32, -1), (0.74, 1))   # (Tiefe, Fahrtrichtung)
LANE_HALF = 0.085                 # halbe Spurbreite in Tiefe
TRAFFIC_REF = 12.0                # Abstand (s), bei dem Fahrzeuge volles Tempo fahren
TRAFFIC_GAP = 14.0                # Mindestabstand Stoßstange-Stoßstange in der Kolonne (u)
CAR_BRAKE = 300.0                 # Bremsverzögerung für Fußgänger vor dem Fahrzeug (u/s²)
CAR_DANGER_SPEED = 42.0           # ab diesem Tempo kann es vorn ernst werden (u/s)
CAR_BUMP_INVULN = 0.8             # nach einem Rempler kurz geschützt (s)
PARK_BANDS = ((0.165, 0.75), (0.925, 0.25))   # Parkstreifen (Tiefe, Anteil): hinten / vorn
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
POINTS_ORIGAMI = 250       # Gaffs Origami gefunden (+ Scanner voll)
COMBO_MAX = 5
SUSPICION_WATCHED = 1.5    # Faktor, wenn die Polizei-Patrouille dich im Suchlicht hat
