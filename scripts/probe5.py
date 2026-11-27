#!/usr/bin/env python3
"""Probe 5: why is the main-library east door (1258,-44,686) unreachable?
Dump columns at threshold/door/inward1/inward2 and the ground profile
east of the door toward the plaza."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from finish_world import World  # noqa: E402
from verify_v3 import standable  # noqa: E402

WORK = HERE
WORLD_DIR = WORK / "staging-v3" / "OUC-West-Coast-v3"
world = World(str(WORLD_DIR))

print("=== columns (y -52..-38, non-air only) ===")
for (cx, cz, lbl) in [(1259, 686, "threshold"), (1258, 686, "door"),
                      (1257, 686, "inward1"), (1256, 686, "inward2")]:
    col = {}
    for yy in range(-52, -37):
        b = world.get_block(cx, yy, cz)
        if b and b != "minecraft:air":
            col[yy] = b
    print(f"  {lbl} ({cx},{cz}): {col} standable={standable(world, cx, cz)}")

print("=== ground profile east of the door, z=686, x=1259..1280 ===")
for x in range(1259, 1281):
    t = world.top_solid(x, 686, y_top=64, y_bottom=-64)
    print(f"  x={x} top={t} standable={standable(world, x, 686)}")
print("=== standable 5x5 around threshold (1259,686) ===")
for dz in range(-2, 3):
    row = []
    for dx in range(-2, 3):
        row.append(str(standable(world, 1259 + dx, 686 + dz)))
    print("  z=%d: %s" % (686 + dz, " ".join(f"{v:>5}" for v in row)))
print("done")
