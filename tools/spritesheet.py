#!/usr/bin/env python3
"""Sprite-Sheet: alle Animationen für ein paar zufällige Looks -> PNG (Look-Check).

Aufruf: python3 tools/spritesheet.py [out.png] [höhe_px] [seed]
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtGui import QColor, QImage, QPainter  # noqa: E402

from shadegunner.render import sprites  # noqa: E402


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "shots/sprites.png"
    hpx = int(sys.argv[2]) if len(sys.argv) > 2 else 72
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    rng = random.Random(seed)
    looks = [sprites.PLAYER_LOOK] + [sprites.random_look(rng, i) for i in range(1, 11)]
    rows = []
    for lk in looks:
        row = []
        anims = ["idle", "walk", "run", "jump", "cower", "die"]
        if lk.get("player"):
            anims = ["idle", "walk", "run", "aim", "shoot", "scan", "hurt", "die"]
        for an in anims:
            for f in range(sprites.frame_count(an)):
                row.append(sprites.get(lk, an, f, hpx, 1, rim=(64, 210, 220), rim_side=1))
        rows.append(row)
    cw = max(r[0][0].width() for r in rows)
    ch = max(r[0][0].height() for r in rows)
    ncol = max(len(r) for r in rows)
    sheet = QImage(cw * ncol, ch * len(rows), QImage.Format.Format_ARGB32_Premultiplied)
    sheet.fill(QColor(40, 44, 70))
    p = QPainter(sheet)
    for j, r in enumerate(rows):
        for i, (img, _e, ax, ay, _m) in enumerate(r):
            p.drawImage(i * cw + cw // 2 - ax, j * ch + ch - 8 - (img.height() - ay), img)
    p.end()
    sheet = sheet.scaled(sheet.width() * 2, sheet.height() * 2, Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.FastTransformation)
    sheet.save(out)
    print("geschrieben:", out, sheet.width(), "x", sheet.height())


if __name__ == "__main__":
    main()
