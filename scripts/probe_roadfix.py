#!/usr/bin/env python3
"""Road-fix continuity probe (corrected classification).

For each of the 43 road centerlines, walk the centerline exactly like
the build does and classify every cell by its TOP block:
  - road: top is gray/white concrete (carriageway or dash)
  - covered: a gray/white surface exists below the top with >=2 air
    above it (road passing under a roof/beam/tree -- walkable)
  - structure: inside a building/court/pitch footprint or a protected
    exclusion rect (steps, gate returns) -- not a break, reported apart
  - oob: outside the 2093x996 map
  - break: anything else (record the top block)
Breaks are grouped into runs. Also prints cross-section strips.
Usage: python3 probe_roadfix.py [out.json]
"""
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from finish_world import World  # noqa: E402
from build_v4 import top_y, is_tree_top  # noqa: E402
from finish_world import AIR

WORK = HERE
WORLD_DIR = WORK / "staging-roadfix" / "OUC-West-Coast-v5"
V3 = json.load(open(WORK / "v3-build-data.json", encoding="utf-8"))
V5 = json.load(open(WORK / "v5-build-data.json", encoding="utf-8"))
PLAN = json.load(open(WORK / "plan-v2.json", encoding="utf-8"))

ROAD_SURFACE = {"minecraft:gray_concrete", "minecraft:white_concrete"}
# protected structures the road must not pave over (steps, gate returns)
EXCLUDE_RECTS = [
    [1259, 688, 1268, 708],   # learning east entrance steps
    [1003, 501, 1010, 509],   # engineering west steps
    [1071, 612, 1079, 619],   # info north building entrance steps
    [1010, 772, 1018, 779],   # info south building entrance steps
    [1636, 738, 1637, 744],   # east gate north return + pillar
    [1636, 754, 1637, 760],   # east gate south return + pillar
]
# the two gate-line cells the road is meant to pave through (side door)
GATE_ROAD_CELLS = {(1636, 740), (1637, 741)}


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


def centerline_cells(pts):
    cells = []
    for (x1, z1), (x2, z2) in zip(pts, pts[1:]):
        steps = max(abs(x2 - x1), abs(z2 - z1), 1)
        dx, dz = x2 - x1, z2 - z1
        for s in range(steps + 1):
            c = (round(x1 + dx * s / steps), round(z1 + dz * s / steps))
            if not cells or cells[-1] != c:
                cells.append(c)
    return cells


def main():
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        WORK / "roadfix-probe-baseline.json"
    world = World(str(WORLD_DIR))
    report = {"world": str(WORLD_DIR), "roads": {}}
    total_break = 0
    for ri, r in enumerate(V3["roads"]):
        cells = centerline_cells(r["pts"])
        classes = []
        for (x, z) in cells:
            if not (0 <= x < 2093 and 0 <= z < 996):
                classes.append(("oob", ""))
                continue
            t = top_y(world, x, z)
            b = world.get_block(x, t, z) if t is not None else None
            if b in ROAD_SURFACE:
                classes.append(("road", b))
                continue
            # covered road? any gray/white surface in the column with
            # >=2 air directly above it (road under a roof/beam/floor)
            covered = False
            if t is not None:
                for y in range(t - 1, -64, -1):
                    bb = world.get_block(x, y, z)
                    if bb in ROAD_SURFACE:
                        air_above = 0
                        for yy in range(y + 1, min(y + 4, 64)):
                            if world.get_block(x, yy, z) in AIR:
                                air_above += 1
                            else:
                                break
                        if air_above >= 2:
                            covered = True
                        break
            if covered:
                classes.append(("covered", b or ""))
                continue
            if in_structure(x, z):
                classes.append(("structure", b or ""))
                continue
            classes.append(("break", b or ""))
        runs = []
        cur = None
        for idx, (cls, blk) in enumerate(classes):
            if cur and cur["cls"] == cls and cur["blk"] == blk:
                cur["end_idx"] = idx
                cur["len"] += 1
            else:
                cur = {"cls": cls, "blk": blk, "start_idx": idx,
                       "end_idx": idx, "len": 1}
                runs.append(cur)
        cnt = Counter(c for c, _ in classes)
        brk = cnt.get("break", 0)
        total_break += brk
        report["roads"][str(ri)] = {
            "type": r["type"], "width": r["width"],
            "name": r.get("name"), "id": r.get("id"),
            "n_cells": len(cells), "counts": dict(cnt),
            "break_runs": [
                {"cls": rn["cls"], "blk": rn["blk"], "len": rn["len"],
                 "from": cells[rn["start_idx"]],
                 "to": cells[rn["end_idx"]]}
                for rn in runs if rn["cls"] in ("break", "structure", "covered")
            ],
        }
        print(f"road {ri:2d} {r['type']:11s} w{r['width']} "
              f"cells={len(cells):4d} road={cnt.get('road', 0):4d} "
              f"covered={cnt.get('covered', 0):3d} structure={cnt.get('structure', 0):3d} "
              f"oob={cnt.get('oob', 0):3d} BREAK={brk:4d}")
        for rn in runs:
            if rn["cls"] in ("break", "structure", "covered"):
                print(f"    {rn['cls'].upper():9s} x{rn['len']:3d} {rn['blk']} "
                      f"{cells[rn['start_idx']]} -> {cells[rn['end_idx']]}")
    print(f"\nTOTAL true breaks: {total_break}")
    json.dump(report, open(out_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("wrote", out_path)

    print("\n--- cross-sections (top block, centre -> out) ---")
    for ri in (8, 7, 13, 2, 34, 38, 40, 6, 14, 24):
        r = V3["roads"][ri]
        pts = r["pts"]
        (ax, az), (bx, bz) = pts[len(pts) // 2 - 1], pts[len(pts) // 2]
        cx, cz = (ax + bx) // 2, (az + bz) // 2
        half = r["width"] // 2
        ew = abs(bx - ax) >= abs(bz - az)
        strip = []
        for o in range(-(half + 2), half + 3):
            x, z = (cx, cz + o) if ew else (cx + o, cz)
            t = top_y(world, x, z)
            b = world.get_block(x, t, z) if t is not None else None
            strip.append((b or "?").replace("minecraft:", ""))
        print(f"road {ri:2d} {r['type']:11s} w{r['width']} at ({cx},{cz}) "
              f"{'EW' if ew else 'NS'}: {' | '.join(strip)}")


if __name__ == "__main__":
    main()
