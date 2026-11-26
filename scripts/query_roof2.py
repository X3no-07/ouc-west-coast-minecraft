"""Roof counts for main (2141, Y=-20) and west wing (2142, Y=-29)."""
import sys
from pathlib import Path
from collections import Counter
sys.path.insert(0, r"C:\Users\lenovo\Documents\Codex\2026-11-25\wo\work\ouc-campus")
# reuse helpers from query_roof by importing it as a module would run it; copy minimal loader
import gzip, zlib, json
import numpy as np
from rules_preview import nbt

WORLD = Path(r"C:\Users\lenovo\Desktop\Games\.minecraft\versions\26.2-Fabric 0.19.3\saves\OUC-West-Coast-LandmarkRevision")
RD = WORLD / "dimensions" / "minecraft" / "overworld" / "region"

def get_chunk(cx, cz):
    rx, rz = cx // 32, cz // 32
    data = (RD / f"r.{rx}.{rz}.mca").read_bytes()
    idx = (cz % 32) * 32 + (cx % 32)
    off = int.from_bytes(data[idx*4:idx*4+3], "big")
    if off == 0:
        return None
    start = off * 4096
    length = int.from_bytes(data[start:start+4], "big")
    return nbt(zlib.decompress(data[start+5:start+4+length]))

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
        return palette[(int(word) >> int(shift)) & ((1 << bits) - 1)]["Name"]
    return None

cache = {}
def blk(x, y, z):
    key = (x // 16, z // 16)
    if key not in cache:
        cache[key] = get_chunk(*key)
    c = cache[key]
    return block_at(c, x, y, z) if c else None

def inside(x, z, poly):
    px, pz = x + 0.5, z + 0.5
    ins = False
    n = len(poly)
    for i in range(n):
        x1, z1 = poly[i]; x2, z2 = poly[(i+1) % n]
        if (z1 > pz) != (z2 > pz):
            xin = (pz - z1) * (x2 - x1) / (z2 - z1) + x1
            if px < xin:
                ins = not ins
    return ins

# MC float polygons from parent (local projection)
polys = {
    "main2141": ([(1049.03,581.62),(1045.2,610.07),(1092.64,616.47),(1096.47,588.02)], -20, (1045,1097,581,617)),
    "west2142": ([(1020.71,553.63),(1039.43,556.23),(1032.17,608.66),(1013.44,606.06)], -29, (1013,1040,553,609)),
}
for name, (poly, y, (x0,x1,z0,z1)) in polys.items():
    counts = Counter(); edge_counts = Counter()
    for x in range(x0, x1+1):
        for z in range(z0, z1+1):
            if not inside(x, z, poly):
                continue
            b = blk(x, y, z)
            counts[b] += 1
            is_edge = any(not inside(x+dx, z+dz, poly) for dx, dz in [(1,0),(-1,0),(0,1),(0,-1)])
            edge_counts[(b, "edge" if is_edge else "interior")] += 1
    print(name, "Y=", y, dict(counts), "total", sum(counts.values()))
    print("  edge/interior:", dict(edge_counts))
    # also one layer above and below
    for yy in (y-1, y+1):
        c = Counter()
        for x in range(x0, x1+1):
            for z in range(z0, z1+1):
                if inside(x, z, poly):
                    c[blk(x, yy, z)] += 1
        print("  Y=", yy, dict(c))
print("done")
