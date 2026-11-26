"""Fast targeted query: read only the region chunks covering the sample area."""
import sys, json, gzip, zlib
from pathlib import Path
from collections import Counter
import numpy as np
sys.path.insert(0, r"C:\Users\lenovo\Documents\Codex\2026-11-25\wo\work\ouc-campus")
from rules_preview import nbt

WORLD = Path(r"C:\Users\lenovo\Desktop\Games\.minecraft\versions\26.2-Fabric 0.19.3\saves\OUC-West-Coast-LandmarkRevision")
print("world exists", WORLD.exists())
meta = json.loads((WORLD / "metadata.json").read_text(encoding="utf-8"))
print("metadata", meta)
level = nbt(gzip.decompress((WORLD / "level.dat").read_bytes()))["Data"]
print("LevelName", level.get("LevelName"), "Version", level.get("Version",{}).get("Name"), "keys", sorted(level.keys()))
print("Spawn", level.get("spawn"))

def get_chunk(cx, cz):
    rx, rz = cx // 32, cz // 32
    rd = WORLD / "dimensions" / "minecraft" / "overworld" / "region"
    if not rd.exists():
        rd = WORLD / "region"
    f = rd / f"r.{rx}.{rz}.mca"
    data = f.read_bytes()
    idx = (cz % 32) * 32 + (cx % 32)
    off = int.from_bytes(data[idx*4:idx*4+3], "big")
    cnt = data[idx*4+3]
    if off == 0:
        return None
    start = off * 4096
    length = int.from_bytes(data[start:start+4], "big")
    comp = data[start+4]
    assert comp == 2, comp
    chunk = nbt(zlib.decompress(data[start+5:start+4+length]))
    assert chunk["xPos"] == cx and chunk["zPos"] == cz
    return chunk

def block_at(chunk, x, y, z):
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
        pi = (int(word) >> int(shift)) & ((1 << bits) - 1)
        return palette[pi]["Name"]
    return None

cache = {}
def blk(x, y, z):
    key = (x // 16, z // 16)
    if key not in cache:
        cache[key] = get_chunk(*key)
    c = cache[key]
    return block_at(c, x, y, z) if c else None

def top_block(x, z, ymax=40, ymin=-60):
    for yy in range(ymax, ymin-1, -1):
        b = blk(x, yy, z)
        if b and b not in ("minecraft:air", "minecraft:cave_air", "minecraft:void_air"):
            return yy, b
    return None

roof = Counter()
for x in range(1020, 1095):
    for z in range(536, 563):
        roof[blk(x, -29, z)] += 1
print("ROOF Y=-29 X1020-1094 Z536-562:", dict(roof))
grass = Counter()
for x in range(1044, 1049):
    for z in range(569, 574):
        grass[blk(x, -45, z)] += 1
print("GRASS Y=-45 X1044-1048 Z569-573:", dict(grass))
print("TOP grass patch:")
for x in range(1044, 1049):
    for z in range(569, 574):
        print(" ", (x, z), top_block(x, z))
print("TOP roof patch corners/centre:")
for (x, z) in [(1023,536),(1094,545),(1050,550),(1020,562),(1094,562),(1060,545)]:
    print(" ", (x, z), top_block(x, z))
print("ROOF at other Y near -29 for centre (1060,550):")
for yy in range(-35, -20):
    print("  y", yy, blk(1060, yy, 550))
print("done")
