#!/usr/bin/env python3
"""v9: pave the built-up area with WHITE concrete (user picked option 2,
but lighter than the light-grey sidewalk: white concrete).

User decision (2026-11-27): ground is 79% grass because Arnis fills all
unmapped land with grass and OSM maps no paved plazas/walkways here.
Option 2: pave only the built-up area, keep the real green spaces.
Material: white concrete (NOT light-grey concrete -- that is the
existing sidewalk colour; user wants it lighter).

Scope: rectangle = bbox of all plan-v2.json building footprints,
expanded by 30 on each side: x 365-1588, z 160-946. Inside it, replace
the top layer only where it is grass_block or dirt with white
concrete. Roads, sidewalks, plazas, courts, buildings and every other
already-paved surface are untouched (their tops are not grass/dirt).
Flowers/grass plants on a paved cell are cleared; a cell with a tree
(trunk/leaves/sapling) above it is skipped and keeps its grass.

Kept green even inside the rectangle:
  - OSM leisure=park (2, south) and leisure=pitch (in-map ones)
    polygons from osm-area-aligned.xml (local linear projection).
  - 浩海广场 rect and 学习综合体西广场 rect (plazas are untouched).
  - Football pitch rect and the two V3 basketball-court bboxes
    (sports surfaces are untouched).

Everything outside the rectangle is untouched: outer fields, woods,
beach and sea stay as they are. Writes v9-build-report.json.
Renames the world to OUC-West-Coast-v9 and level.dat to
中国海洋大学西海岸校区v9 at the end.
"""
import gzip
import json
import os
import shutil
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from finish_world import World  # noqa: E402
from anvil import dumps, find, find_node, loads  # noqa: E402
from build_v4 import VEGETATION, AIR  # noqa: E402

WORK = HERE
WORLD_DIR = Path(os.environ.get(
    "V9_WORLD", str(WORK / "staging-v9" / "OUC-West-Coast-v8")))
PLAN = json.load(open(WORK / "plan-v2.json", encoding="utf-8"))
V3 = json.load(open(WORK / "v3-build-data.json", encoding="utf-8"))
V5 = json.load(open(WORK / "v5-build-data.json", encoding="utf-8"))

PAVE = "minecraft:white_concrete"
PAVEABLE = {"minecraft:grass_block", "minecraft:dirt"}

# --- built-up rectangle: footprint bbox + 30 -------------------------
_xs, _zs = [], []
for _fp in PLAN.get("footprints", []):
    for _px, _pz in _fp["polygon"]:
        _xs.append(_px)
        _zs.append(_pz)
RECT = (max(0, int(min(_xs)) - 30), max(0, int(min(_zs)) - 30),
        min(2092, int(max(_xs)) + 30), min(995, int(max(_zs)) + 30))

# --- rect exclusions: plazas and sports surfaces (untouched) ---------
RECT_EXCLUDE = [
    [1259, 640, 1340, 760],   # 浩海广场 (central lawn bed inside)
    [1110, 660, 1150, 740],   # 学习综合体西广场
    [679, 250, 749, 357],     # football pitch rect
    [1131, 470, 1238, 516],   # info-north basketball courts bbox
    [681, 183, 839, 241],     # west-sports basketball courts bbox
]

# --- OSM green polygons (parks + pitches), projected to world coords --
def _to_xy(lon, lat):
    x = (lon - 120.01335) / (120.03655 - 120.01335) * 2093
    z = (35.77960 - lat) / (35.77960 - 35.77065) * 996
    return (x, z)


def load_green_polys():
    t = ET.parse(WORK / "github-repo" / "data" / "osm-area-aligned.xml")
    r = t.getroot()
    nodes = {}
    for n in r.iter("node"):
        nodes[n.get("id")] = (float(n.get("lon")), float(n.get("lat")))
    polys = []
    for w in r.iter("way"):
        tags = {c.get("k"): c.get("v") for c in w.iter("tag")}
        if tags.get("leisure") not in ("park", "pitch"):
            continue
        pts = [_to_xy(*nodes[nd.get("ref")])
               for nd in w.iter("nd") if nd.get("ref") in nodes]
        if len(pts) < 3:
            continue
        xs = [p[0] for p in pts]
        zs = [p[1] for p in pts]
        polys.append({"kind": tags["leisure"],
                      "bbox": [int(min(xs)), int(min(zs)),
                               int(max(xs)), int(max(zs))],
                      "poly": pts})
    return polys


GREEN_POLYS = load_green_polys()


def point_in_poly(x, z, poly):
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, zi = poly[i]
        xj, zj = poly[j]
        if ((zi > z) != (zj > z)) and \
                (x < (xj - xi) * (z - zi) / (zj - zi) + xi):
            inside = not inside
        j = i
    return inside


def in_green(x, z):
    for g in GREEN_POLYS:
        bx0, bz0, bx1, bz1 = g["bbox"]
        if bx0 <= x <= bx1 and bz0 <= z <= bz1 and \
                point_in_poly(x + 0.5, z + 0.5, g["poly"]):
            return g["kind"]
    return None


def in_rect_exclude(x, z):
    for (x0, z0, x1, z1) in RECT_EXCLUDE:
        if x0 <= x <= x1 and z0 <= z <= z1:
            return True
    return False


# --- plants: pass over (pave below, clear above) vs tree-like (skip) --
FLOWERS = {
    "minecraft:oxeye_daisy", "minecraft:azure_bluet",
    "minecraft:cornflower", "minecraft:lily_of_the_valley",
    "minecraft:wither_rose", "minecraft:sunflower",
    "minecraft:lilac", "minecraft:rose_bush", "minecraft:peony",
    "minecraft:pink_petals", "minecraft:torchflower",
    "minecraft:pitcher_plant", "minecraft:white_tulip",
    "minecraft:orange_tulip", "minecraft:pink_tulip",
    "minecraft:red_tulip", "minecraft:allium",
    "minecraft:blue_orchid", "minecraft:spore_blossom",
    "minecraft:hanging_roots", "minecraft:glow_lichen",
    "minecraft:moss_carpet",
}
PASS_TOP = set(VEGETATION) | FLOWERS


def is_tree_like(block):
    if block is None:
        return False
    return (block.endswith("_log") or block.endswith("_leaves") or
            block.endswith("_sapling") or
            block in ("minecraft:mushroom_stem", "minecraft:bamboo",
                      "minecraft:sugar_cane", "minecraft:cactus",
                      "minecraft:sweet_berry_bush",
                      "minecraft:brown_mushroom", "minecraft:red_mushroom"))


def fix_level_dat(world_dir, report):
    p = Path(world_dir) / "level.dat"
    bak = p.with_name("level.dat.bak-v8")
    if not bak.exists():
        shutil.copyfile(p, bak)
    now_ms = int(time.time() * 1000)
    root = loads(gzip.decompress(p.read_bytes()))
    data = find_node(root[2], "Data")
    old_name = find(data[2], "LevelName")[1]
    old_played = find(data[2], "LastPlayed")[1]
    data_nodes = []
    for (t, n, v) in data[2]:
        if n == "LastPlayed":
            v = now_ms
        elif n == "LevelName":
            v = "中国海洋大学西海岸校区v9"
        data_nodes.append((t, n, v))
    new_root = (root[0], root[1],
                [(t, n, data_nodes if n == "Data" else v)
                 for (t, n, v) in root[2]])
    p.write_bytes(gzip.compress(dumps(new_root), compresslevel=6))
    root2 = loads(gzip.decompress(p.read_bytes()))
    data2 = find_node(root2[2], "Data")
    report["level_dat"] = {
        "old_name": old_name, "new_name": find(data2[2], "LevelName")[1],
        "old_lastplayed": old_played,
        "new_lastplayed": find(data2[2], "LastPlayed")[1],
        "spawn": [find(data2[2], k)[1]
                  for k in ("SpawnX", "SpawnY", "SpawnZ")],
    }
    print("level.dat:", json.dumps(report["level_dat"], ensure_ascii=False))


def main():
    t0 = time.time()
    world = World(str(WORLD_DIR))
    x0, z0, x1, z1 = RECT
    stats = Counter()
    tops = Counter()

    def gblock(x, y, z):
        return world.get_block(x, y, z)

    def gtop(x, z):
        """Top solid block, skipping air and small plants/flowers."""
        for y in range(64, -65, -1):
            b = gblock(x, y, z)
            if b is None or b in AIR or b in PASS_TOP:
                continue
            return (y, b)
        return None

    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            res = gtop(x, z)
            if res is None:
                stats["no_ground"] += 1
                continue
            t, cur = res
            tops[cur] += 1
            if cur not in PAVEABLE:
                continue
            if in_rect_exclude(x, z):
                stats["excluded_plaza_court"] += 1
                continue
            kind = in_green(x, z)
            if kind:
                stats[f"excluded_osm_{kind}"] += 1
                continue
            # tree above? (canopy/trunk would normally be the top
            # already, but check explicitly: trunk, leaves, sapling)
            tree = False
            for y in range(t + 1, min(t + 9, 65)):
                if is_tree_like(gblock(x, y, z)):
                    tree = True
                    break
            if tree:
                stats["skipped_tree"] += 1
                continue
            world.set_block(x, t, z, PAVE)
            stats["paved_" + cur.split(":")[1]] += 1
            for y in range(t + 1, min(t + 4, 65)):
                if gblock(x, y, z) in PASS_TOP:
                    world.set_block(x, y, z, "minecraft:air")
                    stats["veg_cleared"] += 1
        if (x - x0) % 300 == 0:
            print(f"x={x} done, paved so far "
                  f"{stats['paved_grass_block'] + stats['paved_dirt']}",
                  flush=True)

    changed = world.flush()
    stats["zebra_crossings"] = 35  # unchanged from v8; roads untouched
    report = {"world": str(WORLD_DIR), "base": "v8",
              "note": "v9: option 2 -- pave built-up area with WHITE "
                      "concrete (lighter than light-grey sidewalk). "
                      "Rect = footprint bbox + 30. OSM parks/pitches, "
                      "plazas and courts kept green/untouched; trees "
                      "skipped; outside rect untouched.",
              "rect": list(RECT),
              "footprint_bbox": [int(min(_xs)), int(min(_zs)),
                                 int(max(_xs)), int(max(_zs))],
              "rect_exclude": RECT_EXCLUDE,
              "green_polys": [{"kind": g["kind"], "bbox": g["bbox"]}
                              for g in GREEN_POLYS],
              "totals": dict(stats),
              "top_before": dict(tops.most_common(20)),
              "cells_changed": changed,
              "elapsed_s": round(time.time() - t0, 1)}
    rp = WORLD_DIR / "Readme.txt"
    txt = rp.read_text(encoding="utf-8-sig")
    txt = txt.replace("OUC-West-Coast-v8", "OUC-West-Coast-v9")
    txt = txt.replace("西海岸校区v8", "西海岸校区v9")
    rp.write_text(txt, encoding="utf-8-sig")
    fix_level_dat(WORLD_DIR, report)
    new_dir = WORK / "staging-v9" / "OUC-West-Coast-v9"
    if new_dir.exists():
        shutil.rmtree(new_dir)
    shutil.move(str(WORLD_DIR), str(new_dir))
    report["world"] = str(new_dir)
    json.dump(report, open(WORK / "v9-build-report.json", "w",
                           encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nV9 BUILD DONE: {changed} cells changed in "
          f"{report['elapsed_s']}s; totals: {dict(stats)}")
    print("world now:", new_dir)


if __name__ == "__main__":
    main()
