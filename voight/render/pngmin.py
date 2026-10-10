"""Minimaler PNG-Writer (nur stdlib: zlib + struct).

Rein, damit die Software-Preview auf jeder Maschine ohne Pillow/numpy läuft.
"""

import struct
import zlib


def write_png(path, rgb, w, h):
    """rgb: Bytearray/Bytes der Länge w*h*3 (RGB8) -> PNG-Datei."""
    stride = w * 3
    raw = bytearray((stride + 1) * h)
    for y in range(h):
        d = y * (stride + 1)
        raw[d] = 0  # Filter: none
        raw[d + 1:d + 1 + stride] = rgb[y * stride:(y + 1) * stride]

    def chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data +
                struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)  # 8-bit, truecolor RGB
    idat = zlib.compress(bytes(raw), 9)
    with open(path, "wb") as f:
        f.write(sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b""))
    return path
