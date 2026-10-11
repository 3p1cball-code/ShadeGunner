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
| Space | springen |
| V / mittlere Maustaste | Ruf „LAPD! Alle runter!“ (§17) |
| C / rechte Maustaste (beim Zielen) | Schuss abbrechen |
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
**Vollbild**, **Auflösung** (Presets `config.RESOLUTIONS` 1280×720 … 3840×2160),
**Scanlines** (AN/AUS) und **Renderer** (GPU/Software). Im Fenster wird exakt die gewählte
Auflösung gesetzt und zentriert; im Vollbild gilt die Bildschirmauflösung. Persistiert als
`settings.json` neben dem Spielstand; Renderer-Wechsel greift beim nächsten Start.
`config`-unabhängige Werte, live angewandt (Audio-Volumes, CRT-Scan/Maske, Overlay).

ROY (§13) tritt jetzt erst auf, wenn die **Tyrell-Quote erfüllt** ist.

## 16. Blade-Runner-Ausbau: Fahrzeuge, Nudelbar, Spinner-Landung, Origami

**Fahrzeuge (Syd Mead).** Alle Bodenfahrzeuge in `render/vehicles.py` folgen Meads
Formensprache: verkleidete Räder, überbaute Lichtleisten, nachgerüstete Rohre. Der
Polizeiwagen ist ein **Spinner** am Boden (Kapsel-Kanzel über dem vorderen Viertel,
kugelige Radgondeln vor dem Bug, verdecktes Heck, Lichtbalken rot/blau live, roter
Unterboden). Dieselbe Zeichnung liefert `spinner_image()` für die fliegenden Spinner,
die Patrouille und die Landung (gecacht pro Pixelgröße/Richtung). Neu: **Bus**
(Zonen 2–4, Sound wie Laster).

**Nudelbar (White Dragon).** `city._ramen_booth` zeichnet die statische Bude
(Vordach, Noren, Menü-Täfelchen, Regal, Topf, Wok, Theke, sechs Hocker, Gäste von
hinten, Plastikvorhänge, Papierlaternen, Neon-Drache + RAMEN-Schild) und entfernt alles
Lebende der Häuser dahinter. `scene._ramen` lässt sie leben: Lichtpool, Glühbirnen
(eine mit Wackelkontakt), Koch (winkt, schüttelt das Sieb, reicht die Schale), die
flackernde rote Drachenzunge, Tropfen vom Vordach, Dampf. Der Hocker in der Mitte ist
frei – der Koch ruft „IRASSHAI! PLATZ FREI!“ bzw. bei voller Integrität
„FUTATSU DE JUBUN!“ (zwei reichen).

**Spinner-Landung.** Ab Zone 2 landet eine Patrouille mit `SPINNER_LAND_CHANCE` auf dem
Mittelstreifen (`LAND_DEPTH`): Anflug → Sinkflug (Abwind schiebt Figuren und Spieler
weg, Druckringe auf dem Wasserfilm, Gischt) → 7–10 s am Boden (Suchlicht vom Bug,
gleiche Regeln wie das Luft-Suchlicht: Augenreflexe sichtbar, Fehler kosten 1,5×
Verdacht; der Spinner ist ein nicht überspringbares Hindernis) → Abheben. Gezeichnet
wird er tiefensortiert zwischen den Figuren.

**Origami.** Eine Figur pro Zone (eigener Zufallsstrom, ändert die übrige Zone nicht)
neben der Fahrbahn; blinkt alle 2,4 s kurz auf. Aufheben: +`POINTS_ORIGAMI`, Scanner
voll. Zonen-Abschluss und Endbildschirm zeigen den Fund (x/5).

## 17. Dichte, Ruf, Hologramme, Musik

**Problem.** Mehr Menschen je Viertel sind der natürliche Schwierigkeitshebel: Der Prior
(Replikantenanteil) sinkt, Konfidenzen bleiben länger niedrig, Schusslinien sind
verstellt. Gewollt ist trotzdem ein *ruhiges* Spiel: alle sorgfältig beobachten.
Deshalb gibt es **keine Deko-Menge** – jede sichtbare Person ist ein Aktor.

**Drei Sorten Passanten** (`procgen.populate`, je Zone `density`/`sidewalk`/`groups`):
- *Straße:* gehen/stehen über die ganze Tiefe (wie bisher).
- *Gehweg:* Flaneure im Band `config.SIDEWALK` (Tiefe 0,02–0,09) direkt vor den Läden,
  also hinter der Spielertiefe – beobachtbar, scanbar, bleiben bei ihrem Band (`home`).
- *Gruppen:* 2–4 Leute im Kreis (`group`, `gx`), Zustand `loiter` (25–70 s), schauen
  zur Mitte und gestikulieren (Animation `talk`); danach zerstreuen sie sich.
Die Replikanten werden über *alle* Specs gezogen – Gruppenmitglied zu sein ist kein Indiz.
Innenstadt ≈ 127 Aktoren, Simulation ≈ 0,5 ms/Tick.

**Ansprechen (`V` tippen, < 0,3 s).** Nur das Ziel (Reichweite `TALK_RANGE`, CD 2,5 s):
Menschen drehen sich um und heben die Hände (`hands`), oft mit Antwort; wer den
**REIZ-Tell** hat, erstarrt (`freeze`, „REGLOS“). Gezielter Teilscan ohne Ladung, aber
Replikanten fühlen sich eher ertappt (`TALK_ALERT`).

**Ruf an die Menge (`V` halten, loslassen).** Radius wächst mit der Haltezeit
(`SHOUT_RADIUS` 70→160 in `SHOUT_CHARGE` s; MEGAFON ×1,35, CD halbiert). Der Ruf läuft
als **Welle** (`SHOUT_SPEED` 240 u/s, als Ring auf dem Asphalt sichtbar); jede Person
reagiert, wenn die Welle sie erreicht, plus eigener **Schrecksekunde** (`react_t`,
Ältere langsamer):
- REIZ-Tell → `freeze` (Tell aufgedeckt; Menschen zeigen ihn mit derselben Likelihood
  wie im Scan, P(REP) bleibt ehrlich).
- sonst → `duck` (Kugel geht drüber, `line_of_fire`) oder Flucht.
- **Unruhe** (`world.unrest`, +0,34 je Ruf, −0,025/s): mehr Menschen rennen statt zu
  ducken, Geduckte bleiben kürzer unten, Replikanten fühlen sich eher ertappt
  (`× (1 + 1,5·Unruhe)`). Dauerrufen macht die Straße also unbrauchbar.
Nach der Welle meldet der Funk die Bilanz („Ruf: 5 in Deckung, 1 reglos, 2 rennen“).

Bot (12 Runs, neue Dichte): mit Ruf 1×Verdacht/11×Zeitlimit, ohne Ruf ebenso – der
Bot ruft nur bei verstellter Linie und profitiert nach der Unruhe-Regel kaum; er ist
langsam (Zeitlimit), als Balance-Maß nur grob.

**Schwierigkeit** (Einstellungen): LEICHT/NORMAL/SCHWER = Menge ×0,7/×1,0/×1,4
(`config.DIFFICULTY`, skaliert alle drei Sorten), gilt ab dem nächsten Einsatz.

**Holografische Ballerinas** (`render/holo.py`). 3D-Skelett, das zwischen Ballettposen
interpoliert (Vorbereitung, Plié, doppelte Pirouette im Passé, Développé à la seconde,
Arme en couronne, Arabeske mit Promenade, Révérence; Zyklus 12,4 s) und um die Hochachse
dreht. Tutu als Scheibe mit mitdrehenden Falten. Gerendert mit 20 Hz in eine eigene
Textur, Scanline-Maske, Laufband, Aussetzer/Glitch, additiv in Szene und Glow.
Riesige im Mittel-Layer hinter der Häuserfront, kleine auf Projektorsockeln am Gehweg
(mit Spiegelung); im Stromausfall fallen sie aus.

**Musik je Zone** (`audio.zone_music`/`zone_pulse`, Cache `music_zN.wav`/`pulse_zN.wav`):
| Zone | Harmonik | Tempo | Musik | Rhythmus-Spur |
|---|---|---|---|---|
| Außenbezirk | Fm9 … (Titelthema) | frei | CS-80-Flächen, Lead, Glocken | – |
| Vorstadt | Dm9 Bbmaj7 Gm9 A7sus | 90 | + Achtel-Arpeggio | Herzschlag, leiser Shaker |
| Innenstadt | Ebm9 Bmaj7 Abm9 Bb7sus | 90 | + 16tel-Arpeggio, Chor | Kick, Hats, Achtel-Bass |
| Hafen | Cm(add9) Abmaj7 Fm9 G7sus | 112,5 | dunkler, Nebelhorn, Metall | + Snare im Hall, Metall, 16tel-Bass |
| Tyrell | F#m7 Dmaj7 Bm7 C#7 | 90 | voll, hell, Lead in 3 Abschnitten | + Snare, treibender 16tel-Bass |
Akkordlänge = ganze Zahl Schläge, Musik und Rhythmus haben dieselbe Länge → die
Rhythmus-Spur startet immer an der Position der Musik und bleibt taktgleich.
**Spannung** 0..1 (Zielen 0,55, Unruhe, Verdacht, Stromausfall, ROY, fliehender/
angreifender Replikant = 1) regelt den Rhythmus-Pegel zwischen Ruhe- und Vollwert
(`PULSE_LEVEL`); schnell rein, langsam raus. Zonenwechsel = 2,5-s-Überblendung; nur die
aktuelle Spur liegt im Speicher (je ~33 MB float32), alte werden entladen. Erzeugung im
Hilfsprozess ~60 s zusätzlich, beim ersten Start nach Zone 0 (fehlt eine Spur noch,
läuft die bisherige weiter). `DONE_TAG` erzwingt das Nachbauen auf alten Caches.

## 18. Verkehr, Parker, Dampf: es wird immer dichter

**Ziel.** Von Zone zu Zone mehr Gewimmel, bis man (wie im Film) die Übersicht verliert –
gewollt, kein Balancing-Fehler.

**Verkehr** (`sim._update_traffic`). Zonenwert `traffic` = mittlerer Abstand in s
(12 → 6,5 → 2,4 → 2,1 → 1,8), geteilt durch die Schwierigkeits-Dichte. Tempo-Faktor
`traffic_slow = clamp((gap / TRAFFIC_REF)^0,55, 0,35, 1)`: dichter Verkehr fährt langsamer
(Innenstadt ≈ 0,41 → ~55–75 u/s statt 170). Je Spur Kolonne: wer aufläuft, bremst auf das
Tempo des Vordermanns (Abstand `TRAFFIC_GAP + 0,9·vmax`), Stop-and-go durch haltende Taxis
und Parkplatzsucher. Wer >1,5 s steckt, hupt (`jam_honk`, leiser). Dichte Zonen starten
mit gefüllten Spuren (`_prefill_traffic`). Langsame Fahrzeuge (< 25 u/s) fahren niemanden
an. Anfahrtsgeräusch erst ~2,5 s vor der Kamera, höchstens 3 gleichzeitig.

**Parker** (`procgen.parked`, `parked` je 1000 u: 1,5 → 7). Feste Hindernisse
(`kind="parked"`, `veh`, `dir`) auf dem hinteren Parkstreifen (75 %) oder vorn an der
Kamera (25 %, verdeckt Sicht). Höhe = Fahrzeughöhe → nicht springbar; fliehende
Replikanten springen nur über Hindernisse < 13 u. Lichter gedimmt, 25 % Warnblinker,
geparkte Polizei mit Lichtbalken. Passanten, die beim Start in einem Parker stünden,
werden daneben gestellt (`_unstick`).

**Dampf** (`procgen.manholes`, `steam` je 1000 u: 1 → 3,2). Gullis auf/zwischen den Spuren,
30 % als gestreifter Con-Ed-Schlot (kleines Hindernis). Stärke atmet langsam, dazu
zufällige Schübe (alle 9–22 s). Gezeichnet als aufsteigende, wachsende, abdriftende
Ballen; unten hell und leicht emissiv (fängt Neon). **Spielwirkung:** `steam_at(x, d)` –
Beobachtung im Dampf bis zu 75 % langsamer.

**Leistung.** Hindernisse in einem x-Raster (`_obs_near`, 64-u-Zellen) – sonst kosten die
vielen Parker die Kollisionsabfragen; Innenstadt-Sim ≈ 0,85 ms. Szene je Zone
13–19 ms (CPU, 640×360).

**Fahrzeuge bremsen für Fußgänger** (`sim._update_traffic`). Steht der Spieler in der Spur
und vor dem Fahrzeug, bremst es mit `CAR_BRAKE` bis zum Stillstand (Bremsweg =
´sqrt(2·B·Restweg)`, Reaktion `react` je Fahrzeug: früh/nah langsamer, also gefährlicher).
Dabei hupt es (erneut alle 1,5 s). Frontale Berührung kostet nur noch mit Tempo über
`CAR_DANGER_SPEED` ein Herz; dann gibt es zusätzlich eine Rettungschance `World.car_escape`
(0,35 früh, 0,6 ab Innenstadt) – der Fahrer reißt in letzter Sekunde das Steuer herum,
hupt und du bekommst nur einen Rempler. Seitlich/stehend gerammt = `_car_bump`: kurzer
Stun (`hurt`, 0,3 s), Rückstoß, aus der Spur geschoben, **kein** Herzverlust, kurze
Schutzzeit (`CAR_BUMP_INVULN`). So ist der Verkehr früh schnell und gefährlich, ab der
Innenstadt vor allem ein Sicht- und Übersichtsproblem.

**Motorlautstärke** (`events "vehicle"` trägt einen Faktor). `vs = speed/170`,
`density_k = min(1, 3/N)` mit N = Fahrzeuge im Bild; leiser bei langsamem und dichtem
Verkehr (Außenbezirk ≈ 0,96, Innenstadt ≈ 0,19). Höchstens 4 Vorbeifahrten gleichzeitig.
Hupe lauter (`VOLUME["honk"] = 0,55`), neuer Rempler-Sound `bump`.

### Fahrzeug-Varianten (render/vehicles.py)

Fahrzeuge sind nicht mehr nur sechs Einheitsbilder. `_draw_vehicle` zieht aus dem Seed
eine Kombination aus: **Korpusfarbe** (je Art 6–10 Palettenwerte, zusätzlich per
`_tint` ±30 % Helligkeit gestreut), **Akzentfarbe** (`ACCENT`) und **Akzent-Stil**
(Zierlinie, Zweifarbdach, Schweller, Türdecal, Doppelstreifen), **Unterboden-Neon**
(`UNDERGLOW`) und **Schriftzug** (`LIVERY`: Tyrell, Shimata, Pan Am, Off-World, Nexus 6,
Eye Works, DNA Row, Kobayashi, Wallace …). Dazu Taxi-Dachschild (`TAXI/CAB/METRO`,
Farbe = Akzent), Bus-Werbeband in Akzentfarbe, Buslinie (`BUS_ROUTE`, z. B. „12 HADES“)
und Laster-Firmenaufschrift. Der Cache-Schlüssel nutzt `seed % VARIANTS` (16), der
Sprite-Cache leert bei > 1000 Einträgen. Mehr Draw-Aufwand nur beim Erzeugen (gecacht),
Szene-Zeit unverändert.

