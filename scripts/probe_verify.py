#!/usr/bin/env python3
"""Debug probe for v3 verify failures: east-gate BFS + door-sweep BFS + west courts hoops."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from finish_world import World  # noqa: E402
from verify_v3 import standable, floor_y, is_passable  # noqa: E402

WORK = HERE
WORLD_DIR = WORK / "staging-v3" / "OUC-West-Coast-v3"
BUILD = json.load(open(WORK / "v3-build-report.json", encoding="utf-8"))

world = World(str(WORLD_DIR))

print("=== east gate floor map x[1625,1650] z[738,760] ===")
print("    " + "".join(str((x // 10) % 10) if x % 5 == 0 else " " for x in range(1625, 1651)))
for z in range(738, 761):
    row = ""
    for x in range(1625, 1651):
        fy = standable(world, x, z)
        row += "." if fy is None else str(abs(fy) % 10)
    print(f"{z} {row}")
print("floor Y at start (1636,749):", standable(world, 1636, 749))
for (x, z) in [(1635, 749), (1638, 749), (1636, 744), (1636, 754), (1630, 749), (1645, 749)]:
    print(f"  standable({x},{z}) =", standable(world, x, z),
          "top:", world.top_solid(x, z, y_top=64, y_bottom=-64))

print("=== door sweep: threshold + inward-2 standable ===")
for i, r in enumerate(BUILD["door_sweep"]):
    if not r.get("door"):
        continue
    (x, y, z) = r["door"]
    (tx, ty, tz) = r["threshold"]
    inward = {"north": (x, z + 2), "south": (x, z - 2),
              "west": (x + 2, z), "east": (x - 2, z)}[r["facing"]]
    ts = standable(world, tx, tz)
    ins = standable(world, *inward)
    flag = "" if (ts is not None and ins is not None) else "  <-- BFS WOULD FAIL"
    print(f"{r['name']} door=({x},{y},{z}) {r['facing']} thr=({tx},{tz}) stand={ts} "
          f"inward2={inward} stand={ins}{flag}")
    if ts is None or ins is None:
        # show the blocking blocks
        for (bx, bz, lbl) in [(tx, tz, "thr"), (inward[0], inward[1], "in2")]:
            fy = floor_y(world, bx, bz)
            print(f"    {lbl} ({bx},{bz}) floor_y={fy} "
                  f"at floor: {world.get_block(bx, fy, bz) if fy is not None else None} "
                  f"+1: {world.get_block(bx, fy + 1, bz) if fy is not None else None} "
                  f"+2: {world.get_block(bx, fy + 2, bz) if fy is not None else None}")

print("=== west courts x700 hoops ===")
for (x0, sy, cz) in [(700, -33, 203), (700, -33, 221)]:
    for end, lbl in ((x0, "west end"), (x0 + 27, "east end")):
        sgn = 1 if end == x0 else -1
        px = end - sgn
        print(f"court x0={x0} cz={cz} {lbl}: backboard ({end},sy+3={sy+3},{cz})=",
              world.get_block(end, sy + 3, cz),
              "| post ({},{},{})=".format(px, sy + 1, cz),
              world.get_block(px, sy + 1, cz),
              "| surf at end line:", world.top_solid(end, cz, y_top=64, y_bottom=-64))
print("done")
