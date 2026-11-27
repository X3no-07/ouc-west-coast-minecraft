#!/usr/bin/env python3
"""v3 build: finish-pass on a copy of the v2 world (staging-v3).

Reads v3-build-data.json + plan-v2.json (+ v3-ground-fixes.json if present),
applies, in order:
  0. world checks (missing buildings present? rubble patches?)
  1. info-north rebuild (roofs de-redded, clutter cleared, window bands, doors)
  2. seam door at 1358 (听海苑2号楼 north wall, near the 1号楼 corner)
  3. door sweep: every enterable building gets an openable door
  4. road repave (OSM highways: black carriageway + light sidewalks)
  5. basketball courts (28x15, lines, hoops)
  6. east gate: pave passage + approaches (structure kept, 7 m still estimated)
  7. missing buildings (海洋楼 / unnamed near 望海餐厅) if absent from world
  8. level.dat: rename to v3, refresh LastPlayed
Writes v3-build-report.json.  Run on the PC against the staging-v3 copy.
All edits are programmatic block rules; nothing is hand-placed in-game.
"""
import gzip
import json
import math
import sys
import time
from collections import Counter, deque
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from anvil import dumps, find, find_node, loads  # noqa: E402
from finish_world import World  # noqa: E402

WORK = HERE
WORLD_DIR = WORK / "staging-v3" / "OUC-West-Coast-v3"
DATA = json.load(open(WORK / "v3-build-data.json", encoding="utf-8"))
PLAN = json.load(open(WORK / "plan-v2.json", encoding="utf-8"))
GROUND_FIXES = None
_gf = WORK / "v3-ground-fixes.json"
if _gf.exists():
    GROUND_FIXES = json.load(open(_gf, encoding="utf-8"))

AIR = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}
VEGETATION = {"minecraft:tall_grass", "minecraft:grass", "minecraft:fern",
              "minecraft:large_fern", "minecraft:short_grass", "minecraft:dead_bush",
              "minecraft:dandelion", "minecraft:poppy", "minecraft:azure_bluet",
              "minecraft:sunflower", "minecraft:lilac", "minecraft:rose_bush",
              "minecraft:peony", "minecraft:oxeye_daisy", "minecraft:cornflower",
              "minecraft:lily_of_the_valley", "minecraft:allium",
              "minecraft:blue_orchid", "minecraft:red_tulip", "minecraft:orange_tulip",
              "minecraft:white_tulip", "minecraft:pink_tulip", "minecraft:snowdrop"}
TREE_TOP = ("_leaves", "_log", "_wood", "minecraft:mangrove_roots")


def is_tree_top(block):
    return block is not None and (
        block.endswith(TREE_TOP) or block == "minecraft:mushroom_stem")
WALL_GLASS = "minecraft:light_gray_stained_glass"
PIER = "minecraft:smooth_sandstone"
PLINTH = "minecraft:smooth_stone"
DOOR = "minecraft:oak_door"
THRESHOLD = "minecraft:stone_bricks"
FLOOR_IN = "minecraft:oak_planks"

# Anything that may sit on a roof as Arnis clutter (not structure).
CLUTTER_SUFFIX = ("_slab", "_stairs", "_trapdoor", "_pressure_plate",
                  "_button", "_fence", "_wall", "_carpet")
CLUTTER_EXACT = {
    "minecraft:daylight_detector", "minecraft:end_rod", "minecraft:lightning_rod",
    "minecraft:barrel", "minecraft:grindstone", "minecraft:blast_furnace",
    "minecraft:furnace", "minecraft:smoker", "minecraft:cauldron",
    "minecraft:iron_bars", "minecraft:torch",
    "minecraft:lantern", "minecraft:campfire", "minecraft:flower_pot",
    "minecraft:chest", "minecraft:observer", "minecraft:dispenser",
    "minecraft:dropper", "minecraft:note_block", "minecraft:lever",
    "minecraft:target", "minecraft:lectern", "minecraft:smithing_table",
    "minecraft:fletching_table", "minecraft:cartography_table",
    "minecraft:stonecutter", "minecraft:loom", "minecraft:composter",
    "minecraft:beehive", "minecraft:bee_nest", "minecraft:scaffolding",
    "minecraft:ladder", "minecraft:vine", "minecraft:cobweb",
}


def is_clutter(block):
    if block is None:
        return False
    if block in CLUTTER_EXACT:
        return True
    return any(block.endswith(s) for s in CLUTTER_SUFFIX)


# Blocks that can never be part of a parapet (utility / Arnis junk).
# Slabs are deliberately NOT in this list: a slab at roof+1/+2 on the rim
# is the parapet cap (cut_sandstone / polished_diorite), not junk.
PARAPET_BAD_SUFFIX = ("_trapdoor", "_stairs", "_pressure_plate", "_button",
                      "_fence", "_wall", "_carpet")


def is_parapet_keepable(block):
    if block is None or block in AIR:
        return False
    if block in CLUTTER_EXACT:
        return False
    return not any(block.endswith(s) for s in PARAPET_BAD_SUFFIX)


def ground_y(world, x, z):
    """Ground Y under a possible overhang (gate beam, canopy): the top
    solid, unless the block directly under it is air/vegetation, in which
    case scan down for the next solid.  Reads the ORIGINAL world (edits
    are invisible to reads in this codebase), so it is safe to call after
    the ground-fix step."""
    t = top_y(world, x, z)
    if t is None:
        return None
    below = world.get_block(x, t - 1, z)
    if below is not None and below not in AIR and below not in VEGETATION:
        return t
    for y in range(t - 2, -64, -1):
        b = world.get_block(x, y, z)
        if b is not None and b not in AIR and b not in VEGETATION:
            return y
    return t


def top_y(world, x, z):
    t = world.top_solid(x, z, y_top=64, y_bottom=-64)
    return t[0] if t else None


def is_solid(world, x, y, z):
    b = world.get_block(x, y, z)
    return b is not None and b not in AIR


def is_air(world, x, y, z):
    b = world.get_block(x, y, z)
    return b is None or b in AIR


def door_state(facing, half):
    return (f"minecraft:oak_door[facing={facing},half={half},hinge=left,"
            f"open=false,powered=false]")


def _is_passable_block(block):
    if block is None or block in AIR or block in VEGETATION:
        return True
    return block.endswith("_door")


def place_door(world, x, y, z, facing):
    """y = feet level (lower block). Returns (lower, upper) coords.
    Also guarantees a solid floor under the door: Arnis sometimes leaves
    an iron door (or a gap) where the floor should be, so the player would
    fall a block as they step through (main library east door: an iron
    door at -46/-45 under the oak door at -44/-43)."""
    world.set_block(x, y, z, door_state(facing, "lower"))
    world.set_block(x, y + 1, z, door_state(facing, "upper"))
    if _is_passable_block(world.get_block(x, y - 1, z)):
        world.set_block(x, y - 1, z, "minecraft:stone_bricks")
    return (x, y, z), (x, y + 1, z)


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


def poly_cells(poly):
    xs = [p[0] for p in poly]
    zs = [p[1] for p in poly]
    out = []
    for x in range(min(xs), max(xs) + 1):
        for z in range(min(zs), max(zs) + 1):
            if point_in_poly(x + 0.5, z + 0.5, poly):
                out.append((x, z))
    return out


def poly_perimeter(poly):
    """Rasterized boundary cells of a polygon (rect or slanted)."""
    cells = []
    seen = set()
    n = len(poly)
    for i in range(n):
        x1, z1 = poly[i]
        x2, z2 = poly[(i + 1) % n]
        steps = max(abs(x2 - x1), abs(z2 - z1), 1)
        for s in range(steps + 1):
            x = round(x1 + (x2 - x1) * s / steps)
            z = round(z1 + (z2 - z1) * s / steps)
            if (x, z) not in seen:
                seen.add((x, z))
                cells.append((x, z))
    return cells


def modal(values):
    if not values:
        return None
    return Counter(values).most_common(1)[0][0]


# ------------------------------------------------------------------ step 0
def check_building_present(world, poly, name):
    """Sample the footprint: a building counts as present if the modal top
    inside is >= 8 above the modal ground just outside."""
    cells = poly_cells(poly)
    if not cells:
        return {"name": name, "present": False, "reason": "empty polygon"}
    inside_tops = [top_y(world, x, z) for (x, z) in cells[::max(1, len(cells) // 200)]]
    inside_tops = [y for y in inside_tops if y is not None]
    # ground just outside: ring 2 cells out
    xs = [p[0] for p in poly]; zs = [p[1] for p in poly]
    outside = []
    for x in range(min(xs) - 2, max(xs) + 3):
        for z in (min(zs) - 2, max(zs) + 2):
            if not point_in_poly(x + 0.5, z + 0.5, poly):
                outside.append((x, z))
    for z in range(min(zs) - 2, max(zs) + 3):
        for x in (min(xs) - 2, max(xs) + 2):
            if not point_in_poly(x + 0.5, z + 0.5, poly):
                outside.append((x, z))
    ground = [top_y(world, x, z) for (x, z) in outside]
    ground = [y for y in ground if y is not None]
    mi = modal(inside_tops)
    mg = modal(ground)
    present = (mi is not None and mg is not None and mi - mg >= 8)
    return {"name": name, "present": present,
            "modal_top_inside": mi, "modal_ground_outside": mg,
            "sampled_cells": len(inside_tops)}


# ------------------------------------------------------------------ step 1
def rebuild_info_north(world, report):
    info = DATA["info_north"]
    out = {}
    for wing_name, spec in info.items():
        if wing_name == "courtyard":
            continue
        x0, z0, x1, z1 = spec["rect"]
        roof_y = spec["roof_y"]
        ground = spec["ground_y"]
        floors = spec["floors"]
        target = spec["roof_target"]
        cells = [(x, z) for x in range(x0, x1 + 1) for z in range(z0, z1 + 1)]
        perimeter = {(x, z) for (x, z) in cells
                     if x in (x0, x1) or z in (z0, z1)}
        interior = [(x, z) for (x, z) in cells if (x, z) not in perimeter]
        # --- roof: clear clutter above roof_y.  The parapet is a 2-high rim
        # (solid at roof+1, slab cap at roof+2) on/just inside the rect edge;
        # keep keepable blocks there, clear everything else above the roof.
        # Unify the whole roof surface to the target except slab edge trim.
        clutter_cleared = 0
        roof_set = 0
        for (x, z) in cells:
            # near_edge: on the rect boundary or one cell inside it
            # (the parapet rim sits on the edge; the long wing also has a
            # second rim line one cell in on its south side)
            near_edge = (x == x0 or x == x1 or z == z0 or z == z1
                         or x == x0 + 1 or x == x1 - 1 or z == z0 + 1 or z == z1 - 1)
            for y in range(roof_y + 1, roof_y + 11):
                b = world.get_block(x, y, z)
                if b is None or b in AIR:
                    continue
                if y <= roof_y + 2 and near_edge and is_parapet_keepable(b):
                    continue  # parapet rim / cap
                world.set_block(x, y, z, "minecraft:air")
                clutter_cleared += 1
        for (x, z) in cells:
            b = world.get_block(x, roof_y, z)
            if b is None or b in AIR:
                continue
            if b.endswith("_slab"):
                continue  # keep the slab edge trim
            if b != target:
                world.set_block(x, roof_y, z, target)
                roof_set += 1
        # --- walls: regular window bands per floor
        # floor f base Y0 = ground + 5*f ; window band Y0+1..Y0+3
        windows = 0
        piers = 0
        sides = [
            ("north", [(x, z0) for x in range(x0, x1 + 1)]),
            ("south", [(x, z1) for x in range(x0, x1 + 1)]),
            ("west", [(x0, z) for z in range(z0, z1 + 1)]),
            ("east", [(x1, z) for z in range(z0, z1 + 1)]),
        ]
        for _side, line in sides:
            L = len(line)
            for i, (x, z) in enumerate(line):
                # 2-wide piers at both corners; window rhythm 2-on/2-off
                is_window = (i % 4) in (2, 3) and 2 <= i <= L - 3
                for f in range(floors):
                    y0 = ground + 5 * f
                    for y in range(y0 + 1, y0 + 4):
                        b = world.get_block(x, y, z)
                        if b is None or b in AIR:
                            continue
                        if is_window:
                            if b != WALL_GLASS:
                                world.set_block(x, y, z, WALL_GLASS)
                                windows += 1
                        else:
                            if b != PIER:
                                world.set_block(x, y, z, PIER)
                                piers += 1
                    # sill + lintel to pier material (ground-floor sill = plinth)
                    for y, mat in ((y0, PLINTH if f == 0 else PIER),
                                   (y0 + 4, PIER)):
                        b = world.get_block(x, y, z)
                        if b is not None and b not in AIR and b != mat:
                            world.set_block(x, y, z, mat)
        out[wing_name] = {"roof_y": roof_y, "clutter_cleared": clutter_cleared,
                          "roof_cells_set": roof_set, "window_cells": windows,
                          "pier_cells": piers, "roof_target": target}
    # --- doors into the courtyard (ground floor feet Y = -44)
    doors = []
    # main building west wall, facing west into courtyard
    doors.append(("main-west", (1050, -44, 596), "west", (1049, -45, 596), (1051, -45, 596)))
    # long wing south wall, facing south into courtyard
    doors.append(("long-south", (1050, -44, 557), "south", (1050, -45, 558), (1050, -45, 556)))
    # west wing east wall, facing east into courtyard
    doors.append(("west-east", (1037, -44, 585), "east", (1038, -45, 585), (1036, -45, 585)))
    door_out = []
    for name, (dx, dy, dz), facing, (tx, ty, tz), (ix, iy, iz) in doors:
        # cut the wall column (outer face + two cells inward if solid)
        place_door(world, dx, dy, dz, facing)
        # carve 2 deep so the door is walkable (same fix as the door sweep)
        if facing == "west":
            step = (1, 0)
        elif facing == "east":
            step = (-1, 0)
        elif facing == "south":
            step = (0, -1)
        else:
            step = (0, 1)
        inner = (dx + step[0], dy, dz + step[1])
        inner2 = (dx + 2 * step[0], dy, dz + 2 * step[1])
        for (cx, cy, cz) in (inner, inner2):
            if is_solid(world, cx, cy, cz) or is_solid(world, cx, cy + 1, cz):
                world.set_block(cx, cy, cz, "minecraft:air")
                world.set_block(cx, cy + 1, cz, "minecraft:air")
        # threshold outside
        if not is_solid(world, tx, ty, tz):
            world.set_block(tx, ty, tz, THRESHOLD)
        # interior floor patch (2 deep)
        if not is_solid(world, ix, iy, iz):
            world.set_block(ix, iy, iz, FLOOR_IN)
        ix2 = (ix + step[0], iy, iz + step[1])
        if not is_solid(world, ix2[0], ix2[1], ix2[2]):
            world.set_block(ix2[0], ix2[1], ix2[2], FLOOR_IN)
        door_out.append({"name": name, "door": [dx, dy, dz], "facing": facing,
                         "threshold": [tx, ty, tz]})
    out["doors"] = door_out
    report["info_north"] = out
    print("info north done:", json.dumps(out, ensure_ascii=False))

# ------------------------------------------------------------------ step 2
def seam_door(world, report):
    """Door on 听海苑2号楼 north wall (Z=320), near the corner (1363,320)
    where 1号楼's west wall meets it.  Player at (1358,-36,302) looks SE
    at that seam; the door faces north toward the player and the path."""
    sd = DATA["seam_door"]
    wall_z = sd["wall_z"]
    # ground Y just north of the wall (modal of the sampled columns)
    gy = modal([top_y(world, x, wall_z - 1) for x in range(1355, 1364)
                if top_y(world, x, wall_z - 1) is not None])
    if gy is None:
        gy = -50
    # scan candidate columns (closest to the corner first) for a solid wall
    chosen = None
    for x in (1362, 1361, 1363, 1360, 1359, 1358, 1357, 1356, 1355):
        solid = all(is_solid(world, x, gy + 1 + k, wall_z) for k in range(4))
        if solid:
            chosen = x
            break
    if chosen is None:
        report["seam_door"] = {"error": "no solid wall column found on Z=320, X1355-1363"}
        print("seam door: NO solid column")
        return
    feet = gy + 1
    place_door(world, chosen, feet, wall_z, "north")
    # if the wall is 2 thick, clear the inner cell behind the door
    if is_solid(world, chosen, feet, wall_z + 1) or is_solid(world, chosen, feet + 1, wall_z + 1):
        world.set_block(chosen, feet, wall_z + 1, "minecraft:air")
        world.set_block(chosen, feet + 1, wall_z + 1, "minecraft:air")
    # threshold outside (north side) + stone pad
    for dx in (chosen - 1, chosen, chosen + 1):
        if not is_solid(world, dx, gy, wall_z - 1):
            world.set_block(dx, gy, wall_z - 1, THRESHOLD)
    # interior floor patch just inside the door
    for dx in (chosen - 1, chosen, chosen + 1):
        for dz in (wall_z + 1, wall_z + 2):
            if not is_solid(world, dx, gy, dz):
                world.set_block(dx, gy, dz, FLOOR_IN)
    # path: extend the existing grey path (X1352-1356, Z290-310) south to
    # the door pad, then a grey strip along Z=319 to the threshold
    for z in range(311, 320):
        for x in (1353, 1354):
            t = top_y(world, x, z)
            if t is not None and not is_tree_top(world.get_block(x, t, z)) \
                    and not is_solid(world, x, t + 1, z):
                world.set_block(x, t, z, "minecraft:gray_concrete")
    for x in range(1355, chosen):
        t = top_y(world, x, wall_z - 1)
        if t is not None and not is_tree_top(world.get_block(x, t, wall_z - 1)):
            world.set_block(x, t, wall_z - 1, "minecraft:gray_concrete")
    report["seam_door"] = {
        "building": "听海苑2号楼", "wall": "north", "wall_z": wall_z,
        "door": [chosen, feet, wall_z], "facing": "north",
        "threshold": [chosen, gy, wall_z - 1],
        "ground_y": gy, "player": [1358, -36, 302],
        "note": "门在2号楼北墙、距1号楼西墙交角2格（交角柱X1363为两楼共用墙面，门开在其西侧北墙上，朝北向玩家与步道）",
    }
    print("seam door done:", json.dumps(report["seam_door"], ensure_ascii=False))


# ------------------------------------------------------------------ step 3
def build_door_sweep(world, report):
    """One openable door per enterable building footprint in plan-v2.json."""
    # paving cells (plan) + road cells (data) for "nearest paving" choice
    pave = set()
    for p in PLAN.get("paving", []):
        for (x, z) in p.get("cells", []):
            pave.add((x, z))
    road_cells = set()
    for r in DATA["roads"]:
        pts = r["pts"]
        for (x1, z1), (x2, z2) in zip(pts, pts[1:]):
            steps = max(abs(x2 - x1), abs(z2 - z1), 1)
            for s in range(steps + 1):
                cx = round(x1 + (x2 - x1) * s / steps)
                cz = round(z1 + (z2 - z1) * s / steps)
                for dx in range(-r["width"] // 2, r["width"] // 2 + 1):
                    for dz in range(-r["width"] // 2, r["width"] // 2 + 1):
                        road_cells.add((cx + dx, cz + dz))
    near = pave | road_cells

    skip_names = ("采光顶",)
    info_wings = {"主楼", "西翼", "红顶长翼"}
    results = []
    for fp in PLAN.get("footprints", []):
        name = fp["name"]
        if any(s in name for s in skip_names):
            results.append({"name": name, "door": None, "note": "非建筑（采光顶），跳过"})
            continue
        if name in info_wings:
            continue  # handled by the info-north rebuild
        poly = fp["polygon"]
        cells = poly_cells(poly)
        if not cells:
            results.append({"name": name, "door": None, "note": "空多边形"})
            continue
        # ground Y: modal top just outside the polygon
        xs = [p[0] for p in poly]; zs = [p[1] for p in poly]
        outside = []
        for x in range(min(xs) - 1, max(xs) + 2):
            for z in (min(zs) - 1, max(zs) + 1):
                if not point_in_poly(x + 0.5, z + 0.5, poly):
                    outside.append((x, z))
        for z in range(min(zs) - 1, max(zs) + 2):
            for x in (min(xs) - 1, max(xs) + 1):
                if not point_in_poly(x + 0.5, z + 0.5, poly):
                    outside.append((x, z))
        gy = modal([top_y(world, x, z) for (x, z) in outside
                    if top_y(world, x, z) is not None])
        if gy is None:
            results.append({"name": name, "door": None, "note": "无地面"})
            continue
        # interior hollow? sample the centre column
        cx = (min(xs) + max(xs)) // 2
        cz = (min(zs) + max(zs)) // 2
        hollow = 0
        for y in (gy + 1, gy + 2, gy + 3):
            if is_air(world, cx, y, cz):
                hollow += 1
        if hollow < 2:
            results.append({"name": name, "door": None,
                            "note": f"首层实心（中心柱{ cx},{cz} 地面以上仅{hollow}/3为空），不开门",
                            "ground_y": gy})
            continue
        # pick the side with the nearest paving/road; tie -> south, east, west, north
        sides = []
        # north: z=min(zs), south: z=max(zs), west: x=min(xs), east: x=max(xs)
        side_cells = {
            "north": [(x, min(zs)) for x in range(min(xs), max(xs) + 1)],
            "south": [(x, max(zs)) for x in range(min(xs), max(xs) + 1)],
            "west": [(min(xs), z) for z in range(min(zs), max(zs) + 1)],
            "east": [(max(xs), z) for z in range(min(zs), max(zs) + 1)],
        }
        for side, line in side_cells.items():
            best = None
            best_cell = None
            for (x, z) in line:
                # distance outward from the wall to the nearest paving cell
                for d in range(1, 8):
                    if side == "north":
                        cand = (x, z - d)
                    elif side == "south":
                        cand = (x, z + d)
                    elif side == "west":
                        cand = (x - d, z)
                    else:
                        cand = (x + d, z)
                    if cand in near:
                        if best is None or d < best:
                            best = d
                            best_cell = (x, z)
                        break
            sides.append((best if best is not None else 99, side, best_cell))
        sides.sort(key=lambda t: (t[0], {"south": 0, "east": 1, "west": 2, "north": 3}[t[1]]))
        # try every side in paving-distance order (was: best side only --
        # that left the main library building doorless when its best side
        # had no solid column).  A door column is accepted only if the
        # threshold outside it is walkable ground: its top solid within 2
        # of the modal ground Y and 2 air blocks above it (rejects the
        # solid piers and fence/railings Arnis leaves in front of some
        # walls -- those made 3 of the 16 v3 doors unwalkable).
        placed = None
        side_notes = []
        for (_d, side, _cell) in sides:
            line = side_cells[side]
            mid = len(line) // 2
            order = [mid + k for k in range(0, len(line) // 2 + 1)]
            order += [mid - k for k in range(1, len(line) // 2 + 1)]
            tried_solid = 0
            for i in order:
                if not (0 <= i < len(line)):
                    continue
                (x, z) = line[i]
                if not all(is_solid(world, x, gy + 1 + k, z) for k in range(3)):
                    continue
                tried_solid += 1
                outward = {"north": (x, z - 1), "south": (x, z + 1),
                           "west": (x - 1, z), "east": (x + 1, z)}[side]
                (tx, tz) = outward
                top = top_y(world, tx, tz)
                # threshold surface must be within door reach: above gy+1
                # the player stands too high to step through the door
                # (was: abs(top-gy)<=2 -- that let two doors through whose
                # threshold surface sat 1 above the door's feet, and the
                # approach repair had to refuse them).  Below gy-2 is still
                # rejected: the sweep's threshold block would float too far
                # above a deep dip.
                if top is None or top > gy + 1 or top < gy - 2:
                    continue
                if not (is_air(world, tx, top + 1, tz)
                        and is_air(world, tx, top + 2, tz)):
                    continue
                placed = (side, x, z, outward)
                break
            if placed:
                break
            side_notes.append(f"{side}({tried_solid}实心柱均门槛不合格)" if tried_solid
                              else f"{side}无实心墙柱")
        if placed is None:
            results.append({"name": name, "door": None,
                            "note": "四面均无合格门柱：" + "；".join(side_notes),
                            "ground_y": gy})
            continue
        (side, dx, dz, outward) = placed
        feet = gy + 1
        facing = {"north": "north", "south": "south", "west": "west", "east": "east"}[side]
        place_door(world, dx, feet, dz, facing)
        # carve a 2-deep entry so the door is walkable: Arnis ground floors
        # are often solid-filled or stepped 1 up just inside the wall, and
        # a 1-deep clear left 8/16 sweep doors unwalkable (probe2).  Clear
        # inward AND inward-2 at feet/feet+1, floor both at feet-1.
        inward = {"north": (dx, dz + 1), "south": (dx, dz - 1),
                  "west": (dx + 1, dz), "east": (dx - 1, dz)}[side]
        inward2 = {"north": (dx, dz + 2), "south": (dx, dz - 2),
                   "west": (dx + 2, dz), "east": (dx - 2, dz)}[side]
        for (cx, cz) in (inward, inward2):
            for yy in (feet, feet + 1):
                if is_solid(world, cx, yy, cz):
                    world.set_block(cx, yy, cz, "minecraft:air")
        # threshold outside + interior floor patches (2 deep)
        if not is_solid(world, outward[0], gy, outward[1]):
            world.set_block(outward[0], gy, outward[1], THRESHOLD)
        for (ix, iz) in (inward, inward2,
                         (inward[0], inward[1] + 1), (inward[0], inward[1] - 1)):
            if not is_solid(world, ix, gy, iz):
                world.set_block(ix, gy, iz, FLOOR_IN)
        results.append({"name": name, "door": [dx, feet, dz], "facing": facing,
                        "side": side, "ground_y": gy,
                        "threshold": [outward[0], gy, outward[1]]})
    report["door_sweep"] = results
    n_ok = sum(1 for r in results if r.get("door"))
    print(f"door sweep done: {n_ok}/{len(results)} doors placed")
    for r in results:
        if not r.get("door"):
            print("  no door:", r["name"], "-", r.get("note"))


# ------------------------------------------------------------------ step 4
def repair_door_approaches(world, report):
    """Make every placed sweep door actually reachable on foot.  Two Arnis
    habits break otherwise-valid doors: (1) a door on a raised terrace /
    plinth whose only stair is broken -- the main library east door has
    threshold top -45 while the plaza ground 2 cells out is -49, with a
    single stair at -48; (2) a trapdoor/slab sitting on the threshold top,
    raising the walk surface a block above the door's feet.
    Rule (connection only, no invention): walk outward from the threshold;
    if the ground drops, build a straight stone-brick stair, 1 block up per
    cell, filling solid from the local ground up to each step; strip a
    trapdoor/slab off the threshold top so the walk surface is the solid
    top at gy.  At most 6 steps of fill / 8 cells of run; if the stair
    path is blocked or the threshold surface sits more than 1 above the
    door's feet, leave the door and record it as failed."""
    repairs = []
    for r in report.get("door_sweep", []):
        if not r.get("door"):
            continue
        (dx, dy, dz) = r["door"]
        gy = r["ground_y"]
        (tx, _ty, tz) = r["threshold"]
        facing = r["facing"]
        out = {"north": (0, -1), "south": (0, 1),
               "west": (-1, 0), "east": (1, 0)}[facing]
        # 1. threshold walk surface: the sweep leaves a stone-brick
        #    threshold at gy when the original ground dips, so the surface
        #    is max(original top, gy); strip trapdoors/slabs above gy.
        #    NOTE: reads see the ORIGINAL world only -- set_block edits are
        #    invisible -- so this must be a bounded downward scan, never a
        #    "remove then re-read top" loop (that loops forever).
        removed = []
        top = top_y(world, tx, tz)
        surface = gy
        if top is not None and top > gy:
            surface = None
            for yy in range(top, gy, -1):
                b = world.get_block(tx, yy, tz)
                if b and (b.endswith("_trapdoor") or b.endswith("_slab")
                         or b.endswith("_door")):
                    world.set_block(tx, yy, tz, "minecraft:air")
                    removed.append(b)
                elif b is not None and b not in AIR and b not in VEGETATION:
                    surface = yy
                    break
            if surface is None:
                surface = gy
        walk_top = surface
        if walk_top > gy + 1:
            repairs.append({"name": r["name"], "door": [dx, dy, dz],
                            "status": "failed", "steps": [],
                            "note": f"threshold surface {walk_top} is above "
                                    f"door feet {gy + 1}, cannot enter",
                            "trapdoor_removed": removed})
            continue
        # 2. stair down to the surrounding ground, 1 up per cell outward
        steps = []
        status = "ok"
        note = None
        for d in range(1, 9):
            (sx, sz) = (tx + out[0] * d, tz + out[1] * d)
            gt = top_y(world, sx, sz)
            if gt is None:
                status = "failed"
                note = f"outward cell {(sx, sz)} has no ground"
                break
            want = walk_top - d
            if want <= gt:
                break  # reached ground level
            if want - gt > 6:
                status = "failed"
                note = f"step at {(sx, sz)} would need {want - gt} fill"
                break
            if not (is_air(world, sx, want + 1, sz)
                    and is_air(world, sx, want + 2, sz)):
                status = "failed"
                note = f"no headroom above step at {(sx, sz)}"
                break
            steps.append((sx, sz, gt, want))
        else:
            status = "failed"
            note = "drop not resolved within 8 cells"
        if status == "failed":
            repairs.append({"name": r["name"], "door": [dx, dy, dz],
                            "status": "failed", "steps": [], "note": note,
                            "trapdoor_removed": removed})
            continue
        for (sx, sz, gt, want) in steps:
            for yy in range(gt + 1, want + 1):
                world.set_block(sx, yy, sz, "minecraft:stone_bricks")
        repairs.append({"name": r["name"], "door": [dx, dy, dz],
                        "status": "built" if steps else "ok",
                        "steps": [{"cell": [sx, sz], "top": want}
                                  for (sx, sz, _g, want) in steps],
                        "trapdoor_removed": removed})
    report["door_approach_repairs"] = repairs
    n_built = sum(1 for x in repairs if x["status"] == "built")
    n_fail = sum(1 for x in repairs if x["status"] == "failed")
    print(f"door approaches: {n_built} stairs built, {n_fail} failed, "
          f"{len(repairs) - n_built - n_fail} already fine")
    for x in repairs:
        if x["status"] != "ok":
            print("  approach:", x["name"], "-", x["status"],
                  (f"{len(x['steps'])} steps" if x["steps"] else x.get("note", "")),
                  (f"(removed {x['trapdoor_removed']})" if x.get("trapdoor_removed") else ""))



def repave_roads(world, report):
    """OSM highways: black carriageway + light sidewalks, at local ground Y.
    Skips building footprints and existing stone-brick plazas."""
    footprints = [fp["polygon"] for fp in PLAN.get("footprints", [])]
    for m in DATA["missing_buildings"]:
        if m.get("poly"):
            footprints.append(m["poly"])

    def in_building(x, z):
        for poly in footprints:
            if point_in_poly(x + 0.5, z + 0.5, poly):
                return True
        return False

    stats = Counter()
    for r in DATA["roads"]:
        pts = r["pts"]
        width = r["width"]
        mat = "minecraft:" + r["material"]
        walk = ("minecraft:" + r["sidewalk"]) if r.get("sidewalk") else mat
        half = width // 2
        for (x1, z1), (x2, z2) in zip(pts, pts[1:]):
            steps = max(abs(x2 - x1), abs(z2 - z1), 1)
            for s in range(steps + 1):
                cx = round(x1 + (x2 - x1) * s / steps)
                cz = round(z1 + (z2 - z1) * s / steps)
                # perpendicular offsets
                dx = x2 - x1
                dz = z2 - z1
                if abs(dx) >= abs(dz):
                    perp = [(0, o) for o in range(-half, half + 1)]
                else:
                    perp = [(o, 0) for o in range(-half, half + 1)]
                for (ox, oz) in perp:
                    x, z = cx + ox, cz + oz
                    if not (0 <= x < 2093 and 0 <= z < 996):
                        stats["skipped_out_of_bounds"] += 1
                        continue
                    if in_building(x, z):
                        stats["skipped_building"] += 1
                        continue
                    t = top_y(world, x, z)
                    if t is None:
                        stats["no_ground"] += 1
                        continue
                    cur = world.get_block(x, t, z)
                    if cur in ("minecraft:stone_bricks", "minecraft:water") \
                            or is_tree_top(cur):
                        stats["skipped_plaza_water_tree"] += 1
                        continue
                    # sidewalk = outer band; carriageway = inner
                    off = max(abs(ox), abs(oz))
                    target = walk if off >= half else mat
                    if cur != target:
                        world.set_block(x, t, z, target)
                        stats["paved"] += 1
                    # clear vegetation sitting on the new surface
                    above = world.get_block(x, t + 1, z)
                    if above in VEGETATION:
                        world.set_block(x, t + 1, z, "minecraft:air")
                        stats["veg_cleared"] += 1
    report["roads"] = dict(stats)
    print("roads done:", dict(stats))

# ------------------------------------------------------------------ step 5
def build_courts(world, report):
    """28x15 standard courts: green surface, white lines, hoops.
    Court count/layout inside each OSM basketball area is estimated."""
    out = []
    for area in DATA["courts"]:
        area_out = {"area": area["area"], "courts": []}
        for c in area["courts"]:
            x0, z0, x1, z1 = c["x0"], c["z0"], c["x1"], c["z1"]
            cx, cz = c["cx"], c["cz"]
            # surface Y: modal top in the rect
            tops = [top_y(world, x, z) for x in range(x0, x1 + 1, 2)
                    for z in range(z0, z1 + 1, 2)]
            tops = [t for t in tops if t is not None]
            sy = modal(tops)
            capped = 0
            left_high = 0
            if sy is None:
                area_out["courts"].append({"rect": [x0, z0, x1, z1], "error": "no ground"})
                continue
            # level the surface to sy (fill dips, cap highs) in green;
            # remember the real surface Y per cell for lines/hoops
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
                        # cap highs so the court is actually flat: the old
                        # code only recoloured the high top, leaving 4-block
                        # steps at the west courts.  Only cap small bumps
                        # (<=6); anything taller is left alone and reported.
                        if t - sy <= 6:
                            for y in range(sy + 1, t + 1):
                                if is_solid(world, x, y, z):
                                    world.set_block(x, y, z, "minecraft:air")
                            world.set_block(x, sy, z, "minecraft:green_concrete")
                            surf[(x, z)] = sy
                            capped += 1
                        else:
                            world.set_block(x, t, z, "minecraft:green_concrete")
                            surf[(x, z)] = t
                            left_high += 1
                    else:
                        world.set_block(x, t, z, "minecraft:green_concrete")
                        surf[(x, z)] = t
            # white lines (drawn on the real surface at each cell)
            def line(x, z):
                if (x, z) in surf:
                    world.set_block(x, surf[(x, z)], z, "minecraft:white_concrete")
            # boundary
            for x in range(x0, x1 + 1):
                line(x, z0); line(x, z1)
            for z in range(z0, z1 + 1):
                line(x0, z); line(x1, z)
            # centre line + centre circle (r=2 ring)
            for z in range(z0, z1 + 1):
                line(cx, z)
            for dx in range(-2, 3):
                for dz in range(-2, 3):
                    if round(math.hypot(dx, dz)) == 2:
                        line(cx + dx, cz + dz)
            # free-throw lanes (6 deep x 5 wide at each end) + 3-pt arcs (r=6)
            for end, sgn in ((x0, 1), (x1, -1)):
                hx = end + sgn  # hoop x (1 inside the end line)
                for dx in range(0, 6):
                    for dz in (-2, 2):
                        line(end + sgn * dx, cz + dz)
                for dz in range(-2, 3):
                    line(end + sgn * 5, cz + dz)
                for dx in range(-6, 7):
                    for dz in range(-6, 7):
                        d = math.hypot(dx, dz)
                        if 5.5 <= d <= 6.5:
                            ax, az = hx + dx * sgn, cz + dz
                            if x0 <= ax <= x1 and z0 <= az <= z1:
                                line(ax, az)
                # hoop: post (fence) outside, backboard (white) on the line,
                # rim (iron bars) just inside; heights follow the local surface
                px = end - sgn
                hsy = surf.get((end, cz), sy)
                for y in (hsy + 1, hsy + 2, hsy + 3):
                    world.set_block(px, y, cz, "minecraft:dark_oak_fence")
                world.set_block(end, hsy + 3, cz, "minecraft:white_concrete")
                world.set_block(end, hsy + 3, cz + 1, "minecraft:white_concrete")
                world.set_block(hx, hsy + 3, cz, "minecraft:iron_bars")
            area_out["courts"].append({"rect": [x0, z0, x1, z1], "surface_y": sy,
                                       "centre": [cx, sy, cz],
                                       "highs_capped": capped,
                                       "highs_left": left_high})
        out.append(area_out)
    report["courts"] = out
    n = sum(len(a["courts"]) for a in out)
    print(f"courts done: {n} courts in {len(out)} areas")


# ------------------------------------------------------------------ step 6
def fix_east_gate(world, report):
    """Keep the v2 gate structure (7 m still estimated, no photo source).
    Pave the passage + west approach (plaza stone) + east approach (road)."""
    g = DATA["east_gate"]
    x0, x1 = g["x"]
    z0, z1 = g["z"]
    pz0, pz1 = g["passage_z"]
    stats = Counter()
    # passage floor (X1636-1637, Z745-753): stone at the REAL ground, not
    # top_y (top_y returns the beam at -45).  The ground-fix step turned
    # the v2 beam (stone_bricks at -45) to grass because it also used
    # top_y, and reads never see edits, so the beam is restored
    # unconditionally here.
    for x in range(x0, x1 + 1):
        for z in range(pz0, pz1 + 1):
            t = top_y(world, x, z)
            gy = ground_y(world, x, z)
            if gy is None:
                continue
            if t is not None and t > gy:
                # overhang (the beam): restore it to stone_bricks
                world.set_block(x, t, z, "minecraft:stone_bricks")
                stats["beam_restored"] += 1
            if world.get_block(x, gy, z) != "minecraft:stone_bricks":
                world.set_block(x, gy, z, "minecraft:stone_bricks")
                stats["passage_paved"] += 1
    # west approach (X1600-1635, Z745-753): plaza stone
    for x in range(1600, x0):
        for z in range(pz0, pz1 + 1):
            t = top_y(world, x, z)
            if t is None or is_tree_top(world.get_block(x, t, z)):
                continue
            cur = world.get_block(x, t, z)
            if cur != "minecraft:stone_bricks":
                world.set_block(x, t, z, "minecraft:stone_bricks")
                stats["west_paved"] += 1
    # east approach (X1638-1680, Z745-753): road to 海军路
    for x in range(x1 + 1, 1681):
        for z in range(pz0, pz1 + 1):
            t = top_y(world, x, z)
            if t is None or is_tree_top(world.get_block(x, t, z)):
                continue
            cur = world.get_block(x, t, z)
            target = ("minecraft:light_gray_concrete" if z in (pz0, pz1)
                      else "minecraft:black_concrete")
            if cur != target:
                world.set_block(x, t, z, target)
                stats["east_paved"] += 1
    report["east_gate"] = dict(stats)
    print("east gate done:", dict(stats))


# ------------------------------------------------------------------ step 7
def build_generic(world, poly, floors, name):
    """Rule-built rectangular-ish building: walls + window bands + floors
    + flat roof + door.  Returns the door record."""
    cells = poly_cells(poly)
    xs = [p[0] for p in poly]; zs = [p[1] for p in poly]
    # ground Y outside
    outside = []
    for x in range(min(xs) - 1, max(xs) + 2):
        for z in (min(zs) - 1, max(zs) + 1):
            if not point_in_poly(x + 0.5, z + 0.5, poly):
                outside.append((x, z))
    for z in range(min(zs) - 1, max(zs) + 2):
        for x in (min(xs) - 1, max(xs) + 1):
            if not point_in_poly(x + 0.5, z + 0.5, poly):
                outside.append((x, z))
    gy = modal([top_y(world, x, z) for (x, z) in outside
                if top_y(world, x, z) is not None])
    if gy is None:
        return {"name": name, "error": "no ground"}
    roof_y = gy + 5 * floors
    perimeter = poly_perimeter(poly)
    perim_set = set(perimeter)
    interior = [(x, z) for (x, z) in cells if (x, z) not in perim_set]
    # clear the volume first (in case something is already there)
    for (x, z) in cells:
        for y in range(gy + 1, roof_y + 1):
            if is_solid(world, x, y, z):
                world.set_block(x, y, z, "minecraft:air")
    # floors + roof slabs
    for f in range(floors + 1):
        y = gy + 5 * f
        mat = "minecraft:light_gray_concrete" if f == floors else "minecraft:smooth_stone"
        for (x, z) in cells:
            world.set_block(x, y, z, mat)
    # walls with window bands
    for (x, z) in perimeter:
        for f in range(floors):
            y0 = gy + 5 * f
            for y in range(y0 + 1, y0 + 5):
                world.set_block(x, y, z, "minecraft:light_gray_concrete")
    # window bands: along each polygon edge, window if (dist%4) in (2,3)
    n = len(poly)
    for i in range(n):
        x1, z1 = poly[i]
        x2, z2 = poly[(i + 1) % n]
        steps = max(abs(x2 - x1), abs(z2 - z1), 1)
        for s in range(steps + 1):
            x = round(x1 + (x2 - x1) * s / steps)
            z = round(z1 + (z2 - z1) * s / steps)
            if s % 4 in (2, 3):
                for f in range(floors):
                    y0 = gy + 5 * f
                    for y in range(y0 + 1, y0 + 4):
                        world.set_block(x, y, z, WALL_GLASS)
    # door on the south side: southernmost perimeter cell at the middle X
    perim = poly_perimeter(poly)
    door_x = (min(xs) + max(xs)) // 2
    south_cells = [(x, z) for (x, z) in perim if x == door_x]
    if south_cells:
        door_z = max(z for (_x, z) in south_cells)
    else:
        door_z = max(zs)
    feet = gy + 1
    place_door(world, door_x, feet, door_z, "south")
    if not is_solid(world, door_x, gy, door_z + 1):
        world.set_block(door_x, gy, door_z + 1, THRESHOLD)
    return {"name": name, "rect": [min(xs), min(zs), max(xs), max(zs)],
            "floors": floors, "ground_y": gy, "roof_y": roof_y,
            "door": [door_x, feet, door_z], "facing": "south"}


def add_missing_buildings(world, report):
    out = []
    for m in DATA["missing_buildings"]:
        poly = m.get("poly")
        if not poly:
            out.append({"name": m["name"], "error": "no polygon"})
            continue
        check = check_building_present(world, poly, m["name"])
        if check["present"]:
            out.append({"name": m["name"], "status": "already present in world",
                        "check": check})
            continue
        rec = build_generic(world, poly, m["floors_est"], m["name"])
        rec["note"] = m["note"]
        rec["status"] = "built (estimated floors)"
        out.append(rec)
    report["missing_buildings"] = out
    print("missing buildings:", json.dumps(out, ensure_ascii=False))


# ------------------------------------------------------------------ step 8
def fix_level_dat(world_dir, report):
    p = Path(world_dir) / "level.dat"
    bak = p.with_name("level.dat.bak-v2")
    if not bak.exists():
        import shutil
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
            v = "中国海洋大学西海岸校区v3"
        data_nodes.append((t, n, v))
    new_root = (root[0], root[1],
                [(t, n, data_nodes if n == "Data" else v) for (t, n, v) in root[2]])
    p.write_bytes(gzip.compress(dumps(new_root), compresslevel=6))
    root2 = loads(gzip.decompress(p.read_bytes()))
    data2 = find_node(root2[2], "Data")
    report["level_dat"] = {
        "old_name": old_name, "new_name": find(data2[2], "LevelName")[1],
        "old_lastplayed": old_played, "new_lastplayed": find(data2[2], "LastPlayed")[1],
        "spawn": [find(data2[2], k)[1] for k in ("SpawnX", "SpawnY", "SpawnZ")],
    }
    print("level.dat:", json.dumps(report["level_dat"], ensure_ascii=False))


# ------------------------------------------------------------------ main
def main():
    t0 = time.time()
    report = {"world": str(WORLD_DIR), "ground_fixes_present": bool(GROUND_FIXES)}
    world = World(str(WORLD_DIR))
    # step 0: checks
    checks = []
    for m in DATA["missing_buildings"]:
        if m.get("poly"):
            checks.append(check_building_present(world, m["poly"], m["name"]))
    report["checks"] = checks
    print("step 0 checks:", json.dumps(checks, ensure_ascii=False))
    # step 1
    rebuild_info_north(world, report)
    # step 2
    seam_door(world, report)
    # step 3
    build_door_sweep(world, report)
    # step 3a: make every placed door reachable (stairs over drops,
    # trapdoors off thresholds); runs before ground fixes so a
    # fix cell can only recolour the stair base, never its height
    repair_door_approaches(world, report)
    # step 3b: ground rubble fixes (if a fixes file was supplied); runs
    # BEFORE the road repave so a real OSM road still wins over a fix cell
    if GROUND_FIXES:
        n = 0
        for fix in GROUND_FIXES.get("fixes", []):
            for (x, z) in fix["cells"]:
                t = top_y(world, x, z)
                if t is not None and not is_tree_top(world.get_block(x, t, z)):
                    world.set_block(x, t, z, "minecraft:" + fix["material"])
                    n += 1
        report["ground_fixes_applied"] = n
        print("ground fixes applied:", n)
    # step 4
    repave_roads(world, report)
    # step 5
    build_courts(world, report)
    # step 6
    fix_east_gate(world, report)
    # step 7
    add_missing_buildings(world, report)
    # flush
    changed = world.flush()
    report["cells_changed"] = changed
    report["elapsed_s"] = round(time.time() - t0, 1)
    # step 8
    fix_level_dat(WORLD_DIR, report)
    out = WORK / "v3-build-report.json"
    json.dump(report, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"BUILD DONE: {changed} cells changed in {report['elapsed_s']}s; report -> {out}")


if __name__ == "__main__":
    main()
