#!/usr/bin/env python3
"""Probe 4: dump full columns around the 3 failing sweep doors."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from finish_world import World  # noqa: E402
from verify_v3 import standable, standable_at  # noqa: E402

WORK = HERE
WORLD_DIR = WORK / "staging-v3" / "OUC-West-Coast-v3"
BUILD = json.load(open(WORK / "v3-build-report.json", encoding="utf-8"))

world = World(str(WORLD_DIR))
names = ["海德楼·南楼", "智慧海洋楼", "听海苑3号楼"]
for r in BUILD["door_sweep"]:
    if not r.get("door") or r["name"] not in names:
        continue
    (x, y, z) = r["door"]
    gy = r["ground_y"]
    (tx, ty, tz) = r["threshold"]
    inward = {"north": (x, z + 1), "south": (x, z - 1),
              "west": (x + 1, z), "east": (x - 1, z)}[r["facing"]]
    inward2 = {"north": (x, z + 2), "south": (x, z - 2),
               "west": (x + 2, z), "east": (x - 2, z)}[r["facing"]]
    print(f"=== {r['name']} door=({x},{y},{z}) {r['facing']} gy={gy} ===")
    for (cx, cz, lbl) in [(tx, tz, "threshold"), (x, z, "door"),
                          (inward[0], inward[1], "inward1"),
                          (inward2[0], inward2[1], "inward2")]:
        col = {}
        for yy in range(gy - 3, gy + 5):
            b = world.get_block(cx, yy, cz)
            if b and b != "minecraft:air":
                col[yy] = b
        print(f"  {lbl} ({cx},{cz}): {col} standable={standable(world, cx, cz)}")
    print("  threshold neighbours standable:")
    for (nx, nz) in [(tx + 1, tz), (tx - 1, tz), (tx, tz + 1), (tx, tz - 1)]:
        print(f"    ({nx},{nz}) standable={standable(world, nx, nz)} "
              f"top={world.top_solid(nx, nz, y_top=64, y_bottom=-64)}")
print("done")
