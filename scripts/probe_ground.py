#!/usr/bin/env python3
"""Probe the (944,694) area and the class-30 speckle patches before build."""
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from finish_world import World  # noqa: E402

WORK = HERE
WORLD_DIR = WORK / "staging-v3" / "OUC-West-Coast-v3"
LON0, LAT0 = 120.01335, 35.77065
DLON, DLAT = 0.0232, 0.00895

world = World(str(WORLD_DIR))

def mc_to_lonlat(x, z):
    return LON0 + x / 2092 * DLON, LAT0 + (1 - z / 995) * DLAT

import numpy as np
with np.load(WORK / "sentinel-surface.npz") as src:
    left, bottom, right, top = [float(v) for v in src["bounds"]]
    bare = src["stable_low_vegetation"]
rows, cols = bare.shape
padded = np.pad(bare, 1, mode="edge")

def sentinel_class(x, z):
    lon, lat = mc_to_lonlat(x, z)
    col = int((lon - left) / (right - left) * cols)
    row = int((top - lat) / (top - bottom) * rows)
    if not (0 <= row < rows and 0 <= col < cols):
        return None
    sup = int(padded[row:row + 3, col:col + 3].sum())
    return 50 if (bool(bare[row, col]) and sup >= 5) else 30

SYM = {
    "minecraft:grass_block": "G",
    "minecraft:gray_concrete_powder": ".",
    "minecraft:cyan_terracotta": "C",
    "minecraft:stone_bricks": "S",
    "minecraft:cobblestone": "o",
    "minecraft:stone": "s",
    "minecraft:white_concrete": "W",
    "minecraft:cracked_stone_bricks": "K",
    "minecraft:dirt": "d",
    "minecraft:gravel": "v",
    "minecraft:coarse_dirt": "D",
}

def show_window(x0, z0, x1, z1, label, step=2):
    print(f"--- {label} x[{x0},{x1}] z[{z0},{z1}] step {step} ---")
    mix = Counter()
    cls50 = 0
    n = 0
    for z in range(z0, z1 + 1, step):
        line = ""
        for x in range(x0, x1 + 1, step):
            t = world.top_solid(x, z, y_top=64, y_bottom=-64)
            b = t[1] if t else "?"
            mix[b] += 1
            line += SYM.get(b, "?")
            c = sentinel_class(x, z)
            if c == 50:
                cls50 += 1
            n += 1
        print(f"{z:4d} {line}")
    print("mix:", dict(mix.most_common(10)))
    print(f"sentinel class-50 fraction in window: {cls50}/{n} = {cls50/n:.2f}")

show_window(905, 655, 985, 735, "(944,694) area 80x80")
show_window(1498, 145, 1607, 233, "P5 speckle patch", step=4)
show_window(146, 65, 244, 114, "P6 speckle patch", step=2)
print("done")
