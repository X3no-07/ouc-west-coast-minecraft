#!/usr/bin/env python3
"""v8: 1-wide WWGG dashed white concrete centre line + widened main
roads, on top of the v6 world (staging-v8 copy). v7 is void (deleted):
it wrongly made the centre line a 2-wide SOLID line.

User corrections on v7 (this round):
  - Centre line must be 1 block wide, white concrete, DASHED. A dash
    is 2 white blocks laid lengthwise along the road (1 wide, 2 long),
    then 2 grey blocks: 2 white / 2 grey repeating -- exactly the
    original v5 style ((s//2)%2==0 on the single centre column).
    NOT 2 wide, NOT solid, NOT the sparse 1-in-4 dots.
  - Main roads (primary/secondary/tertiary) are too narrow at 7-9:
    widen by 2 on EACH side (+4 total: 7 -> 11, 9 -> 13 carriageway).
    Only pave empty land and grass in the new strip; where a building
    stands, do not pave and do not demolish. After widening, the
    centre line is re-centred on the widened carriageway.
  - Widened main-road cross-section: 1-wide dashed white centre line,
    dark-grey asphalt carriageway, 1-wide solid white edge line,
    1 stone kerb at the outside, 1 light-grey sidewalk outside that.
  - Small roads (residential/service, 4-5 wide): width unchanged,
    centre line the same 1-wide WWGG dash, NO edge line, NO kerb,
    just asphalt + centre line (sidewalk kept as in v6).

Everything else identical to build_v6.py / build_v7.py: same 44
roads (V3 + the Gaoyu middle segment), same structure guards, same
zebra logic (using the widened width). Writes v8-build-report.json.
Renames the world to OUC-West-Coast-v8 and level.dat to
中国海洋大学西海岸校区v8 at the end.
"""
import gzip
import json
import os
import shutil
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from finish_world import World  # noqa: E402
from anvil import dumps, find, find_node, loads  # noqa: E402
from build_v4 import top_y, is_tree_top, VEGETATION, AIR  # noqa: E402
from build_v5 import is_trim, is_door_block  # noqa: E402

WORK = HERE
WORLD_DIR = Path(os.environ.get(
    "V8_WORLD", str(WORK / "staging-v8" / "OUC-West-Coast-v6")))
V3 = json.load(open(WORK / "v3-build-data.json", encoding="utf-8"))
V5 = json.load(open(WORK / "v5-build-data.json", encoding="utf-8"))
PLAN = json.load(open(WORK / "plan-v2.json", encoding="utf-8"))

ROAD = "minecraft:gray_concrete"
ROAD_LINE = "minecraft:white_concrete"
KERB = "minecraft:stone_bricks"
WALK = "minecraft:light_gray_concrete"
MAIN_TYPES = {"primary", "secondary", "tertiary"}
GUARD_BLOCKS = {"minecraft:red_terracotta", "minecraft:red_concrete",
                "minecraft:green_concrete", "minecraft:water"}
# Natural ground only: the widened strip may only be paved over
# empty land / grass. Anything built or decorated is left alone.
NATURAL = {"minecraft:grass_block", "minecraft:dirt",
           "minecraft:coarse_dirt", "minecraft:podzol",
           "minecraft:mycelium", "minecraft:sand",
           "minecraft:red_sand", "minecraft:gravel",
           "minecraft:snow_block", "minecraft:snow",
           "minecraft:mud", "minecraft:rooted_dirt",
           "minecraft:farmland"}
EXCLUDE_RECTS = [
    [1259, 688, 1268, 708],   # learning east entrance steps
    [1003, 501, 1010, 509],   # engineering west steps
    [1071, 612, 1079, 619],   # info north building entrance steps
    [1010, 772, 1018, 779],   # info south building entrance steps
    [1636, 738, 1637, 744],   # east gate north return + pillar
    [1636, 754, 1637, 760],   # east gate south return + pillar
]
GATE_ROAD_CELLS = {(1636, 740), (1637, 741)}

# The missing middle of Gaoyu Road (OSM 1292071627 + 1292071628),
# same as v6/v7.
NEW_ROAD = {"id": 1292071627, "osm_ids": [1292071627, 1292071628],
            "type": "residential", "name": "高峪路", "width": 5,
            "material": "black_concrete",
            "sidewalk": "light_gray_concrete",
            "pts": [[981, 375], [1014, 375], [1136, 375],
                    [1176, 375], [1233, 374]]}
ROADS = V3["roads"] + [NEW_ROAD]
# Effective widths: main roads +4 (2 each side); small roads unchanged.
for r in ROADS:
    r["_old_width"] = r["width"]
    r["_width"] = r["width"] + 4 if r["type"] in MAIN_TYPES else r["width"]


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


def rect_poly(rect):
    x0, z0, x1, z1 = rect
    return [[x0, z0], [x1, z0], [x1, z1], [x0, z1]]


def build_footprints():
    fps = [fp["polygon"] for fp in PLAN.get("footprints", [])]
    for m in V3.get("missing_buildings", []):
        if m.get("poly"):
            fps.append(m["poly"])
    fps.append(rect_poly(V5["learning"]["west_plaza"]["rect"]))
    fps.append(rect_poly([984, 694, 1008, 718]))  # v4 low building
    for area in V3["courts"]:
        fps.append(rect_poly(area["bbox"]))
    fps.append(rect_poly(V5["football"]["pitch_rect"]))
    return fps


FOOTPRINTS = build_footprints()


def in_structure(x, z):
    if (x, z) in GATE_ROAD_CELLS:
        return False
    for (x0, z0, x1, z1) in EXCLUDE_RECTS:
        if x0 <= x <= x1 and z0 <= z <= z1:
            return True
    for poly in FOOTPRINTS:
        if point_in_poly(x + 0.5, z + 0.5, poly):
            return True
    return False


def seg_intersect(p1, p2, p3, p4):
    def orient(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return 0 if v == 0 else (1 if v > 0 else -1)
    d1 = orient(p3, p4, p1)
    d2 = orient(p3, p4, p2)
    d3 = orient(p1, p2, p3)
    d4 = orient(p1, p2, p4)
    if d1 * d2 < 0 and d3 * d4 < 0:
        x1, y1 = p1
        x2, y2 = p2
        x3, y3 = p3
        x4, y4 = p4
        den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if den == 0:
            return None
        px = ((x1 * y2 - y1 * x2) * (x3 - x4) -
              (x1 - x2) * (x3 * y4 - y3 * x4)) / den
        py = ((x1 * y2 - y1 * x2) * (y3 - y4) -
              (y1 - y2) * (x3 * y4 - y3 * x4)) / den
        return (round(px), round(py))
    best = None
    for a in (p1, p2):
        for b in (p3, p4):
            d = abs(a[0] - b[0]) + abs(a[1] - b[1])
            if d <= 3 and (best is None or d < best[0]):
                best = (d, ((a[0] + b[0]) // 2, (a[1] + b[1]) // 2))
    return best[1] if best else None


def fix_level_dat(world_dir, report):
    p = Path(world_dir) / "level.dat"
    bak = p.with_name("level.dat.bak-v6")
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
            v = "中国海洋大学西海岸校区v8"
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
    overlay = {}
    kerb_cells = set()

    def gblock(x, y, z):
        v = overlay.get((x, y, z))
        return v if v is not None else world.get_block(x, y, z)

    def gtop_y(x, z):
        for y in range(64, -65, -1):
            b = gblock(x, y, z)
            if b is None or b in AIR or b in VEGETATION:
                continue
            return y
        return None

    def gset(x, y, z, block):
        world.set_block(x, y, z, block)
        overlay[(x, y, z)] = block
        if block == KERB:
            kerb_cells.add((x, z))
        else:
            kerb_cells.discard((x, z))

    stats = Counter()
    per_road = {}
    for ri, r in enumerate(ROADS):
        pts = r["pts"]
        width = r["_width"]
        old_half = r["_old_width"] // 2
        half = width // 2
        is_main = r["type"] in MAIN_TYPES
        rs = Counter()
        for (x1, z1), (x2, z2) in zip(pts, pts[1:]):
            steps = max(abs(x2 - x1), abs(z2 - z1), 1)
            dx, dz = x2 - x1, z2 - z1
            ew = abs(dx) >= abs(dz)
            for s in range(steps + 1):
                cx = round(x1 + dx * s / steps)
                cz = round(z1 + dz * s / steps)
                for o in range(-(half + 1), half + 2):
                    x, z = (cx, cz + o) if ew else (cx + o, cz)
                    ao = abs(o)
                    if is_main:
                        if ao == half + 1:
                            target = WALK
                        elif ao == half:
                            target = KERB
                        elif ao == half - 1:
                            target = ROAD_LINE
                            rs["edge_white"] += 1
                        elif o == 0:
                            # centre line, 1 wide, v5 WWGG dash:
                            # 2 white, 2 grey along the road
                            target = ROAD_LINE if (s // 2) % 2 == 0 else ROAD
                            rs["centre_white" if target == ROAD_LINE
                               else "centre_grey"] += 1
                        else:
                            target = ROAD
                    else:
                        if ao == half + 1:
                            target = WALK
                        elif o == 0:
                            # centre line, 1 wide, v5 WWGG dash
                            target = ROAD_LINE if (s // 2) % 2 == 0 else ROAD
                            rs["centre_white" if target == ROAD_LINE
                               else "centre_grey"] += 1
                        else:
                            target = ROAD
                    if not (0 <= x < 2093 and 0 <= z < 996):
                        rs["skipped_oob"] += 1
                        continue
                    if in_structure(x, z):
                        rs["skipped_structure"] += 1
                        continue
                    t = gtop_y(x, z)
                    if t is None:
                        rs["no_ground"] += 1
                        continue
                    cur = gblock(x, t, z)
                    if cur is None or is_trim(cur) or is_door_block(cur) \
                            or cur in GUARD_BLOCKS or is_tree_top(cur):
                        rs["skipped_guard"] += 1
                        continue
                    # New widened strip (outside the old road
                    # footprint): only pave empty land / grass, or
                    # existing road surface / road furniture. Never
                    # pave over built or decorated ground, never
                    # demolish a building.
                    if is_main and ao > old_half + 1:
                        if cur not in NATURAL and cur not in (
                                ROAD, ROAD_LINE, WALK, KERB):
                            rs["widen_blocked"] += 1
                            continue
                    if target in (WALK, KERB) and \
                            cur in (ROAD, ROAD_LINE):
                        rs["kept_road"] += 1
                        continue
                    if target == WALK and cur == KERB and \
                            (x, z) in kerb_cells:
                        rs["kept_kerb"] += 1
                        continue
                    if cur != target:
                        gset(x, t, z, target)
                        rs["paved"] += 1
                    above = gblock(x, t + 1, z)
                    if above in VEGETATION:
                        gset(x, t + 1, z, "minecraft:air")
                        rs["veg_cleared"] += 1
        per_road[str(ri)] = dict(rs)
        stats.update(rs)
        print(f"road {ri:2d} {r['type']:11s} w{r['_old_width']}->{width}: "
              f"{dict(rs)}")
    # --- zebra crossings at junctions between width>=5 roads ---
    roads = ROADS
    points = []
    for i in range(len(roads)):
        if roads[i]["_width"] < 5:
            continue
        for j in range(i + 1, len(roads)):
            if roads[j]["_width"] < 5:
                continue
            for a, b in zip(roads[i]["pts"], roads[i]["pts"][1:]):
                for c, d in zip(roads[j]["pts"], roads[j]["pts"][1:]):
                    p = seg_intersect(a, b, c, d)
                    if p is not None:
                        points.append((p, i, j))
    uniq = []
    for (p, i, j) in points:
        if not any(abs(p[0] - q[0]) <= 4 and abs(p[1] - q[1]) <= 4
                   for (q, _, _) in uniq):
            uniq.append((p, i, j))
    zebra = 0
    for (p, i, j) in uniq[:60]:
        for ri in (i, j):
            r = roads[ri]
            half = r["_width"] // 2
            is_main = r["type"] in MAIN_TYPES
            best = None
            for (a, b) in zip(r["pts"], r["pts"][1:]):
                d = abs(a[0] - p[0]) + abs(a[1] - p[1]) + \
                    abs(b[0] - p[0]) + abs(b[1] - p[1])
                if best is None or d < best[0]:
                    best = (d, a, b)
            _, a, b = best
            along_ew = abs(b[0] - a[0]) >= abs(b[1] - a[1])
            lo = -(half - 1) if is_main else -half
            hi = (half - 1) if is_main else half
            for k in (-3, -1, 1, 3):
                for o in range(lo, hi + 1):
                    if along_ew:
                        x, z = p[0] + k, p[1] + o
                    else:
                        x, z = p[0] + o, p[1] + k
                    if not (0 <= x < 2093 and 0 <= z < 996):
                        continue
                    if in_structure(x, z):
                        continue
                    t = gtop_y(x, z)
                    if t is None:
                        continue
                    cur = gblock(x, t, z)
                    if cur in (ROAD, ROAD_LINE):
                        gset(x, t, z, ROAD_LINE)
                        zebra += 1
    stats["zebra_cells"] = zebra
    stats["zebra_crossings"] = len(uniq[:60])
    changed = world.flush()
    report = {"world": str(WORLD_DIR), "base": "v6",
              "note": "v8: centre line 1-wide WWGG dashed white "
                      "concrete (v5 style) on all roads; main roads "
                      "widened +4 (7->11, 9->13), new strip only over "
                      "empty land/grass, no demolition; small roads "
                      "unchanged width, centre line only, no edge "
                      "line, no kerb",
              "widths": {str(ri): {"old": r["_old_width"],
                                    "new": r["_width"],
                                    "type": r["type"]}
                         for ri, r in enumerate(ROADS)},
              "totals": dict(stats), "per_road": per_road,
              "cells_changed": changed,
              "elapsed_s": round(time.time() - t0, 1)}
    # Readme + level.dat + folder rename to v8
    rp = WORLD_DIR / "Readme.txt"
    txt = rp.read_text(encoding="utf-8-sig")
    txt = txt.replace("OUC-West-Coast-v6", "OUC-West-Coast-v8")
    txt = txt.replace("西海岸校区v6", "西海岸校区v8")
    rp.write_text(txt, encoding="utf-8-sig")
    fix_level_dat(WORLD_DIR, report)
    new_dir = WORK / "staging-v8" / "OUC-West-Coast-v8"
    if new_dir.exists():
        shutil.rmtree(new_dir)
    shutil.move(str(WORLD_DIR), str(new_dir))
    report["world"] = str(new_dir)
    json.dump(report, open(WORK / "v8-build-report.json", "w",
                           encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nV8 BUILD DONE: {changed} cells changed in "
          f"{report['elapsed_s']}s; totals: {dict(stats)}")
    print("world now:", new_dir)


if __name__ == "__main__":
    main()
