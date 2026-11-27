#!/usr/bin/env python3
"""Next-version build: panorama-driven appearance correction for the rest of
the OUC West Coast campus, on a copy of the v4 world.

Sources (all verified, read before writing this):
  v5-panorama-checklist.md -- live browser, 39 panorama points 2026-11-27
  v5-resources.md / v5-resources-round2.md -- photo/resource tables
  (official canteen photos tinghai_1f_1.jpg / wanghai_1f_1.jpg)
Ground/roof heights below were probed from the v4 world (probe_v5.py).

Steps (in order):
  1. roads: grey asphalt carriageway + stone kerbs + light sidewalks +
     dashed white centre lines + zebra crossings at road junctions
  2. HaoHai square (pale beige slabs, lawn bed, red sculpture group,
     stone bollards) + learning-complex west plaza
  3. learning complex facades + east main entrance (10-step staircase)
  4. dorms: brown/cream grid + blue glass + red roofs (Tinghai 1-9,
     Wanghai phase-1 4); Wanghai phase-2 east walls -> yellow
  5. Tinghai restaurant (dark-blue louvre upper, grey pillars, external
     white stair) + Wanghai restaurant (classical cream facade, red
     pitched roof, pediment, north blue-glass bay, south steps)
  6. engineering building (unnamed-144, inferred): brown stone arch
     front, cream wings, red pitched tower cap, arched entrance + steps
  7. basketball courts: red surround, floodlight poles, dark-green fence
  8. football field: turf, lines, red track, goals (no stands)
  9. east gate refinement: pillar caps/bases, plaque band, beam cap,
     wall returns + pedestrian side doors, forecourt paving
 10. leisure park: blue walkways (loop around the unnamed cluster),
     blue OUC letters sculpture
 11. level.dat rename + LastPlayed refresh
Writes v5-build-report.json. Run on the PC against the staging copy.
Set V5_WORLD to override the world dir (VM dry-run).
"""
import gzip
import json
import math
import os
import shutil
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from anvil import dumps, find, find_node, loads  # noqa: E402
from build_v4 import (is_parapet_keepable, place_door, stair_state,  # noqa: E402
                      modal, top_y, is_solid, is_air, is_glass,
                      is_tree_top, VEGETATION, AIR)
from finish_world import World  # noqa: E402

WORK = HERE
WORLD_DIR = Path(os.environ.get(
    "V5_WORLD", str(WORK / "staging-v5" / "OUC-West-Coast-v5")))
V5 = json.load(open(WORK / "v5-build-data.json", encoding="utf-8"))
V3 = json.load(open(WORK / "v3-build-data.json", encoding="utf-8"))
PLAN = json.load(open(WORK / "plan-v2.json", encoding="utf-8"))

# --- palette ---
LC_FIELD = "minecraft:light_gray_concrete"   # 学习综合体浅灰石材
LC_FIN = "minecraft:gray_concrete"           # 深灰蓝竖鳍/窄窗
LC_GLASS = "minecraft:light_blue_stained_glass"
LC_WHITE = "minecraft:white_concrete"        # 底层白色鳍片带
DORM_FIELD = "minecraft:brown_terracotta"    # 宿舍棕/红棕板
DORM_GRID = "minecraft:smooth_sandstone"     # 奶油网格框
DORM_GROUND = "minecraft:brown_concrete"     # 宿舍底层深棕
DORM_GLASS = "minecraft:light_blue_stained_glass"
ROOF_RED = "minecraft:red_terracotta"
ROAD = "minecraft:gray_concrete"             # 深灰沥青
ROAD_LINE = "minecraft:white_concrete"
ROAD_LINE_Y = "minecraft:yellow_concrete"
KERB = "minecraft:stone_bricks"
WALK = "minecraft:light_gray_concrete"
PLAZA_BEIGE = "minecraft:smooth_sandstone"   # 浩海广场浅米色石板
PLAZA_LIGHT = "minecraft:light_gray_concrete"
PATH_BLUE = "minecraft:blue_concrete"
STEP_FILL = "minecraft:stone_bricks"
FLOOR_IN = "minecraft:oak_planks"
WHITE_STAIR = "minecraft:white_concrete_stairs"

TRIM_SKIP_SUFFIX = ("_slab", "_stairs", "_trapdoor", "_pressure_plate",
                    "_button", "_fence", "_wall", "_carpet")
TRIM_SKIP_EXACT = {
    "minecraft:daylight_detector", "minecraft:end_rod", "minecraft:lightning_rod",
    "minecraft:barrel", "minecraft:torch", "minecraft:lantern",
    "minecraft:campfire", "minecraft:flower_pot", "minecraft:chest",
    "minecraft:lever", "minecraft:target", "minecraft:lectern",
    "minecraft:ladder", "minecraft:vine", "minecraft:cobweb",
    "minecraft:light", "minecraft:iron_bars",
}


def is_trim(block):
    if block is None:
        return False
    if block in TRIM_SKIP_EXACT:
        return True
    return any(block.endswith(s) for s in TRIM_SKIP_SUFFIX)


def is_door_block(block):
    return block is not None and block.endswith("_door")


def ground_y(world, x, z):
    """Highest solid block at/below the local surface (v3's ground_y)."""
    for y in range(64, -65, -1):
        b = world.get_block(x, y, z)
        if b is None:
            continue
        if b in AIR or b in VEGETATION or is_tree_top(b):
            continue
        return y
    return None


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


def face_cells(rect):
    x0, z0, x1, z1 = rect
    return ([(x, z0) for x in range(x0, x1 + 1)] +
            [(x, z1) for x in range(x0, x1 + 1)] +
            [(x0, z) for z in range(z0, z1 + 1)] +
            [(x1, z) for z in range(z0, z1 + 1)])


# ------------------------------------------------------------------ step 1
def repave_roads(world, report):
    """Grey asphalt + stone kerbs + light sidewalks + dashed centre lines.

    Skips building footprints, plazas (stone bricks), the info courtyard
    walkways (blue), court surfaces (green/white), water and trees.
    Zebra crossings are painted at road-junction points afterwards.
    """
    footprints = [fp["polygon"] for fp in PLAN.get("footprints", [])]
    for m in V3.get("missing_buildings", []):
        if m.get("poly"):
            footprints.append(m["poly"])
    footprints.append(rect_poly(V5["learning"]["west_plaza"]["rect"]))
    footprints.append(rect_poly([984, 694, 1008, 718]))  # v4 low building
    for area in V3["courts"]:
        footprints.append(rect_poly(area["bbox"]))
    footprints.append(rect_poly(V5["football"]["pitch_rect"]))

    def in_building(x, z):
        for poly in footprints:
            if point_in_poly(x + 0.5, z + 0.5, poly):
                return True
        return False

    SKIP_TOP = {"minecraft:stone_bricks", "minecraft:water",
                "minecraft:blue_concrete", "minecraft:green_concrete",
                "minecraft:white_concrete"}
    stats = Counter()
    # keep the per-road centre-line phase so dashes line up per segment
    crossings = []
    for ri, r in enumerate(V3["roads"]):
        pts = r["pts"]
        width = r["width"]
        half = width // 2
        for (x1, z1), (x2, z2) in zip(pts, pts[1:]):
            steps = max(abs(x2 - x1), abs(z2 - z1), 1)
            dx, dz = x2 - x1, z2 - z1
            for s in range(steps + 1):
                cx = round(x1 + dx * s / steps)
                cz = round(z1 + dz * s / steps)
                if abs(dx) >= abs(dz):
                    perp = [(0, o) for o in range(-half, half + 1)]
                else:
                    perp = [(o, 0) for o in range(-half, half + 1)]
                for (ox, oz) in perp:
                    x, z = cx + ox, cz + oz
                    if not (0 <= x < 2093 and 0 <= z < 996):
                        stats["skipped_oob"] += 1
                        continue
                    if in_building(x, z):
                        stats["skipped_building"] += 1
                        continue
                    t = top_y(world, x, z)
                    if t is None:
                        stats["no_ground"] += 1
                        continue
                    cur = world.get_block(x, t, z)
                    if cur in SKIP_TOP or is_tree_top(cur):
                        stats["skipped_plaza_water_tree"] += 1
                        continue
                    off = max(abs(ox), abs(oz))
                    if off >= half:
                        target = WALK
                    elif off == half - 1:
                        target = KERB
                    elif off == 0 and (s // 2) % 2 == 0:
                        target = ROAD_LINE
                    else:
                        target = ROAD
                    if cur != target:
                        world.set_block(x, t, z, target)
                        stats["paved"] += 1
                    above = world.get_block(x, t + 1, z)
                    if above in VEGETATION:
                        world.set_block(x, t + 1, z, "minecraft:air")
                        stats["veg_cleared"] += 1
        crossings.append((ri, pts))
    # --- zebra crossings at junctions between width>=5 roads ---
    def seg_intersect(p1, p2, p3, p4):
        def orient(a, b, c):
            v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            return 0 if v == 0 else (1 if v > 0 else -1)
        d1 = orient(p3, p4, p1)
        d2 = orient(p3, p4, p2)
        d3 = orient(p1, p2, p3)
        d4 = orient(p1, p2, p4)
        if d1 * d2 < 0 and d3 * d4 < 0:
            # intersection point
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
        # near-touch (T-junction): closest endpoints within 3
        best = None
        for a in (p1, p2):
            for b in (p3, p4):
                d = abs(a[0] - b[0]) + abs(a[1] - b[1])
                if d <= 3 and (best is None or d < best[0]):
                    best = (d, ((a[0] + b[0]) // 2, (a[1] + b[1]) // 2))
        return best[1] if best else None

    points = []
    roads = V3["roads"]
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
    # dedupe nearby points
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
            # direction of the road at the crossing: use its nearest segment
            best = None
            for (a, b) in zip(r["pts"], r["pts"][1:]):
                d = abs(a[0] - p[0]) + abs(a[1] - p[1]) + \
                    abs(b[0] - p[0]) + abs(b[1] - p[1])
                if best is None or d < best[0]:
                    best = (d, a, b)
            _, a, b = best
            along_ew = abs(b[0] - a[0]) >= abs(b[1] - a[1])
            for k in (-3, -1, 1, 3):
                for o in range(-(half - 1), half):
                    if along_ew:
                        x, z = p[0] + k, p[1] + o
                    else:
                        x, z = p[0] + o, p[1] + k
                    if not (0 <= x < 2093 and 0 <= z < 996):
                        continue
                    if in_building(x, z):
                        continue
                    t = top_y(world, x, z)
                    if t is None:
                        continue
                    cur = world.get_block(x, t, z)
                    if cur in (ROAD, "minecraft:black_concrete", WALK, ROAD_LINE):
                        world.set_block(x, t, z, ROAD_LINE)
                        zebra += 1
    stats["zebra_cells"] = zebra
    stats["zebra_crossings"] = len(uniq[:60])
    report["roads"] = dict(stats)
    print("roads done:", dict(stats))


# ------------------------------------------------------------------ step 2
def repave_square(world, report):
    """HaoHai square: pale beige slabs + lawn bed + red sculpture group +
    stone bollards. West plaza: light-grey slabs + concentric joints."""
    sq = V5["haoha_square"]
    x0, z0, x1, z1 = sq["rect"]
    counts = Counter()
    RECOLORABLE = {"minecraft:stone_bricks", "minecraft:black_concrete",
                   "minecraft:light_gray_concrete",
                   "minecraft:gray_concrete_powder", "minecraft:cyan_terracotta",
                   "minecraft:cobblestone", "minecraft:cracked_stone_bricks"}
    # NOTE: grey concrete (road carriageway) and white concrete (lane
    # dashes) are deliberately NOT recolorable: the diagonal road
    # 1292068339 crosses the square's north strip and must stay a road.
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            t = top_y(world, x, z)
            if t is None:
                continue
            b = world.get_block(x, t, z)
            if b is None or b in AIR or is_tree_top(b):
                continue
            above = world.get_block(x, t + 1, z)
            if above is not None and above not in AIR and above not in VEGETATION:
                continue
            if b in RECOLORABLE:
                world.set_block(x, t, z, PLAZA_BEIGE)
                counts["plaza_slabs"] += 1
    # lawn bed: raised grass with stone edging
    bx0, bz0, bx1, bz1 = sq["lawn_bed"]
    bed_top = None
    for x in range(bx0, bx1 + 1):
        for z in range(bz0, bz1 + 1):
            t = top_y(world, x, z)
            if t is None:
                continue
            if bed_top is None:
                bed_top = t
            edge = (x in (bx0, bx1) or z in (bz0, bz1))
            world.set_block(x, t + 1, z,
                            "minecraft:stone_bricks" if edge
                            else "minecraft:grass_block")
            counts["lawn_bed_cells"] += 1
    # red sculpture group on the bed (schematic: no text in-game)
    sx, sz = sq["sculpture"]
    base = (bed_top or -49) + 1
    for y in range(base + 1, base + 6):
        world.set_block(sx + 5, y, sz, "minecraft:red_concrete")
    for dx in (-3, -2):
        for dz in (-1, 0):
            world.set_block(sx + dx, base + 1, sz + dz, "minecraft:red_concrete")
    for dx in (7, 8):
        for dz in (-1, 0):
            world.set_block(sx + dx, base + 1, sz + dz, "minecraft:red_concrete")
    counts["sculpture_cells"] = 5 + 4 + 4
    # stone bollards along the plaza east edge (south of the Z650-671 road)
    for z in range(sq["bollard_z"][0] + 26, sq["bollard_z"][1] + 1, 4):
        t = top_y(world, sq["bollard_x"], z)
        if t is None:
            continue
        b = world.get_block(sq["bollard_x"], t, z)
        if b in (PLAZA_BEIGE, WALK, ROAD):
            world.set_block(sq["bollard_x"], t + 1, z, "minecraft:smooth_stone")
            counts["bollards"] += 1
    # west plaza: light-grey slabs + concentric smooth-stone joints
    wp = V5["learning"]["west_plaza"]
    wx0, wz0, wx1, wz1 = wp["rect"]
    cx, cz = wp["center"]
    for x in range(wx0, wx1 + 1):
        for z in range(wz0, wz1 + 1):
            t = top_y(world, x, z)
            if t is None:
                continue
            b = world.get_block(x, t, z)
            if b is None or b in AIR or is_tree_top(b):
                continue
            if b not in ("minecraft:grass_block", "minecraft:dirt",
                         "minecraft:stone_bricks", "minecraft:black_concrete",
                         "minecraft:light_gray_concrete",
                         "minecraft:gray_concrete_powder"):
                continue
            above = world.get_block(x, t + 1, z)
            if above is not None and above not in AIR and above not in VEGETATION:
                continue
            ring = round(math.hypot(x - cx, z - cz))
            mat = ("minecraft:smooth_stone" if ring % 6 == 0
                   else PLAZA_LIGHT)
            if b != mat:
                world.set_block(x, t, z, mat)
                counts["west_plaza_cells"] += 1
    # lamp posts at the west plaza corners (white post + light)
    for (lx, lz) in ((wx0 + 3, wz0 + 3), (wx1 - 3, wz0 + 3),
                     (wx0 + 3, wz1 - 3), (wx1 - 3, wz1 - 3)):
        t = top_y(world, lx, lz)
        if t is None:
            continue
        for y in range(t + 1, t + 4):
            world.set_block(lx, y, lz, "minecraft:white_concrete")
        world.set_block(lx, t + 4, lz, "minecraft:light")
        counts["lamp_posts"] += 1
    report["squares"] = dict(counts)
    print("squares done:", dict(counts))


# ------------------------------------------------------------------ step 3
def recolor_learning(world, report):
    """Learning complex: light-grey stone field, dark fins, blue glass.
    West face + east face of the main block get a central blue-glass
    curtain-wall bay; east face fins every 3rd column + white ground band.
    Roofs stay flat white (aerial: white/grey library roofs)."""
    L = V5["learning"]
    parts = [("学习综合体·图书馆主楼", L["main"]),
             ("学习综合体·北楼西侧", L["north_west"]),
             ("学习综合体·南楼西侧", L["south_west"]),
             ("学习综合体·北楼东侧低区", L["north_east_low"]),
             ("学习综合体·南楼东侧低区", L["south_east_low"])] + \
            [(c["name"], c) for c in L["corridors"]]
    bay = L["curtain_bay"]
    out = {}
    for name, s in parts:
        x0, z0, x1, z1 = s["rect"]
        gy, ry = s["ground_y"], s["roof_y"]
        counts = Counter()
        is_main = (name == "学习综合体·图书馆主楼")
        for side, line in (("west", [(x0, z) for z in range(z0, z1 + 1)]),
                           ("east", [(x1, z) for z in range(z0, z1 + 1)]),
                           ("north", [(x, z0) for x in range(x0, x1 + 1)]),
                           ("south", [(x, z1) for x in range(x0, x1 + 1)])):
            fin_every = 3 if (is_main and side == "east") else 4
            for i, (x, z) in enumerate(line):
                coord = z if side in ("west", "east") else x
                in_bay = is_main and side in ("west", "east") and \
                    bay[0] <= coord <= bay[1]
                is_fin = (i % fin_every == 0)
                for y in range(gy + 1, ry + 1):
                    b = world.get_block(x, y, z)
                    if b is None or b in AIR:
                        continue
                    if is_door_block(b) or b == "minecraft:light":
                        continue
                    if is_trim(b) and not is_glass(b):
                        continue
                    if y == ry:
                        continue  # roof line
                    if is_glass(b):
                        if b != LC_GLASS:
                            world.set_block(x, y, z, LC_GLASS)
                            counts["glass"] += 1
                        continue
                    if in_bay:
                        # curtain wall: full-height blue glass, fin frame
                        if i in (0, len(line) - 1) or (coord in (bay[0], bay[1])):
                            if b != LC_FIN:
                                world.set_block(x, y, z, LC_FIN)
                                counts["fin"] += 1
                        elif b != LC_GLASS:
                            world.set_block(x, y, z, LC_GLASS)
                            counts["curtain"] += 1
                        continue
                    if y <= gy + 3:
                        # ground band: main -> blue glass curtain;
                        # wings/low -> white with dark-glass colonnade
                        if is_main:
                            if is_fin:
                                if b != LC_FIN:
                                    world.set_block(x, y, z, LC_FIN)
                                    counts["fin"] += 1
                            elif b != LC_GLASS:
                                world.set_block(x, y, z, LC_GLASS)
                                counts["curtain"] += 1
                        else:
                            if is_fin:
                                if b != LC_FIN:
                                    world.set_block(x, y, z, LC_FIN)
                                    counts["fin"] += 1
                            elif b != LC_WHITE:
                                world.set_block(x, y, z, LC_WHITE)
                                counts["ground_white"] += 1
                        continue
                    if is_fin:
                        if b != LC_FIN:
                            world.set_block(x, y, z, LC_FIN)
                            counts["fin"] += 1
                    elif b != LC_FIELD:
                        world.set_block(x, y, z, LC_FIELD)
                        counts["field"] += 1
        out[name] = dict(counts)
        print(f"learning {name}: {dict(counts)}")
    report["learning_facades"] = out
    return out


def build_east_entrance(world, report):
    """Learning-complex east entrance: door in the curtain wall + a
    10-step, 3-tier granite staircase (21 wide) down to HaoHai square,
    central 3 columns in white concrete (the white ramp/stair)."""
    e = V5["learning"]["east_entrance"]
    wall_x = e["wall_x"]
    dz = e["door_z"]
    feet = e["door_feet"]
    gy_out = modal([top_y(world, x, z)
                    for x in range(wall_x + 1, wall_x + 12)
                    for z in range(e["step_z0"], e["step_z1"] + 1)
                    if top_y(world, x, z) is not None])
    if gy_out is None:
        report["learning_east_entrance"] = {"error": "no ground outside"}
        return None
    # door column: find a solid cell near dz on the wall face
    chosen = None
    for cz in [dz, dz - 1, dz + 1, dz - 2, dz + 2]:
        if is_solid(world, wall_x, feet, cz) and \
                is_solid(world, wall_x, feet + 1, cz):
            chosen = cz
            break
    if chosen is None:
        report["learning_east_entrance"] = {"error": "no solid wall column"}
        return None
    dz = chosen
    place_door(world, wall_x, feet, dz, "east")
    # interior landing 3 deep (west) + down-stair to the ground floor
    for d in (1, 2, 3):
        for y in (feet, feet + 1):
            if is_solid(world, wall_x - d, y, dz):
                world.set_block(wall_x - d, y, dz, "minecraft:air")
    for ox in (-1, 0, 1):
        for d in (1, 2, 3):
            b = world.get_block(wall_x - d, feet - 1, dz + ox)
            if b is None or b in AIR or is_glass(b):
                world.set_block(wall_x - d, feet - 1, dz + ox, FLOOR_IN)
    # ground surface inside (first solid below the landing)
    ground_in = None
    for y in range(feet - 1, -64, -1):
        b = world.get_block(wall_x - 2, y, dz)
        if b is not None and b not in AIR and not is_glass(b) \
                and b != "minecraft:light":
            ground_in = y + 1
            break
    down = 0
    if ground_in is not None and feet - ground_in > 1:
        drop = feet - ground_in
        if 0 < drop <= 6:
            for i in range(drop * 2):
                x = wall_x - (4 + i)
                cell_y = (feet - 1) - (i // 2)
                for oz in (-1, 0, 1):
                    world.set_block(x, cell_y, dz + oz,
                                    "minecraft:stone_stairs[facing=east,"
                                    "half=bottom,shape=straight]")
                    for y in (cell_y + 1, cell_y + 2):
                        if is_solid(world, x, y, dz + oz):
                            world.set_block(x, y, dz + oz, "minecraft:air")
                    for y in range(cell_y - 1, ground_in - 1, -1):
                        if not is_solid(world, x, y, dz + oz):
                            world.set_block(x, y, dz + oz, LC_WHITE)
                down += 1
    # outside staircase: 10 steps, 21 wide, 3 tiers (paired rises)
    # heights from the wall outward: -45,-45,-46,-46,-47,-47,-48,-48,-49,-49
    heights = [feet, feet, feet - 1, feet - 1, feet - 2, feet - 2,
               feet - 3, feet - 3, feet - 4, feet - 4]
    steps = 0
    for k, cell_y in enumerate(heights):
        x = wall_x + 1 + k
        for z in range(e["step_z0"], e["step_z1"] + 1):
            white = abs(z - dz) <= 1  # central white ramp/stair
            st = ("minecraft:white_concrete_stairs" if white
                  else "minecraft:stone_stairs")
            world.set_block(
                x, cell_y, z,
                f"{st}[facing=west,half=bottom,shape=straight]")
            steps += 1
            for y in range(cell_y - 1, gy_out, -1):
                if not is_solid(world, x, y, z):
                    world.set_block(x, y, z, STEP_FILL)
    # headroom above the top steps
    for k in (0, 1):
        x = wall_x + 1 + k
        cell_y = heights[k]
        for z in range(e["step_z0"], e["step_z1"] + 1):
            for y in (cell_y + 1, cell_y + 2):
                if is_solid(world, x, y, z):
                    world.set_block(x, y, z, "minecraft:air")
    res = {"door": [wall_x, feet, dz], "facing": "east",
           "ground_y_outside": gy_out, "steps": steps,
           "ground_in": ground_in, "down_treads": down}
    report["learning_east_entrance"] = res
    print(f"east entrance: {res}")
    return res


# ------------------------------------------------------------------ step 4
def field_set(world, rect, ground_y, roof_y):
    """Most common non-glass, non-trim wall materials on the faces."""
    counts = Counter()
    for (x, z) in face_cells(rect):
        for y in range(ground_y + 1, roof_y + 1):
            b = world.get_block(x, y, z)
            if b is None or b in AIR or is_glass(b):
                continue
            if is_door_block(b) or b == "minecraft:light":
                continue
            if is_trim(b):
                continue
            counts[b] += 1
    return {b for b, _ in counts.most_common(3)}


def recolor_dorm(world, spec, roof=True):
    """Brown/red-brown panels + cream grid + blue glass + dark-brown
    ground floor; roof -> red terracotta (flat top layer only)."""
    x0, z0, x1, z1 = spec["rect"]
    gy, ry = spec["ground_y"], spec["roof_y"]
    fields = field_set(world, spec["rect"], gy, ry)
    counts = Counter()
    # roof first (so the wall pass never touches it)
    if roof:
        for x in range(x0, x1 + 1):
            for z in range(z0, z1 + 1):
                b = world.get_block(x, ry, z)
                if b is None or b in AIR or b.endswith("_slab"):
                    continue
                if b != ROOF_RED:
                    world.set_block(x, ry, z, ROOF_RED)
                    counts["roof"] += 1
        for x in range(x0, x1 + 1):
            for z in range(z0, z1 + 1):
                near_edge = (x in (x0, x0 + 1, x1 - 1, x1) or
                             z in (z0, z0 + 1, z1 - 1, z1))
                for y in range(ry + 1, ry + 11):
                    b = world.get_block(x, y, z)
                    if b is None or b in AIR:
                        continue
                    if y <= ry + 2 and near_edge and is_parapet_keepable(b):
                        continue
                    world.set_block(x, y, z, "minecraft:air")
                    counts["clutter_cleared"] += 1
    for side, line in (("west", [(x0, z) for z in range(z0, z1 + 1)]),
                       ("east", [(x1, z) for z in range(z0, z1 + 1)]),
                       ("north", [(x, z0) for x in range(x0, x1 + 1)]),
                       ("south", [(x, z1) for x in range(x0, x1 + 1)])):
        for i, (x, z) in enumerate(line):
            grid_col = (i % 3 == 0)
            for y in range(gy + 1, ry + 1):
                b = world.get_block(x, y, z)
                if b is None or b in AIR:
                    continue
                if is_door_block(b) or b == "minecraft:light":
                    continue
                if is_trim(b) and not is_glass(b):
                    continue
                if y == ry:
                    continue
                if is_glass(b):
                    if b != DORM_GLASS:
                        world.set_block(x, y, z, DORM_GLASS)
                        counts["glass"] += 1
                    continue
                if b not in fields:
                    continue
                if y <= gy + 3:
                    if b != DORM_GROUND:
                        world.set_block(x, y, z, DORM_GROUND)
                        counts["ground"] += 1
                elif grid_col or (y - gy) % 4 == 0:
                    if b != DORM_GRID:
                        world.set_block(x, y, z, DORM_GRID)
                        counts["grid"] += 1
                elif b != DORM_FIELD:
                    world.set_block(x, y, z, DORM_FIELD)
                    counts["field"] += 1
    print(f"dorm {spec['name']}: {dict(counts)}")
    return dict(counts)


def recolor_yellow_walls(world, spec):
    """Wanghai phase-2 east dorm: walls -> yellow concrete (as west/mid
    in v2); the red pitched roof is already there, leave it alone."""
    x0, z0, x1, z1 = spec["rect"]
    gy, ry = spec["ground_y"], spec["roof_y"]
    fields = field_set(world, spec["rect"], gy, ry)
    counts = Counter()
    for (x, z) in face_cells(spec["rect"]):
        for y in range(gy + 1, ry + 1):
            b = world.get_block(x, y, z)
            if b is None or b in AIR or is_glass(b):
                continue
            if is_door_block(b) or b == "minecraft:light":
                continue
            if is_trim(b):
                continue
            if b in fields and b != "minecraft:yellow_concrete":
                world.set_block(x, y, z, "minecraft:yellow_concrete")
                counts["yellow"] += 1
    print(f"yellow {spec['name']}: {dict(counts)}")
    return dict(counts)


# ------------------------------------------------------------------ step 5
def recolor_tinghai_restaurant(world, report):
    """Dark navy-blue louvre upper floor, grey stone pillar ground floor,
    glass doors + 2 steps on the east (courtyard) face, white external
    stair on the north end of the east face up to the 2nd floor."""
    s = V5["tinghai_restaurant"]
    x0, z0, x1, z1 = s["rect"]
    gy, ry = s["ground_y"], s["roof_y"]
    fields = field_set(world, s["rect"], gy, ry)
    counts = Counter()
    for side, line in (("west", [(x0, z) for z in range(z0, z1 + 1)]),
                       ("east", [(x1, z) for z in range(z0, z1 + 1)]),
                       ("north", [(x, z0) for x in range(x0, x1 + 1)]),
                       ("south", [(x, z1) for x in range(x0, x1 + 1)])):
        for i, (x, z) in enumerate(line):
            is_fin = (i % 3 == 0)
            for y in range(gy + 1, ry + 1):
                b = world.get_block(x, y, z)
                if b is None or b in AIR:
                    continue
                if is_door_block(b) or b == "minecraft:light":
                    continue
                if is_trim(b) and not is_glass(b):
                    continue
                if y == ry:
                    continue
                if is_glass(b):
                    if b != DORM_GLASS:
                        world.set_block(x, y, z, DORM_GLASS)
                        counts["glass"] += 1
                    continue
                if b not in fields:
                    continue
                if y <= gy + 4:
                    # ground floor: grey stone pillars + glass between
                    if is_fin:
                        if b != "minecraft:stone_bricks":
                            world.set_block(x, y, z, "minecraft:stone_bricks")
                            counts["pillar"] += 1
                    elif b != DORM_GLASS:
                        world.set_block(x, y, z, DORM_GLASS)
                        counts["glass"] += 1
                else:
                    if is_fin:
                        if b != "minecraft:gray_concrete":
                            world.set_block(x, y, z, "minecraft:gray_concrete")
                            counts["fin"] += 1
                    elif b != "minecraft:blue_concrete":
                        world.set_block(x, y, z, "minecraft:blue_concrete")
                        counts["louvre"] += 1
    # ground entrance: east face centre, glass doors + 2 steps
    cz = (z0 + z1) // 2
    gy_out = modal([top_y(world, x, z) for x in range(x1 + 1, x1 + 5)
                    for z in range(cz - 2, cz + 3)
                    if top_y(world, x, z) is not None]) or gy
    feet = gy + 1
    place_door(world, x1, feet, cz, "east")
    for k, cell_y in enumerate((feet - 1, feet - 2)):
        x = x1 + 1 + k
        for z in range(cz - 2, cz + 3):
            world.set_block(x, cell_y, z,
                            "minecraft:stone_stairs[facing=west,half=bottom,"
                            "shape=straight]")
            for y in range(cell_y - 1, gy_out, -1):
                if not is_solid(world, x, y, z):
                    world.set_block(x, y, z, STEP_FILL)
    counts["entrance_steps"] = 10
    # external white stair: east face north end, up to the 2nd floor door
    # 10 half-steps from the courtyard (-44) to the upper slab (-39)
    up_feet = gy + 5
    for k in range(10):
        z = z0 + 4 + k
        cell_y = gy + (k // 2)
        for x in (x1 + 1, x1 + 2):
            world.set_block(
                x, cell_y, z,
                "minecraft:white_concrete_stairs[facing=north,half=bottom,"
                "shape=straight]")
            for y in range(cell_y - 1, gy_out, -1):
                if not is_solid(world, x, y, z):
                    world.set_block(x, y, z, "minecraft:white_concrete")
        # glass railing on the outer edge
        world.set_block(x1 + 3, cell_y + 1, z, "minecraft:glass_pane")
        counts["ext_stair"] += 2
    place_door(world, x1, up_feet, z0 + 14, "east")
    # landing in front of the upper door
    for x in (x1 + 1, x1 + 2):
        for z in (z0 + 13, z0 + 14, z0 + 15):
            b = world.get_block(x, up_feet - 1, z)
            if b is None or b in AIR:
                world.set_block(x, up_feet - 1, z, "minecraft:white_concrete")
    report["tinghai_restaurant"] = {"counts": dict(counts),
                                    "ground_door": [x1, feet, cz],
                                    "upper_door": [x1, up_feet, z0 + 14]}
    print(f"tinghai restaurant: {dict(counts)}")


def recolor_wanghai_restaurant(world, report):
    """Classical cream facade: tall pilasters, arched blue glass, red
    pitched roof, triangular pediment on the south (Gaoyu Rd) face,
    blue-glass bay on the north (courtyard) face, south steps."""
    s = V5["wanghai_restaurant"]
    x0, z0, x1, z1 = s["rect"]
    gy, ry = s["ground_y"], s["roof_y"]
    fields = field_set(world, s["rect"], gy, ry)
    counts = Counter()
    for side, line in (("west", [(x0, z) for z in range(z0, z1 + 1)]),
                       ("east", [(x1, z) for z in range(z0, z1 + 1)]),
                       ("north", [(x, z0) for x in range(x0, x1 + 1)]),
                       ("south", [(x, z1) for x in range(x0, x1 + 1)])):
        for i, (x, z) in enumerate(line):
            is_pil = (i % 4 == 0)
            for y in range(gy + 1, ry + 1):
                b = world.get_block(x, y, z)
                if b is None or b in AIR:
                    continue
                if is_door_block(b) or b == "minecraft:light":
                    continue
                if is_trim(b) and not is_glass(b):
                    continue
                if y == ry:
                    continue
                if is_glass(b):
                    if b != DORM_GLASS:
                        world.set_block(x, y, z, DORM_GLASS)
                        counts["glass"] += 1
                    continue
                if b not in fields:
                    continue
                if is_pil:
                    if b != "minecraft:smooth_stone":
                        world.set_block(x, y, z, "minecraft:smooth_stone")
                        counts["pilaster"] += 1
                elif b != DORM_GRID:
                    world.set_block(x, y, z, DORM_GRID)
                    counts["field"] += 1
    # north blue-glass bay (projecting 1 cell, 2 storeys)
    for x in range((x0 + x1) // 2 - 15, (x0 + x1) // 2 + 16):
        for y in range(gy + 1, gy + 10):
            world.set_block(x, y, z0 - 1, DORM_GLASS)
            counts["bay_glass"] += 1
    for x in ((x0 + x1) // 2 - 16, (x0 + x1) // 2 + 16):
        for y in range(gy + 1, gy + 10):
            world.set_block(x, y, z0 - 1, "minecraft:smooth_stone")
            counts["bay_frame"] += 1
    # pitched red roof: ridge along X at z=324, +4 at the ridge
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            h = ry + max(0, 4 - abs(z - 324) // 6)
            for y in range(ry + 1, h + 1):
                world.set_block(x, y, z, ROOF_RED)
                counts["pitched_roof"] += 1
    # triangular pediment on the south face
    cx = (x0 + x1) // 2
    for dy, half in ((1, 9), (2, 7), (3, 5), (4, 3)):
        for x in range(cx - half, cx + half + 1):
            world.set_block(x, ry + dy, z1, "minecraft:smooth_stone")
            counts["pediment"] += 1
    # south entrance: double glass doors + 3 steps, 9 wide
    feet = gy + 1
    place_door(world, cx - 1, feet, z1, "south")
    place_door(world, cx, feet, z1, "south")
    for k, cell_y in enumerate((feet - 1, feet - 2, feet - 3)):
        z = z1 + 1 + k
        for x in range(cx - 4, cx + 5):
            world.set_block(x, cell_y, z,
                            "minecraft:stone_stairs[facing=north,half=bottom,"
                            "shape=straight]")
            for y in range(cell_y - 1, gy - 1, -1):
                if not is_solid(world, x, y, z):
                    world.set_block(x, y, z, STEP_FILL)
    counts["south_steps"] = 27
    report["wanghai_restaurant"] = {"counts": dict(counts),
                                    "doors": [[cx - 1, feet, z1],
                                              [cx, feet, z1]]}
    print(f"wanghai restaurant: {dict(counts)}")


# ------------------------------------------------------------------ step 6
def recolor_engineering(world, report):
    """unnamed-144, inferred as the engineering building: brown stone
    field, cream pilasters, blue vertical strip windows, arched
    ground-floor colonnade, red pitched tower cap at the north end,
    arched west entrance with 8 steps down to the road."""
    s = V5["engineering"]
    x0, z0, x1, z1 = s["rect"]
    gy, ry = s["ground_y"], s["roof_y"]
    fields = field_set(world, s["rect"], gy, ry)
    counts = Counter()
    for side, line in (("west", [(x0, z) for z in range(z0, z1 + 1)]),
                       ("east", [(x1, z) for z in range(z0, z1 + 1)]),
                       ("north", [(x, z0) for x in range(x0, x1 + 1)]),
                       ("south", [(x, z1) for x in range(x0, x1 + 1)])):
        for i, (x, z) in enumerate(line):
            is_pil = (i % 4 == 0)
            for y in range(gy + 1, ry + 1):
                b = world.get_block(x, y, z)
                if b is None or b in AIR:
                    continue
                if is_door_block(b) or b == "minecraft:light":
                    continue
                if is_trim(b) and not is_glass(b):
                    continue
                if y == ry:
                    continue
                if is_glass(b):
                    if b != DORM_GLASS:
                        world.set_block(x, y, z, DORM_GLASS)
                        counts["glass"] += 1
                    continue
                if b not in fields:
                    continue
                if y <= gy + 4:
                    # ground-floor arched colonnade: cream pillars + glass
                    if i % 3 == 0:
                        if b != DORM_GRID:
                            world.set_block(x, y, z, DORM_GRID)
                            counts["colonnade"] += 1
                    elif b != DORM_GLASS:
                        world.set_block(x, y, z, DORM_GLASS)
                        counts["glass"] += 1
                elif is_pil:
                    if b != DORM_GRID:
                        world.set_block(x, y, z, DORM_GRID)
                        counts["pilaster"] += 1
                elif b != DORM_FIELD:
                    world.set_block(x, y, z, DORM_FIELD)
                    counts["field"] += 1
    # red pitched tower cap over the north end (z 492-499)
    for x in range(x0, x1 + 1):
        for z in range(z0, z0 + 8):
            h = ry + max(0, 3 - abs(z - (z0 + 3)))
            for y in range(ry + 1, h + 1):
                world.set_block(x, y, z, ROOF_RED)
                counts["tower_roof"] += 1
    # arched west entrance: 5-wide opening, door feet gy+4, 8 steps west
    dz = (z0 + z1) // 2
    feet = gy + 4
    for z in range(dz - 2, dz + 3):
        for y in range(feet, feet + 4):
            world.set_block(x0, y, z, "minecraft:air")
    place_door(world, x0, feet, dz, "west")
    # arch frame: protruding pilasters + stepped corbel band
    for z in (dz - 3, dz + 3):
        for y in range(gy + 1, ry):
            world.set_block(x0 - 1, y, z, DORM_FIELD)
            counts["arch_pilaster"] += 1
    for y, (za, zb) in ((ry - 7, (dz - 3, dz + 3)),
                        (ry - 6, (dz - 2, dz + 2))):
        for z in range(za, zb + 1):
            for x in (x0 - 1, x0):
                world.set_block(x, y, z, DORM_FIELD)
                counts["arch_corbel"] += 1
    # interior landing + down-stair (west-facing, same pattern as v4)
    for d in (1, 2, 3):
        for y in (feet, feet + 1):
            if is_solid(world, x0 + d, y, dz):
                world.set_block(x0 + d, y, dz, "minecraft:air")
    for oz in (-1, 0, 1):
        for d in (1, 2, 3):
            b = world.get_block(x0 + d, feet - 1, dz + oz)
            if b is None or b in AIR or is_glass(b):
                world.set_block(x0 + d, feet - 1, dz + oz, FLOOR_IN)
    ground_in = None
    for y in range(feet - 1, -64, -1):
        b = world.get_block(x0 + 2, y, dz)
        if b is not None and b not in AIR and not is_glass(b) \
                and b != "minecraft:light":
            ground_in = y + 1
            break
    down = 0
    if ground_in is not None and feet - ground_in > 1:
        drop = feet - ground_in
        if 0 < drop <= 6:
            for i in range(drop * 2):
                x = x0 + (4 + i)
                cell_y = (feet - 1) - (i // 2)
                for oz in (-1, 0, 1):
                    world.set_block(
                        x, cell_y, dz + oz,
                        "minecraft:stone_stairs[facing=west,half=bottom,"
                        "shape=straight]")
                    for y in (cell_y + 1, cell_y + 2):
                        if is_solid(world, x, y, dz + oz):
                            world.set_block(x, y, dz + oz, "minecraft:air")
                    for y in range(cell_y - 1, ground_in - 1, -1):
                        if not is_solid(world, x, y, dz + oz):
                            world.set_block(x, y, dz + oz, DORM_GRID)
                down += 1
    # outside steps: 8 half-steps, 9 wide, down to the road
    gy_out = modal([top_y(world, x, z)
                    for x in range(x0 - 8, x0)
                    for z in range(dz - 4, dz + 5)
                    if top_y(world, x, z) is not None]) or gy
    for k in range(8):
        x = x0 - 1 - k
        cell_y = feet - (k // 2)
        for z in range(dz - 4, dz + 5):
            world.set_block(x, cell_y, z,
                            "minecraft:stone_stairs[facing=east,half=bottom,"
                            "shape=straight]")
            counts["steps"] += 1
            for y in range(cell_y - 1, gy_out, -1):
                if not is_solid(world, x, y, z):
                    world.set_block(x, y, z, STEP_FILL)
    for k in (0, 1):
        x = x0 - 1 - k
        cell_y = feet - (k // 2)
        for z in range(dz - 4, dz + 5):
            for y in (cell_y + 1, cell_y + 2):
                if is_solid(world, x, y, z):
                    world.set_block(x, y, z, "minecraft:air")
    report["engineering"] = {"counts": dict(counts),
                             "door": [x0, feet, dz],
                             "ground_in": ground_in,
                             "down_treads": down,
                             "ground_out": gy_out}
    print(f"engineering: {dict(counts)}")


# ------------------------------------------------------------------ step 7
def finish_courts(world, report):
    """Basketball courts (v3 built the surfaces/lines/hoops): add the
    red surround, floodlight poles and dark-green fencing per panorama."""
    out = []
    for area in V3["courts"]:
        ao = {"area": area["area"]}
        # red surround: 1-cell ring around each court
        ring = 0
        for c in area["courts"]:
            x0, z0, x1, z1 = c["x0"], c["z0"], c["x1"], c["z1"]
            for x in range(x0 - 1, x1 + 2):
                for z in (z0 - 1, z1 + 1):
                    t = top_y(world, x, z)
                    if t is None:
                        continue
                    b = world.get_block(x, t, z)
                    if b in ("minecraft:green_concrete", "minecraft:green_terracotta",
                             "minecraft:grass_block",
                             "minecraft:dirt", "minecraft:gray_concrete",
                             "minecraft:black_concrete"):
                        world.set_block(x, t, z, ROOF_RED)
                        ring += 1
            for z in range(z0 - 1, z1 + 2):
                for x in (x0 - 1, x1 + 1):
                    t = top_y(world, x, z)
                    if t is None:
                        continue
                    b = world.get_block(x, t, z)
                    if b in ("minecraft:green_concrete", "minecraft:green_terracotta",
                             "minecraft:grass_block",
                             "minecraft:dirt", "minecraft:gray_concrete",
                             "minecraft:black_concrete"):
                        world.set_block(x, t, z, ROOF_RED)
                        ring += 1
        ao["red_surround"] = ring
        # floodlight poles at the area corners (inset 2)
        bx0, bz0, bx1, bz1 = area["bbox"]
        poles = 0
        for (px, pz) in ((bx0 + 2, bz0 + 2), (bx1 - 2, bz0 + 2),
                         (bx0 + 2, bz1 - 2), (bx1 - 2, bz1 - 2)):
            t = top_y(world, px, pz)
            if t is None:
                continue
            for y in range(t + 1, t + 7):
                world.set_block(px, y, pz, "minecraft:white_concrete")
            world.set_block(px, t + 7, pz, "minecraft:yellow_concrete")
            world.set_block(px, t + 6, pz + 1, "minecraft:light")
            world.set_block(px, t + 6, pz - 1, "minecraft:light")
            poles += 1
        ao["floodlight_poles"] = poles
        # dark-green fence around the area, gaps mid-side for entry
        fence = 0
        for x in range(bx0, bx1 + 1):
            for z in (bz0, bz1):
                if abs(x - (bx0 + bx1) // 2) <= 1:
                    continue
                t = top_y(world, x, z)
                if t is None:
                    continue
                b = world.get_block(x, t, z)
                if b in ("minecraft:gray_concrete", "minecraft:black_concrete",
                         "minecraft:light_gray_concrete"):
                    continue
                for y in (t + 1, t + 2):
                    world.set_block(x, y, z, "minecraft:green_stained_glass_pane")
                fence += 1
        for z in range(bz0, bz1 + 1):
            for x in (bx0, bx1):
                if abs(z - (bz0 + bz1) // 2) <= 1:
                    continue
                t = top_y(world, x, z)
                if t is None:
                    continue
                b = world.get_block(x, t, z)
                if b in ("minecraft:gray_concrete", "minecraft:black_concrete",
                         "minecraft:light_gray_concrete"):
                    continue
                for y in (t + 1, t + 2):
                    world.set_block(x, y, z, "minecraft:green_stained_glass_pane")
                fence += 1
        ao["fence_posts"] = fence
        out.append(ao)
        print(f"courts {area['area']}: {ao}")
    report["courts_finish"] = out


# ------------------------------------------------------------------ step 8
def build_football(world, report):
    """Football field: levelled green turf, white lines, red running
    track around it, goals at both ends. No stands (panorama: none)."""
    f = V5["football"]
    x0, z0, x1, z1 = f["pitch_rect"]
    fx0, fz0, fx1, fz1 = f["field_rect"]
    tops = [top_y(world, x, z) for x in range(x0, x1 + 1, 2)
            for z in range(z0, z1 + 1, 2)]
    tops = [t for t in tops if t is not None]
    sy = modal(tops)
    counts = Counter()
    if sy is None:
        report["football"] = {"error": "no ground"}
        return
    # level the whole pitch rect to sy
    surf = {}
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            t = top_y(world, x, z)
            if t is None:
                continue
            if t < sy:
                for y in range(t + 1, sy + 1):
                    world.set_block(x, y, z, "minecraft:green_concrete")
                surf[(x, z)] = sy
            elif t > sy:
                if t - sy <= 6:
                    for y in range(sy + 1, t + 1):
                        if is_solid(world, x, y, z):
                            world.set_block(x, y, z, "minecraft:air")
                    world.set_block(x, sy, z, "minecraft:green_concrete")
                    surf[(x, z)] = sy
                    counts["capped"] += 1
                else:
                    world.set_block(x, t, z, "minecraft:green_concrete")
                    surf[(x, z)] = t
            else:
                world.set_block(x, t, z, "minecraft:green_concrete")
                surf[(x, z)] = t

    def line(x, z):
        if (x, z) in surf:
            world.set_block(x, surf[(x, z)], z, "minecraft:white_concrete")
            counts["lines"] += 1

    # red running track: outer 4 cells of the pitch rect
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            if x < fx0 or x > fx1 or z < fz0 or z > fz1:
                if (x, z) in surf:
                    world.set_block(x, surf[(x, z)], z, ROOF_RED)
                    counts["track"] += 1
    # field lines
    for x in range(fx0, fx1 + 1):
        line(x, fz0)
        line(x, fz1)
    for z in range(fz0, fz1 + 1):
        line(fx0, z)
        line(fx1, z)
    cz = (fz0 + fz1) // 2
    for x in range(fx0, fx1 + 1):
        line(x, cz)
    cx = (fx0 + fx1) // 2
    for dx in range(-3, 4):
        for dz in range(-3, 4):
            if round(math.hypot(dx, dz)) == 3:
                line(cx + dx, cz + dz)
    # penalty boxes (8 deep x 20 wide) at both ends
    for (ze, sgn) in ((fz0, 1), (fz1, -1)):
        for dx in range(-10, 11):
            line(cx + dx, ze + sgn * 8)
        for dz in range(0, 9):
            line(cx - 10, ze + sgn * dz)
            line(cx + 10, ze + sgn * dz)
    # goals: white posts + crossbar at both ends
    for (ze, sgn) in ((fz0, 1), (fz1, -1)):
        gy = surf.get((cx, ze), sy)
        for px in (cx - 4, cx + 4):
            for y in (gy + 1, gy + 2):
                world.set_block(px, y, ze, "minecraft:white_concrete")
        for px in range(cx - 4, cx + 5):
            world.set_block(px, gy + 3, ze, "minecraft:white_concrete")
        counts["goals"] += 1
    report["football"] = {"surface_y": sy, "counts": dict(counts),
                          "centre": [cx, sy, cz]}
    print(f"football: {dict(counts)}")


# ------------------------------------------------------------------ step 9
def refine_east_gate(world, report):
    """East gate refinement on the v2/v3 structure (7 m still estimated,
    no photo source): pillar caps + bases, plaque band + beam cap,
    wall returns with pedestrian side doors, forecourt repaved to match
    HaoHai square stone, east approach re-laid as road."""
    g = V5["east_gate"]
    x0, x1 = g["x"]
    z0, z1 = g["z"]
    pz0, pz1 = g["passage_z"]
    gy = g["ground_y"]
    beam_y = g["beam_y"]
    counts = Counter()
    # pillar caps: smooth stone over the pillars (was grass)
    for z in (z0, z0 + 1, z1 - 1, z1):
        for x in (x0, x1):
            if world.get_block(x, beam_y, z) != "minecraft:stone_bricks":
                world.set_block(x, beam_y, z, "minecraft:smooth_stone")
                counts["pillar_caps"] += 1
    # beam cap: light quartz trim on top of the beam
    for x in (x0, x1):
        for z in range(pz0, pz1 + 1):
            if world.get_block(x, beam_y + 1, z) in (None, "minecraft:air"):
                world.set_block(x, beam_y + 1, z, "minecraft:smooth_quartz")
                counts["beam_cap"] += 1
    # plaque band: light strip under the beam, both faces
    for x in (x0 - 1, x1 + 1):
        for z in range(pz0 + 1, pz1):
            if world.get_block(x, beam_y - 1, z) in (None, "minecraft:air"):
                world.set_block(x, beam_y - 1, z, "minecraft:white_concrete")
                counts["plaque_band"] += 1
    # clear vegetation in the passage
    for x in (x0, x1):
        for z in range(pz0, pz1 + 1):
            for y in range(gy + 1, beam_y):
                if world.get_block(x, y, z) in VEGETATION:
                    world.set_block(x, y, z, "minecraft:air")
                    counts["passage_veg_cleared"] += 1
            if world.get_block(x, gy, z) != "minecraft:stone_bricks":
                world.set_block(x, gy, z, "minecraft:stone_bricks")
                counts["passage_paved"] += 1
    # wall returns + pedestrian side doors
    doors = []
    for (rz0, rz1) in g["wall_returns"]:
        for x in (x0, x1):
            for z in range(rz0, rz1 + 1):
                t = top_y(world, x, z)
                if t is None:
                    continue
                for y in range(t + 1, t + 5):
                    world.set_block(x, y, z, "minecraft:stone_bricks")
                world.set_block(x, t + 5, z, "minecraft:smooth_stone")
                counts["wall_cells"] += 1
    for dz in g["side_doors_z"]:
        # modal ground around the door spot (both sides of the wall)
        gys = [top_y(world, x, z) for x in range(x0 - 3, x1 + 4)
               for z in range(dz - 1, dz + 2)
               if top_y(world, x, z) is not None]
        feet = (modal(gys) or gy) + 1
        # cut the opening through both wall columns
        for x in (x0, x1):
            for y in (feet, feet + 1):
                world.set_block(x, y, dz, "minecraft:air")
        place_door(world, x0, feet, dz, "east")
        # level stone pads on both sides
        for x in range(x0 - 3, x1 + 4):
            for z in range(dz - 1, dz + 2):
                t = top_y(world, x, z)
                if t is None or t >= feet:
                    continue
                for y in range(t + 1, feet):
                    world.set_block(x, y, z, STEP_FILL)
                counts["door_pad"] += 1
        doors.append([x0, feet, dz])
    # forecourt: west approach -> pale beige stone (matches HaoHai square)
    for x in range(1600, x0):
        for z in range(pz0, pz1 + 1):
            t = top_y(world, x, z)
            if t is None:
                continue
            b = world.get_block(x, t, z)
            if b is None or b in AIR or is_tree_top(b):
                continue
            if b != PLAZA_BEIGE:
                world.set_block(x, t, z, PLAZA_BEIGE)
                counts["forecourt"] += 1
    # east approach: grey carriageway + light edges
    for x in range(x1 + 1, 1681):
        for z in range(pz0, pz1 + 1):
            t = top_y(world, x, z)
            if t is None:
                continue
            b = world.get_block(x, t, z)
            if b is None or b in AIR or is_tree_top(b):
                continue
            target = WALK if z in (pz0, pz1) else ROAD
            if b != target:
                world.set_block(x, t, z, target)
                counts["east_approach"] += 1
    report["east_gate"] = {"counts": dict(counts), "doors": doors,
                           "beam_y": beam_y, "ground_y": gy}
    print(f"east gate: {dict(counts)}")


# ------------------------------------------------------------------ step 10
def build_leisure(world, report):
    """Blue walkways looping around the unnamed building cluster +
    freestanding blue OUC letters on the park lawn."""
    L = V5["leisure"]
    footprints = [fp["polygon"] for fp in PLAN.get("footprints", [])]
    footprints.append(rect_poly([984, 694, 1008, 718]))
    footprints.append(rect_poly(V5["engineering"]["rect"]))

    def in_building(x, z):
        for poly in footprints:
            if point_in_poly(x + 0.5, z + 0.5, poly):
                return True
        return False

    counts = Counter()
    RECOLORABLE = {"minecraft:grass_block", "minecraft:dirt",
                   "minecraft:stone_bricks", "minecraft:black_concrete",
                   "minecraft:light_gray_concrete", "minecraft:gray_concrete",
                   "minecraft:gray_concrete_powder", "minecraft:cobblestone"}
    for p in L["paths"]:
        xs, zs = p["x"], p["z"]
        # paths are axis-aligned rectangles; walk the whole rect
        cells = [(x, z) for x in range(xs[0], xs[1] + 1)
                 for z in range(zs[0], zs[1] + 1)]
        for (x, z) in cells:
            if in_building(x, z):
                continue
            t = top_y(world, x, z)
            if t is None:
                continue
            b = world.get_block(x, t, z)
            if b is None or b in AIR or is_tree_top(b):
                continue
            above = world.get_block(x, t + 1, z)
            if above is not None and above not in AIR and above not in VEGETATION:
                continue
            if b in RECOLORABLE or b == PATH_BLUE:
                if b != PATH_BLUE:
                    world.set_block(x, t, z, PATH_BLUE)
                    counts["walkway"] += 1
    # OUC letters: 5 high, 1 thick, facing south, on the lawn
    letters = {"O": ["0110", "1001", "1001", "1001", "0110"],
               "U": ["1001", "1001", "1001", "1001", "0110"],
               "C": ["0110", "1000", "1000", "1000", "0110"]}
    z0 = L["ouc_letters"]["z"]
    gy = L["ouc_letters"]["base_ground"]
    for (x0, x1), ch in zip(L["ouc_letters"]["letters"], "OUC"):
        pat = letters[ch]
        for dx in range(4):
            for dy in range(5):
                if pat[4 - dy][dx] == "1":
                    world.set_block(x0 + dx, gy + 1 + dy, z0, PATH_BLUE)
                    counts["letters"] += 1
    report["leisure"] = dict(counts)
    print("leisure done:", dict(counts))


# ------------------------------------------------------------------ step 11
def fix_level_dat(world_dir, report):
    p = Path(world_dir) / "level.dat"
    bak = p.with_name("level.dat.bak-v4")
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
            v = "中国海洋大学西海岸校区v5"
        data_nodes.append((t, n, v))
    new_root = (root[0], root[1],
                [(t, n, data_nodes if n == "Data" else v) for (t, n, v) in root[2]])
    p.write_bytes(gzip.compress(dumps(new_root), compresslevel=6))
    root2 = loads(gzip.decompress(p.read_bytes()))
    data2 = find_node(root2[2], "Data")
    report["level_dat"] = {
        "old_name": old_name, "new_name": find(data2[2], "LevelName")[1],
        "old_lastplayed": old_played,
        "new_lastplayed": find(data2[2], "LastPlayed")[1],
        "spawn": [find(data2[2], k)[1] for k in ("SpawnX", "SpawnY", "SpawnZ")],
    }
    print("level.dat:", report["level_dat"])


def main():
    t0 = time.time()
    report = {"world": str(WORLD_DIR), "base": "v4",
              "note": "internal build; do not announce a version number "
                      "until the parent chat accepts it"}
    world = World(str(WORLD_DIR))
    repave_roads(world, report)
    repave_square(world, report)
    recolor_learning(world, report)
    build_east_entrance(world, report)
    dorms = {}
    for s in V5["dorms_tinghai"] + V5["dorms_wanghai_phase1"]:
        dorms[s["name"]] = recolor_dorm(world, s)
    dorms[V5["wanghai_phase2_east"]["name"]] = \
        recolor_yellow_walls(world, V5["wanghai_phase2_east"])
    report["dorms"] = dorms
    recolor_tinghai_restaurant(world, report)
    recolor_wanghai_restaurant(world, report)
    recolor_engineering(world, report)
    finish_courts(world, report)
    build_football(world, report)
    refine_east_gate(world, report)
    build_leisure(world, report)
    changed = world.flush()
    report["cells_changed"] = changed
    report["elapsed_s"] = round(time.time() - t0, 1)
    fix_level_dat(WORLD_DIR, report)
    out = WORK / "v5-build-report.json"
    json.dump(report, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"BUILD DONE: {changed} cells changed in {report['elapsed_s']}s; report -> {out}")


if __name__ == "__main__":
    main()
