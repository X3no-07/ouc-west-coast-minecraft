#!/usr/bin/env python3
"""Probe 3: which sampled sweep door still fails BFS, and does the east-gate
route reach the learning-complex east-wing door threshold (1187,774)?"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from finish_world import World  # noqa: E402
from verify_v3 import bfs  # noqa: E402

WORK = HERE
WORLD_DIR = WORK / "staging-v3" / "OUC-West-Coast-v3"
BUILD = json.load(open(WORK / "v3-build-report.json", encoding="utf-8"))

world = World(str(WORLD_DIR))

print("=== sweep doors: BFS threshold -> inward-2 (all 16) ===")
for i, r in enumerate(BUILD["door_sweep"]):
    if not r.get("door"):
        continue
    (x, y, z) = r["door"]
    (tx, ty, tz) = r["threshold"]
    inward = {"north": (x, z + 2), "south": (x, z - 2),
              "west": (x + 2, z), "east": (x - 2, z)}[r["facing"]]
    found, length, visited, why = bfs(world, (tx, tz), inward,
                                      box_pad=20, max_cells=20000)
    mark = "sampled" if i % 4 == 0 else "       "
    print(f"[{mark}] {r['name']} door=({x},{y},{z}) {r['facing']}: "
          f"BFS={'OK len='+str(length) if found else 'FAIL '+why} (visited {visited})")

print("=== east gate -> learning complex east-wing door threshold (1187,774) ===")
found, length, visited, why = bfs(world, (1645, 749), (1187, 774),
                                  box_pad=150, max_cells=200000)
print("gate->east-wing door:", found, "len", length, "visited", visited, why)
print("=== east gate -> south corridor door threshold (1214,803) ===")
found, length, visited, why = bfs(world, (1645, 749), (1214, 803),
                                  box_pad=150, max_cells=200000)
print("gate->south corridor door:", found, "len", length, "visited", visited, why)
print("=== is there a door on the main library east wall x=1258? ===")
for r in BUILD["door_sweep"]:
    if r.get("door") and r["door"][0] == 1258:
        print("door at x=1258:", r)
print("(none found above means no east-wall door on the main building)")
print("done")
