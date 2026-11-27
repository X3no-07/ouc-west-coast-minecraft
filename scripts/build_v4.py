#!/usr/bin/env python3
"""v4 build: panorama-driven appearance correction on a copy of the v3 world.

Base: staging-v4/OUC-West-Coast-v4 (copy of the v3 world).  All edits are
programmatic block rules; nothing is hand-placed in-game.

Panorama source (verified by live browser, parent chat 2026-11-27 04:29):
  official OUC VR panorama https://www.kuleiman.com/165316/index.html
  (41 points; default Yushan campus, switch to 西海岸校区 at the bottom).
  Info buildings: two tall slabs facing each other across a green courtyard,
  low white ~2-floor building at one end of the courtyard; flat roofs,
  light-grey parapet, NO red roof; facade light-grey tile/stone with dark
  grey vertical fins; ground floor dark-framed blue-grey glass curtain wall;
  each floor a horizontal row of blue glass windows; main entrances face the
  courtyard: wide grey stone steps (~8-9), dark grey flat canopy, double
  glass doors; courtyard grey stone paving + blue walkway + lawn.

Steps (in order):
  0. checks (info buildings present; low-building rect clear of roads)
  1. info-north + info-south facade rework (recolour in place: field /
     fins / blue glass / ground-floor curtain wall) + roofs unified to
     flat light-grey concrete (south big roof de-redded)
  2. main entrances (north main south wall, south big north wall):
     raised door (+4, 8 stair blocks), canopy, interior landing,
     interior down-stair to the ground floor where the floor-1 slab is
     more than 1 above the landing
  3. low white building in the courtyard (new, ~2 floors; position
     estimated: west end of the courtyard, east/west unconfirmed)
  4. courtyard repave (blue walkways, stone plazas, road strips -> stone)
  5. level.dat rename to v4 + LastPlayed refresh
Writes v4-build-report.json.  Run on the PC against the staging-v4 copy.
Set V4_WORLD to override the world dir (used for the VM dry-run).
"""
import gzip
import json
import math
import os
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from anvil import dumps, find, find_node, loads  # noqa: E402
from finish_world import World  # noqa: E402

WORK = HERE
WORLD_DIR = Path(os.environ.get(
    "V4_WORLD", str(WORK / "staging-v4" / "OUC-West-Coast-v4")))
DATA = json.load(open(WORK / "v4-build-data.json", encoding="utf-8"))

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


# --- panorama palette (verified) ---
FIELD = "minecraft:light_gray_concrete"      # 浅灰瓷砖/石材贴面
FIN = "minecraft:gray_concrete"              # 深灰竖向鳍片/竖框
GLASS = "minecraft:light_blue_stained_glass"  # 蓝色玻璃窗
ROOF = "minecraft:light_gray_concrete"       # 平顶浅灰
CANOPY = "minecraft:black_concrete"          # 深灰/黑平板挑檐
LOW_WALL = "minecraft:white_concrete"        # 低楼白色外墙
STEP_STAIR = "minecraft:stone_stairs"
STEP_FILL = "minecraft:stone_bricks"
FLOOR_IN = "minecraft:oak_planks"
WALK_BLUE = "minecraft:blue_concrete"        # 院落蓝色步道
PLAZA = "minecraft:stone_bricks"             # 院落灰石砖铺装

GLASS_SET = ("glass",)  # substring match: any *glass* block
PIER_SET = {
    "minecraft:smooth_sandstone", "minecraft:polished_andesite",
    "minecraft:smooth_stone", "minecraft:white_concrete",
    "minecraft:calcite", "minecraft:stone_bricks",
    "minecraft:polished_diorite", "minecraft:sandstone",
    "minecraft:cut_sandstone", "minecraft:smooth_quartz",
    "minecraft:quartz_block",
    # extra wall bands found by the v4 dry-run probe (west wing brown
    # terracotta, south small cyan terracotta): same treatment as piers
    "minecraft:brown_terracotta", "minecraft:cyan_terracotta",
}
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
PARAPET_BAD_SUFFIX = ("_trapdoor", "_stairs", "_pressure_plate", "_button",
                      "_fence", "_wall", "_carpet")


def is_clutter(block):
    if block is None:
        return False
    if block in CLUTTER_EXACT:
        return True
    return any(block.endswith(s) for s in CLUTTER_SUFFIX)


def is_parapet_keepable(block):
    if block is None or block in AIR:
        return False
    if block in CLUTTER_EXACT:
        return False
    return not any(block.endswith(s) for s in PARAPET_BAD_SUFFIX)


def is_glass(block):
    return block is not None and "glass" in block


def is_solid(world, x, y, z):
    b = world.get_block(x, y, z)
    return b is not None and b not in AIR


def is_air(world, x, y, z):
    b = world.get_block(x, y, z)
    return b is None or b in AIR


def top_y(world, x, z):
    t = world.top_solid(x, z, y_top=64, y_bottom=-64)
    return t[0] if t else None


def modal(values):
    if not values:
        return None
    return Counter(values).most_common(1)[0][0]


def door_state(block, facing, half):
    return (f"{block}[facing={facing},half={half},hinge=left,"
            f"open=false,powered=false]")


def place_door(world, x, y, z, facing, block="minecraft:oak_door"):
    """y = feet level (lower block). Guarantees a solid floor under the door."""
    world.set_block(x, y, z, door_state(block, facing, "lower"))
    world.set_block(x, y + 1, z, door_state(block, facing, "upper"))
    below = world.get_block(x, y - 1, z)
    if below is None or below in AIR or below in VEGETATION:
        world.set_block(x, y - 1, z, "minecraft:stone_bricks")
    return (x, y, z), (x, y + 1, z)


def stair_state(facing):
    return f"minecraft:stone_stairs[facing={facing},half=bottom,shape=straight]"


# ------------------------------------------------------------------ step 0
def check_info_present(world, report):
    """Info north (3 wings) + info south (2 parts) must be present in v3."""
    checks = []
    for group, spec in (("info_north", DATA["info_north"]),
                        ("info_south", DATA["info_south"])):
        for name, s in spec.items():
            x0, z0, x1, z1 = s["rect"]
            tops = [top_y(world, x, z)
                    for x in range(x0, x1 + 1, 4)
                    for z in range(z0, z1 + 1, 4)]
            tops = [t for t in tops if t is not None]
            mi = modal(tops)
            checks.append({"name": f"{group}.{name}", "rect": s["rect"],
                           "modal_top": mi, "roof_y": s["roof_y"],
                           "present": mi is not None and mi - s["ground_y"] >= 8})
    # low-building rect: must be clear ground (no road/building tops)
    lb = DATA["low_building"]
    x0, z0, x1, z1 = lb["rect"]
    bad = []
    for x in range(x0, x1 + 1, 2):
        for z in range(z0, z1 + 1, 2):
            t = world.top_solid(x, z, y_top=64, y_bottom=-64)
            if t is None:
                continue
            ty, tb = t
            if tb in ("minecraft:black_concrete", "minecraft:light_gray_concrete",
                      "minecraft:stone_bricks") and ty > lb["ground_y"] + 1:
                bad.append((x, z, ty, tb))
            if ty > lb["ground_y"] + 2 and not is_tree_top(tb):
                bad.append((x, z, ty, tb))
    checks.append({"name": "low_building_rect_clear", "rect": lb["rect"],
                   "obstructions": bad[:10], "clear": not bad})
    report["checks"] = checks
    print("step 0 checks:", json.dumps(checks, ensure_ascii=False))
    return checks


# ------------------------------------------------------------------ step 1
def recolor_facade(world, rect, roof_y, ground_y, name):
    """Recolour one wing in place, panorama palette.

    Faces: field light-grey tile; every 4th column a dark-grey fin;
    glass cells -> blue glass; ground-floor band -> continuous blue-grey
    glass curtain wall (except fin columns). Roof -> flat light-grey.
    Only touches cells that already hold a wall/glass block; air, doors,
    lights and slab trim are left alone. Returns counts.
    """
    x0, z0, x1, z1 = rect
    counts = {"field": 0, "fin": 0, "glass": 0, "curtain": 0, "roof": 0,
              "clutter_cleared": 0}
    # --- roof: unify + clear clutter above (parapet rule, as in v3) ---
    cells = [(x, z) for x in range(x0, x1 + 1) for z in range(z0, z1 + 1)]
    for (x, z) in cells:
        near_edge = (x == x0 or x == x1 or z == z0 or z == z1
                     or x == x0 + 1 or x == x1 - 1 or z == z0 + 1 or z == z1 - 1)
        for y in range(roof_y + 1, roof_y + 11):
            b = world.get_block(x, y, z)
            if b is None or b in AIR:
                continue
            if y <= roof_y + 2 and near_edge and is_parapet_keepable(b):
                continue
            world.set_block(x, y, z, "minecraft:air")
            counts["clutter_cleared"] += 1
    for (x, z) in cells:
        b = world.get_block(x, roof_y, z)
        if b is None or b in AIR:
            continue
        if b.endswith("_slab"):
            continue  # keep slab edge trim
        if b != ROOF:
            world.set_block(x, roof_y, z, ROOF)
            counts["roof"] += 1
    # --- walls: four faces ---
    sides = [
        [(x, z0) for x in range(x0, x1 + 1)],
        [(x, z1) for x in range(x0, x1 + 1)],
        [(x0, z) for z in range(z0, z1 + 1)],
        [(x1, z) for z in range(z0, z1 + 1)],
    ]
    for line in sides:
        for i, (x, z) in enumerate(line):
            is_fin = (i % 4 == 0)
            for y in range(ground_y, roof_y + 1):
                b = world.get_block(x, y, z)
                if b is None or b in AIR:
                    continue
                if b.endswith("_door") or b == "minecraft:light":
                    continue
                if y == ground_y:
                    continue  # keep plinth
                if y == roof_y:
                    continue  # roof handled above
                if is_glass(b):
                    if y <= ground_y + 4 and not is_fin:
                        world.set_block(x, y, z, GLASS)
                        counts["curtain"] += 1
                    elif b != GLASS:
                        world.set_block(x, y, z, GLASS)
                        counts["glass"] += 1
                elif b in PIER_SET:
                    if y <= ground_y + 4:
                        # ground floor: curtain wall, fins stay dark
                        if is_fin:
                            if b != FIN:
                                world.set_block(x, y, z, FIN)
                                counts["fin"] += 1
                        else:
                            if b != GLASS:
                                world.set_block(x, y, z, GLASS)
                                counts["curtain"] += 1
                    elif is_fin:
                        if b != FIN:
                            world.set_block(x, y, z, FIN)
                            counts["fin"] += 1
                    elif b != FIELD:
                        world.set_block(x, y, z, FIELD)
                        counts["field"] += 1
                # anything else (trim, slabs, trapdoors...) left alone
    print(f"facade {name}: {json.dumps(counts, ensure_ascii=False)}")
    return counts


def rebuild_info_facades(world, report):
    out = {}
    for group, spec in (("info_north", DATA["info_north"]),
                        ("info_south", DATA["info_south"])):
        for name, s in spec.items():
            key = f"{group}.{name}"
            out[key] = recolor_facade(world, s["rect"], s["roof_y"],
                                      s["ground_y"], key)
    report["facades"] = out
    return out


# ------------------------------------------------------------------ step 2
def build_main_entrance(world, spec, report):
    """Raised main entrance facing the courtyard.

    Door feet = courtyard surface + 4 (8 half-block steps, ~8-9 real steps
    at ~17 cm each, marked as an estimate). Wide 9-cell staircase, dark
    flat canopy above the door, interior landing; a down-stair to the
    ground floor is added only when the floor-1 slab sits more than 1
    above the landing (north building); otherwise the landing steps
    straight up onto floor 1 (south building).
    """
    name = spec["building"]
    wall_z = spec["wall_z"]
    dx = spec["door_x"]
    facing = spec["facing"]
    # courtyard side is opposite the facing: door faces south -> steps go
    # to larger z; faces north -> steps go to smaller z.
    out_dir = 1 if facing == "south" else -1
    in_dir = -out_dir
    # --- outside ground: modal top along the step run ---
    run_z = [wall_z + out_dir * k for k in range(1, 9)]
    gy = modal([top_y(world, x, z) for x in range(dx - 4, dx + 5)
                for z in run_z if top_y(world, x, z) is not None])
    if gy is None:
        report.setdefault("main_entrances", {})[name] = {"error": "no ground"}
        print(f"entrance {name}: NO ground")
        return None
    feet = gy + 5
    # --- find a solid wall column near dx (existing window gaps are air) --
    chosen = None
    for cx in [dx, dx - 1, dx + 1, dx - 2, dx + 2, dx - 3, dx + 3, dx - 4, dx + 4]:
        if is_solid(world, cx, feet, wall_z) and is_solid(world, cx, feet + 1, wall_z):
            chosen = cx
            break
    if chosen is None:
        report.setdefault("main_entrances", {})[name] = {
            "error": "no solid wall column", "door_x_wanted": dx}
        print(f"entrance {name}: NO solid column")
        return None
    dx = chosen
    # --- cut the opening + carve 3 deep inside (the full landing) ---
    # The landing floor is 3 deep (d=1..3) and the down-stair starts at
    # d=4, so all 3 rows need headroom: the south building's floor-1 slab
    # sits at feet+1 over the 3rd row and would otherwise block the walk.
    place_door(world, dx, feet, wall_z, facing)
    for d in (1, 2, 3):
        for y in (feet, feet + 1):
            cx, cz = dx, wall_z + in_dir * d
            if is_solid(world, cx, y, cz):
                world.set_block(cx, y, cz, "minecraft:air")
    # --- interior landing: 3x3 floor at feet-1, just inside ---
    for ox in (-1, 0, 1):
        for d in (1, 2, 3):
            cx, cz = dx + ox, wall_z + in_dir * d
            b = world.get_block(cx, feet - 1, cz)
            if b is None or b in AIR or is_glass(b):
                world.set_block(cx, feet - 1, cz, FLOOR_IN)
    # --- interior floor levels: ground slab + next slab up ---
    col = [world.get_block(dx, y, wall_z + in_dir * 2)
           for y in range(feet - 1, -64, -1)]
    ground_surface = None
    for k, b in enumerate(col):
        y = feet - 1 - k
        if b is not None and b not in AIR and not is_glass(b) \
                and b != "minecraft:light":
            ground_surface = y + 1
            break
    floor1_surface = None
    for y in range(feet + 1, feet + 8):
        b = world.get_block(dx, y, wall_z + in_dir * 2)
        if b is not None and b not in AIR and not is_glass(b) \
                and b != "minecraft:light":
            floor1_surface = y + 1
            break
    landing_surface = feet  # top of the feet-1 floor blocks
    need_down_stair = False
    down_treads = 0
    if floor1_surface is None or floor1_surface - landing_surface > 1:
        # build a down-stair from the landing to the ground floor
        if ground_surface is not None:
            drop = landing_surface - ground_surface
            if 0 < drop <= 6:
                need_down_stair = True
                down_treads = drop * 2
    if need_down_stair:
        # treads run away from the wall (in_dir), 3 wide, 0.5 rise each
        for i in range(down_treads):
            z = wall_z + in_dir * (4 + i)
            cell_y = (feet - 1) - (i // 2)
            for ox in (-1, 0, 1):
                world.set_block(dx + ox, cell_y, z,
                                stair_state("south" if in_dir < 0 else "north"))
                # headroom: 2 above each tread
                for y in (cell_y + 1, cell_y + 2):
                    if is_solid(world, dx + ox, y, z):
                        world.set_block(dx + ox, y, z, "minecraft:air")
                # underfill down to the ground slab
                for y in range(cell_y - 1, ground_surface - 1, -1):
                    if not is_solid(world, dx + ox, y, z):
                        world.set_block(dx + ox, y, z, LOW_WALL)
    # --- outside staircase: 8 half-steps, 9 wide ---
    steps = 0
    for k in range(8):
        z = wall_z + out_dir * (8 - k)  # k=0 farthest, k=7 closest
        cell_y = gy + 1 + (k // 2)
        for ox in range(-4, 5):
            x = dx + ox
            world.set_block(x, cell_y, z,
                            stair_state("north" if out_dir > 0 else "south"))
            steps += 1
            for y in range(cell_y - 1, gy, -1):
                if not is_solid(world, x, y, z):
                    world.set_block(x, y, z, STEP_FILL)
    # --- headroom above the top steps ---
    # The wall face can carry a protruding pilaster/trim (south face: solid
    # white/grey concrete at feet/feet+1 above the top step). Clear the 2
    # cells above the top two step rows so the player can walk up. The
    # canopy sits at canopy_y = feet+2, above this headroom, and is left
    # alone.
    for k in (6, 7):
        z = wall_z + out_dir * (8 - k)
        cell_y = gy + 1 + (k // 2)
        for ox in range(-4, 5):
            for y in (cell_y + 1, cell_y + 2):
                if is_solid(world, dx + ox, y, z):
                    world.set_block(dx + ox, y, z, "minecraft:air")
    # --- canopy: dark flat plate, 9 wide x 5 deep, just above the door ---
    canopy_y = feet + 2
    canopy = 0
    for ox in range(-4, 5):
        for d in range(0, 5):
            x, z = dx + ox, wall_z + out_dir * d
            world.set_block(x, canopy_y, z, CANOPY)
            canopy += 1
    res = {"building": name, "door": [dx, feet, wall_z], "facing": facing,
           "ground_y_outside": gy, "steps": steps, "canopy_cells": canopy,
           "canopy_y": canopy_y, "landing_surface": landing_surface,
           "ground_surface_in": ground_surface,
           "floor1_surface_in": floor1_surface,
           "down_stair": need_down_stair, "down_treads": down_treads}
    report.setdefault("main_entrances", {})[name] = res
    print(f"entrance {name}: {json.dumps(res, ensure_ascii=False)}")
    return res


# ------------------------------------------------------------------ step 3
def build_low_building(world, report):
    """New ~2-floor white building at the west end of the courtyard.

    White walls, horizontal blue-glass window bands, flat light-grey roof,
    central dark doorway on the east face. Position is an estimate
    (panorama: 'one end of the courtyard'; east/west unconfirmed).
    """
    lb = DATA["low_building"]
    x0, z0, x1, z1 = lb["rect"]
    gy = lb["ground_y"]
    floors = lb["floors"]
    roof_y = gy + 5 * floors  # -36
    # clear the footprint
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            for y in range(gy, roof_y + 7):
                b = world.get_block(x, y, z)
                if b is not None and b not in AIR:
                    world.set_block(x, y, z, "minecraft:air")
    # floor slab
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            world.set_block(x, gy, z, LOW_WALL)
    # walls: perimeter, window bands 2-on/2-off, 3 high per floor
    sides = [
        [(x, z0) for x in range(x0, x1 + 1)],
        [(x, z1) for x in range(x0, x1 + 1)],
        [(x0, z) for z in range(z0, z1 + 1)],
        [(x1, z) for z in range(z0, z1 + 1)],
    ]
    windows = 0
    for line in sides:
        for i, (x, z) in enumerate(line):
            is_window = (i % 4) in (2, 3) and 2 <= i <= len(line) - 3
            for f in range(floors):
                y0 = gy + 5 * f
                for y in range(y0 + 1, y0 + 4):
                    world.set_block(x, y, z,
                                    GLASS if is_window else LOW_WALL)
                    if is_window:
                        windows += 1
                for y in (y0, y0 + 4):
                    world.set_block(x, y, z, LOW_WALL)
    # roof slab + parapet
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            world.set_block(x, roof_y, z, ROOF)
    for x in range(x0, x1 + 1):
        for z in (z0, z1):
            world.set_block(x, roof_y + 1, z, LOW_WALL)
            world.set_block(x, roof_y + 2, z, "minecraft:white_concrete_slab")
    for z in range(z0, z1 + 1):
        for x in (x0, x1):
            world.set_block(x, roof_y + 1, z, LOW_WALL)
            world.set_block(x, roof_y + 2, z, "minecraft:white_concrete_slab")
    # central dark doorway on the east face
    ddx, ddy, ddz = lb["door"]
    place_door(world, ddx, ddy, ddz, lb["facing"], "minecraft:dark_oak_door")
    # threshold outside (east side)
    tx = ddx + 1
    t = top_y(world, tx, ddz)
    if t is not None:
        b = world.get_block(tx, t, ddz)
        if b is not None and b not in AIR and not is_tree_top(b):
            world.set_block(tx, t, ddz, STEP_FILL)
    res = {"rect": lb["rect"], "roof_y": roof_y, "ground_y": gy,
           "window_cells": windows, "door": lb["door"],
           "facing": lb["facing"],
           "note": lb["note"]}
    report["low_building"] = res
    print(f"low building: {json.dumps(res, ensure_ascii=False)}")
    return res


# ------------------------------------------------------------------ step 4
def repave_courtyard(world, report):
    """Courtyard: grey stone paving + blue walkways + lawn kept.

    The two OSM roads crossing the courtyard are treated as pedestrian
    plaza paths (their black-concrete tops become stone bricks) -- a
    judgement call: the panorama shows a pedestrian courtyard, no cars.
    The low-building rect is excluded.
    """
    cy = DATA["courtyard"]
    x0, z0, x1, z1 = cy["rect"]
    lb = DATA["low_building"]["rect"]
    lx0, lz0, lx1, lz1 = lb

    def inside_low(x, z):
        return lx0 - 1 <= x <= lx1 + 1 and lz0 - 1 <= z <= lz1 + 1

    RECOLORABLE = {
        "minecraft:grass_block", "minecraft:dirt",
        "minecraft:black_concrete", "minecraft:light_gray_concrete",
        "minecraft:gray_concrete", "minecraft:gray_concrete_powder",
        "minecraft:cracked_stone_bricks", "minecraft:cyan_terracotta",
        "minecraft:stone_bricks",
    }
    counts = {"plaza": 0, "walkway": 0, "road_to_stone": 0, "skipped": 0}

    def recolor_top(x, z, mat, key):
        t = top_y(world, x, z)
        if t is None:
            return False
        b = world.get_block(x, t, z)
        if b is None or b in AIR or is_tree_top(b):
            return False
        above = world.get_block(x, t + 1, z)
        if above is not None and above not in AIR and above not in VEGETATION:
            return False  # not a ground surface (e.g. under a roof)
        if b not in RECOLORABLE and b != "minecraft:stone_bricks":
            return False
        if b == "minecraft:black_concrete":
            counts["road_to_stone"] += 1
        if b != mat:
            world.set_block(x, t, z, mat)
            counts[key] += 1
        return True

    # plazas first
    for (px0, pz0, px1, pz1) in (cy["plaza_north"], cy["plaza_south"]):
        for x in range(px0, px1 + 1):
            for z in range(pz0, pz1 + 1):
                if inside_low(x, z):
                    counts["skipped"] += 1
                    continue
                recolor_top(x, z, PLAZA, "plaza")
    # road strips inside the courtyard rect -> stone
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            if inside_low(x, z):
                continue
            t = top_y(world, x, z)
            if t is not None and world.get_block(x, t, z) == "minecraft:black_concrete":
                above = world.get_block(x, t + 1, z)
                if above is None or above in AIR or above in VEGETATION:
                    world.set_block(x, t, z, PLAZA)
                    counts["road_to_stone"] += 1
    # blue walkways last (they win over plaza)
    wx0, wx1 = cy["walk_ns"]
    for x in range(wx0, wx1 + 1):
        for z in range(z0, z1 + 1):
            if inside_low(x, z):
                continue
            recolor_top(x, z, WALK_BLUE, "walkway")
    wz0, wz1 = cy["walk_ew"]
    for z in range(wz0, wz1 + 1):
        for x in range(x0, x1 + 1):
            if inside_low(x, z):
                continue
            recolor_top(x, z, WALK_BLUE, "walkway")
    report["courtyard"] = counts
    print(f"courtyard: {json.dumps(counts, ensure_ascii=False)}")
    return counts


# ------------------------------------------------------------------ step 5
def fix_level_dat(world_dir, report):
    p = Path(world_dir) / "level.dat"
    bak = p.with_name("level.dat.bak-v3")
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
            v = "中国海洋大学西海岸校区v4"
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


def main():
    t0 = time.time()
    report = {"world": str(WORLD_DIR), "base": "v3"}
    world = World(str(WORLD_DIR))
    check_info_present(world, report)
    rebuild_info_facades(world, report)
    for _key, spec in DATA["main_entrances"].items():
        build_main_entrance(world, spec, report)
    build_low_building(world, report)
    repave_courtyard(world, report)
    changed = world.flush()
    report["cells_changed"] = changed
    report["elapsed_s"] = round(time.time() - t0, 1)
    fix_level_dat(WORLD_DIR, report)
    out = WORK / "v4-build-report.json"
    json.dump(report, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"BUILD DONE: {changed} cells changed in {report['elapsed_s']}s; report -> {out}")


if __name__ == "__main__":
    main()

