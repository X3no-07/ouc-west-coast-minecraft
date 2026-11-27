#!/usr/bin/env python3
"""Road-fix probe 2: for suspicious cells, print the column profile and
which footprint (if any) contains the cell, so the fix can tell a real
plaza/court/building apart from Arnis ground noise."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from finish_world import World  # noqa: E402
from build_v4 import top_y  # noqa: E402

WORK = HERE
WORLD_DIR = WORK / "staging-roadfix" / "OUC-West-Coast-v5"
V3 = json.load(open(WORK / "v3-build-data.json", encoding="utf-8"))
V5 = json.load(open(WORK / "v5-build-data.json", encoding="utf-8"))
PLAN = json.load(open(WORK / "plan-v2.json", encoding="utf-8"))


def point_in_poly(x, z, poly):
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, zi = poly[i]
        xj, zj = poly[j]
        if ((zi > z) != (zj > z)) and \
                (x < (xj - xi) * (z - zi) / (zj - zi) + xi):
            inside = not inside
        j = i
    return inside


def rect_poly(rect):
    x0, z0, x1, z1 = rect
    return [[x0, z0], [x1, z0], [x1, z1], [x0, z1]]


NAMED = []
for i, fp in enumerate(PLAN.get("footprints", [])):
    NAMED.append((f"plan[{i}]", fp["polygon"]))
for m in V3.get("missing_buildings", []):
    if m.get("poly"):
        NAMED.append((f"missing:{m['name']}", m["poly"]))
NAMED.append(("learning-west-plaza", rect_poly(V5["learning"]["west_plaza"]["rect"])))
NAMED.append(("v4-low-building", rect_poly([984, 694, 1008, 718])))
for area in V3["courts"]:
    NAMED.append((f"court-area:{area['area']}", rect_poly(area["bbox"])))
    for ci, c in enumerate(area["courts"]):
        NAMED.append((f"court-rect:{area['area']}#{ci}",
                      rect_poly([c["x0"], c["z0"], c["x1"], c["z1"]])))
NAMED.append(("football-pitch", rect_poly(V5["football"]["pitch_rect"])))


def main():
    world = World(str(WORLD_DIR))
    cells = [
        (1290, 652, "road34 dirt start"),
        (1320, 656, "road34 beige"),
        (1040, 640, "road6 dirt run"),
        (1030, 730, "road14 dirt run"),
        (220, 867, "road22 stone run"),
        (1133, 505, "road10 black apron"),
        (1145, 510, "road10 black apron 2"),
        (1258, 750, "road2 quartz slab"),
        (1266, 774, "road2 smooth quartz slab"),
        (1636, 740, "road24 smooth stone"),
        (1358, 330, "road38 under dorm"),
        (1279, 280, "road40 under dorm"),
        (1031, 12, "road7 air dip"),
        (1291, 588, "road2 stone single"),
        (1457, 282, "road4 stone single"),
        (1558, 688, "road11 air dip"),
        (1284, 650, "road34 west end"),
        (1285, 640, "road2 plaza start"),
    ]
    for (x, z, why) in cells:
        t = top_y(world, x, z)
        hits = [name for (name, poly) in NAMED
                if point_in_poly(x + 0.5, z + 0.5, poly)]
        prof = []
        for y in range(-58, -30):
            b = world.get_block(x, y, z)
            if b and b not in ("minecraft:air", "minecraft:cave_air"):
                prof.append(f"{y}:{b.replace('minecraft:', '')}")
        print(f"({x},{z}) {why}: top_y={t} top={world.get_block(x, t, z) if t is not None else None}")
        print(f"   in: {hits if hits else 'none'}")
        print(f"   column: {' '.join(prof)}")


if __name__ == "__main__":
    main()
