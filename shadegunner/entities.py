"""Aktoren der Spielwelt: Spieler, Passanten, Replikanten.

Reine Daten + einfache Bewegung. Die Spiel-Logik lebt in sim.World.
"""

from dataclasses import dataclass, field


@dataclass
class Actor:
    x: float
    depth: float                       # 0 = fern (Horizont), 1 = nah (Kamera)
    body: tuple = (26, 30, 50)
    accent: tuple = (64, 210, 220)

    is_replicant: bool = False
    player: bool = False
    alive: bool = True
    deactivated: bool = False
    escaped: bool = False

    vx: float = 0.0
    depth_v: float = 0.0

    # Tells: name -> bool (vorhanden). `revealed` = bereits aufgedeckt.
    tells: dict = field(default_factory=dict)
    revealed: set = field(default_factory=set)

    scanned: bool = False              # mindestens einmal gescannt
    exposure: float = 0.0              # Beobachtungszeit-Reservoir

    # Wanderung / Idle
    phase: float = 0.0
    speed: float = 0.0

    # Transiente Bildschirm-Markierung (z. B. Scan-Blitz), Farbe + Restzeit
    highlight: tuple = (0, 0, 0)
    highlight_t: float = 0.0
    uid: int = 0

    def mark(self, color, t=0.4):
        self.highlight = color
        self.highlight_t = t
