# ShadeGunner — Design-Doc

> Arbeitstitel. 16-Farben-Cyberpunk-Sidescroller im Blade-Runner-Universum.
> Engine: `asciiplay`-Renderpfad (Bayer-Dither + CRT + Parallax), GPU über PyQt6/QtOpenGL.
> Dieses Dokument ist die Spezifikation, gegen die gebaut wird. Stand: 10.10.2026

---

## 1. Pitch

Du bist ein Blade Runner. Von den Außenbezirken von L.A. arbeitest du dich
durch immer dichtere Straßenschluchten bis ins Tyrell-HQ. Deine Aufgabe:
**Replikanten deaktivieren** — aber sie verstecken sich unter Menschen. Je
weiter du vordringst, desto mehr Passanten, desto besser getarnte Replikanten.

Der Reiz ist **die Entscheidung unter Unsicherheit**, nicht das Schießen:
Beobachten → Tells sammeln → scannen → entscheiden → mit den Folgen leben.

---

## 2. Kern-Loop

```
Straße durchqueren (Belt-Scroller)
   → verdächtige NPCs beobachten/scannen (Ressource: Scan-Ladungen)
   → Tells auswerten (Replikant vs. Mensch, mit Restunsicherheit)
   → deaktivieren (Belohnung) | falsch liegen (Suspicion/Strafe)
   → Auftrag (Quote) erfüllen → Ausgang am Straßenende öffnet sich
   → Upgrade wählen (1 aus 3, nur für diesen Run) → nächste Zone Richtung Tyrell HQ
```

**Run-Struktur:** ein Run = eine Route von Zone 0 (Außenbezirk) bis Zone 4
(Tyrell). Integrität 0 oder Verdacht 100 % beenden den Run. Persistent ist
(vorerst) nur der Highscore; ein globaler Skillbaum bleibt eine Option (§7).

---

## 3. Die Spielebene

Reine Seitenansicht scheidet aus: eine dichte Menge auf einer Linie wird in
16-Farben-Dither unlesbar, und genau die Menge ist die Mechanik.

**Gewählt: Belt-Scroller-Ebene** (Streets-of-Rage-Plane) mit kleinem Tiefen-
und Höhen-Offset. Figuren staffeln sich, man kann *in* der Menge stehen. Pro
NPC bleibt genug Fläche für Silhouette + einen Tell.

- Achse X: vorwärts/rückwärts durch die Straße
- Achse Y (Tiefe): vordere/ hintere Bahn (Schritt rein/raus) — echte
  Zentralperspektive (`persp.py`), Boden Mode-7-artig
- Achse Z: Sprunghöhe (seit 10.10.2026) — kein Platformer, sondern ein Verb:
  über Hindernisse, Schlägen und Nexus-Sprungangriffen ausweichen. Der Schatten
  bleibt am Boden und zeigt die Tiefe.

### 3a. Die Straße lebt (Abwechslung ohne neue Regeln)

| Element | Wirkung | Gegenspiel |
|---|---|---|
| **Verkehr** auf zwei Fahrspuren (Tiefe 0.32 / 0.74) | Treffer = −1 Integrität, Passanten weichen aus | HUD-Warnung „→ FAHRZEUG“ + Hupe, Spur wechseln |
| **Hindernisse** neben den Spuren (Absperrung, Kisten, Müll, Feuertonne, Automat) | blockieren den Weg, leuchten teils | springen oder außen herum; flüchtende Replikanten springen drüber |
| **Polizei-Suchlicht** (Spinner-Patrouille, ab Vorstadt) | Augenreflexe im Lichtkegel werden sichtbar | aber: im Licht kostet ein getöteter Mensch 1,5× Verdacht |
| **Stromausfall** (Zufall, 9 s) | Lichter aus, Replikantenaugen glühen, Reflexe auf Distanz | Taschenlampe; kurzes Zeitfenster |
| **Kopfgeld** (HODGE, LEON, ZHORA, PRIS, ROY) | benannter Nexus-6 mit Personenbeschreibung, +400; ab Innenstadt zäh (2 Treffer) und mit Doppelgänger | Beschreibung ist ein Hinweis, kein Beweis |
| **Sprungangriff** (aggressive Replikanten ab Innenstadt) | Satz auf den Spieler | springen oder Tiefe wechseln |

---

## 4. Tell- und Scan-System

Ein Replikant ist ein Sampling aus **Tells**; kein Tell ist für sich beweisend.

| Tell | Erkennbarkeit | Basis-Wahrscheinlichkeit (Replikant) |
|---|---|---|
| Verlangsamte Pupillenreaktion | Scan nötig | 0.55 |
| Anachronistisches Detail (Kleidung/Modelljahr) | Beobachtung | 0.30 |
| Körperspannung / Gait (zu gleichmäßig) | Beobachtung, Skill | 0.40 |
| Reaktion auf Reiz (Licht/Frage) | Aktiver Scan | 0.50 |
| Seriennummer-Fragment | Nur Nahbereich/Scan-Lv3 | 0.70 |

**Ablauf eines Urteils:**
1. Beobachten (kostenlos, wenige Sekunden) → schwache Tells.
2. Scannen (kostet 1 Ladung, kurze Standzeit) → starke Tells + Konfidenz-Anzeige.
3. Entscheidung: `deaktivieren` oder `passieren lassen`.
4. Konsequenz:
   - Replikant korrekt deaktiviert → Skillpunkte, „sauberer" Kill.
   - Mensch getötet → **Suspicion steigt stark**; zu viel → Run-Fehler.
   - Replikant entwischt → entkommt Richtung Stadtzentrum, zählt nicht.

**Konfidenz statt Wahrheit:** Der Skillbaum senkt Unsicherheit und Kosten,
macht Identifikation aber **nie sicher**. Es bleibt immer ein Restrisiko.

---

## 5. Eskalation (drei Achsen, lesbar)

1. **NPC-Dichte**: steigt von Außenbezirk → Innenstadt (mehr Rauschen).
2. **Tarntiefe der Replikanten**: weniger/undifferenziertere Tells, mehr
   Gegen-Tells (menschliche Zufälle, die einen Replikanten vortäuschen).
3. **Zeitdruck**: „Replikantenzahl" pro Zone begrenzt; entkommene Replikanten
   erhöhen den Druck.

Regel: Jede Steigerung muss dem Spieler erlauben, ein Scheitern *einer eigenen
Entscheidung* zuzuschreiben. Keine rohe Multiplikation ins Unfaire.

---

## 6. Zonen (authored macro) + Procgen (micro)

Feste Zonen-Sequenz mit eigener Identität; innerhalb der Zone prozedural
assemblierte Straßen/Begegnungen.

| # | Zone | Dichte | Replikanten | Farbklima |
|---|---|---|---|---|
| 0 | Außenbezirk / Gewerbe | niedrig | offensichtlich | kalt, leer |
| 1 | Vorstadt / Wohnblocks | mittel | gemischt | trüb, flackernd |
| 2 | Innenstadt / Neonmarkt | hoch | subtil | Neon, Regen |
| 3 | Industrie / Hafen | hoch | aggressiv | Rost, Dunst |
| 4 | Tyrell-Bezirk | maximal | Elite | clean, kalt-weiß |

Jede Zone: 2–4 Straßen (procgen Layout) + ein Abschluss-Event. Letzte Zone:
Tyrell-HQ.

---

## 7. Upgrades (pro Run) — Skillbaum (global) zurückgestellt

Umgesetzt: zwischen den Zonen 1 aus 3 Upgrades (Scan-Akku, Schnellscan,
Tiefenscan, Feldblick, Panzerweste, Laufschuhe, Ruhige Hand, Kaltes Blut,
Peilsender, Instinkt). Der globale Skillbaum unten ist weiterhin eine Option.

Ursprüngliche Idee: Beim Deaktivieren von Replikanten und beim sauberen Abschluss einer Zone gibt es
Skillpunkte. Gespeichert wird **global** (`~/.local/share/shadegunner/save.json`),
nicht pro Run.

Beispielzweige (jeder nur „mehr Werkzeug", nie „Garantie"):
- **Analyse**: mehr Scan-Ladungen, Scan-Reichweite, zusätzliche Tell-Anzeige,
  schnellere Konfidenz.
- **Beobachtung**: Gait-Erkennung, anachronistische Details hervorgehoben.
- **Einsatz**: schnellere Deaktivierung, weniger Suspicion bei Fehlern,
  Betäubung statt Tod (kein Kill, aber Replikant verliert sich).
- **Mut**: mehr Zonen pro Run, bessere Zonenbelohnung.

---

## 8. Renderpfad

Alles läuft durch die `asciiplay`-Pipeline:

```
CPU (QPainter, 640×360):  Himmel/Wolken -> Suchscheinwerfer -> Skyline fern/mittel
   (+ Luftstraßen, Billboards) -> Nebelschwaden -> Häuserfront (Läden, Neon + Lichthöfe)
   -> nasser Boden (Spiegelungen, Lichtkegel) -> Straßennebel -> Figuren/Fahrzeuge/
   Hindernisse tiefensortiert -> Stromausfall-Schleier -> Scheinwerfer, Suchlicht,
   Regen (im Lichtkegel hell) -> Glow-Pass (Leuchtschicht)
GPU:  Grading (S-Kurve, Sättigung, Schwarzpunkt) -> BAYER_FRAG (Palette, 8×8)
   -> HUD-Overlay (1280×720, ohne Dither) -> CRT-Kette (persist, focus, bloom, crt)
```

Palette `noir16`: Index 7 ist seit 10.10.2026 ein dunkles Natrium-Orange statt
eines Graus — ohne diesen Eintrag ditherte Laternenlicht rot statt orange.

- Palette: `noir16` (custom cyberpunk) als Default, `pal16` (CGA/EGA) optional.
- Dither-Zelle: 2–4 px (konfigurierbar), CRT-Kette aus `asciiplay` übernommen.
- Parallax: 2–4 Hintergrundbänder mit unterschiedlicher Scroll-Geschwindigkeit.

---

## 9. Lesbarkeitsregeln (16 Farben / Dither)

- NPC-Silhouetten müssen sich **auf Distanz** unterscheiden: klare Kontur,
  ein Farbakzent pro Figur (Kopfband/Jacke), kein Detailrauschen am Rand.
- Neon dient als Blickfang und Wegweiser, nicht als Fläche.
- Der Tell-Farbakzent ist im Bild **konsistent** (z. B. Cyanblitz am Auge).
- Vordergrund/Menge dunkel und ruhig halten; Replikanten-Hinweise hell/gesättigt.
- Scannbare NPCs bekommen ein dezentes Overlay, nie Vollflächen-Highlight.

---

## 10. Meilensteine

- **M0** Palette + Dither + Software-Preview (Look validieren). ✔
- **M1** Sim-Kern: Belt-Bewegung, Crowd, Procgen-Straße, Zonenwechsel. ✔
- **M2** Tells/Scan/Entscheidung/Konsequenz. ✔
- **M3** Upgrades pro Run + Highscore ✔ — globaler Skillbaum offen.
- **M4** GPU-Renderer (QtOpenGL, echte Shader) + Input + HUD. ✔
- **M5** Polish: Soundtrack + SFX ✔, Verkehr/Suchlicht/Stromausfall/Kopfgeld ✔,
  Balancing (laufend), weitere Ereignisse.

---

## 11. Steuerung

| Taste | Aktion |
|---|---|
| A/D, W/S (Pfeile) | gehen, Tiefe; Shift sprinten |
| Space / C | springen |
| Maus zeigen / klicken | Ziel wählen (Klick = genau diese Figur) |
| Q / Tab / Mausrad | Ziel wechseln |
| R / rechte Maustaste | gewähltes Ziel scannen (zu weit = Meldung, kein Umschwenken) |
| E / linke Maustaste | halten = zielen, loslassen = schießen |
| P/Esc, H, F, M | Pause, Hilfe, Vollbild, Ton |

## 12. Sound

Alles synthetisch (`audio.py`), beim ersten Start in einem Hilfsprozess nach
`~/.cache/shadegunner/audio-v2/` (~11 s, numpy): Vangelis-artiger Soundtrack
(CS-80-Flächen, Lead mit Portamento, FM-Glocken, Gong, zirkulärer Faltungshall
→ nahtloser 128-s-Loop), Stereo-Vorbeifahrten mit Doppler (Spinner, Auto, LKW,
Motorrad), Patrouille mit Sirene, Donner zum Blitz, Stromausfall/Wiederanlauf.
Wiedergabe über einen eigenen Software-Mixer auf einem einzigen `QAudioSink`
(nicht `QSoundEffect`: das öffnet je Effekt einen Strom mit der Medienrolle
"event", die PipeWire/WirePlumber auf System-Benachrichtigungslautstärke
herunterzieht).

## 13. Endboss ROY (Zone 5, Tyrell)

Kurz vor dem Zonenende tritt ROY auf (`config.ROY_TRIGGER`). Das Ausgangstor
bleibt gesperrt, bis er liegt. Er wechselt zwischen **Rede** (unverwundbar,
Sprung-Angriffe ausgesetzt) und **Kampf** (verwundbar); alle `ROY_PER_LINE`
Treffer folgt der nächste Satz aus `ROY_LINES` (das Monolog-Zitat). Insgesamt
`ROY_HP` = 4 Sätze × 2 Treffer. Über ihm steht dauerhaft „ROY", oben eine
Segment-Leiste, unten der Satz als Typewriter-Untertitel. Er greift mit dem
bestehenden Nexus-Verhalten an (Punch + Sprungangriff, per Sprung/Tiefe
ausweichbar) und flieht nie.

## 14. Renderpfade & Software-Fallback

Zwei Pfade teilen sich die Spiellogik (`game._GameMixin`):

- **`GameWidget` (OpenGL 3.3):** Standard. GPU macht Grading, Bayer-Dither, HUD-Overlay
  und die CRT-Kette (`render/shaders.py`).
- **`SoftwareGameWidget` (CPU):** Fallback, wenn kein OpenGL 3.3 verfügbar ist (VM,
  Server/RDP, alte/keine GPU) oder per `--software` / `SHADEGUNNER_SOFTWARE=1`.
  `render/sodither.py` spiegelt Grading und Palette des Shaders (6-Bit-Farb-LUT) und
  legt Scanlines + Vignette darüber.

`app.main` prüft per Offscreen-Kontext, ob OpenGL 3.3 geht, und wählt automatisch den
passenden Pfad. Der Software-Pfad lief verifiziert in einer GPU-losen Windows-VM.

## 15. Einstellungen (Grafik/Sound)

Eigener Screen (Titel/Pause mit `S`): **Musik**- und **Effekt**-Lautstärke (je 0–100 %),
**Vollbild**, **Scanlines** (AN/AUS) und **Renderer** (GPU/Software). Persistiert als
`settings.json` neben dem Spielstand; Renderer-Wechsel greift beim nächsten Start.
`config`-unabhängige Werte, live angewandt (Audio-Volumes, CRT-Scan/Maske, Overlay).

ROY (§13) tritt jetzt erst auf, wenn die **Tyrell-Quote erfüllt** ist.
