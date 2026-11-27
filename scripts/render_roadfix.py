#!/usr/bin/env python3
"""Render top-down screenshots of the road-fixed world (staging-roadfix).

Reuses render_v5.py's TopMaps + colour helpers; only the source line
and the output dir differ. Reads block data straight from the region
files of the fixed world. No hand-drawn art, no AI images.
Output: ~/workspace/minecraft-ouc/road-fix-screenshots/*.png
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
from render_v5 import TopMaps, color_for, add_label, north_arrow, font  # noqa: E402

WORLD = Path(__file__).parent / "staging-roadfix" / "OUC-West-Coast-v5"
OUT = Path(__file__).parent / "road-fix-screenshots"
OUT.mkdir(exist_ok=True)


def top_image(tm, x0, z0, x1, z1, title, subtitle, scale=3):
    ty, tn = tm.area(x0, z0, x1, z1)
    nz, nx = ty.shape
    uniq = sorted({n for n in tn.flat if n})
    lut = {n: color_for(n) for n in uniq}
    idx_of = {n: i for i, n in enumerate(uniq)}
    arr = np.zeros((nz, nx), dtype=np.int32)
    for n, i in idx_of.items():
        arr[tn == n] = i
    palette = np.array([lut[n] for n in uniq], dtype=np.uint8)
    rgb = palette[arr]
    img = Image.fromarray(rgb, "RGB")
    if scale != 1:
        img = img.resize((nx * scale, nz * scale), Image.NEAREST)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, img.width - 1, img.height - 1], outline=(60, 60, 60), width=3)
    north_arrow(d, img.width - 46, 52)
    lines = [(title, 30, True),
             (subtitle, 22, False),
             ("来源：修路后世界文件（staging-roadfix，由正式版 v5 世界改出，未定版本号）｜俯视图，1 格 = 1 米，北在上方",
              20, False),
             ("世界文件渲染图，非游戏内截图", 20, False)]
    return add_label(img, lines, 150)


JOBS = [
    ("01_山海北路_俯视.png", "山海北路（中央东西主干道）",
     "X 900–1450，Z 340–410｜全幅深灰车道 + 白实线边线 + 稀虚线 + 石砖路牙 + 浅灰人行道",
     (900, 340, 1450, 410), 2),
    ("02_融合中路_俯视.png", "融合中路（浩海广场东侧）",
     "X 1300–1440，Z 610–800｜主路断面同上，东接海军路",
     (1300, 610, 1440, 800), 2),
    ("03_听海苑楼内路_俯视.png", "听海苑楼内路",
     "X 1170–1450，Z 180–370｜楼内路全幅深灰车道 + 稀虚线，两侧各 1 格浅灰人行道",
     (1170, 180, 1450, 370), 3),
    ("04_望海苑楼内路_俯视.png", "望海苑楼内路",
     "X 380–660，Z 180–360｜楼内路断面同上，宿舍楼间小路",
     (380, 180, 660, 360), 3),
    ("05_浩海广场穿路处_俯视.png", "浩海广场穿路处",
     "X 1245–1355，Z 630–770｜2 号、34 号路车道完整穿过广场石板，路口斑马线",
     (1245, 630, 1355, 770), 3),
]


def main():
    tm = TopMaps(WORLD)
    for fname, title, subtitle, bbox, scale in JOBS:
        x0, z0, x1, z1 = bbox
        img = top_image(tm, x0, z0, x1, z1, title, subtitle, scale=scale)
        img.save(OUT / fname)
        print("saved", fname, img.size, flush=True)


if __name__ == "__main__":
    main()
