# ShadeGunner

16-Farben-Cyberpunk-Sidescroller im Blade-Runner-Universum. Als Blade Runner
arbeitest du dich von den Außenbezirken bis ins Tyrell-HQ und musst
**Replikanten unter Passanten erkennen, scannen und deaktivieren** – und mit den
Folgen deiner Entscheidungen leben.

Gebaut auf dem `asciiplay`-Renderpfad: Bayer-Dither gegen eine feste 16-Farben-
Palette plus CRT-Kette (Wölbung, Scanlines, Schattenmaske, Bloom, Nachleuchten).
Die Szene wird auf der CPU komponiert, Figuren und Sound sind prozedural, die
Post-Verarbeitung läuft auf der GPU. Python 3 + PyQt6.

## Screenshots

| | |
|---|---|
| ![Außenbezirk](screenshots/level0.png) | ![Vorstadt](screenshots/level1.png) |
| ![Innenstadt](screenshots/level2.png) | ![Hafen](screenshots/level3.png) |

![Tyrell](screenshots/level4.png)

## Kern-Loop

Beobachten → Ziel wählen → **scannen** (begrenzte Ladungen) → **Tell-Konfidenz**
(Naive Bayes, über den echten Replikantenanteil der Zone kalibriert) →
zielen/schießen (Passanten in der Schusslinie fangen die Kugel) → Quote erfüllen,
Ausgang öffnet sich → 1 aus 3 Upgrades. **Zivilisten töten ⇒ Verdacht** (ab 100 %
ist der Einsatz verloren).

- **Zonen:** Außenbezirk → Vorstadt → Innenstadt → Hafen → Tyrell.
- **Abwechslung:** Springen (über Hindernisse, Schlägen ausweichen), Verkehr auf zwei
  Fahrspuren, Polizei-Suchlicht (macht Augenreflexe sichtbar), Stromausfall,
  Kopfgeld-Replikanten und Ramen-Stände (füllen ein Herz auf).
- **Endboss:** In Tyrell tritt **ROY** auf. Er redet seine Sprüche (dabei
  unverwundbar) und verträgt zwischen den Sätzen Treffer. Das Tor öffnet erst,
  wenn er liegt.

## Steuerung

| Taste | Aktion |
|---|---|
| `A/D`, `W/S` (Pfeile) | gehen, Tiefe (nah/fern) |
| `Shift` | sprinten |
| `Space` | springen |
| Maus zeigen / klicken | Ziel wählen |
| `Q` / `Tab` / Mausrad | Ziel wechseln |
| `R` / rechte Maustaste | gewähltes Ziel scannen |
| `E` / linke Maustaste | halten = zielen, loslassen = schießen |
| `C` / rechte Maustaste | Schuss abbrechen (Waffe senken) |
| `P` Pause · `H` Hilfe · `F` Vollbild · `M` Ton | |

## Start

```bash
pip install -r requirements.txt
python3 -m shadegunner            # oder: tools/run.sh
```

Beim ersten Start wird der Soundtrack einmalig (~11 s) nach
`~/.cache/shadegunner/audio-v2/` erzeugt; danach startet es sofort.
Abschalten: `SHADEGUNNER_NOSOUND=1`.

## Windows

Zwei Wege:

1. **Aus dem Quelltext** – einmalig `install.bat` (installiert PyQt6 und numpy),
   danach starten mit `tools\run.bat`.
2. **Eigenständige `.exe`** (kein Python nötig, der Weg für Steam):
   `tools\build_windows.bat` baut mit PyInstaller `dist\ShadeGunner\ShadeGunner.exe`.
   Diesen kompletten Ordner an Steam ausliefern.
   Wichtig: PyInstaller kann eine Windows-`.exe` **nur auf Windows** erzeugen –
   der Build muss also auf einem Windows-Rechner laufen (die Spec `shadegunner.spec`
   liegt bei).

Auf Windows liegen Speicherstand unter `%APPDATA%\shadegunner\` und der
Klang-Cache unter `%LOCALAPPDATA%\shadegunner\`.

## Technik

- Interne (Dither-)Auflösung 640×360, wird per CRT/Anzeige hochskaliert.
- Palette `noir16` (eigene Noir-Palette) als Standard.
- Das Spiel selbst ist **numpy-frei**; numpy wird nur zur Klang-Erzeugung genutzt
  (mit Fallback ohne numpy).
- Tests: `python3 tests/test_sim.py` (Simulation, ohne GL).

## Werkzeuge

- `tools/glshot.py` – Offscreen-GPU-Render nach PNG (`--hud`, `--size=1920x1080`, …)
- `tools/playtest.py` – End-to-End mit echtem `GameWidget`
- `tools/autoplay.py` – Balancing-Bot
- `tools/spritesheet.py` – Sprite-Übersicht
