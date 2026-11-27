#!/usr/bin/env python3
"""v6: white-line correction + the missing Gaoyu Road middle segment,
on top of the road-fixed v5 world (staging-v6 copy).

White lines (corrected spec -- white WOOL is void, use white concrete):
  - centre line: 2 blocks wide (offsets 0 and 1), dashed in the v5
    style: 2 white, 2 grey repeating along the road ((s//2)%2==0).
    NO solid centre line, NO sparse 1-in-4 dash.
  - edge lines: unchanged from the road fix: main roads
    (primary/secondary/tertiary) keep the 1-block solid white concrete
    edge line at |off| = half-1; residential/service keep no edge line.
  - carriageway otherwise full dark-grey asphalt; kerb and sidewalk
    unchanged from the road fix.

Missing road (found by probing OSM + both worlds):
  - OSM ways 1292071627 + 1292071628, both residential, both named
    高峪路, bridge x 981-1233 at z~375, i.e. the middle of 山海北路
    between kept roads 1292071620 (west) and 1292068336 (east).
    make_v3_data.py's dedupe dropped them: same name + type as the
    neighbours, and their bboxes touch the neighbours' at the shared
    endpoints, which the overlap test counts as overlap.
  - Added here as one road with pts through the junctions of roads
    5 (1014,375), 10 (1136,375) and 21 (1176,375), same residential
    w5 cross-section as its neighbours. Nothing invented: the geometry
    is the two OSM ways joined end to end.
Writes v6-build-report.json. Does NOT touch level.dat (rename step
is separate). Does NOT touch anything but roads.
"""
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from finish_world import World  # noqa: E402
from build_v4 import top_y, is_tree_top, VEGETATION, AIR  # noqa: E402
from build_v5 import is_trim, is_door_block  # noqa: E402

WORK = HERE
WORLD_DIR = Path(os.environ.get(
    "V6_WORLD", str(WORK / "staging-v6" / "OUC-West-Coast-v5")))
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
EXCLUDE_RECTS = [
    [1259, 688, 1268, 708],   # learning east entrance steps
    [1003, 501, 1010, 509],   # engineering west steps
    [1071, 612, 1079, 619],   # info north building entrance steps
    [1010, 772, 1018, 779],   # info south building entrance steps
    [1636, 738, 1637, 744],   # east gate north return + pillar
    [1636, 754, 1637, 760],   # east gate south return + pillar
]
GATE_ROAD_CELLS = {(1636, 740), (1637, 741)}

# The missing middle of Gaoyu Road (OSM 1292071627 + 1292071628).
NEW_ROAD = {"id": 1292071627, "osm_ids": [1292071627, 1292071628],
            "type": "residential", "name": "高峪路", "width": 5,
            "material": "black_concrete",
            "sidewalk": "light_gray_concrete",
            "pts": [[981, 375], [1014, 375], [1136, 375],
                    [1176, 375], [1233, 374]]}
ROADS = V3["roads"] + [NEW_ROAD]


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
        width = r["width"]
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
                        elif o in (0, 1):
                            # centre line, 2 wide, v5 dash: 2 white, 2 grey
                            target = ROAD_LINE if (s // 2) % 2 == 0 else ROAD
                            rs["centre_white" if target == ROAD_LINE
                               else "centre_grey"] += 1
                        else:
                            target = ROAD
                    else:
                        if ao == half + 1:
                            target = WALK
                        elif o in (0, 1):
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
        print(f"road {ri:2d} {r['type']:11s} w{width}: {dict(rs)}")
    # --- zebra crossings at junctions between width>=5 roads ---
    roads = ROADS
    points = []
    for i in range(len(roads)):
        if roads[i]["width"] < 5:
            continue
        for j in range(i + 1, len(roads)):
            if roads[j]["width"] < 5:
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
            half = r["width"] // 2
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
    report = {"world": str(WORLD_DIR), "base": "v5+roadfix",
              "note": "v6: white concrete centre 2-wide WWGG dash, "
                      "1-wide white concrete edge lines kept; "
                      "missing Gaoyu middle segment added; "
                      "no version number in level.dat yet",
              "new_road": {"osm_ids": NEW_ROAD["osm_ids"],
                           "name": NEW_ROAD["name"],
                           "type": NEW_ROAD["type"],
                           "width": NEW_ROAD["width"],
                           "pts": NEW_ROAD["pts"],
                           "why_missing": "dropped by make_v3_data.py "
                           "dedupe: same name+type as neighbours, "
                           "bbox touching at shared endpoints "
                           "counted as overlap"},
              "totals": dict(stats), "per_road": per_road,
              "cells_changed": changed,
              "elapsed_s": round(time.time() - t0, 1)}
    json.dump(report, open(WORK / "v6-build-report.json", "w",
                           encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nV6 BUILD DONE: {changed} cells changed in "
          f"{report['elapsed_s']}s; totals: {dict(stats)}")


if __name__ == "__main__":
    main()
