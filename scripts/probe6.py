#!/usr/bin/env python3
"""Probe 6: for the no-door buildings, WHY does every wall column fail the
threshold check?  Counts failure reasons per side (top too high / too low /
no headroom / no solid wall column).  Tells us whether relaxing the lower
bound would actually add doors."""
import json
import sys
from pathlib import Path
from collections import Counter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from finish_world import World  # noqa: E402

WORK = HERE
WORLD_DIR = WORK / "staging-v3" / "OUC-West-Coast-v3"
PLAN = json.load(open(WORK / "plan-v2.json", encoding="utf-8"))
BUILD = json.load(open(WORK / "v3-build-report.json", encoding="utf-8"))

world = World(str(WORLD_DIR))
AIR = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}


def is_solid(x, y, z):
    b = world.get_block(x, y, z)
    return b is not None and b not in AIR


def is_air(x, y, z):
    b = world.get_block(x, y, z)
    return b is None or b in AIR


def top_y(x, z):
    t = world.top_solid(x, z, y_top=64, y_bottom=-64)
    return t[0] if t else None


# ground_y per building from the build report
gy_by_name = {r["name"]: r.get("ground_y") for r in BUILD["door_sweep"]}
targets = ["听海苑8号楼", "智慧海洋楼·北翼", "听海苑7号楼", "听海苑1号楼"]
for fp in PLAN.get("footprints", []):
    name = fp["name"]
    if name not in targets:
        continue
    gy = gy_by_name.get(name)
    xs = [p[0] for p in fp["polygon"]]
    zs = [p[1] for p in fp["polygon"]]
    print(f"=== {name} gy={gy} X{min(xs)}-{max(xs)} Z{min(zs)}-{max(zs)} ===")
    sides = {
        "north": [(x, min(zs)) for x in range(min(xs), max(xs) + 1)],
        "south": [(x, max(zs)) for x in range(min(xs), max(xs) + 1)],
        "west": [(min(xs), z) for z in range(min(zs), max(zs) + 1)],
        "east": [(max(xs), z) for z in range(min(zs), max(zs) + 1)],
    }
    for side, line in sides.items():
        c = Counter()
        for (x, z) in line:
            if not all(is_solid(x, gy + 1 + k, z) for k in range(3)):
                c["no_solid_wall"] += 1
                continue
            out = {"north": (x, z - 1), "south": (x, z + 1),
                   "west": (x - 1, z), "east": (x + 1, z)}[side]
            top = top_y(out[0], out[1])
            if top is None:
                c["no_ground"] += 1
            elif top > gy + 1:
                c["top_too_high"] += 1
            elif top < gy - 2:
                c["top_too_low"] += 1
            elif not (is_air(out[0], top + 1, out[1])
                     and is_air(out[0], top + 2, out[1])):
                c["no_headroom"] += 1
            else:
                c["OK"] += 1
        print(f"  {side}: {dict(c)}")
print("done")
