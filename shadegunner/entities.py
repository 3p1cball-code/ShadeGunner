"""Aktoren der Spielwelt: Spieler, Passanten, Replikanten.

Reine Daten. Verhalten (KI, Animation, Kampf) lebt in sim.World.
"""

from dataclasses import dataclass, field


@dataclass
class Actor:
    x: float
    depth: float                       # 0 = hinten (Bordstein), 1 = nah (Kamera)
    look: dict = field(default_factory=dict)
    uid: int = 0

    is_replicant: bool = False
    player: bool = False
    alive: bool = True
    dead_t: float = 0.0                # Sekunden seit Tod (Animation, Blutlache)
    escaped: bool = False

    facing: int = 1
    speed: float = 20.0                # bevorzugte Gehgeschwindigkeit
    vx: float = 0.0
    vd: float = 0.0
    target_depth: float = 0.5

    # Verhalten: walk | idle | loiter | panic | flee | attack | cower | duck | freeze | hands | hurt | dead
    #            Spieler: idle | walk | run | aim | shoot | scan | hurt | dead
    state: str = "walk"
    state_t: float = 0.0
    timer: float = 0.0                 # Restzeit des aktuellen Zustands
    anim: str = "walk"
    phase: float = 0.0                 # Animationsphase 0..1 (zyklisch)
    frame: int = 0
    hit_done: bool = True

    # Tells: name -> bool (vorhanden). `revealed` = bereits aufgedeckt.
    tells: dict = field(default_factory=dict)
    revealed: set = field(default_factory=set)
    scanned: bool = False
    exposure: float = 0.0
    alert: bool = False                # Replikant weiß, dass er erkannt wurde
    aggressive: bool = False
    aimed_t: float = 0.0               # wie lange der Spieler schon auf ihn zielt

    glint_t: float = 0.0               # Restzeit Augenreflex
    glint_next: float = 5.0
    flash_t: float = 0.0               # Treffer-Blitz
    knock: float = 0.0                 # Rückstoß-Geschwindigkeit
    hp: int = 1
    invuln: float = 0.0
    attack_cd: float = 0.0

    boss: bool = False                 # Endboss (ROY)
    boss_invuln: bool = False

    z: float = 0.0                     # Sprunghöhe (Welt-Einheiten)
    vz: float = 0.0
    dodge_t: float = 0.0               # weicht gerade Verkehr aus (schnelle Tiefenbewegung)
    lit_t: float = 0.0                 # Sekunden im Suchlicht
    bounty: bool = False               # Kopfgeld-Ziel der Zone
    name: str = ""
    group: int = -1                    # Gruppe, die zusammen herumsteht (-1 = allein)
    home: tuple = None                 # bevorzugtes Tiefenband (lo, hi), z. B. hinterer Gehweg
    gx: float = 0.0                    # Gruppenmitte (x), der Blick geht dorthin
    react_t: float = 0.0               # Reaktionslatenz (Schreck, Alter)
