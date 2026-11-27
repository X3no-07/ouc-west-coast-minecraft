#!/usr/bin/env python3
"""v10 screenshots: south gate + learning-complex west facade.
Reuses render_v5.py's TopMaps + colour helpers; iso_image is copied
from render_v5.py with only the source line changed to v10.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from render_v5 import (TopMaps, color_for, shade, add_label,  # noqa: E402
                       north_arrow, Y_MIN, SKIP)
from anvil import loads  # noqa: E402,F401  (kept for parity)

WORLD = Path(__file__).parent / "staging-v10" / "OUC-West-Coast-v10"
OUT = Path(__file__).parent / "v10-screenshots"
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
             ("来源：v10 世界文件（OUC-West-Coast-v10.zip）｜俯视图，1 格 = 1 米，北在上方",
              20, False),
             ("世界文件渲染图，非游戏内截图", 20, False)]
    return add_label(img, lines, 150)


def iso_image(tm, x0, z0, x1, z1, title, subtitle, flip=False):
    """Oblique view. flip=True: viewer from the north-west instead."""
    ty, tn = tm.area(x0, z0, x1, z1)
    nz, nx = ty.shape
    # Per-block lookup (cached chunk volumes) so side faces can be drawn
    # as true vertical bands: roof band, window/louver band, wall, base —
    # instead of one flat colour per column, which hid wall features
    # such as the 听海餐厅 blue louvers (2–3 blocks below the roofline).
    vols = {}

    def block_at(gx, y, gz):
        yy = y - Y_MIN
        if yy < 0 or yy >= 128:
            return None
        cx, cz = gx >> 4, gz >> 4
        key = (cx, cz)
        if key not in vols:
            vols[key] = tm.column_volume(cx, cz)
        vol = vols[key]
        if vol is None:
            return None
        names3d, solid3d = vol
        lx, lz = gx & 15, gz & 15
        if not solid3d[yy, lz, lx]:
            return None
        b = names3d[yy, lz, lx]
        if not b or b in SKIP:
            return None
        return b
    tw, th, vh = 14, 7, 7
    y_lo = int(ty[ty > -999].min()) if (ty > -999).any() else 0
    y_hi = int(ty.max())
    if flip:
        # viewer from NW: screen x grows with (z - x), y grows with -(x + z)
        def scr(gx, gz, y):
            return ((gz - z0) - (gx - x0)) * tw // 2, (-(gx - x0) - (gz - z0)) * th // 2 - (y - y_lo) * vh
        order = sorted(((gx, gz) for gz in range(z0, z1 + 1) for gx in range(x0, x1 + 1)),
                       key=lambda p: (-(p[0] + p[1]), p[0]))
        front = lambda gx, gz: [(gx - 1, gz), (gx, gz - 1), (gx - 1, gz - 1)]
    else:
        def scr(gx, gz, y):
            return ((gx - x0) - (gz - z0)) * tw // 2, ((gx - x0) + (gz - z0)) * th // 2 - (y - y_lo) * vh
        order = sorted(((gx, gz) for gz in range(z0, z1 + 1) for gx in range(x0, x1 + 1)),
                       key=lambda p: (p[0] + p[1], p[0]))
        front = lambda gx, gz: [(gx + 1, gz), (gx, gz + 1), (gx + 1, gz + 1)]
    xs = [scr(x0, z0, y_lo)[0], scr(x1, z0, y_lo)[0], scr(x0, z1, y_lo)[0], scr(x1, z1, y_lo)[0]]
    ys = [scr(x0, z0, y_hi)[1], scr(x1, z1, y_lo)[1]]
    W = max(xs) - min(xs) + tw + 80
    H = max(ys) - min(ys) + (y_hi - y_lo) * vh + th + 120
    ox = -min(xs) + 40
    oy = -min(ys) + 60
    img = Image.new("RGB", (W, H), (232, 236, 240))
    d = ImageDraw.Draw(img)

    def top_at(gx, gz):
        if gx < x0 or gx > x1 or gz < z0 or gz > z1:
            return None
        v = ty[gz - z0, gx - x0]
        return None if v <= -999 else int(v)

    for (gx, gz) in order:
        top = top_at(gx, gz)
        if top is None:
            continue
        tname = tn[gz - z0, gx - x0]
        sx, sy = scr(gx, gz, top)
        sx += ox
        sy += oy
        # Visible side heights: each face is hidden only by the neighbour
        # directly in front of it. (A single max over all front neighbours
        # is wrong: the lateral neighbour on the same roof would hide a
        # face whose own front neighbour is far below.)
        def _h(nx, nz):
            v = top_at(nx, nz)
            return max(0, top - v) if v is not None else 0
        if flip:
            # left face = north face (neighbour z-1), right = west (x-1)
            h_left = _h(gx, gz - 1)
            h_right = _h(gx - 1, gz)
        else:
            # left face = south face (neighbour z+1), right = east (x+1)
            h_left = _h(gx, gz + 1)
            h_right = _h(gx + 1, gz)

        def draw_face(h, side):
            # side -1 = left face, +1 = right face; one band per block,
            # air gaps left unpainted (reads as a recess/opening).
            for dd in range(h):
                bname = block_at(gx, top - dd, gz)
                if bname is None:
                    continue
                c = shade(color_for(bname), 0.72 if side < 0 else 0.58)
                if side < 0:
                    d.polygon([(sx, sy + th // 2 + dd * vh),
                               (sx - tw // 2, sy + dd * vh),
                               (sx - tw // 2, sy + (dd + 1) * vh),
                               (sx, sy + th // 2 + (dd + 1) * vh)], fill=c)
                else:
                    d.polygon([(sx, sy + th // 2 + dd * vh),
                               (sx + tw // 2, sy + dd * vh),
                               (sx + tw // 2, sy + (dd + 1) * vh),
                               (sx, sy + th // 2 + (dd + 1) * vh)], fill=c)
        if h_left > 0:
            draw_face(h_left, -1)
        if h_right > 0:
            draw_face(h_right, +1)
        top_c = color_for(tname)
        d.polygon([(sx, sy - th // 2), (sx + tw // 2, sy),
                   (sx, sy + th // 2), (sx - tw // 2, sy)],
                  fill=top_c, outline=shade(top_c, 0.82))
    d.rectangle([0, 0, W - 1, H - 1], outline=(60, 60, 60), width=3)
    lines = [(title, 30, True),
             (subtitle, 22, False),
             ("来源：v10 世界文件（OUC-West-Coast-v10.zip）｜斜视图，方块渲染，可看立面与台阶",
              20, False),
             ("世界文件渲染图，非游戏内截图", 20, False)]
    return add_label(img, lines, 150)

JOBS = [
    ("top", "01_大门区_俯视.png", "南大门区",
     "X 1180–1270，Z 965–996｜招牌墙 + 花坛 + 翼墙 + 灰色前广场",
     (1180, 965, 1270, 996), {"scale": 6}),
    ("iso", "02_大门_斜视_南面.png", "南大门（南面）",
     "X 1180–1265，Z 968–996｜斜视（东南看）：浅灰石英招牌墙 + 红色“中国海洋大学”六字 + 白色翼墙，墙前花坛",
     (1180, 968, 1265, 996), {"flip": False}),
    ("iso", "03_大门招牌墙_特写.png", "南大门招牌墙（特写）",
     "X 1190–1255，Z 984–996｜斜视（东南看）：红色“中国海洋大学”六字 + 白色翼墙 + 墙前花坛",
     (1190, 984, 1255, 996), {"flip": False}),
    ("iso", "04_学习综合体西立面_斜视.png", "学习综合体西立面",
     "X 1100–1270，Z 645–755｜斜视（西北看）：浅灰石英 + 蓝玻璃条窗 + 石英鳍片，中央三层内收门洞 + 蓝玻璃幕墙，西广场浅灰大石板",
     (1100, 645, 1270, 755), {"flip": True}),
    ("top", "05_学习综合体西广场_俯视.png", "学习综合体西广场",
     "X 1100–1270，Z 645–755｜浅灰大石板（10 格接缝）+ 门洞前石英露台，西立面在右",
     (1100, 645, 1270, 755), {"scale": 3}),
]


def main():
    tm = TopMaps(WORLD)
    for kind, fname, title, subtitle, bbox, kw in JOBS:
        x0, z0, x1, z1 = bbox
        if kind == "top":
            img = top_image(tm, x0, z0, x1, z1, title, subtitle, **kw)
        else:
            img = iso_image(tm, x0, z0, x1, z1, title, subtitle, **kw)
        img.save(OUT / fname)
        print("saved", fname, img.size, flush=True)


if __name__ == "__main__":
    main()
