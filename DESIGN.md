# VOIGHT — Design-Doc

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
   → Skillpunkte → globaler Skillbaum (Tools/Verben, nie Freifahrtschein)
   → nächste Zone Richtung Tyrell HQ
```

**Run-Struktur:** ein Run = eine Route von Zone 0 (Außenbezirk) bis Zone N
(Tyrell). Tod/Abbruch beendet den Run; Skills und Freischaltungen bleiben.

---

## 3. Die Spielebene

Reine Seitenansicht scheidet aus: eine dichte Menge auf einer Linie wird in
16-Farben-Dither unlesbar, und genau die Menge ist die Mechanik.

**Gewählt: Belt-Scroller-Ebene** (Streets-of-Rage-Plane) mit kleinem Tiefen-
und Höhen-Offset. Figuren staffeln sich, man kann *in* der Menge stehen. Pro
NPC bleibt genug Fläche für Silhouette + einen Tell.

- Achse X: vorwärts/rückwärts durch die Straße
- Achse Y (Tiefe): vordere/ hintere Bahn (Schritt rein/raus)
- Achse Z: nur für Parallax-Hintergrund (2–4 Ebenen)

Höhe (Sprung) gibt es nicht — keine Plattform-Mechanik. Bewegung ist flüssig,
kein Pixel-Platformer.

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

## 7. Skillbaum (persistent, global)

Beim Deaktivieren von Replikanten und beim sauberen Abschluss einer Zone gibt es
Skillpunkte. Gespeichert wird **global** (`~/.local/share/voight/save.json`),
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
3D-Szene (Belt + Parallax)  ->  kleines Offscreen-FBO (Dither-Grid)
        -> BAYER_FRAG (mode 3, 16-Farben-Palette, Bayer 8×8)
        -> CRT-Kette (persist, focus, bloom, crt)
        -> Bildschirm
```

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

- **M0** Palette + Dither + Software-Preview (Look validieren).
- **M1** Sim-Kern: Belt-Bewegung, Crowd, Procgen-Straße, Zonenwechsel.
- **M2** Tells/Scan/Entscheidung/Konsequenz.
- **M3** Skillbaum + persistenter Save.
- **M4** GPU-Renderer (QtOpenGL, echte Shader) + Input + HUD.
- **M5** Polish: Sound, Neon-Animationen, Balancing, mehr Zonen.
