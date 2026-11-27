#!/usr/bin/env python3
"""v3 ground check (runs on the PC, read-only except its own outputs).

1. Confirms the generating rule for the (944,694) rubble: reads
   sentinel-surface.npz (stable_low_vegetation -> ESA class 50 -> Arnis
   urban rubble) and reports the class at that point.
2. Maps Arnis class-50 rubble patches: sample the map on an 8-cell grid,
   flood-fill each hit at full resolution (patches < ~8 cells wide may be
   missed; the known patch is ~80x80).  A patch counts as rubble only if
   it is speckled (holds cobble / coloured terracotta / gravel), so
   uniform stone_bricks paving is left alone.  Proposes a repave per
   patch (grass for open ground, stone_bricks when it touches a skirt
   or lies inside OSM place=square 浩海广场).  The rubble set includes
   gray_concrete_powder: the (944,694) blob mixes it with stone_bricks
   and cyan terracotta, and leaving it out would leave grey speckle
   behind in the repaved grass.
3. Reports the terrain Y range of the two basketball areas.
Writes v3-ground-fixes.json (consumed by build_v3.py) and prints a report.
"""
import json
import sys
from collections import Counter, deque
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from finish_world import World  # noqa: E402

WORK = HERE
WORLD_DIR = WORK / "staging-v3" / "OUC-West-Coast-v3"
PLAN = json.load(open(WORK / "plan-v2.json", encoding="utf-8"))
DATA = json.load(open(WORK / "v3-build-data.json", encoding="utf-8"))

LON0, LAT0 = 120.01335, 35.77065
DLON, DLAT = 0.0232, 0.00895

RUBBLE = {
    "minecraft:stone_bricks", "minecraft:cobblestone",
    "minecraft:mossy_cobblestone", "minecraft:stone",
    "minecraft:cyan_terracotta", "minecraft:light_blue_terracotta",
    "minecraft:white_concrete", "minecraft:andesite",
    "minecraft:polished_andesite", "minecraft:diorite",
    "minecraft:polished_diorite", "minecraft:granite",
    "minecraft:polished_granite", "minecraft:gravel",
    "minecraft:coarse_dirt",
    "minecraft:gray_concrete_powder",
}
RUBBLE_MARKERS = {
    "minecraft:cobblestone", "minecraft:mossy_cobblestone",
    "minecraft:cyan_terracotta", "minecraft:light_blue_terracotta",
    "minecraft:gravel", "minecraft:coarse_dirt",
}


def mc_to_lonlat(x, z):
    lon = LON0 + x / 2092 * DLON
    lat = LAT0 + (1 - z / 995) * DLAT
    return lon, lat


def sentinel_class_at(x, z):
    npz = WORK / "sentinel-surface.npz"
    if not npz.exists():
        return None, "sentinel-surface.npz not found"
    try:
        import numpy as np
    except ImportError:
        return None, "numpy not available"
    with np.load(npz) as src:
        left, bottom, right, top = [float(v) for v in src["bounds"]]
        bare = src["stable_low_vegetation"]
    rows, cols = bare.shape
    lon, lat = mc_to_lonlat(x, z)
    col = int((lon - left) / (right - left) * cols)
    row = int((top - lat) / (top - bottom) * rows)
    if not (0 <= row < rows and 0 <= col < cols):
        return None, f"MC ({x},{z}) outside sentinel bounds"
    padded = np.pad(bare, 1, mode="edge")
    support = int(padded[row:row + 3, col:col + 3].sum())
    is_bare = bool(bare[row, col])
    cls = 50 if (is_bare and support >= 5) else 30
    return cls, (f"bare={is_bare} support={support}/9 class={cls} "
                 f"(npz {rows}x{cols}, bounds {left},{bottom},{right},{top})")


# OSM place=square 浩海广场 (way from osm-area-aligned-v2.xml, MC coords).
# Its paving is real (uniform stone_bricks, Sentinel class 30 at centre):
# never repave it to grass, whatever the speckle markers say.
HAOHAI_SQUARE = [(1280, 658), (1268, 759), (1544, 793), (1556, 692)]


def point_in_poly(x, z, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        x1, z1 = poly[i]
        x2, z2 = poly[(i + 1) % n]
        if (z1 > z) != (z2 > z):
            xi = (x2 - x1) * (z - z1) / (z2 - z1) + x1
            if x < xi:
                inside = not inside
    return inside


def main():
    world = World(str(WORLD_DIR))
    report = {}
    # --- 1. sentinel class at (944,694)
    cls, detail = sentinel_class_at(944, 694)
    report["patch_944_694"] = {"sentinel_class": cls, "detail": detail}
    print(f"(944,694) sentinel: class={cls} ({detail})", flush=True)
    mix = Counter()
    for x in range(905, 986):
        for z in range(655, 736):
            t = world.top_solid(x, z, y_top=64, y_bottom=-64)
            if t:
                mix[t[1]] += 1
    report["patch_944_694"]["top_mix_80x80"] = dict(mix.most_common(12))
    print("  top mix 80x80:", dict(mix.most_common(12)), flush=True)

    # --- 2. rubble patches (8-cell grid sample + flood fill)
    footprints = [fp["polygon"] for fp in PLAN.get("footprints", [])]
    for m in DATA["missing_buildings"]:
        if m.get("poly"):
            footprints.append(m["poly"])
    # bbox pre-checks so in_building stays cheap inside the flood fill
    fp_boxes = []
    for p in footprints:
        xs = [c[0] for c in p]; zs = [c[1] for c in p]
        fp_boxes.append((min(xs), min(zs), max(xs), max(zs), p))

    def in_building(x, z):
        for (x0, z0, x1, z1, p) in fp_boxes:
            if x0 <= x <= x1 and z0 <= z <= z1:
                if point_in_poly(x + 0.5, z + 0.5, p):
                    return True
        return False

    pave = set()
    for p in PLAN.get("paving", []):
        for (x, z) in p.get("cells", []):
            pave.add((x, z))
    road = set()
    for r in DATA["roads"]:
        pts = r["pts"]
        for (x1, z1), (x2, z2) in zip(pts, pts[1:]):
            steps = max(abs(x2 - x1), abs(z2 - z1), 1)
            for s in range(steps + 1):
                cx = round(x1 + (x2 - x1) * s / steps)
                cz = round(z1 + (z2 - z1) * s / steps)
                for dx in range(-r["width"] // 2, r["width"] // 2 + 1):
                    for dz in range(-r["width"] // 2, r["width"] // 2 + 1):
                        road.add((cx + dx, cz + dz))

    def top_block(x, z):
        t = world.top_solid(x, z, y_top=64, y_bottom=-64)
        return t[1] if t else None

    def is_rubble_cell(x, z):
        if not (0 <= x < 2093 and 0 <= z < 996):
            return False
        if (x, z) in pave or (x, z) in road or in_building(x, z):
            return False
        return top_block(x, z) in RUBBLE

    print("sampling map on an 8-cell grid...", flush=True)
    hits = []
    for x in range(0, 2093, 8):
        for z in range(0, 996, 8):
            if is_rubble_cell(x, z):
                hits.append((x, z))
    print(f"grid hits: {len(hits)}", flush=True)
    # flood-fill each hit at full resolution
    seen = set()
    patches = []
    for h in hits:
        if h in seen:
            continue
        comp = {}
        dq = deque([h])
        seen.add(h)
        while dq:
            (x, z) = dq.popleft()
            b = top_block(x, z)
            if b not in RUBBLE:
                continue
            comp[(x, z)] = b
            for nb in ((x + 1, z), (x - 1, z), (x, z + 1), (x, z - 1)):
                if nb not in seen and 0 <= nb[0] < 2093 and 0 <= nb[1] < 996:
                    if nb not in pave and nb not in road and not in_building(*nb):
                        seen.add(nb)
                        dq.append(nb)
        if len(comp) >= 20:
            markers = sum(1 for b in comp.values() if b in RUBBLE_MARKERS)
            xs = [c[0] for c in comp]; zs = [c[1] for c in comp]
            patches.append({"cells": comp, "n": len(comp), "markers": markers,
                            "bbox": [min(xs), min(zs), max(xs), max(zs)],
                            "mix": dict(Counter(comp.values()).most_common(6))})
    patches.sort(key=lambda p: -p["n"])
    print(f"patches (>=20 cells): {len(patches)}", flush=True)
    fixes = []
    for p in patches:
        if p["markers"] == 0:
            print(f"  leave: {p['n']} cells bbox {p['bbox']} "
                  f"(uniform stone, likely deliberate paving) {p['mix']}", flush=True)
            continue
        xs = [c[0] for c in p["cells"]]
        zs = [c[1] for c in p["cells"]]
        cx = sum(xs) / len(xs)
        cz = sum(zs) / len(zs)
        if point_in_poly(cx, cz, HAOHAI_SQUARE):
            mat = "stone_bricks"
            reason = "OSM place=square 浩海广场（实测铺装，Sentinel 30 类）"
        else:
            touches = any((x + dx, z + dz) in pave
                          for (x, z) in p["cells"]
                          for dx in (-2, -1, 0, 1, 2) for dz in (-2, -1, 0, 1, 2))
            mat = "stone_bricks" if touches else "grass_block"
            reason = ("adjoins building skirt/plaza" if touches
                      else "open ground, no OSM feature (construction-era bare ground)")
        fixes.append({"material": mat, "cells": [list(c) for c in p["cells"]],
                      "reason": reason})
        print(f"  fix {mat}: {p['n']} cells bbox {p['bbox']} "
              f"[{reason}] mix={p['mix']}", flush=True)
    json.dump({"fixes": fixes},
              open(WORK / "v3-ground-fixes.json", "w", encoding="utf-8"), ensure_ascii=False)
    report["fixes"] = [{"material": f["material"], "n_cells": len(f["cells"]),
                        "reason": f["reason"]} for f in fixes]
    report["patches_left_alone"] = [
        {"n_cells": p["n"], "bbox": p["bbox"], "mix": p["mix"]}
        for p in patches if p["markers"] == 0]
    # --- 3. court terrain
    courts = {}
    for area in DATA["courts"]:
        x0, z0, x1, z1 = area["bbox"]
        ys = []
        for x in range(x0, x1 + 1, 3):
            for z in range(z0, z1 + 1, 3):
                t = world.top_solid(x, z, y_top=64, y_bottom=-64)
                if t:
                    ys.append(t[0])
        courts[area["area"]] = {"y_min": min(ys), "y_max": max(ys),
                                 "y_modal": Counter(ys).most_common(1)[0][0],
                                 "sampled": len(ys)}
    report["courts_terrain"] = courts
    print("court terrain:", json.dumps(courts, ensure_ascii=False), flush=True)
    json.dump(report, open(WORK / "v3-ground-check.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("wrote v3-ground-fixes.json + v3-ground-check.json", flush=True)


if __name__ == "__main__":
    main()
