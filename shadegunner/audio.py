"""Synthetischer Sound: alles prozedural erzeugt, als WAV gecacht, via QtMultimedia gespielt.

Kein Asset. Die Erzeugung läuft beim ersten Start in einem *eigenen Prozess*
(`python -m shadegunner.audio --build DIR`), damit das Spiel nicht unter dem GIL
ruckelt, und schreibt nach ~/.cache/shadegunner/audio-v2/:

  - Soundtrack (Stereo, ~2 min, nahtlos): Vangelis-artig - CS-80-Bläserflächen aus
    verstimmten Sägezähnen mit "Wah"-Blende, Solo-Lead mit Portamento und
    verzögertem Vibrato, FM-Glocken, Sub-Drone, tiefe Gongschläge; Hall per
    zirkulärer FFT-Faltung (dadurch läuft auch der Nachhall nahtlos über den Loop).
  - Stereo-Vorbeifahrten mit Doppler: Spinner, Autos, Laster, Motorräder.
  - Effekte: Blaster, Scan, Treffer, Sprung, Hupe, Donner, Stromausfall, Sirene ...

numpy wird nur hier (und nur zur Erzeugung) benutzt; fehlt es, gibt es die alte
einfache Klangfläche und die Basiseffekte. Abschalten: SHADEGUNNER_NOSOUND=1 / Taste M.
"""

import math
import os
import random
import subprocess
import sys
import wave
from array import array

SR = 22050
MSR = 32000            # Abtastrate Musik/Stereo
VERSION = "audio-v2"
DONE_TAG = "ok-zones1"     # ändern, wenn neue Klänge dazukommen -> Hilfsprozess baut nach


def cache_dir():
    if os.name == "nt":   # Windows: %LOCALAPPDATA%
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    d = os.path.join(base, "shadegunner", VERSION)
    os.makedirs(d, exist_ok=True)
    return d


def _write(path, samples, sr=SR):
    peak = max(1e-6, max(abs(s) for s in samples))
    k = 0.89 / peak if peak > 0.89 else 1.0
    data = array("h", (int(max(-1.0, min(1.0, s * k)) * 32767) for s in samples))
    tmp = path + ".tmp"
    with wave.open(tmp, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())
    os.replace(tmp, path)


def _env(i, n, a=0.005, r=None):
    t = i / SR
    dur = n / SR
    e = min(1.0, t / a) if a > 0 else 1.0
    if r is not None:
        e *= max(0.0, 1.0 - max(0.0, t - (dur - r)) / r)
    return e


# ====================================================================== einfache Effekte (stdlib)

def sfx_shot():
    n = int(SR * 0.42)
    rng = random.Random(1)
    out, ph, lp = [], 0.0, 0.0
    for i in range(n):
        t = i / SR
        f = 120 + 1400 * math.exp(-t * 26)
        ph += 2 * math.pi * f / SR
        tone = math.sin(ph) * math.exp(-t * 9)
        nz = rng.uniform(-1, 1)
        lp += (nz - lp) * 0.35
        noise = lp * math.exp(-t * 18)
        thump = math.sin(2 * math.pi * 55 * t) * math.exp(-t * 14)
        out.append((0.55 * tone + 0.6 * noise + 0.7 * thump) * _env(i, n, 0.002))
    return out


def sfx_beeps(freqs, dur=0.07, gap=0.03, vol=0.45, wave_="sine"):
    out = []
    for f in freqs:
        n = int(SR * dur)
        for i in range(n):
            t = i / SR
            ph = 2 * math.pi * f * t
            s = math.sin(ph) if wave_ == "sine" else (1.0 if math.sin(ph) > 0 else -1.0) * 0.5
            out.append(s * vol * math.exp(-t * 18) * _env(i, n, 0.003))
        out.extend([0.0] * int(SR * gap))
    return out


def sfx_scan():
    n = int(SR * 0.75)
    out = []
    ph = 0.0
    for i in range(n):
        t = i / SR
        f = 700 + 1100 * (t / 0.75) + 60 * math.sin(2 * math.pi * 18 * t)
        ph += 2 * math.pi * f / SR
        trem = 0.5 + 0.5 * math.sin(2 * math.pi * 24 * t)
        out.append(math.sin(ph) * 0.3 * trem * _env(i, n, 0.02, 0.1))
    return out


def sfx_tone(f0, f1, dur, vol=0.5, square=False, decay=3.0):
    n = int(SR * dur)
    out, ph = [], 0.0
    for i in range(n):
        t = i / SR
        f = f0 + (f1 - f0) * (t / dur)
        ph += 2 * math.pi * f / SR
        s = math.sin(ph)
        if square:
            s = 0.6 if s > 0 else -0.6
        out.append(s * vol * math.exp(-t * decay) * _env(i, n, 0.004, 0.03))
    return out


def sfx_dissonant():
    n = int(SR * 1.1)
    out = []
    for i in range(n):
        t = i / SR
        s = (math.sin(2 * math.pi * 110 * t) + math.sin(2 * math.pi * 116.5 * t) +
             0.5 * math.sin(2 * math.pi * 164 * t))
        out.append(s * 0.3 * math.exp(-t * 2.2) * _env(i, n, 0.01, 0.1))
    return out


def sfx_hurt():
    n = int(SR * 0.35)
    rng = random.Random(4)
    out, lp = [], 0.0
    for i in range(n):
        t = i / SR
        lp += (rng.uniform(-1, 1) - lp) * 0.12
        s = (0.7 if math.sin(2 * math.pi * (90 - 40 * t) * t) > 0 else -0.7) * 0.5 + lp * 1.2
        out.append(s * math.exp(-t * 8) * _env(i, n, 0.002))
    return out


def sfx_noise_burst(dur, lp_k, decay, vol=0.6, seed=9, thump=0.0, f_thump=60.0):
    n = int(SR * dur)
    rng = random.Random(seed)
    out, lp = [], 0.0
    for i in range(n):
        t = i / SR
        lp += (rng.uniform(-1, 1) - lp) * lp_k
        s = lp * math.exp(-t * decay) + thump * math.sin(2 * math.pi * f_thump * t) * math.exp(-t * 10)
        out.append(s * vol * _env(i, n, 0.004))
    return out


def rain_loop(dur=4.0):
    n = int(SR * dur)
    rng = random.Random(7)
    raw, lp, lp2 = [], 0.0, 0.0
    for i in range(n):
        x = rng.uniform(-1, 1)
        lp += (x - lp) * 0.22
        lp2 += (lp - lp2) * 0.5
        s = lp2 * 0.5
        if rng.random() < 0.0016:
            s += rng.uniform(0.3, 0.7)
        raw.append(s)
    fade = int(SR * 0.5)
    out = raw[: n - fade]
    for i in range(fade):
        k = i / fade
        out[i] = raw[i] * k + raw[n - fade + i] * (1 - k)
    return out


def music_pad_simple():
    """Fallback ohne numpy: kurze, langsame Moll-Fläche."""
    chords = [[146.83, 220.0, 293.66, 349.23], [116.54, 233.08, 293.66, 349.23],
              [130.81, 196.0, 261.63, 329.63], [110.0, 220.0, 261.63, 329.63]]
    seg = 6.0
    n_seg = int(SR * seg)
    total = n_seg * len(chords)
    out = [0.0] * total
    rng = random.Random(11)
    for ci, ch in enumerate(chords):
        start = ci * n_seg
        for f in ch:
            ph, lp = rng.random(), 0.0
            for i in range(n_seg + SR):
                t = i / SR
                ph = (ph + f / SR) % 1.0
                lp += ((2 * ph - 1) - lp) * 0.04
                a = min(1.0, t / 2.0) * (1.0 if t < seg else max(0.0, 1 - (t - seg)))
                out[(start + i) % total] += lp * a * 0.1
    return out


BASIC = {
    "shot": sfx_shot,
    "scan": sfx_scan,
    "scan_done": lambda: sfx_beeps((880, 1320), 0.09, 0.02, 0.4),
    "target": lambda: sfx_beeps((1900,), 0.025, 0.0, 0.2),
    "tell": lambda: sfx_beeps((1250, 1650), 0.05, 0.01, 0.3),
    "kill_rep": lambda: sfx_beeps((660, 880, 1320), 0.08, 0.01, 0.4),
    "kill_civ": sfx_dissonant,
    "hurt": sfx_hurt,
    "escape": lambda: sfx_tone(700, 180, 0.6, 0.35, True, 2.5),
    "gate": lambda: sfx_beeps((220, 220), 0.12, 0.06, 0.4, "square"),
    "quota": lambda: sfx_beeps((523, 659, 784, 1046), 0.09, 0.0, 0.4),
    "clear": lambda: sfx_beeps((392, 523, 659, 784, 1046), 0.13, 0.02, 0.45),
    "fail": lambda: sfx_tone(400, 60, 1.4, 0.45, True, 1.2),
    "ui": lambda: sfx_beeps((1320,), 0.04, 0.0, 0.3),
    "no": lambda: sfx_beeps((180,), 0.12, 0.0, 0.4, "square"),
    "alert": lambda: sfx_beeps((990, 740, 990, 740), 0.06, 0.01, 0.35, "square"),
    "jump": lambda: sfx_noise_burst(0.22, 0.25, 14, 0.35, seed=21),
    "land": lambda: sfx_noise_burst(0.16, 0.08, 22, 0.6, seed=22, thump=0.6, f_thump=70),
    "tough": lambda: sfx_beeps((1480, 1110), 0.05, 0.0, 0.45, "square"),
    "leap": lambda: sfx_noise_burst(0.35, 0.18, 7, 0.45, seed=23),
    "car_hit": lambda: sfx_noise_burst(0.6, 0.05, 6, 0.9, seed=24, thump=1.0, f_thump=48),
    "honk": lambda: sfx_beeps((311, 247), 0.22, 0.03, 0.5, "square"),
    "bump": lambda: sfx_noise_burst(0.18, 0.12, 18, 0.5, seed=25, thump=0.5, f_thump=90),
    "bounty": lambda: sfx_beeps((392, 494, 587, 784), 0.12, 0.0, 0.45),
    "ramen": lambda: sfx_beeps((523, 659, 784, 1046), 0.1, 0.02, 0.42),
    "boss": lambda: sfx_tone(150, 52, 1.8, 0.5, True, 0.8),
    "shout": lambda: sfx_tone(420, 980, 0.42, 0.5, True, 1.4),
    "talk": lambda: sfx_tone(700, 940, 0.16, 0.4, True, 5.0),
    "rain": rain_loop,
}

# ====================================================================== numpy-Synthese


def _np_sounds():
    """Name -> (Erzeuger, Abtastrate, Stereo?) für alles, was numpy braucht."""
    import numpy as np

    rs = np.random.default_rng(1919)

    def saw(freq, sr):
        ph = np.cumsum(freq / sr) % 1.0
        return 2.0 * ph - 1.0

    def fft_lp(x, cut, sr, q=1.0):
        X = np.fft.rfft(x)
        f = np.fft.rfftfreq(len(x), 1.0 / sr)
        X *= 1.0 / (1.0 + (f / cut) ** (2 * q))
        return np.fft.irfft(X, len(x))

    def fft_bp(x, lo, hi, sr):
        X = np.fft.rfft(x)
        f = np.fft.rfftfreq(len(x), 1.0 / sr)
        X *= 1.0 / (1.0 + (lo / np.maximum(f, 1.0)) ** 4) / (1.0 + (f / hi) ** 4)
        return np.fft.irfft(X, len(x))

    def env_ar(n, sr, a, r, hold=None):
        t = np.arange(n) / sr
        e = np.minimum(1.0, t / max(a, 1e-4))
        if hold is not None:
            e *= np.clip(1.0 - (t - hold) / max(r, 1e-4), 0.0, 1.0)
        return e

    def reverb_ir(sr, dur, seed, damp=2.2):
        n = int(sr * dur)
        r = np.random.default_rng(seed)
        t = np.arange(n) / sr
        ir = r.standard_normal(n) * np.exp(-t * (6.9 / dur))
        # hohe Frequenzen klingen schneller aus: zwei Bänder mischen
        dark = fft_lp(ir, 1800.0, sr)
        ir = dark + (ir - dark) * np.exp(-t * damp * 3)
        ir[:int(sr * 0.012)] *= np.linspace(0, 1, int(sr * 0.012))
        return ir / np.sqrt(np.sum(ir ** 2))

    def fft_conv(x, ir):
        n = len(x) + len(ir) - 1
        m = 1 << (n - 1).bit_length()
        return np.fft.irfft(np.fft.rfft(x, m) * np.fft.rfft(ir, m), m)[:len(x)]

    def circ_conv(x, ir):
        n = len(x)
        h = np.zeros(n)
        m = min(n, len(ir))
        h[:m] = ir[:m]
        return np.fft.irfft(np.fft.rfft(x) * np.fft.rfft(h), n)

    def stereo_out(L, R):
        st = np.stack([L, R], axis=1)
        st = np.tanh(st * 1.1) / np.tanh(1.1)
        return st / max(1e-6, np.max(np.abs(st))) * 0.9

    # ------------------------------------------------------------------ Soundtrack
    def soundtrack():
        sr = MSR
        bpm_s = 8.0                                   # Sekunden pro Akkord
        # f-Moll-Färbung, große langsame Flächen (Fm9 - Dbmaj7 - Bbm9 - C7sus4)
        chords = [
            [43.65, 87.31, 130.81, 174.61, 207.65, 261.63, 311.13, 392.0],
            [34.65, 69.30, 138.59, 174.61, 207.65, 261.63, 349.23],
            [29.14, 58.27, 116.54, 174.61, 233.08, 277.18, 349.23, 523.25],
            [32.70, 65.41, 130.81, 196.0, 233.08, 349.23, 392.0],
        ]
        sections = 4
        n_ch = len(chords) * sections
        N = int(sr * bpm_s * n_ch)
        L = np.zeros(N)
        R = np.zeros(N)
        seg = int(sr * bpm_s)

        def add(sig, start, pan=0.0, gain=1.0):
            gl = math.cos((pan + 1) * math.pi / 4) * gain
            gr = math.sin((pan + 1) * math.pi / 4) * gain
            pos, i = start % N, 0
            while i < len(sig):                       # zirkulär einfügen (Loop-Naht)
                m = min(len(sig) - i, N - pos)
                L[pos:pos + m] += sig[i:i + m] * gl
                R[pos:pos + m] += sig[i:i + m] * gr
                i += m
                pos = 0

        # --- CS-80-Bläserfläche
        for ci in range(n_ch):
            ch = chords[ci % len(chords)]
            sec = ci // len(chords)
            start = ci * seg
            n = seg + int(sr * 3.5)
            t = np.arange(n) / sr
            amp = env_ar(n, sr, 1.6, 3.2, hold=bpm_s)
            wah = np.clip(t / 1.4, 0, 1) * np.exp(-np.maximum(0, t - 1.4) * 0.6)
            for vi, f in enumerate(ch[1:]):
                vib = 1.0 + 0.0035 * np.sin(2 * math.pi * (5.1 + vi * 0.13) * t) * np.clip((t - 1.5) / 2.0, 0, 1)
                sig = np.zeros(n)
                for det in (-0.0042, 0.0, 0.0047):
                    sig += saw(f * (1 + det) * vib, sr)
                dark = fft_lp(sig, 420.0 + f * 0.6, sr)
                bright = fft_lp(sig, 2200.0 + f, sr)
                voice = (dark + (bright - dark) * (0.25 + 0.75 * wah)) * amp
                g = 0.045 * (0.75 if f > 300 else 1.0) * (0.8 if sec == 0 else 1.0)
                add(voice, start, pan=((vi % 4) - 1.5) * 0.35, gain=g)
            # Sub-Drone (Grundton)
            f0 = ch[0]
            drone = (np.sin(2 * math.pi * f0 * t) * 0.8 + 0.35 * fft_lp(saw(f0 * 2, sr), 220.0, sr)) * amp
            add(drone, start, 0.0, 0.16)

        # --- Gongschläge an den Abschnittsgrenzen (der tiefe "Boom" der Titelmusik)
        for sec in range(sections):
            start = sec * len(chords) * seg
            n = int(sr * 7.0)
            t = np.arange(n) / sr
            f = 38.0 * (1 + 0.6 * np.exp(-t * 3.0))
            body = np.sin(2 * math.pi * np.cumsum(f) / sr) * np.exp(-t * 0.65)
            metal = sum(np.sin(2 * math.pi * fr * t + p) * np.exp(-t * d)
                        for fr, p, d in ((113.0, 0.3, 0.9), (171.4, 1.1, 1.3), (236.2, 2.0, 1.8), (311.7, 0.7, 2.6)))
            hit = fft_lp(rs.standard_normal(n), 900.0, sr) * np.exp(-t * 9.0)
            add((body * 1.0 + metal * 0.18 + hit * 0.5) * env_ar(n, sr, 0.004, 1), start, 0.0, 0.32)

        # --- Solo-Lead (Portamento + verzögertes Vibrato), in Abschnitt 2 und 4
        melody = [  # (Akkord-Index im Abschnitt, Startbeat 0..7, Länge s, Frequenz)
            (0, 1.0, 3.5, 523.25), (0, 4.6, 3.2, 466.16), (1, 0.6, 2.4, 415.30), (1, 3.2, 4.4, 349.23),
            (2, 0.8, 2.2, 415.30), (2, 3.0, 2.0, 466.16), (2, 5.2, 3.0, 523.25), (3, 1.0, 6.5, 392.0),
        ]
        melody2 = [
            (0, 0.8, 2.6, 622.25), (0, 3.6, 4.0, 523.25), (1, 0.8, 3.0, 698.46), (1, 4.0, 3.6, 622.25),
            (2, 0.6, 2.4, 523.25), (2, 3.2, 4.2, 466.16), (3, 0.6, 3.0, 523.25), (3, 3.8, 4.0, 392.0),
        ]
        for sec, mel in ((1, melody), (3, melody2)):
            base = sec * len(chords) * seg
            notes = sorted(mel, key=lambda m: m[0] * 8 + m[1])
            total = int(sr * (len(chords) * bpm_s + 4))
            freq = np.zeros(total)
            gate = np.zeros(total)
            prev = notes[0][3]
            for (ci, beat, dur, f) in notes:
                s0 = int(sr * (ci * bpm_s + beat))
                s1 = min(total, s0 + int(sr * dur))
                glide = int(sr * 0.18)
                seg_f = np.full(s1 - s0, f)
                g = min(glide, s1 - s0)
                seg_f[:g] = np.linspace(prev, f, g)
                freq[s0:s1] = seg_f
                gate[s0:s1] = 1.0
                prev = f
            # Lücken mit dem letzten Ton füllen (für Release)
            last = notes[0][3]
            for i in range(0, total, 64):
                if freq[i] == 0:
                    freq[i:i + 64] = last
                else:
                    last = freq[i]
            freq[freq == 0] = last
            # Hüllkurve aus dem Gate: weicher Anstieg / Ausklang (Block-Glättung)
            k = int(sr * 0.25)
            kern = np.ones(k) / k
            amp = np.convolve(gate, kern, mode="same")
            # Vibrato setzt pro Ton verzögert ein
            onset = np.zeros(total)
            run = 0.0
            for i in range(0, total, 256):
                run = run + 256 / sr if gate[i] > 0 else 0.0
                onset[i:i + 256] = min(1.0, max(0.0, (run - 0.6) / 1.2))
            t = np.arange(total) / sr
            vib = 1.0 + 0.009 * onset * np.sin(2 * math.pi * 5.6 * t)
            fv = freq * vib
            lead = saw(fv, sr) * 0.6 + np.sign(np.sin(2 * math.pi * np.cumsum(fv * 0.5) / sr)) * 0.25
            lead = fft_lp(lead, 1900.0, sr) * amp
            add(lead, base, pan=0.15, gain=0.11)

        # --- FM-Glocken (fern, in Abschnitt 3 und 4)
        bell_notes = [1046.5, 932.3, 784.0, 698.5, 622.3, 523.3]
        for sec in (2, 3):
            base = sec * len(chords) * seg
            for k in range(14):
                st = base + int(sr * (k * 2.25 + 0.4))
                n = int(sr * 3.0)
                t = np.arange(n) / sr
                fc = bell_notes[(k * 5 + sec) % len(bell_notes)]
                idx = 2.6 * np.exp(-t * 2.2)
                b = np.sin(2 * math.pi * fc * t + idx * np.sin(2 * math.pi * fc * 3.5 * t)) * np.exp(-t * 1.6)
                add(b * env_ar(n, sr, 0.002, 1), st, pan=0.6 * (1 if k % 2 else -1), gain=0.035)

        # --- Hall (zirkulär -> nahtloser Loop), dazu leichtes Pre-Delay
        irL = reverb_ir(sr, 5.0, 3)
        irR = reverb_ir(sr, 5.0, 4)
        pre = int(sr * 0.03)
        irL = np.concatenate([np.zeros(pre), irL])
        irR = np.concatenate([np.zeros(pre), irR])
        wetL = circ_conv(L, irL)
        wetR = circ_conv(R, irR)
        outL = 0.8 * L + 0.62 * wetL
        outR = 0.8 * R + 0.62 * wetR
        return stereo_out(outL, outR)

    # ------------------------------------------------------------------ Vorbeifahrten (Doppler)
    def passby(dur, t0, src, pan_span=1.0, dist=0.35, sr=SR, rev=0.25):
        n = int(sr * dur)
        t = np.arange(n) / sr
        x = (t - t0) / (dur * 0.5)                      # -..+ Position relativ zum Hörer
        r = np.sqrt(x ** 2 + dist ** 2)
        vr = np.gradient(r) * sr * (dur * 0.5)          # Radialgeschw. (normiert)
        dop = 1.0 / (1.0 + 0.045 * vr)                  # Tonhöhe: höher beim Nähern
        gain = 1.0 / (r / dist) ** 1.25
        gain *= np.clip(t / 0.4, 0, 1) * np.clip((dur - t) / 0.5, 0, 1)
        sig = src(n, sr, dop, t) * gain
        pan = np.clip(x * pan_span, -1, 1)
        Lc, Rc = np.cos((pan + 1) * math.pi / 4), np.sin((pan + 1) * math.pi / 4)
        L, R = sig * Lc, sig * Rc
        ir = reverb_ir(sr, 1.6, 7)
        L = L + rev * fft_conv(L, ir)
        R = R + rev * fft_conv(R, reverb_ir(sr, 1.6, 8))
        return stereo_out(L, R)

    def spinner_src(n, sr, dop, t):
        noise = rs.standard_normal(n)
        roar = fft_bp(noise, 120.0, 1400.0, sr) * 1.2
        whine = sum(np.sin(2 * math.pi * np.cumsum(f * dop) / sr + p) * a
                    for f, p, a in ((880.0, 0.0, 0.25), (1330.0, 1.2, 0.18), (1760.0, 2.1, 0.08)))
        hum = np.sin(2 * math.pi * np.cumsum(62.0 * dop) / sr) * 0.5
        throb = 1.0 + 0.25 * np.sin(2 * math.pi * 7.0 * t)
        return (roar + whine + hum) * throb

    def car_src(f_eng, hiss_lo, hiss_hi, eng_amp):
        def f(n, sr, dop, t):
            noise = rs.standard_normal(n)
            hiss = fft_bp(noise, hiss_lo, hiss_hi, sr) * 1.4            # Reifen auf nassem Asphalt
            eng = fft_lp(saw(f_eng * dop, sr), f_eng * 4, sr) * eng_amp
            return hiss + eng
        return f

    def patrol():
        sr = SR
        n = int(sr * 7.0)
        t = np.arange(n) / sr
        noise = rs.standard_normal(n)
        hover = fft_bp(noise, 90.0, 900.0, sr) * (1.0 + 0.35 * np.sin(2 * math.pi * 9.0 * t))
        whine = np.sin(2 * math.pi * 740.0 * t) * 0.12
        siren_f = 620 + 180 * np.sin(2 * math.pi * 0.45 * t)
        siren = np.sin(2 * math.pi * np.cumsum(siren_f) / sr) * 0.18 * np.clip((t - 1.0) / 1.5, 0, 1)
        e = np.clip(t / 1.8, 0, 1) * np.clip((7.0 - t) / 2.0, 0, 1)
        sig = (hover + whine + fft_lp(siren, 1200, sr)) * e
        ir = reverb_ir(sr, 2.2, 9)
        L = sig + 0.4 * fft_conv(sig, ir)
        R = np.roll(sig, int(sr * 0.012)) + 0.4 * fft_conv(sig, reverb_ir(sr, 2.2, 10))
        return stereo_out(L, R)

    def thunder():
        sr = SR
        n = int(sr * 6.0)
        t = np.arange(n) / sr
        noise = rs.standard_normal(n)
        crack = fft_bp(noise, 300, 4000, sr) * np.exp(-np.maximum(0, t - 0.6) * 8) * (t > 0.6)
        rumble = fft_lp(noise, 160.0, sr) * 3.0
        rumble *= np.clip((t - 0.7) / 0.6, 0, 1) * np.exp(-np.maximum(0, t - 1.3) * 0.75)
        rumble *= 1.0 + 0.5 * np.sin(2 * math.pi * 1.3 * t) * np.sin(2 * math.pi * 0.37 * t)
        sig = crack * 0.4 + rumble
        L = sig
        R = np.roll(sig, int(sr * 0.02))
        return stereo_out(L, R)

    def blackout():
        sr = SR
        n = int(sr * 2.2)
        t = np.arange(n) / sr
        f = 120.0 * np.exp(-t * 1.6) + 20
        hum = (np.sin(2 * math.pi * np.cumsum(f) / sr) + 0.4 * np.sin(2 * math.pi * np.cumsum(f * 2) / sr))
        clunk = fft_lp(rs.standard_normal(n), 600, sr) * np.exp(-t * 18) * 1.5
        sig = (hum * np.exp(-t * 1.2) * 0.8 + clunk)
        return stereo_out(sig, np.roll(sig, 40))

    def power_up():
        sr = SR
        n = int(sr * 1.4)
        t = np.arange(n) / sr
        f = 30 + 90 * (1 - np.exp(-t * 2.5))
        hum = np.sin(2 * math.pi * np.cumsum(f) / sr) * np.clip(t / 0.3, 0, 1) * np.exp(-np.maximum(0, t - 0.9) * 4)
        buzz = np.sign(np.sin(2 * math.pi * 100 * t)) * 0.08 * (np.sin(t * 40) > 0.3)
        sig = hum * 0.7 + buzz * np.exp(-t * 2)
        return stereo_out(sig, sig)

    # ------------------------------------------------------------------ Zonen-Soundtracks
    # Zone 0 behält `soundtrack()`. Ab Zone 1 wird es mit der Straße dichter: mehr
    # Stimmen, Arpeggio, Chor, Industrie-Klänge; dazu je Zone eine *taktgleiche*
    # Rhythmus-Spur (pulse_zN), die das Spiel nach Spannung lauter/leiser mischt.
    def hz(n):                                  # MIDI-Note -> Hz
        return 440.0 * 2 ** ((n - 69) / 12)

    # Akkorde als MIDI: [Grundton(tief), Stimmen ...]
    ZT = {
        1: dict(seed=11, chord_s=8.0, bpm=90, cut=520.0, pad=0.040, arp=(8, 0.030), choir=0.0, bells=0.03,
                lead=(1, 3), clank=0.0, horn=0.0,
                chords=[[38, 50, 57, 62, 65, 69, 76], [34, 46, 58, 62, 65, 69, 74],
                        [31, 43, 58, 62, 65, 69, 74], [33, 45, 57, 62, 64, 67, 76]]),          # Dm9 Bbmaj7 Gm9 A7sus
        2: dict(seed=12, chord_s=8.0, bpm=90, cut=600.0, pad=0.038, arp=(16, 0.028), choir=0.030, bells=0.03,
                lead=(1, 3), clank=0.0, horn=0.0,
                chords=[[39, 51, 58, 63, 66, 70, 77], [35, 47, 59, 63, 66, 70, 75],
                        [32, 44, 59, 63, 66, 68, 75], [34, 46, 58, 63, 65, 68, 72]]),          # Ebm9 Bmaj7 Abm9 Bb7sus
        3: dict(seed=13, chord_s=6.4, bpm=112.5, cut=430.0, pad=0.036, arp=(16, 0.022), choir=0.024, bells=0.0,
                lead=(2,), clank=0.05, horn=0.10,
                chords=[[36, 48, 55, 60, 62, 63, 67], [32, 44, 55, 60, 63, 67, 72],
                        [29, 41, 56, 60, 63, 65, 72], [31, 43, 55, 60, 62, 65, 71]]),          # Cm(add9) Abmaj7 Fm9 G7sus
        4: dict(seed=14, chord_s=8.0, bpm=90, cut=760.0, pad=0.036, arp=(16, 0.026), choir=0.036, bells=0.035,
                lead=(1, 2, 3), clank=0.0, horn=0.0,
                chords=[[42, 54, 61, 66, 69, 73, 76], [38, 50, 62, 66, 69, 73, 78],
                        [35, 47, 59, 62, 66, 69, 78], [37, 49, 61, 65, 68, 71, 80]]),          # F#m7 Dmaj7 Bm7 C#7
    }

    class Bus:
        def __init__(self, n):
            self.N = n
            self.L = np.zeros(n)
            self.R = np.zeros(n)

        def add(self, sig, start, pan=0.0, gain=1.0):
            gl = math.cos((pan + 1) * math.pi / 4) * gain
            gr = math.sin((pan + 1) * math.pi / 4) * gain
            pos, i, N = int(start) % self.N, 0, self.N
            while i < len(sig):
                m = min(len(sig) - i, N - pos)
                self.L[pos:pos + m] += sig[i:i + m] * gl
                self.R[pos:pos + m] += sig[i:i + m] * gr
                i += m
                pos = 0

        def verb(self, dur, wet, seeds=(3, 4)):
            irL = reverb_ir(MSR, dur, seeds[0])
            irR = reverb_ir(MSR, dur, seeds[1])
            return self.L + wet * circ_conv(self.L, irL), self.R + wet * circ_conv(self.R, irR)

    def zone_len(c):
        return int(MSR * c["chord_s"] * len(c["chords"]) * 4)

    def lead_voice(bus, notes, total, base, gain):
        """Solo-Lead: Portamento, verzögertes Vibrato (wie im Titelthema)."""
        sr = MSR
        freq = np.zeros(total)
        gate = np.zeros(total)
        prev = notes[0][1]
        for (t0, f, dur) in notes:
            s0 = int(sr * t0)
            s1 = min(total, s0 + int(sr * dur))
            if s1 <= s0:
                continue
            g = min(int(sr * 0.18), s1 - s0)
            seg_f = np.full(s1 - s0, f)
            seg_f[:g] = np.linspace(prev, f, g)
            freq[s0:s1] = seg_f
            gate[s0:s1] = 1.0
            prev = f
        last = notes[0][1]
        for i in range(0, total, 64):
            if freq[i] == 0:
                freq[i:i + 64] = last
            else:
                last = freq[i]
        k = int(sr * 0.25)
        amp = np.convolve(gate, np.ones(k) / k, mode="same")
        onset = np.zeros(total)
        run = 0.0
        for i in range(0, total, 256):
            run = run + 256 / sr if gate[i] > 0 else 0.0
            onset[i:i + 256] = min(1.0, max(0.0, (run - 0.6) / 1.2))
        t = np.arange(total) / sr
        fv = freq * (1.0 + 0.009 * onset * np.sin(2 * math.pi * 5.6 * t))
        sig = saw(fv, sr) * 0.6 + np.sign(np.sin(2 * math.pi * np.cumsum(fv * 0.5) / sr)) * 0.25
        bus.add(fft_lp(sig, 1900.0, sr) * amp, base, pan=0.15, gain=gain)

    def zone_music(z):
        c = ZT[z]
        sr = MSR
        r = np.random.default_rng(c["seed"])
        cs = c["chord_s"]
        seg = int(sr * cs)
        chords = c["chords"]
        n_ch = len(chords) * 4
        N = zone_len(c)
        bus = Bus(N)
        beat = 60.0 / c["bpm"]
        for ci in range(n_ch):
            ch = chords[ci % len(chords)]
            sec = ci // len(chords)
            start = ci * seg
            n = seg + int(sr * 3.0)
            t = np.arange(n) / sr
            amp = env_ar(n, sr, 1.4, 2.8, hold=cs)
            wah = np.clip(t / 1.2, 0, 1) * np.exp(-np.maximum(0, t - 1.2) * 0.6)
            # Bläserfläche (CS-80): je dichter die Zone, desto mehr Stimmen/Verstimmung
            for vi, m in enumerate(ch[1:]):
                f = hz(m)
                vib = 1.0 + 0.0035 * np.sin(2 * math.pi * (5.0 + vi * 0.13) * t) * np.clip((t - 1.4) / 2.0, 0, 1)
                sig = sum(saw(f * (1 + d) * vib, sr) for d in (-0.005, -0.0015, 0.0018, 0.0052))
                dark = fft_lp(sig, c["cut"] + f * 0.6, sr)
                bright = fft_lp(sig, 2400.0 + f, sr)
                voice = (dark + (bright - dark) * (0.2 + 0.8 * wah)) * amp
                bus.add(voice, start, pan=((vi % 4) - 1.5) * 0.4, gain=c["pad"] * (0.75 if f > 300 else 1.0))
            f0 = hz(ch[0])
            drone = (np.sin(2 * math.pi * f0 * t) * 0.8 + 0.4 * fft_lp(saw(f0 * 2, sr), 240.0, sr)) * amp
            bus.add(drone, start, 0.0, 0.17)
            # Chor ("Aah"): Sägezähne durch zwei Formanten
            if c["choir"] > 0 and sec >= 1:
                for vi, m in enumerate(ch[2:6]):
                    f = hz(m)
                    src = sum(saw(f * (1 + d), sr) for d in (-0.006, 0.0, 0.006))
                    vox = fft_bp(src, 600, 1250, sr) + 0.5 * fft_bp(src, 2300, 3200, sr)
                    bus.add(vox * amp, start, pan=0.7 * (1 if vi % 2 else -1), gain=c["choir"])
            # Arpeggio aus den Akkordtönen (FM-Zupfen), ab Abschnitt 2 voller
            steps, g_arp = c["arp"]
            if steps and sec >= 1 - (z >= 3):
                step = beat * (4.0 / steps) * (1 if steps == 8 else 1)
                tones = sorted(ch[2:]) + [ch[3] + 12]
                k = 0
                tt = 0.0
                while tt < cs - 1e-6:
                    m = tones[(k * (3 if z % 2 else 2)) % len(tones)] + (12 if (k // 8) % 2 and z >= 2 else 0)
                    f = hz(m)
                    nn = int(sr * min(0.9, step * 3))
                    tn = np.arange(nn) / sr
                    pl = np.sin(2 * math.pi * f * tn + 1.8 * np.exp(-tn * 9) * np.sin(2 * math.pi * f * 2 * tn))
                    pl *= np.exp(-tn * (5.0 if steps == 16 else 3.2)) * np.minimum(1.0, tn / 0.003)
                    acc = 1.0 if k % 4 == 0 else 0.7
                    bus.add(pl, start + int(sr * tt), pan=0.45 * math.sin(k * 0.7), gain=g_arp * acc)
                    tt += step
                    k += 1
        # Gongschläge an den Abschnittsgrenzen
        for sec in range(4):
            n = int(sr * 7.0)
            t = np.arange(n) / sr
            f = hz(c["chords"][0][0]) * (1 + 0.6 * np.exp(-t * 3.0))
            body = np.sin(2 * math.pi * np.cumsum(f) / sr) * np.exp(-t * 0.65)
            metal = sum(np.sin(2 * math.pi * fr * t + ph) * np.exp(-t * d)
                        for fr, ph, d in ((113.0, 0.3, 0.9), (171.4, 1.1, 1.3), (236.2, 2.0, 1.8)))
            bus.add((body + metal * 0.18) * env_ar(n, sr, 0.004, 1), sec * len(chords) * seg, 0.0, 0.30)
        # Nebelhorn + Hafenmetall
        if c["horn"] > 0:
            for k in range(4):
                n = int(sr * 4.5)
                t = np.arange(n) / sr
                f = hz(c["chords"][0][0] + 12)
                hs = fft_bp(saw(f * (1 + 0.004 * np.sin(t * 3)), sr) + saw(f * 1.5, sr) * 0.4, 80, 700, sr)
                hs *= np.clip(t / 0.6, 0, 1) * np.clip((4.5 - t) / 1.5, 0, 1)
                bus.add(hs, int(sr * (k * cs * 4 + cs * 1.5)), pan=-0.7 if k % 2 else 0.7, gain=c["horn"])
        if c["clank"] > 0:
            for k in range(int(N / sr / 3.1)):
                n = int(sr * 1.6)
                t = np.arange(n) / sr
                base = r.uniform(180, 420)
                cl = sum(np.sin(2 * math.pi * base * q * t) * np.exp(-t * (3 + 2 * q))
                         for q in (1.0, 2.76, 5.4, 8.9))
                bus.add(cl, int(r.uniform(0, N)), pan=r.uniform(-0.9, 0.9), gain=c["clank"] * r.uniform(0.4, 1))
        # Glocken
        if c["bells"] > 0:
            for k in range(int(N / sr / 2.4)):
                st = int(sr * (k * 2.4 + 0.4))
                ci = (st // seg) % len(chords)
                m = chords[ci][2 + (k * 3) % (len(chords[ci]) - 2)] + 24
                n = int(sr * 3.0)
                t = np.arange(n) / sr
                fc = hz(m)
                b = np.sin(2 * math.pi * fc * t + 2.6 * np.exp(-t * 2.2) * np.sin(2 * math.pi * fc * 3.5 * t))
                bus.add(b * np.exp(-t * 1.6), st, pan=0.6 * (1 if k % 2 else -1), gain=c["bells"])
        # Solo-Lead: aus Akkordtönen gesetzte Phrasen, in den angegebenen Abschnitten
        for sec in c["lead"]:
            notes = []
            for ci in range(len(chords)):
                ch = chords[ci]
                pool = [m + 12 for m in ch[3:]]
                tt = 0.6 + r.uniform(0, 0.6)
                while tt < cs - 1.2:
                    d = r.choice((1.6, 2.2, 3.0, 3.6))
                    notes.append((ci * cs + tt, hz(int(r.choice(pool))), min(d, cs - tt)))
                    tt += d + r.choice((0.2, 0.4, 0.8))
            total = int(sr * (len(chords) * cs + 4))
            lead_voice(bus, notes, total, sec * len(chords) * seg, 0.10)
        L, R = bus.verb(5.0, 0.62 if z != 3 else 0.75)
        return stereo_out(0.8 * L, 0.8 * R)

    def zone_pulse(z):
        """Rhythmus-Spur, taktgleich zum Zonen-Track (gleiche Länge, gleiche Akkorde)."""
        c = ZT[z]
        sr = MSR
        N = zone_len(c)
        beat = 60.0 / c["bpm"]
        cs = c["chord_s"]
        dry, room = Bus(N), Bus(N)
        rr = np.random.default_rng(c["seed"] + 100)

        def kick():
            n = int(sr * 0.5)
            t = np.arange(n) / sr
            f = 44 + 70 * np.exp(-t * 28)
            return np.sin(2 * math.pi * np.cumsum(f) / sr) * np.exp(-t * 7.5) + \
                fft_lp(rr.standard_normal(n), 2500, sr) * np.exp(-t * 120) * 0.25

        def hat(dec=55.0):
            n = int(sr * 0.25)
            t = np.arange(n) / sr
            x = rr.standard_normal(n)
            return (x - fft_lp(x, 6500, sr)) * np.exp(-t * dec)

        def snare():
            n = int(sr * 0.6)
            t = np.arange(n) / sr
            return fft_bp(rr.standard_normal(n), 900, 5000, sr) * np.exp(-t * 14) + \
                np.sin(2 * math.pi * 185 * t) * np.exp(-t * 22) * 0.6

        def clank():
            n = int(sr * 0.5)
            t = np.arange(n) / sr
            return sum(np.sin(2 * math.pi * 310 * q * t) * np.exp(-t * (14 + 6 * q)) for q in (1, 2.76, 5.4))

        K, H, Ho, S, C = kick(), hat(), hat(14.0), snare(), clank()
        n_beats = int(round(N / sr / beat))
        bass_cache = {}
        for b in range(n_beats):
            t0 = b * beat
            pos = int(sr * t0)
            bar_beat = b % 4
            ci = int(t0 // cs) % len(c["chords"])
            root = c["chords"][ci][0]
            # Herzschlag (Vorstadt) / gerade Kick (ab Innenstadt)
            if z == 1:
                if bar_beat in (0, 2):
                    dry.add(K, pos, 0.0, 0.55)
                    dry.add(K, pos + int(sr * beat * 0.38), 0.0, 0.32)
                for e in range(2):
                    dry.add(hat(80.0), pos + int(sr * beat * e / 2), 0.35, 0.10 if e else 0.06)
                continue
            dry.add(K, pos, 0.0, 0.62)
            for e in range(4 if z >= 3 else 2):
                q = beat * e / (4 if z >= 3 else 2)
                acc = 0.16 if e % 2 else 0.08
                dry.add(H, pos + int(sr * q), 0.3 * (1 if e % 2 else -1), acc)
            if bar_beat == 2 and z == 2:
                dry.add(Ho, pos + int(sr * beat * 0.5), 0.25, 0.12)
            if z >= 3 and bar_beat in (1, 3):
                room.add(S, pos, 0.0, 0.40)
            if z == 3 and bar_beat in (1, 3):
                dry.add(C, pos + int(sr * beat * 0.75), -0.5, 0.18)
            # Bass-Sequenzer (Achtel, ab Hafen Sechzehntel): Grundton, Oktave, Quinte
            div = 4 if z >= 3 else 2
            for e in range(div):
                patt = (0, 12, 7, 12) if div == 4 else (0, 12)
                m = root + 12 + patt[e % len(patt)]
                if (m, div) not in bass_cache:
                    dur = beat / div * 0.95
                    n = int(sr * dur)
                    t = np.arange(n) / sr
                    f = hz(m)
                    x = saw(np.full(n, f), sr) + saw(np.full(n, f * 1.004), sr)
                    x = fft_lp(x, 260 + f * 3, sr) * np.exp(-t * 7) * np.minimum(1, t / 0.004)
                    x[-64:] *= np.linspace(1, 0, 64)
                    bass_cache[(m, div)] = x
                acc = 1.0 if e == 0 else 0.72
                dry.add(bass_cache[(m, div)], pos + int(sr * beat * e / div), 0.0, 0.20 * acc)
        L1, R1 = dry.verb(1.2, 0.18, (21, 22))
        L2, R2 = room.verb(3.5, 0.9, (23, 24))
        return stereo_out(L1 + L2, R1 + R2)

    out = {"music": (soundtrack, MSR, True), "patrol": (patrol, SR, True), "thunder": (thunder, SR, True),
           "blackout": (blackout, SR, True), "power_up": (power_up, SR, True)}
    for name, dur, t0, src, span in (
            ("spinner", 7.0, 3.4, spinner_src, 1.0),
            ("car", 4.2, 2.5, car_src(55.0, 900.0, 5200.0, 0.5), 1.0),
            ("truck", 5.0, 2.9, car_src(38.0, 500.0, 3000.0, 0.9), 1.0),
            ("bike", 3.4, 2.0, car_src(130.0, 1200.0, 6000.0, 0.6), 1.0)):
        for dname, sgn in (("lr", 1.0), ("rl", -1.0)):
            out[f"{name}_{dname}"] = (
                (lambda dur=dur, t0=t0, src=src, span=span, sgn=sgn: passby(dur, t0, src, span * sgn)), SR, True)
    for z in ZT:                                  # zuletzt: Zonen-Tracks (werden erst später gebraucht)
        out[f"music_z{z}"] = ((lambda z=z: zone_music(z)), MSR, True)
        out[f"pulse_z{z}"] = ((lambda z=z: zone_pulse(z)), MSR, True)
    return out


def _write_np(path, st, sr):
    import numpy as np
    data = (np.clip(st, -1, 1) * 32767).astype("<i2")
    ch = 2 if st.ndim == 2 else 1
    tmp = path + ".tmp"
    with wave.open(tmp, "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())
    os.replace(tmp, path)


def build(d):
    """Alle Klänge erzeugen (läuft im Hilfsprozess). Reihenfolge: wichtig zuerst."""
    os.makedirs(d, exist_ok=True)
    for name, fn in BASIC.items():
        path = os.path.join(d, name + ".wav")
        if not os.path.exists(path):
            _write(path, fn())
    try:
        snd = _np_sounds()
    except ImportError:
        path = os.path.join(d, "music.wav")
        if not os.path.exists(path):
            _write(path, music_pad_simple())
        snd = {}
    for name, (fn, sr, _st) in snd.items():
        path = os.path.join(d, name + ".wav")
        if not os.path.exists(path):
            _write_np(path, fn(), sr)
    with open(os.path.join(d, "DONE"), "w") as f:
        f.write(DONE_TAG + "\n")


# ====================================================================== Wiedergabe

LOOPS = ("rain", "music")
# Rhythmus-Spur je Zone: Pegel in Ruhe .. bei voller Spannung (x Musiklautstärke)
PULSE_LEVEL = {1: (0.22, 0.85), 2: (0.30, 0.9), 3: (0.38, 0.95), 4: (0.42, 1.0)}


def _lazy(name):
    """Zonen-Spuren werden nicht vorab geladen (Speicher), sondern bei Zonenwechsel."""
    return name.startswith("music_z") or name.startswith("pulse_z")
VOLUME = {"music": 0.5, "rain": 0.16, "target": 0.25, "ui": 0.4, "shot": 0.55, "spinner_lr": 0.45,
          "spinner_rl": 0.45, "car_lr": 0.38, "car_rl": 0.38, "truck_lr": 0.45, "truck_rl": 0.45,
          "bike_lr": 0.35, "bike_rl": 0.35, "patrol": 0.45, "thunder": 0.6, "honk": 0.55, "bump": 0.45,
          "jump": 0.3,
          "land": 0.3, "scan": 0.4, "alert": 0.4}


class Mixer:
    """Eigener Software-Mixer auf *einem* QAudioSink-Strom (Push-Modus, aus dem Spieltakt gefüttert).

    Warum nicht QSoundEffect: Qt öffnet dafür pro Effekt einen eigenen Strom mit
    der Medienrolle "event" - PipeWire/WirePlumber gibt dem die Lautstärke der
    System-Benachrichtigungen (oft -20..-30 dB). Ein QAudioSink läuft als "music".
    """

    RATE = 32000
    LATENCY = 0.11           # Sekunden Puffer (Effekt-Latenz)
    MAX_VOICES = 28

    def __init__(self):
        import numpy as np
        from PyQt6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices
        self.np = np
        fmt = QAudioFormat()
        fmt.setSampleRate(self.RATE)
        fmt.setChannelCount(2)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        self.sink = QAudioSink(QMediaDevices.defaultAudioOutput(), fmt)
        self.sink.setBufferSize(int(self.RATE * 4 * self.LATENCY * 2))
        self.dev = self.sink.start()
        self.data = {}           # name -> float32 (n, 2)
        self.voices = []         # [name, pos, vol, loop]
        self._last_start = {}

    def load(self, name, path):
        np = self.np
        with wave.open(path, "rb") as w:
            sr, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
            x = np.frombuffer(w.readframes(n), dtype="<i2").astype(np.float32) / 32767.0
        x = x.reshape(-1, ch)
        if ch == 1:
            x = np.repeat(x, 2, axis=1)
        if sr != self.RATE:
            m = int(round(len(x) * self.RATE / sr))
            t = np.linspace(0, len(x) - 1, m)
            x = np.stack([np.interp(t, np.arange(len(x)), x[:, c]) for c in range(2)], axis=1).astype(np.float32)
        self.data[name] = np.ascontiguousarray(x)

    def unload(self, name):
        self.stop(name)
        self.data.pop(name, None)

    def pos(self, name):
        for v in self.voices:
            if v[0] == name:
                return v[1]
        return 0

    def play(self, name, vol, loop=False, now=0.0, pos=0):
        if name not in self.data:
            return
        if not loop and now - self._last_start.get(name, -1.0) < 0.03:
            return                                   # gleiche Quelle doppelt im selben Frame
        self._last_start[name] = now
        if len(self.voices) >= self.MAX_VOICES:
            one_shots = [v for v in self.voices if not v[3]]
            if one_shots:
                self.voices.remove(one_shots[0])
        self.voices.append([name, pos % len(self.data[name]), vol, loop])

    def stop(self, name):
        self.voices = [v for v in self.voices if v[0] != name]

    def set_vol(self, name, vol):
        for v in self.voices:
            if v[0] == name:
                v[2] = vol

    def playing(self, name):
        return any(v[0] == name for v in self.voices)

    def pump(self, silent=False):
        """Puffer bis zur Ziel-Latenz auffüllen."""
        np = self.np
        free = self.sink.bytesFree()
        queued = self.sink.bufferSize() - free
        want = int(self.RATE * 4 * self.LATENCY) - queued
        n = min(free, max(0, want)) // 4
        if n <= 0:
            return
        out = np.zeros((n, 2), np.float32)
        if not silent:
            keep = []
            for v in self.voices:
                name, pos, vol, loop = v
                d = self.data[name]
                L = len(d)
                i = 0
                while i < n:
                    m = min(n - i, L - pos)
                    out[i:i + m] += d[pos:pos + m] * vol
                    i += m
                    pos += m
                    if pos >= L:
                        if not loop:
                            break
                        pos = 0
                if loop or pos < L:
                    v[1] = pos
                    keep.append(v)
            self.voices = keep
            # weiches Limiting statt hartem Clipping
            np.tanh(out * 1.2, out=out)
        self.dev.write((out * 32000).astype("<i2").tobytes())

    def close(self):
        try:
            self.sink.stop()
        except Exception:  # noqa: BLE001
            pass


class Audio:
    """Erzeugung im Hilfsprozess; Wiedergabe über den eigenen Mixer (Fallback: QSoundEffect)."""

    def __init__(self):
        self.enabled = os.environ.get("SHADEGUNNER_NOSOUND", "") not in ("1", "true", "yes")
        self.muted = False
        self._fx = {}
        self._loaded = set()
        self._started_loops = False
        self._proc = None
        self._poll_t = 0.0
        self._music_vol = 1.0
        self.music_vol = 1.0     # Nutzer-Lautstärke Musik (0..1)
        self.sfx_vol = 1.0       # Nutzer-Lautstärke Effekte (0..1)
        self._t = 0.0
        self.mixer = None
        # Zonen-Musik: nur die aktuelle Spur liegt im Speicher, Wechsel per Überblendung
        self._zone = 0
        self._want = 0
        self._mus = "music"
        self._pulse = None
        self._gain = {"music": 1.0}         # Überblend-Faktor je Musik-Stimme
        self._tension = 0.0
        if not self.enabled:
            return
        try:
            from PyQt6.QtMultimedia import QSoundEffect  # noqa: F401
        except Exception:
            self.enabled = False
            return
        try:
            self.mixer = Mixer()
        except Exception as exc:  # noqa: BLE001
            print(f"[audio] Mixer nicht verfügbar ({exc}) - Fallback QSoundEffect (leise: Rolle 'event')")
            self.mixer = None
        self.dir = cache_dir()
        missing = any(not os.path.exists(os.path.join(self.dir, n + ".wav")) for n in BASIC)
        try:
            with open(os.path.join(self.dir, "DONE")) as f:
                done = f.read().strip() == DONE_TAG
        except OSError:
            done = False
        if missing or not done:   # neue Klänge nachbauen
            try:
                kw = {}
                if getattr(sys, "frozen", False):     # gepackte .exe: sich selbst aufrufen
                    cmd = [sys.executable, "--build-audio", self.dir]
                else:
                    cmd = [sys.executable, "-m", "shadegunner.audio", "--build", self.dir]
                    kw["cwd"] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                if os.name == "nt":
                    kw["creationflags"] = 0x08000000   # CREATE_NO_WINDOW (kein Konsolen-Blitz)
                self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                              stderr=subprocess.DEVNULL, **kw)
            except Exception as exc:  # noqa: BLE001
                print(f"[audio] Erzeugung fehlgeschlagen: {exc}")

    @property
    def _ready(self):
        return bool(self._fx)

    def poll(self):
        """Im GUI-Thread regelmäßig aufrufen: lädt fertige WAVs nach (auch während der Erzeugung)."""
        if not self.enabled:
            return
        self._poll_t -= 1 / 60
        if self._poll_t > 0:
            return
        self._poll_t = 0.5
        try:
            names = sorted(fn[:-4] for fn in os.listdir(self.dir) if fn.endswith(".wav"))
            for name in names:
                if name in self._loaded or _lazy(name):
                    continue
                self._loaded.add(name)
                path = os.path.join(self.dir, name + ".wav")
                if self.mixer is not None:
                    self.mixer.load(name, path)
                    self._fx[name] = True
                else:
                    self._fx[name] = self._qsound(name, path)
                if name in LOOPS and self._started_loops and not self.muted:
                    if self.mixer is not None and name == "music":
                        self._start_music()
                    else:
                        self._start_loop(name)
        except Exception as exc:  # noqa: BLE001
            print(f"[audio] Fehler beim Laden: {exc}")
            self.enabled = False
        if self._want != self._zone:
            self.set_zone(self._want)

    # ---------------------------------------------------------------- Zonen-Musik
    def set_zone(self, z):
        """Musik der Zone z: Zone 0 = Titelthema, ab 1 eigener Track + Rhythmus-Spur.
        Fehlt die Datei noch (Erzeugung läuft), bleibt die alte Musik und poll() versucht
        es später erneut."""
        self._want = z
        if self.mixer is None or z == self._zone:
            return
        mus = "music" if z == 0 else f"music_z{z}"
        pulse = None if z == 0 else f"pulse_z{z}"
        for n in (mus, pulse):
            if n is not None and not os.path.exists(os.path.join(self.dir, n + ".wav")):
                return
        try:
            for n in (mus, pulse):
                if n is not None and n not in self.mixer.data:
                    self.mixer.load(n, os.path.join(self.dir, n + ".wav"))
        except Exception as exc:  # noqa: BLE001
            print(f"[audio] Zonen-Musik nicht ladbar: {exc}")
            self._want = self._zone
            return
        self._zone = z
        self._mus, self._pulse = mus, pulse
        self._fx[mus] = True
        self._gain.setdefault(mus, 0.0)
        if pulse:
            self._gain.setdefault(pulse, 0.0)
        if self._started_loops and not self.muted:
            self._start_music()

    def _start_music(self):
        """Aktuelle Musik + Rhythmus starten - die Rhythmus-Spur immer taktgleich."""
        m = self.mixer
        if m is None or self._mus not in m.data:
            return
        if not m.playing(self._mus):
            m.play(self._mus, 0.0, loop=True)
        if self._pulse and self._pulse in m.data and not m.playing(self._pulse):
            m.play(self._pulse, 0.0, loop=True, pos=m.pos(self._mus))

    def _tension_of(self, world, mode):
        """0..1: wie angespannt die Lage ist (treibt die Rhythmus-Spur)."""
        if world is None or mode not in ("play", "pause"):
            return 0.0
        t = 0.8 * getattr(world, "unrest", 0.0)
        if getattr(world, "aiming", False):
            t = max(t, 0.55)
        if getattr(world, "boss", None) is not None:
            t = max(t, 0.9)
        if getattr(world, "blackout_t", 0) > 0:
            t = max(t, 0.5)
        run = getattr(world, "run", None)
        t = max(t, 0.6 * getattr(run, "suspicion", 0.0))
        for a in getattr(world, "actors", ()):
            if a.alive and getattr(a, "alert", False) and a.state in ("flee", "attack", "punch", "leap"):
                t = 1.0
                break
        return min(1.0, t)

    def _qsound(self, name, path):
        from PyQt6.QtCore import QUrl
        from PyQt6.QtMultimedia import QSoundEffect
        pool = []
        count = 3 if name in ("shot", "target", "ui", "tell") else (1 if name in LOOPS else 2)
        for _ in range(count):
            e = QSoundEffect()
            e.setSource(QUrl.fromLocalFile(path))
            e.setVolume(VOLUME.get(name, 0.6))
            if name in LOOPS:
                e.setLoopCount(-2)
            pool.append(e)
        return [pool, 0]

    def _start_loop(self, name):
        base = VOLUME.get(name, 0.6) * (self.music_vol if name == "music" else self.sfx_vol)
        if self.mixer is not None:
            if not self.mixer.playing(name):
                self.mixer.play(name, base, loop=True)
        else:
            e = self._fx[name][0][0]
            e.setVolume(base)
            if not e.isPlaying():
                e.play()

    def loops(self, on=True):
        for name in LOOPS:
            if self.mixer is not None and name == "music":      # Zonen-Musik (eigene Logik)
                if on and not self.muted:
                    self._start_music()
                else:
                    for n in list(self._gain):
                        self.mixer.stop(n)
                continue
            if name not in self._fx:
                continue
            if on and not self.muted:
                self._start_loop(name)
            elif self.mixer is not None:
                self.mixer.stop(name)
            else:
                self._fx[name][0][0].stop()
        self._started_loops = on

    def play(self, name, vol=None):
        if not self.enabled or self.muted or name not in self._fx:
            return
        v = VOLUME.get(name, 0.6) if vol is None else max(0.0, min(1.0, vol))
        v = max(0.0, min(1.0, v * (self.music_vol if name == "music" else self.sfx_vol)))
        if self.mixer is not None:
            self.mixer.play(name, v, now=self._t)
            return
        pool = self._fx[name]
        e = pool[0][pool[1] % len(pool[0])]
        pool[1] += 1
        e.setVolume(v)
        e.play()

    def toggle_mute(self):
        self.muted = not self.muted
        self.loops(not self.muted)
        if self.muted and self.mixer is not None:
            self.mixer.voices = []
        return self.muted

    def update(self, dt, world=None, mode="play"):
        """Mixer füttern; Musik bei Stromausfall absenken."""
        if not self.enabled:
            return
        self._t += dt
        goal = 0.35 if (world is not None and getattr(world, "blackout_t", 0) > 0) else 1.0
        self._music_vol += (goal - self._music_vol) * min(1.0, dt * 1.5)
        mus = VOLUME["music"] * self.music_vol * self._music_vol
        rain = VOLUME["rain"] * self.sfx_vol
        if self.mixer is not None:
            if world is not None:
                z = getattr(world, "zone_index", 0) if mode != "title" else 0
                if z != self._want or z != self._zone:
                    self.set_zone(z)
            tg = self._tension_of(world, mode)
            # schnell rein, langsam raus - die Spannung soll nachklingen
            k = dt * (1.2 if tg > self._tension else 0.18)
            self._tension += (tg - self._tension) * min(1.0, k)
            lo, hi = PULSE_LEVEL.get(self._zone, (0.0, 0.0))
            for n in list(self._gain):
                if n == self._mus:
                    goal_g = 1.0
                elif n == self._pulse:
                    goal_g = lo + (hi - lo) * self._tension
                else:
                    goal_g = 0.0
                g = self._gain[n]
                g += max(-dt / 2.5, min(dt / 2.5, goal_g - g))      # 2,5 s Überblendung
                self._gain[n] = g
                if g <= 0.0 and goal_g == 0.0 and n not in (self._mus, self._pulse):
                    del self._gain[n]
                    self.mixer.unload(n)                 # Speicher frei (bis zu ~33 MB je Spur)
                    self._fx.pop(n, None)
                    self._loaded.discard(n)
                else:
                    self.mixer.set_vol(n, mus * g)
            self.mixer.set_vol("rain", rain)
            self.mixer.pump(silent=self.muted)
        elif "music" in self._fx:
            self._fx["music"][0][0].setVolume(mus)

    def set_volumes(self, music=None, sfx=None):
        """Nutzer-Lautstärken setzen und sofort anwenden (0..1)."""
        if music is not None:
            self.music_vol = max(0.0, min(1.0, music))
        if sfx is not None:
            self.sfx_vol = max(0.0, min(1.0, sfx))
        if not self.enabled:
            return
        mus = VOLUME["music"] * self.music_vol * self._music_vol
        rain = VOLUME["rain"] * self.sfx_vol
        if self.mixer is not None:
            for n, g in self._gain.items():
                self.mixer.set_vol(n, mus * g)
            self.mixer.set_vol("rain", rain)
        elif self._fx:
            if "music" in self._fx:
                self._fx["music"][0][0].setVolume(mus)
            if "rain" in self._fx:
                self._fx["rain"][0][0].setVolume(rain)

    def handle_events(self, events, world=None):
        for ev in events:
            k = ev[0]
            if k == "shot":
                self.play("shot")
            elif k == "scan_start":
                self.play("scan")
            elif k == "scan_done":
                self.play("scan_done")
            elif k == "target":
                self.play("target")
            elif k == "tell":
                self.play("tell")
            elif k == "kill":
                self.play("kill_rep" if ev[2] else "kill_civ")
            elif k == "hurt":
                self.play("hurt")
            elif k == "escape":
                self.play("escape")
            elif k == "gate_locked":
                self.play("gate")
            elif k == "quota":
                self.play("quota")
            elif k == "zone_clear":
                self.play("clear")
            elif k == "fail":
                self.play("fail")
            elif k in ("no_charge", "no_target", "scan_abort"):
                self.play("no")
            elif k in ("attack", "flee"):
                self.play("alert")
            elif k == "jump":
                self.play("jump")
            elif k == "land":
                if world is not None and ev[1] == 0:
                    self.play("land")
            elif k == "leap":
                self.play("leap")
            elif k == "tough":
                self.play("tough")
            elif k == "bounty":
                self.play("bounty")
            elif k == "ramen":
                self.play("ramen")
            elif k == "holster":
                self.play("ui")
            elif k == "boss":
                self.play("boss")
            elif k == "boss_line":
                self.play("tell")
            elif k == "boss_hit":
                self.play("tough")
            elif k == "boss_blocked":
                self.play("no")
            elif k == "honk":
                self.play("honk")
            elif k == "car_hit":
                self.play("car_hit")
            elif k == "bump":
                self.play("bump")
            elif k == "jam_honk":
                self.play("honk", VOLUME["honk"] * 0.5)
            elif k == "vehicle":
                kind, d = ev[1], ev[2]
                vol = ev[3] if len(ev) > 3 else 1.0     # leiser bei langsamer/dichter Fahrt
                # dichter Verkehr: höchstens 4 Vorbeifahrten gleichzeitig anstoßen
                self._veh_t = [x for x in getattr(self, "_veh_t", []) if self._t - x < 2.5]
                if len(self._veh_t) >= 4:
                    continue
                self._veh_t.append(self._t)
                if kind == "police":        # Boden-Spinner: Turbinen statt Motor
                    self.play(f"spinner_{'lr' if d > 0 else 'rl'}", VOLUME["spinner_lr"] * 0.8 * vol)
                else:
                    cls = "truck" if kind in ("truck", "bus") else (kind if kind == "bike" else "car")
                    nm = f"{cls}_{'lr' if d > 0 else 'rl'}"
                    self.play(nm, VOLUME.get(nm, 0.4) * vol)
            elif k == "spinner":
                d, s = ev[1], ev[2]
                self.play(f"spinner_{'lr' if d > 0 else 'rl'}", VOLUME["spinner_lr"] * min(1.0, 0.5 + s * 0.35))
            elif k == "patrol":
                self.play("patrol")
            elif k in ("spinner_land", "spinner_lift"):
                d = ev[1]
                self.play(f"spinner_{'lr' if d > 0 else 'rl'}", VOLUME["spinner_lr"])
            elif k == "spinner_touch":
                self.play("car_hit", VOLUME.get("car_hit", 0.5) * 0.45)
            elif k == "shout":
                self.play("shout")
            elif k == "talk":
                self.play("talk")
            elif k == "origami":
                self.play("bounty")
            elif k == "greet":
                self.play("ui")
            elif k == "thunder":
                self.play("thunder")
            elif k == "blackout":
                self.play("blackout")
            elif k == "blackout_end":
                self.play("power_up")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--build":
        build(sys.argv[2])
