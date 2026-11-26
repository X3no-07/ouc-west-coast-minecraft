"""Query blocks in the installed LandmarkRevision world, on the PC."""
import sys, json, gzip
from pathlib import Path
from collections import Counter
sys.path.insert(0, r"C:\Users\lenovo\Documents\Codex\2026-11-25\wo\work\ouc-campus")
from rules_preview import nbt, iter_chunks

WORLD = Path(r"C:\Users\lenovo\Desktop\Games\.minecraft\versions\26.2-Fabric 0.19.3\saves\OUC-West-Coast-LandmarkRevision")
print("world exists", WORLD.exists())
meta = json.loads((WORLD / "metadata.json").read_text(encoding="utf-8"))
print("metadata", meta)
level = nbt(gzip.decompress((WORLD / "level.dat").read_bytes()))["Data"]
print("LevelName", level["LevelName"], "Version", level["Version"]["Name"], "Spawn", level["SpawnX"], level["SpawnY"], level["SpawnZ"])

# Build a lookup for requested columns only, by decoding sections.
# We need block name at (x,y,z). Decode palette per section.
import numpy as np

def block_at(chunk, x, y, z):
    # chunk local
    lx, lz = x % 16, z % 16
    for section in chunk["sections"]:
        if "block_states" not in section:
            continue
        lowest = section["Y"] * 16
        if not (lowest <= y < lowest + 16):
            continue
        state = section["block_states"]
        palette = state["palette"]
        if len(palette) == 1:
            return palette[0]["Name"]
        bits = max(4, (len(palette) - 1).bit_length())
        per_word = 64 // bits
        data = state["data"].astype(np.uint64)
        idx = (y - lowest) * 256 + lz * 16 + lx
        word = data[idx // per_word]
        shift = (idx % per_word) * bits
        pi = int((word >> shift) & ((1 << bits) - 1))
        return palette[pi]["Name"]
    return None

targets_roof = []
for x in range(1020, 1095):
    for z in range(536, 563):
        targets_roof.append((x, -29, z))
targets_grass = [(x, -45, z) for x in range(1044, 1049) for z in range(569, 574)]

wanted = {}
for (x, y, z) in targets_roof + targets_grass:
    wanted.setdefault((x // 16, z // 16), []).append((x, y, z))

roof_counts = Counter()
grass_counts = Counter()
grass_list = []
roof_by_y = Counter()
# also top surface for grass area: find highest non-air per column in that patch
for fname in sorted((WORLD / "region").glob("*.mca")):
    for chunk in iter_chunks(fname):
        key = (chunk["xPos"], chunk["zPos"])
        if key not in wanted:
            continue
        for (x, y, z) in wanted[key]:
            b = block_at(chunk, x, y, z)
            if y == -29:
                roof_counts[b] += 1
            else:
                grass_counts[b] += 1
                grass_list.append(((x, y, z), b))
print("ROOF Y=-29 X1020-1094 Z536-562 counts:", dict(roof_counts))
print("GRASS patch X1044-1048 Z569-573 Y=-45 counts:", dict(grass_counts))
print("GRASS list sample:", grass_list[:10])
# top block per column in grass patch and roof patch: scan y from 30 down to -60
# reuse block_at per column
top = {}
for fname in sorted((WORLD / "region").glob("*.mca")):
    for chunk in iter_chunks(fname):
        key = (chunk["xPos"], chunk["zPos"])
        if key not in wanted:
            continue
        for (x, y, z) in wanted[key]:
            if y == -45:
                for yy in range(30, -61, -1):
                    b = block_at(chunk, x, yy, z)
                    if b and b not in ("minecraft:air", "minecraft:cave_air", "minecraft:void_air"):
                        top[(x, z)] = (yy, b)
                        break
print("TOP in grass patch (x,z)->(y,block):")
for k in sorted(top):
    print(" ", k, top[k])
