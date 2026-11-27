#!/usr/bin/env python3
"""v4 verify: runs validate_mojang.py (vanilla 1.21.4 read) and read-back
checks on the built staging-v4 world.  Writes v4-verify-report.json.

Checks:
  - info north/south facades: roof material (flat light-grey, no red),
    clutter above roof, face field/fin/glass mix, ground-floor curtain wall
  - main entrances: door blocks + facing, steps, canopy, BFS courtyard ->
    interior (box-constrained so the path must use the new entrance)
  - low white building: presence, height, roof, walls, door, BFS
  - courtyard: blue walkways, stone plazas, no black concrete left
  - regression: v3 doors still present and correct
Set V4_WORLD to override the world dir (VM dry-run).
"""
import json
import os
import shutil
import subprocess
import sys
from collections import Counter, deque
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from finish_world import World  # noqa: E402
from build_v4 import is_parapet_keepable  # noqa: E402

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

FIELD = "minecraft:light_gray_concrete"
FIN = "minecraft:gray_concrete"
GLASS = "minecraft:light_blue_stained_glass"


def is_passable(block):
    # Light blocks have no collision box in-game, so a player walks
    # through them; treat them as passable (v3 did not, its routes just
    # happened to avoid lights).
    if block is None or block in AIR or block in VEGETATION:
        return True
    if block == "minecraft:light":
        return True
    return block.endswith("_door")


def floor_below(world, x, z, y_max, y_bottom=-64):
    for y in range(y_max, y_bottom - 1, -1):
        b = world.get_block(x, y, z)
        if b is None:
            continue
        if is_passable(b):
            continue
        return y
    return None


def floor_y(world, x, z, y_top=64, y_bottom=-64):
    return floor_below(world, x, z, y_top, y_bottom)


def standable_at(world, x, z, y_ref):
    fy = floor_below(world, x, z, y_ref + 1)
    if fy is None:
        return None
    b = world.get_block(x, fy, z)
    if b in ("minecraft:water", "minecraft:lava"):
        return None
    if not is_passable(world.get_block(x, fy + 1, z)):
        return None
    if not is_passable(world.get_block(x, fy + 2, z)):
        return None
    return fy


def standable(world, x, z):
    fy = floor_y(world, x, z)
    if fy is None:
        return None
    b = world.get_block(x, fy, z)
    if b in ("minecraft:water", "minecraft:lava"):
        return None
    if not is_passable(world.get_block(x, fy + 1, z)):
        return None
    if not is_passable(world.get_block(x, fy + 2, z)):
        return None
    return fy


def bfs(world, start, goal, max_cells=200000, box_pad=120):
    """2D BFS over standable ground cells. Step up at most 1, drop at most 3.
    Returns (found, path_len_cells, visited, why)."""
    sx, sz = start
    gx, gz = goal
    x0 = min(sx, gx) - box_pad; x1 = max(sx, gx) + box_pad
    z0 = min(sz, gz) - box_pad; z1 = max(sz, gz) + box_pad
    s_floor = standable(world, sx, sz)
    if s_floor is None:
        return False, 0, 0, "start not standable"
    dist = {(sx, sz): 0}
    floors = {(sx, sz): s_floor}
    dq = deque([(sx, sz)])
    visited = 0
    while dq:
        (x, z) = dq.popleft()
        visited += 1
        if visited > max_cells:
            return False, 0, visited, "cell budget exceeded"
        if (x, z) == (gx, gz):
            return True, dist[(x, z)], visited, "ok"
        for (nx, nz) in ((x + 1, z), (x - 1, z), (x, z + 1), (x, z - 1)):
            if (nx, nz) in dist or not (x0 <= nx <= x1 and z0 <= nz <= z1):
                continue
            nf = standable_at(world, nx, nz, floors[(x, z)])
            if nf is None:
                continue
            if nf - floors[(x, z)] > 1 or floors[(x, z)] - nf > 3:
                continue
            dist[(nx, nz)] = dist[(x, z)] + 1
            floors[(nx, nz)] = nf
            dq.append((nx, nz))
    return False, 0, visited, "no path"


def door_blocks_ok(world, door, facing, block="minecraft:oak_door"):
    (x, y, z) = door
    lo = world.get_block_state(x, y, z) or ""
    up = world.get_block_state(x, y + 1, z) or ""
    return (lo.startswith(block) and f"facing={facing}" in lo
            and "half=lower" in lo and up.startswith(block)
            and f"facing={facing}" in up and "half=upper" in up)


def face_mix(world, rect, ground_y, roof_y):
    """Count FIELD/FIN/GLASS/other on the four faces (ground..roof)."""
    x0, z0, x1, z1 = rect
    mix = Counter()
    lines = ([(x, z0) for x in range(x0, x1 + 1)] +
             [(x, z1) for x in range(x0, x1 + 1)] +
             [(x0, z) for z in range(z0, z1 + 1)] +
             [(x1, z) for z in range(z0, z1 + 1)])
    for (x, z) in lines:
        for y in range(ground_y, roof_y + 1):
            b = world.get_block(x, y, z)
            if b is None or b in AIR:
                continue
            if b == FIELD:
                mix["field"] += 1
            elif b == FIN:
                mix["fin"] += 1
            elif b == GLASS:
                mix["glass"] += 1
            else:
                mix[f"other:{b}"] += 1
    return dict(mix)


def main():
    BUILD = json.load(open(WORK / "v4-build-report.json", encoding="utf-8"))
    report = {}
    world = World(str(WORLD_DIR))
    # --- 0. vanilla validation (needs jpype; only in PC `py`) ---
    print("running validate_mojang.py ...", flush=True)
    try:
        val_py = shutil.which("py") or sys.executable
        r = subprocess.run([val_py, str(WORK / "validate_mojang.py"),
                            str(WORLD_DIR)], capture_output=True, text=True,
                           timeout=1800)
        report["validate_mojang"] = {"returncode": r.returncode,
                                     "stdout": r.stdout[-2000:],
                                     "stderr": r.stderr[-2000:]}
        print(r.stdout[-1500:], flush=True)
    except Exception as e:  # noqa: BLE001
        report["validate_mojang"] = {"error": str(e)}
        print("validate_mojang failed to run:", e, flush=True)

    # --- 1. facades ---
    fac = {}
    for group, spec in (("info_north", DATA["info_north"]),
                        ("info_south", DATA["info_south"])):
        for name, s in spec.items():
            x0, z0, x1, z1 = s["rect"]
            roof_y = s["roof_y"]
            roof_mix = Counter()
            clutter = 0
            for x in range(x0, x1 + 1):
                for z in range(z0, z1 + 1):
                    b = world.get_block(x, roof_y, z)
                    if b:
                        roof_mix[b] += 1
                    near_edge = (x == x0 or x == x1 or z == z0 or z == z1
                                 or x == x0 + 1 or x == x1 - 1
                                 or z == z0 + 1 or z == z1 - 1)
                    for y in range(roof_y + 1, roof_y + 11):
                        bb = world.get_block(x, y, z)
                        if not bb or bb in AIR:
                            continue
                        if y <= roof_y + 2 and near_edge and is_parapet_keepable(bb):
                            continue
                        clutter += 1
            # ground-floor curtain wall: glass cells in band ground+1..+4
            curtain = 0
            for (x, z) in ([(x, z0) for x in range(x0, x1 + 1)] +
                           [(x, z1) for x in range(x0, x1 + 1)] +
                           [(x0, z) for z in range(z0, z1 + 1)] +
                           [(x1, z) for z in range(z0, z1 + 1)]):
                for y in range(s["ground_y"] + 1, s["ground_y"] + 5):
                    if world.get_block(x, y, z) == GLASS:
                        curtain += 1
            fac[f"{group}.{name}"] = {
                "roof_top_mix": dict(roof_mix.most_common(5)),
                "red_roof_cells": roof_mix.get("minecraft:red_terracotta", 0),
                "clutter_above_roof": clutter,
                "face_mix": face_mix(world, s["rect"], s["ground_y"], roof_y),
                "curtain_glass_cells": curtain}
    report["facades"] = fac
    print("facades:", json.dumps(fac, ensure_ascii=False), flush=True)

    # --- 2. main entrances ---
    ent = {}
    for name, e in BUILD.get("main_entrances", {}).items():
        if "door" not in e:
            ent[name] = {"error": e.get("error", "no door")}
            continue
        (dx, dy, dz) = e["door"]
        facing = e["facing"]
        out_dir = 1 if facing == "south" else -1
        stairs = 0
        for k in range(8):
            z = dz + out_dir * (8 - k)
            for ox in range(-4, 5):
                if world.get_block(dx + ox, e["ground_y_outside"] + 1 + (k // 2), z) \
                        == "minecraft:stone_stairs":
                    stairs += 1
        canopy = 0
        for ox in range(-4, 5):
            for d in range(0, 5):
                if world.get_block(dx + ox, e["canopy_y"], dz + out_dir * d) \
                        == "minecraft:black_concrete":
                    canopy += 1
        # BFS: courtyard bottom of steps -> interior (box-constrained)
        start = (dx, dz + out_dir * 10)
        goal = (dx, dz - out_dir * 12)
        found, length, visited, why = bfs(world, start, goal, box_pad=8)
        ent[name] = {"door": e["door"], "facing": facing,
                     "blocks_ok": door_blocks_ok(world, (dx, dy, dz), facing),
                     "stair_blocks": stairs, "canopy_cells": canopy,
                     "bfs": {"found": found, "path_len": length,
                             "visited": visited, "why": why}}
    report["main_entrances"] = ent
    print("main entrances:", json.dumps(ent, ensure_ascii=False), flush=True)

    # --- 3. low building ---
    lb = BUILD.get("low_building", {})
    low = {}
    if lb and "rect" in lb:
        x0, z0, x1, z1 = lb["rect"]
        roof_y = lb["roof_y"]
        tops = Counter()
        roof_mix = Counter()
        wall_mix = Counter()
        for x in range(x0, x1 + 1, 2):
            for z in range(z0, z1 + 1, 2):
                t = world.top_solid(x, z, y_top=64, y_bottom=-64)
                if t:
                    tops[t[0]] += 1
                    roof_mix[t[1]] += 1
        for (x, z) in ([(x, z0) for x in range(x0, x1 + 1)] +
                       [(x, z1) for x in range(x0, x1 + 1)] +
                       [(x0, z) for z in range(z0, z1 + 1)] +
                       [(x1, z) for z in range(z0, z1 + 1)]):
            for y in range(lb["ground_y"] + 1, roof_y):
                b = world.get_block(x, y, z)
                if b:
                    wall_mix[b] += 1
        (ddx, ddy, ddz) = lb["door"]
        found, length, visited, why = bfs(world, (ddx + 2, ddz),
                                          (ddx - 4, ddz), box_pad=8)
        low = {"modal_top": tops.most_common(3), "roof_mix": dict(roof_mix.most_common(4)),
               "wall_mix": dict(wall_mix.most_common(5)),
               "door_blocks_ok": door_blocks_ok(
                   world, (ddx, ddy, ddz), lb["facing"], "minecraft:dark_oak_door"),
               "bfs": {"found": found, "path_len": length,
                       "visited": visited, "why": why}}
    report["low_building"] = low
    print("low building:", json.dumps(low, ensure_ascii=False), flush=True)

    # --- 4. courtyard ---
    cy = DATA["courtyard"]
    x0, z0, x1, z1 = cy["rect"]
    lb_rect = BUILD.get("low_building", {}).get("rect") or [0, 0, -1, -1]
    lx0, lz0, lx1, lz1 = lb_rect
    blue = 0
    stone = 0
    black_left = 0
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            if lx0 - 1 <= x <= lx1 + 1 and lz0 - 1 <= z <= lz1 + 1:
                continue
            t = world.top_solid(x, z, y_top=64, y_bottom=-64)
            if not t:
                continue
            ty, tb = t
            if tb == "minecraft:blue_concrete":
                blue += 1
            elif tb == "minecraft:stone_bricks":
                stone += 1
            elif tb == "minecraft:black_concrete" and ty <= -44:
                # ground-level black tops only: the north canopy is black
                # concrete at y=-39 and must not count as leftover road
                black_left += 1
    report["courtyard"] = {"blue_walkway_top_cells": blue,
                           "stone_bricks_top_cells": stone,
                           "black_concrete_left": black_left}
    print("courtyard:", json.dumps(report["courtyard"], ensure_ascii=False), flush=True)

    # --- 5. regression: v3 doors still there ---
    v3 = json.load(open(WORK / "v3-build-report.json", encoding="utf-8"))
    reg = []
    for d in v3["info_north"]["doors"]:
        (x, y, z) = d["door"]
        reg.append({"name": d["name"],
                    "blocks_ok": door_blocks_ok(world, (x, y, z), d["facing"])})
    (sx, sy, sz) = v3["seam_door"]["door"]
    reg.append({"name": "seam_door_1358",
                "blocks_ok": door_blocks_ok(world, (sx, sy, sz), "north")})
    report["v3_doors_regression"] = reg
    print("v3 doors:", json.dumps(reg, ensure_ascii=False), flush=True)

    out = WORK / "v4-verify-report.json"
    json.dump(report, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"VERIFY DONE; report -> {out}")


if __name__ == "__main__":
    main()
