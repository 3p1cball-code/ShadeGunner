"""Übersetzung Deutsch/Englisch.

Schlüssel ist der deutsche Text (wie im Quelltext), Wert die englische Fassung.
`tr()` übersetzt exakt; mit Argumenten wird ein Template formatiert. Fehlt ein
Eintrag, bleibt der deutsche Text stehen (kein Absturz).

Die Sprache liegt als Modulzustand an und wird beim Start aus den Einstellungen
gesetzt (`settings["lang"]`).
"""

_LANG = "de"


def get_lang():
    return _LANG


def set_lang(lang):
    global _LANG
    _LANG = "en" if lang == "en" else "de"


def tr(s, *args, **kw):
    """Text übersetzen (de->en) und, falls Argumente da sind, als Template füllen."""
    txt = s if _LANG == "de" else TR.get(s, s)
    if args or kw:
        try:
            txt = txt.format(*args, **kw)
        except (IndexError, KeyError, ValueError):
            pass
    return txt


def lang_name(lang):
    return "ENGLISH" if lang == "en" else "DEUTSCH"


TR = {
    # ---------------------------------------------------------------- Titel
    "ENTER  NEUER EINSATZ": "ENTER  NEW ASSIGNMENT",
    "H  STEUERUNG      S  EINSTELLUNGEN      ESC  ENDE": "H  CONTROLS      S  SETTINGS      ESC  QUIT",
    "BESTWERT {:06d}  RANG {}  EINSÄTZE {}": "BEST {:06d}  RANK {}  RUNS {}",
    "REPLIKANTEN SIND WIE JEDE ANDERE MASCHINE.": "REPLICANTS ARE LIKE ANY OTHER MACHINE.",

    # ---------------------------------------------------------------- Welt-Markierungen
    "FLÜCHTET": "FLEEING",
    "ANGRIFF!": "ATTACK!",
    "IN DER LINIE!": "IN THE LINE!",
    "ERGIBT SICH": "SURRENDERS",
    "(REDET)": "(SPEAKING)",

    # ---------------------------------------------------------------- Warnungen
    "→ FAHRZEUG": "→ VEHICLE",
    "FAHRZEUG ←": "VEHICLE ←",
    "SPINNER LANDET - ABSTAND HALTEN": "SPINNER LANDING - KEEP CLEAR",
    "POLIZEIKONTROLLE AM BODEN": "POLICE CHECKPOINT ON THE GROUND",
    "IM SUCHLICHT - DIE POLIZEI SIEHT ZU": "IN THE SPOTLIGHT - POLICE IS WATCHING",
    "SUCHLICHT: AUGENREFLEXE WERDEN SICHTBAR": "SPOTLIGHT: EYE REFLEXES VISIBLE",
    "STROMAUSFALL": "BLACKOUT",
    "IM DUNKELN LEUCHTEN REPLIKANTENAUGEN": "REPLICANT EYES GLOW IN THE DARK",
    "STEHEN BLEIBEN": "STAND STILL",

    # ---------------------------------------------------------------- Panels
    "SEKTOR": "SECTOR",
    "SEKTOR {}/5": "SECTOR {}/5",
    "SEKTOR {} / 5": "SECTOR {} / 5",
    "AUFTRAG": "MISSION",
    "REST {}": "LEFT {}",
    "PUNKTE": "SCORE",
    "KETTE X{}": "COMBO X{}",
    "KOPFGELD  {}": "BOUNTY  {}",
    "KASSIERT ✓": "COLLECTED ✓",
    "ENTKOMMEN ✗": "ESCAPED ✗",
    "INTEGRITÄT": "INTEGRITY",
    "VERDACHT": "SUSPICION",
    "RUF  V": "SHOUT  V",
    "BEREIT": "READY",
    "HALTEN": "HOLD",
    "UNRUHE": "UNREST",
    "AUSGANG OFFEN": "EXIT OPEN",
    "AUSGANG GESPERRT": "EXIT LOCKED",
    "RUF LÄDT NOCH - LOSLASSEN BRICHT AB": "SHOUT STILL CHARGING - RELEASE CANCELS",
    "LOSLASSEN: ALLE RUNTER!   RADIUS {:3d}%": "RELEASE: EVERYONE DOWN!   RADIUS {:3d}%",
    "TIPPEN = ZIEL ANSPRECHEN   HALTEN = MENGE": "TAP = ADDRESS TARGET   HOLD = CROWD",
    "      C / RMT = ABBRECHEN": "      C / RMB = CANCEL",
    "SCHUSSLINIE BLOCKIERT": "LINE OF FIRE BLOCKED",
    "ZIEL ERFASST - LOSLASSEN = FEUER": "TARGET LOCKED - RELEASE = FIRE",
    "ZIELEN...": "AIMING...",
    "KEIN ZIEL - SCHUSS GERADEAUS": "NO TARGET - STRAIGHT SHOT",
    "H HILFE  P PAUSE": "H HELP  P PAUSE",

    # ---------------------------------------------------------------- Ziel-Panel
    "KEIN ZIEL  (MAUS / Q / TAB)": "NO TARGET  (MOUSE / Q / TAB)",
    "SUBJEKT #{:04d}": "SUBJECT #{:04d}",
    "SCAN {:3d}%": "SCAN {:3d}%",
    "GESCANNT": "SCANNED",
    "BEOBACHTE": "OBSERVE",
    "AUFFÄLLIG": "SUSPICIOUS",
    "UNAUFFÄLLIG": "NORMAL",
    "? SCAN": "? SCAN",
    "? BEOBACHTEN": "? OBSERVE",
    "? NAHSCAN": "? CLOSE SCAN",
    "NAHSCAN": "CLOSE SCAN",
    "P(REP)": "P(REP)",
    "PUPILLE": "PUPIL",
    "REIZ": "STIMULUS",
    "SERIE": "SERIAL",
    "GANG": "GAIT",
    "DETAIL": "DETAIL",

    # ---------------------------------------------------------------- Einstellungen
    "EINSTELLUNGEN": "SETTINGS",
    "MUSIK": "MUSIC",
    "EFFEKTE": "SFX",
    "VOLLBILD": "FULLSCREEN",
    "AUFLÖSUNG": "RESOLUTION",
    "SCANLINES": "SCANLINES",
    "RENDERER": "RENDERER",
    "SCHWIERIGKEIT": "DIFFICULTY",
    "SPRACHE": "LANGUAGE",
    "AN": "ON",
    "AUS": "OFF",
    "QUALITÄT": "QUALITY",
    "HOCH": "HIGH",
    "MITTEL": "MEDIUM",
    "NIEDRIG": "LOW",
    "REFLEXIONEN": "REFLECTIONS",
    "REGEN": "RAIN",
    "VIEL": "HEAVY",
    "WENIG": "LIGHT",
    "NEBEL": "FOG",
    "FX": "FX",
    "▲ MEHR": "▲ MORE",
    "▼ MEHR": "▼ MORE",
    "WENIGER EFFEKTE = MEHR BILDER PRO SEKUNDE": "FEWER EFFECTS = MORE FRAMES PER SECOND",
    "LEICHT": "EASY",
    "NORMAL": "NORMAL",
    "SCHWER": "HARD",
    "DEUTSCH": "DEUTSCH",
    "RENDERER WECHSELT MIT DEM NÄCHSTEN START": "RENDERER CHANGES ON NEXT START",
    "MEHR MENSCHEN JE VIERTEL - GILT AB DEM NÄCHSTEN EINSATZ": "MORE PEOPLE PER BLOCK - FROM NEXT RUN",
    "▲▼  WÄHLEN      ← →  ÄNDERN      ESC / S  ZURÜCK": "▲▼  SELECT      ← →  CHANGE      ESC / S  BACK",

    # ---------------------------------------------------------------- Pause
    "PAUSE": "PAUSE",
    "P / ESC  WEITER      S  EINSTELLUNGEN      H  HILFE      Q  ZUM TITEL":
        "P / ESC  RESUME      S  SETTINGS      H  HELP      Q  TO TITLE",

    # ---------------------------------------------------------------- Sektor-Abschluss
    "AUFTRAG VERFEHLT": "MISSION FAILED",
    "SEKTOR GESÄUBERT": "SECTOR CLEARED",
    "REPLIKANTEN DEAKTIVIERT": "REPLICANTS DEACTIVATED",
    "MENSCHEN GETÖTET": "CIVILIANS KILLED",
    "ENTKOMMEN": "ESCAPED",
    "SCANS / SCHÜSSE": "SCANS / SHOTS",
    "ZEIT": "TIME",
    "NICHT GEFUNDEN": "NOT FOUND",
    "PUNKTE (SEKTOR)": "SCORE (SECTOR)",
    "ENTER  WEITER": "ENTER  CONTINUE",
    "AUSRÜSTUNG WÄHLEN": "CHOOSE EQUIPMENT",
    "1-3 / PFEILE + ENTER": "1-3 / ARROWS + ENTER",
    "HUHN": "CHICKEN", "STREICHHOLZMANN": "MATCHSTICK MAN", "SCHAF": "SHEEP",
    "KRANICH": "CRANE", "EINHORN": "UNICORN",

    # ---------------------------------------------------------------- Ende
    "TYRELL HQ ERREICHT": "TYRELL HQ REACHED",
    "ALL DIESE MOMENTE WERDEN VERLOREN SEIN": "ALL THOSE MOMENTS WILL BE LOST",
    "IN DER ZEIT, SOWIE TRÄNEN IM REGEN.": "IN TIME, LIKE TEARS IN RAIN.",
    "EINSATZ BEENDET": "RUN OVER",
    "VERDACHT ZU HOCH - DIENSTMARKE ENTZOGEN": "SUSPICION TOO HIGH - BADGE REVOKED",
    "INTEGRITÄT VERLOREN": "INTEGRITY LOST",
    "SEKTOR ERREICHT": "SECTOR REACHED",
    "REPLIKANTEN": "REPLICANTS",
    "MENSCHEN": "CIVILIANS",
    "RANG {}": "RANK {}",
    "NEUER BESTWERT!": "NEW BEST!",
    "ENTER  ZUM TITEL     R  SOFORT NEU": "ENTER  TO TITLE     R  RESTART NOW",

    # ---------------------------------------------------------------- Intro
    "AUFTRAG: {} VON {} REPLIKANTEN DEAKTIVIEREN": "MISSION: DEACTIVATE {} OF {} REPLICANTS",
    "TARNUNG": "CAMOUFLAGE",
    "AGGRESSION": "AGGRESSION",
    "PASSANTEN CA. {}": "PASSERSBY ~{}",
    "QUOTE {}%": "QUOTA {}%",
    "KOPFGELD +{}: {}": "BOUNTY +{}: {}",
    "  (ZÄH: 2 TREFFER)": "  (TOUGH: 2 HITS)",
    "BELIEBIGE TASTE": "PRESS ANY KEY",

    # ---------------------------------------------------------------- Zonen
    "Außenbezirk": "Outskirts",
    "Vorstadt": "Suburbs",
    "Innenstadt": "Downtown",
    "Hafen": "Harbor",
    "Tyrell": "Tyrell",

    # ---------------------------------------------------------------- ROY
    "Nicht sehr sportlich, auf einen unbewaffneten Gegner zu schießen.":
        "Not very sporting to fire on an unarmed opponent.",
    "Ich dachte, du wärst gut. Bist du nicht der Gute?":
        "I thought you were supposed to be good. Aren't you the good man?",
    "Komm schon. Zeig mir, was du drauf hast!": "Come on. Show me what you're made of!",
    "Stolz auf dich, kleiner Mann?": "Proud of yourself, little man?",
    "Ganz schön, in Angst zu leben, nicht wahr? Das heißt es, ein Sklave zu sein.":
        "Quite an experience to live in fear, isn't it? That's what it is to be a slave.",
    "Zeit zu sterben.": "Time to die.",
    "ROY lässt von dir ab.": "ROY lets go of you.",
    "Er hat dir das Leben gerettet.": "He saved your life.",
    "ROY HAT DICH VERSCHONT": "ROY SPARED YOU",
    "SIE HABEN GANZE ARBEIT GELEISTET, SIR.": "YOU'VE DONE A MAN'S JOB, SIR.",
    "SCHADE, DASS ER NICHT LEBEN WIRD.": "TOO BAD HE WON'T LIVE.",
    "ABER WER LEBT SCHON?": "BUT THEN AGAIN, WHO DOES?",
    "(SCHWEIGT)": "(SILENT)",
    "Ich habe Dinge gesehen, von denen ihr Menschen nicht einmal träumt.":
        "I've seen things you people wouldn't believe.",
    "Angriffsschiffe in Flammen vor der Schulter des Orion.":
        "Attack ships on fire off the shoulder of Orion.",
    "Ich sah C-Strahlen glitzern im Dunkeln am Tannhäuser Tor.":
        "I watched C-beams glitter in the dark near the Tannhäuser Gate.",
    "All diese Momente werden verloren sein in der Zeit - wie Tränen im Regen.":
        "All those moments will be lost in time, like tears in rain.",

    # ---------------------------------------------------------------- Upgrades
    "SCAN-AKKU": "SCAN CELL",
    "+2 SCAN-LADUNGEN": "+2 SCAN CHARGES",
    "SCHNELLSCAN": "QUICK SCAN",
    "SCANS 45% KÜRZER": "SCANS 45% FASTER",
    "TIEFENSCAN": "DEEP SCAN",
    "SCAN ZEIGT ALLE TELLS, SERIE AUF DISTANZ": "SCAN SHOWS ALL TELLS, SERIAL AT RANGE",
    "FELDBLICK": "FIELD VISION",
    "BEOBACHTUNG DOPPELT SO SCHNELL": "OBSERVATION TWICE AS FAST",
    "PANZERWESTE": "BODY ARMOR",
    "+1 INTEGRITÄT, VOLL GEHEILT": "+1 INTEGRITY, FULLY HEALED",
    "LAUFSCHUHE": "RUNNING SHOES",
    "+20% TEMPO": "+20% SPEED",
    "RUHIGE HAND": "STEADY HAND",
    "SOFORT SCHIESSEN, KEINE ZIELZEIT": "FIRE INSTANTLY, NO AIM TIME",
    "KALTES BLUT": "COLD BLOOD",
    "FEHLER KOSTEN 35% WENIGER VERDACHT": "MISTAKES COST 35% LESS SUSPICION",
    "PEILSENDER": "TRACKER",
    "FLÜCHTENDE SIND 30% LANGSAMER": "FLEEING ONES 30% SLOWER",
    "INSTINKT": "INSTINCT",
    "AUGENREFLEXE DOPPELT SO HÄUFIG": "EYE REFLEXES TWICE AS COMMON",
    "MEGAFON": "MEGAPHONE",
    "RUF ALLE 6 S STATT 12, 35% WEITER": "SHOUT EVERY 6S INSTEAD OF 12, 35% WIDER",

    # ---------------------------------------------------------------- Sprechblasen / Funk
    "REGLOS": "MOTIONLESS",
    "REIZ: NORMAL": "STIMULUS: NORMAL",
    "ZU WEIT": "TOO FAR",
    "ABGEWEHRT": "DEFLECTED",
    "ZÄH! NOCH EINMAL": "TOUGH! AGAIN",
    "VOR DEN AUGEN DER POLIZEI": "IN FRONT OF THE POLICE",
    "REMPLER": "BUMP",
    "AUSGEWICHEN": "DODGED",
    "SUCHLICHT: AUGENREFLEX": "SPOTLIGHT: EYE REFLEX",
    "SUCHLICHT: AUGEN NORMAL": "SPOTLIGHT: EYES NORMAL",
    "AUGENREFLEX IM DUNKELN": "EYE REFLEX IN THE DARK",
    "AUGENREFLEX!": "EYE REFLEX!",
    "FUTATSU DE JUBUN!": "FUTATSU DE JUBUN!",
    "IRASSHAI! PLATZ FREI!": "IRASSHAI! SEAT'S FREE!",
    "RAMEN  +1 ♥": "RAMEN  +1 ♥",
    "MENSCH  {}": "HUMAN  {}",
    "REPLIKANT +{}": "REPLICANT +{}",
    "KETTE X{}": "COMBO X{}",
    "KOPFGELD {} +{}": "BOUNTY {} +{}",
    "KETTE X{}": "COMBO X{}",
    "KOPFGELD {} +{}": "BOUNTY {} +{}",
    "ORIGAMI: {}  +{}": "ORIGAMI: {}  +{}",
    "{}: AUFFÄLLIG": "{}: SUSPICIOUS",
    "{}: NORMAL": "{}: NORMAL",
    "ANGEFAHREN! -1": "HIT BY CAR! -1",
    "-1 INTEGRITÄT": "-1 INTEGRITY",
    "LAPD! ALLE RUNTER!": "LAPD! EVERYONE DOWN!",
    "POLIZEI! KÖPFE RUNTER!": "POLICE! HEADS DOWN!",
    "BLADE RUNNER! IN DECKUNG!": "BLADE RUNNER! TAKE COVER!",
    "RUNTER! SOFORT!": "DOWN! NOW!",
    "SIE DA! STEHEN BLEIBEN!": "YOU THERE! HALT!",
    "HALT! POLIZEI!": "STOP! POLICE!",
    "HEY! SIE! HÄNDE HOCH!": "HEY! YOU! HANDS UP!",
    "KEINE BEWEGUNG!": "DON'T MOVE!",
    "ICH HAB NICHTS GETAN!": "I DIDN'T DO ANYTHING!",
    "WAS WOLLEN SIE?": "WHAT DO YOU WANT?",
    "NICHT SCHIESSEN!": "DON'T SHOOT!",
    "ICH WOHN HIER!": "I LIVE HERE!",
    "BIN NUR AUF DEM HEIMWEG": "JUST HEADING HOME",
    "HAB MEINEN AUSWEIS NICHT DABEI": "DON'T HAVE MY ID ON ME",
    "OKAY, OKAY!": "OKAY, OKAY!",
    "Scan abgebrochen.": "Scan aborted.",
    "Waffe gesenkt - Schuss abgebrochen.": "Weapon lowered - shot cancelled.",
    "Ausgang gesperrt: Auftrag {}/{}.": "Exit locked: mission {}/{}.",
    "Niemand in Rufweite angesprochen.": "Nobody within shout range.",
    "Ruf: {} in Deckung, {} reglos, {} rennen.": "Shout: {} in cover, {} motionless, {} running.",
    "Keine Scan-Ladung.": "No scan charge.",
    "Ziel zu weit für den Scan - näher ran.": "Target too far to scan - get closer.",
    "ROY deaktiviert.": "ROY deactivated.",
    "Kopfgeld kassiert: {}.": "Bounty collected: {}.",
    "Replikant deaktiviert.": "Replicant deactivated.",
    "Auftrag erfüllt - Ausgang offen.": "Mission complete - exit open.",
    "MENSCH getötet! Verdacht steigt.": "CIVILIAN killed! Suspicion rising.",
    "Polizei-Spinner mit Suchlicht über der Straße.": "Police spinner with searchlight overhead.",
    "Polizei-Spinner setzt zur Landung an - Kontrolle!": "Police spinner coming in to land - checkpoint!",
    "Koch: Zwei reichen. (Integrität ist voll.)": "Cook: Two are enough. (Integrity full.)",
    "Koch: Akimashita! Ein Platz an der Theke ist frei.": "Cook: Akimashita! A seat at the counter is free.",
    "Am Nudelstand gestärkt: +1 Integrität.": "Refuelled at the noodle stand: +1 integrity.",
    "Gaff war hier. Scanner wieder voll geladen.": "Gaff was here. Scanner fully recharged.",
    "Stromausfall! Im Dunkeln leuchten Replikantenaugen.": "Blackout! Replicant eyes glow in the dark.",
    "Ein Replikant ist entkommen.": "A replicant escaped.",
    "Zone '{}' geschafft.": "Sector '{}' cleared.",

    # ---------------------------------------------------------------- Hilfe
    "STEUERUNG": "CONTROLS",
    "A D / PFEILE        GEHEN            SHIFT  SPRINTEN": "A D / ARROWS        WALK            SHIFT  SPRINT",
    "W S / PFEILE        TIEFE (VOR / ZURÜCK IN DER STRASSE)": "W S / ARROWS        DEPTH (FWD / BACK IN THE STREET)",
    "SPACE               SPRINGEN (ÜBER HINDERNISSE, SCHLÄGEN AUSWEICHEN)": "SPACE               JUMP (OVER OBSTACLES, DODGE BLOWS)",
    'V / MITTLERE MT     TIPPEN: ZIEL ANSPRECHEN   HALTEN+LOSLASSEN: "ALLE RUNTER!"':
        'V / MIDDLE MB       TAP: ADDRESS TARGET   HOLD+RELEASE: "EVERYONE DOWN!"',
    "MAUS ZEIGEN/KLICKEN ZIEL WÄHLEN    Q / TAB / RAD  ZIEL WECHSELN":
        "MOVE/CLICK MOUSE    PICK TARGET    Q / TAB / WHEEL  CYCLE TARGET",
    "R / RECHTE MT       GEWÄHLTES ZIEL SCANNEN (1 LADUNG)": "R / RIGHT MB        SCAN SELECTED TARGET (1 CHARGE)",
    "E / LINKE MT        HALTEN = ZIELEN, LOSLASSEN = SCHIESSEN": "E / LEFT MB         HOLD = AIM, RELEASE = FIRE",
    "C / RECHTE MT       SCHUSS ABBRECHEN (WAFFE SENKEN, KEIN SCHUSS)":
        "C / RIGHT MB        CANCEL SHOT (LOWER WEAPON, NO SHOT)",
    "P / ESC  PAUSE    F  VOLLBILD    M  TON    H  HILFE": "P / ESC  PAUSE    F  FULLSCREEN    M  SOUND    H  HELP",
    "REGELN": "RULES",
    "REPLIKANTEN SEHEN AUS WIE MENSCHEN. KEIN TELL BEWEIST ETWAS.":
        "REPLICANTS LOOK LIKE PEOPLE. NO TELL IS PROOF.",
    "BEOBACHTEN (ZIEL HALTEN) DECKT GANG UND DETAIL AUF.":
        "OBSERVING (HOLD TARGET) REVEALS GAIT AND DETAIL.",
    "AUGENREFLEX IM BLICK = PUPILLEN-TELL. SCAN ZEIGT DIE STARKEN TELLS,":
        "EYE REFLEX IN SIGHT = PUPIL TELL. SCAN SHOWS THE STRONG TELLS,",
    "DIE SERIENNUMMER NUR AUS DER NÄHE. P(REP) IST EHRLICH KALIBRIERT.":
        "THE SERIAL NUMBER ONLY UP CLOSE. P(REP) IS HONESTLY CALIBRATED.",
    "WER FLIEHT ODER ANGREIFT, VERRÄT SICH - MENSCHEN GREIFEN NIE AN.":
        "WHOEVER FLEES OR ATTACKS GIVES THEMSELVES AWAY - HUMANS NEVER ATTACK.",
    "PASSANTEN IN DER SCHUSSLINIE FANGEN DIE KUGEL. TIEFE WECHSELN!":
        "PASSERSBY IN THE LINE OF FIRE CATCH THE BULLET. CHANGE DEPTH!",
    "MENSCH GETÖTET = VERDACHT. BEI 100% IST DER EINSATZ VORBEI.":
        "HUMAN KILLED = SUSPICION. AT 100% THE RUN IS OVER.",
    "AUFTRAG ERFÜLLEN -> AUSGANG AM STRASSENENDE ÖFFNET SICH.":
        "COMPLETE THE MISSION -> THE EXIT AT THE END OPENS.",
    "KOPFGELD: DER BESCHRIEBENE NEXUS-6 BRINGT EXTRA - VORSICHT, DOPPELGÄNGER.":
        "BOUNTY: THE DESCRIBED NEXUS-6 PAYS EXTRA - BEWARE DOUBLES.",
    "FAHRZEUGE AUF DEN SPUREN AUSWEICHEN. SUCHLICHT UND STROMAUSFALL":
        "DODGE VEHICLES IN THE LANES. SPOTLIGHT AND BLACKOUT",
    "MACHEN AUGENREFLEXE SICHTBAR - ABER IM SUCHLICHT SIEHT DIE POLIZEI ZU.":
        "MAKE EYE REFLEXES VISIBLE - BUT IN THE SPOTLIGHT THE POLICE WATCH.",
    "RUF: WER REGLOS STEHEN BLEIBT, ZEIGT DEN REIZ-TELL. GEDUCKTE: DIE KUGEL GEHT DRÜBER.":
        "SHOUT: WHO STAYS STILL SHOWS THE STIMULUS TELL. DUCKING ONES: BULLETS GO OVER.",
    "JEDER RUF MACHT DIE STRASSE UNRUHIGER: MEHR LEUTE RENNEN, REPLIKANTEN WERDEN NERVÖS.":
        "EVERY SHOUT MAKES THE STREET RESTLESS: MORE RUN, REPLICANTS GET NERVOUS.",
    "LANDET EIN SPINNER: ABWIND SCHIEBT ALLE WEG, DANN KONTROLLE VOM BODEN AUS.":
        "IF A SPINNER LANDS: DOWNDRAFT PUSHES EVERYONE AWAY, THEN CHECK FROM THE GROUND.",
    "NUDELBAR: KURZ AN DER THEKE STEHEN = +1 HERZ.  GAFFS ORIGAMI: SCANNER VOLL.":
        "NOODLE BAR: STAND AT THE COUNTER = +1 HEART.  GAFF'S ORIGAMI: SCANNER FULL.",

    # ---------------------------------------------------------------- Beschreibung (Kopfgeld)
    "TRENCHCOAT": "TRENCHCOAT", "LANGER MANTEL": "LONG COAT", "JACKE": "JACKET",
    "KLEID": "DRESS", "REGENCAPE": "RAIN CAPE", "KUTTE": "ROBE", "KAPUZENPULLI": "HOODIE",
    "WESTE": "VEST", "ANZUG": "SUIT", "OVERALL": "OVERALLS",
    "KURZE HAARE": "SHORT HAIR", "LANGE HAARE": "LONG HAIR", "DUTT": "BUN", "HUT": "HAT",
    "KAPPE": "CAP", "KAPUZE AUF": "HOOD UP", "STROHHUT": "CONICAL HAT", "IROKESE": "MOHAWK",
    "GLATZE": "BALD", "MÜTZE": "BEANIE", "PFERDESCHWANZ": "PONYTAIL", "LEUCHTVISIER": "GLOW VISOR",
    "AFRO": "AFRO", "LEUCHTSCHIRM": "GLOWING UMBRELLA",
    "dunkelblau": "dark blue", "blau": "blue", "grau": "grey", "rot": "red", "türkis": "teal",
    "violett": "violet", "grün": "green", "hellblau": "light blue", "schwarz": "black", "gelb": "yellow",
    "weiß": "white", "pink": "pink", "orange": "orange",
}
