#!/usr/bin/env python3
"""v9 screenshots: white-concrete paving of the built-up area.
Reuses render_v5.py's TopMaps + colour helpers.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from render_v5 import TopMaps, color_for, add_label, north_arrow  # noqa: E402

WORLD = Path(__file__).parent / "staging-v9" / "OUC-West-Coast-v9"
OUT = Path(__file__).parent / "v9-screenshots"
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
             ("来源：v9 世界文件（OUC-West-Coast-v9.zip）｜俯视图，1 格 = 1 米，北在上方",
              20, False),
             ("世界文件渲染图，非游戏内截图", 20, False)]
    return add_label(img, lines, 150)


JOBS = [
    ("01_楼群核心区_俯视.png", "楼群核心区（建成区铺白水泥地）",
     "X 600–1600，Z 180–820｜建成区矩形 X 365–1588、Z 160–946 内草地改白混凝土，路、楼、广场、球场不动",
     (600, 180, 1600, 820), 2),
    ("02_南边公园边界_俯视.png", "南边公园边界（白地与绿公园的分界）",
     "X 1100–1500，Z 780–980｜北边建成区是白混凝土，南边公园（OSM leisure=park）留绿",
     (1100, 780, 1500, 980), 3),
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
