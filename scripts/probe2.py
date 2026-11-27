#!/usr/bin/env python3
"""Probe 2: gate beam vs ground, west court highs, door ground-floor air."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from finish_world import World  # noqa: E402

WORK = HERE
V2 = r"C:\Users\lenovo\Desktop\Games\.minecraft\versions\26.2-Fabric 0.19.3\saves\OUC-West-Coast-v2"
V3 = WORK / "staging-v3" / "OUC-West-Coast-v3"
BUILD = json.load(open(WORK / "v3-build-report.json", encoding="utf-8"))

w2 = World(V2)
w3 = World(str(V3))

def col(w, x, z, y0, y1):
    return {y: w.get_block(x, y, z) for y in range(y0, y1 + 1)}

print("=== gate passage column (1636,749) y -53..-43 ===")
print("v2:", {y: b for y, b in col(w2, 1636, 749, -53, -43).items() if b and b != "minecraft:air"})
print("v3:", {y: b for y, b in col(w3, 1636, 749, -53, -43).items() if b and b != "minecraft:air"})
print("=== gate column (1636,745) ===")
print("v2:", {y: b for y, b in col(w2, 1636, 745, -53, -43).items() if b and b != "minecraft:air"})
print("v3:", {y: b for y, b in col(w3, 1636, 745, -53, -43).items() if b and b != "minecraft:air"})
print("=== gate post column (1635,749) / (1638,749) v3 ===")
print("1635:", {y: b for y, b in col(w3, 1635, 749, -53, -43).items() if b and b != "minecraft:air"})
print("1638:", {y: b for y, b in col(w3, 1638, 749, -53, -43).items() if b and b != "minecraft:air"})
print("=== west court column (700,203) y -35..-27 v3 ===")
print({y: b for y, b in col(w3, 700, 203, -35, -27).items() if b and b != "minecraft:air"})
print("=== west court column (710,203) y -35..-27 v3 ===")
print({y: b for y, b in col(w3, 710, 203, -35, -27).items() if b and b != "minecraft:air"})
print("=== door ground-floor air check (inward-2 at gy+1, gy+2) ===")
for r in BUILD["door_sweep"]:
    if not r.get("door"):
        continue
    (x, y, z) = r["door"]
    gy = r["ground_y"]
    inward = {"north": (x, z + 2), "south": (x, z - 2),
              "west": (x + 2, z), "east": (x - 2, z)}[r["facing"]]
    ix, iz = inward
    b1 = w3.get_block(ix, gy + 1, iz)
    b2 = w3.get_block(ix, gy + 2, iz)
    bf = w3.get_block(ix, gy, iz)
    ok = (bf not in (None, "minecraft:air")) and b1 in (None, "minecraft:air") and b2 in (None, "minecraft:air")
    print(f"{r['name']}: inward2=({ix},{iz}) floor@{gy}={bf} +1={b1} +2={b2} {'WALKABLE' if ok else 'BLOCKED'}")
print("done")
