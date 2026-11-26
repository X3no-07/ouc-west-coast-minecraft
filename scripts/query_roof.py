"""Dump roof structure for info-north long wing + columns, and highways near it."""
import sys, json, gzip, zlib
from pathlib import Path
from collections import Counter
import numpy as np
sys.path.insert(0, r"C:\Users\lenovo\Documents\Codex\2026-11-25\wo\work\ouc-campus")
from rules_preview import nbt

WORLD = Path(r"C:\Users\lenovo\Desktop\Games\.minecraft\versions\26.2-Fabric 0.19.3\saves\OUC-West-Coast-LandmarkRevision")
RD = WORLD / "dimensions" / "minecraft" / "overworld" / "region"
if not RD.exists():
    RD = WORLD / "region"

def get_chunk(cx, cz):
    rx, rz = cx // 32, cz // 32
    f = RD / f"r.{rx}.{rz}.mca"
    data = f.read_bytes()
    idx = (cz % 32) * 32 + (cx % 32)
    off = int.from_bytes(data[idx*4:idx*4+3], "big")
    if off == 0:
        return None
    start = off * 4096
    length = int.from_bytes(data[start:start+4], "big")
    chunk = nbt(zlib.decompress(data[start+5:start+4+length]))
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

def column(x, z, y0=-60, y1=0):
    out = []
    for yy in range(y0, y1+1):
        b = blk(x, yy, z)
        if b and b != "minecraft:air":
            out.append((yy, b))
    return out

# 1) column profiles at sample points in long wing (2143: X1020-1094 Z535-562, roof -29)
print("COLUMNS long wing:")
for (x, z) in [(1050,550),(1060,545),(1030,540),(1080,555),(1025,550),(1090,550),(1050,537),(1050,560)]:
    print(" ", (x,z), column(x,z))
print("COLUMNS main 2141 (X1045-1096 Z581-616):")
for (x, z) in [(1070,600),(1055,590),(1090,610)]:
    print(" ", (x,z), column(x,z))
print("COLUMNS west wing 2142:")
for (x, z) in [(1025,580),(1030,600)]:
    print(" ", (x,z), column(x,z))
# 2) roof Y=-29 spatial map: for each block type, min/max x/z and count by distance from footprint edge?
# Use original 2143 polygon in MC float coords (from parent): [(1093.9,544.68),(1022.75,535.58),(1020.5,553.2),(1091.65,562.3)]
# point-in-polygon test
poly = [(1093.9,544.68),(1022.75,535.58),(1020.5,553.2),(1091.65,562.3)]
def inside(x, z):
    # ray casting, point at cell centre x+0.5,z+0.5
    px, pz = x+0.5, z+0.5
    ins = False
    n = len(poly)
    for i in range(n):
        x1,z1 = poly[i]; x2,z2 = poly[(i+1)%n]
        if ((z1>pz)!=(z2>pz)):
            xin = (pz-z1)*(x2-x1)/(z2-z1)+x1
            if px < xin:
                ins = not ins
    return ins
counts = Counter()
edge_counts = Counter()
for x in range(1020,1095):
    for z in range(536,563):
        if not inside(x,z):
            continue
        b = blk(x,-29,z)
        counts[b]+=1
        # edge if any 4-neighbour outside polygon
        is_edge = any(not inside(x+dx,z+dz) for dx,dz in [(1,0),(-1,0),(0,1),(0,-1)])
        edge_counts[(b, "edge" if is_edge else "interior")]+=1
print("ROOF -29 inside 2143 polygon:", dict(counts), "total", sum(counts.values()))
print("ROOF -29 edge vs interior:", dict(edge_counts))
# 3) what is at Y=-28 and -30 in same polygon (parapet above? floor below?)
for y in (-30,-28):
    c = Counter()
    for x in range(1020,1095):
        for z in range(536,563):
            if inside(x,z):
                c[blk(x,y,z)]+=1
    print(f"Y={y} inside 2143:", dict(c))
# 4) ground columns in courtyard patch + around: top block and y
print("GROUND courtyard + surroundings top:")
for (x,z) in [(1044,569),(1046,571),(1048,573),(1040,575),(1055,575),(1030,565),(1060,570)]:
    col = column(x,z, y0=-60, y1=-30)
    print(" ", (x,z), col)
print("done")
