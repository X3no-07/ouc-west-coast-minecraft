#!/usr/bin/env python3
"""v3 verify: runs validate_mojang.py (vanilla 1.21.4 read) and read-back
checks on the built staging-v3 world.  Writes v3-verify-report.json.

Checks:
  - info north per wing: roof material, clutter above roof, window bands, doors
  - seam door (1358): door blocks + threshold + BFS inside/outside
  - door sweep: every door's blocks + BFS threshold -> inward-2
  - east gate -> learning complex main entrance: BFS walkable
  - courts: surface / line / hoop counts
  - new buildings: presence, height, roof, door
"""
import json
import shutil
import subprocess
import sys
from collections import Counter, deque
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from finish_world import World  # noqa: E402
from build_v3 import is_parapet_keepable  # noqa: E402  (same parapet rule as the build)

WORK = HERE
WORLD_DIR = WORK / "staging-v3" / "OUC-West-Coast-v3"
DATA = json.load(open(WORK / "v3-build-data.json", encoding="utf-8"))
PLAN = json.load(open(WORK / "plan-v2.json", encoding="utf-8"))
# BUILD (v3-build-report.json) is loaded inside main(): it only exists
# after build_v3.py has run.

AIR = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}
VEGETATION = {"minecraft:tall_grass", "minecraft:grass", "minecraft:fern",
              "minecraft:large_fern", "minecraft:short_grass", "minecraft:dead_bush",
              "minecraft:dandelion", "minecraft:poppy", "minecraft:azure_bluet",
              "minecraft:sunflower", "minecraft:lilac", "minecraft:rose_bush",
              "minecraft:peony", "minecraft:oxeye_daisy", "minecraft:cornflower",
              "minecraft:lily_of_the_valley", "minecraft:allium",
              "minecraft:blue_orchid", "minecraft:red_tulip", "minecraft:orange_tulip",
              "minecraft:white_tulip", "minecraft:pink_tulip", "minecraft:snowdrop"}


def is_passable(block):
    """Blocks a walking player can move through (air, plants, doors)."""
    if block is None or block in AIR or block in VEGETATION:
        return True
    return block.endswith("_door")


def floor_below(world, x, z, y_max, y_bottom=-64):
    """Highest non-passable block at or below y_max, or None.
    The cap matters: under a beam/roof the highest solid is the beam,
    but a walking player stands on the ground below it."""
    for y in range(y_max, y_bottom - 1, -1):
        b = world.get_block(x, y, z)
        if b is None:
            continue
        if is_passable(b):
            continue
        return y
    return None


def floor_y(world, x, z, y_top=64, y_bottom=-64):
    """Highest non-passable block Y (the floor), or None."""
    return floor_below(world, x, z, y_top, y_bottom)


def standable_at(world, x, z, y_ref):
    """(floor_y) if a player standing on a floor near y_ref can stand at
    (x,z): the floor is the highest solid at or below y_ref+1 (so a beam
    above does not count as the floor), with 2 passable blocks above it."""
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
    """(floor_y) if a player can stand at (x,z), else None."""
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
    """2D BFS over standable ground cells. start/goal are (x,z).
    The floor of each step is found relative to the floor the player is
    on (cap = current floor + 1), so multi-storey interiors and gate
    beams do not fake the floor.  Step up at most 1, drop at most 3.
    Returns (found, path_len_cells, visited)."""
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


def door_blocks_ok(world, door, facing):
    (x, y, z) = door
    lo = world.get_block_state(x, y, z) or ""
    up = world.get_block_state(x, y + 1, z) or ""
    return (lo.startswith("minecraft:oak_door") and f"facing={facing}" in lo
            and "half=lower" in lo and up.startswith("minecraft:oak_door")
            and f"facing={facing}" in up and "half=upper" in up)


def main():
    BUILD = json.load(open(WORK / "v3-build-report.json", encoding="utf-8"))
    report = {}
    world = World(str(WORLD_DIR))
    # --- 0. vanilla validation (subprocess; needs the validation/ JRE+jars)
    # NOTE: validate_mojang.py needs jpype, which is only installed in the
    # `py` (3.12) interpreter on the PC -- `python` (3.8) has no jpype, so a
    # plain sys.executable call fails with ModuleNotFoundError.  Prefer `py`.
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

    # --- 1. info north
    info = {}
    for wing_name, spec in DATA["info_north"].items():
        if wing_name == "courtyard":
            continue
        x0, z0, x1, z1 = spec["rect"]
        roof_y = spec["roof_y"]
        roof_mix = Counter()
        clutter = 0
        # parapet rule (same as the build): a keepable block on/just inside
        # the edge, at roof+1/+2, is the parapet rim+cap, not clutter
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
        # window glass on the four walls (ground floor band)
        glass = 0
        for (x, z) in ([(x, z0) for x in range(x0, x1 + 1)] +
                       [(x, z1) for x in range(x0, x1 + 1)] +
                       [(x0, z) for z in range(z0, z1 + 1)] +
                       [(x1, z) for z in range(z0, z1 + 1)]):
            for y in range(spec["ground_y"] + 1, spec["ground_y"] + 4):
                if world.get_block(x, y, z) == "minecraft:light_gray_stained_glass":
                    glass += 1
        info[wing_name] = {"roof_top_mix": dict(roof_mix.most_common(5)),
                           "clutter_above_roof": clutter,
                           "ground_floor_glass_cells": glass}
    info["doors"] = []
    for d in BUILD["info_north"]["doors"]:
        (x, y, z) = d["door"]
        info["doors"].append({"name": d["name"], "door": d["door"],
                              "blocks_ok": door_blocks_ok(world, (x, y, z), d["facing"])})
    report["info_north"] = info
    print("info north:", json.dumps(info, ensure_ascii=False), flush=True)

    # --- 2. seam door + BFS
    sd = BUILD["seam_door"]
    (dx, dy, dz) = sd["door"]
    seam = {"door": sd["door"], "facing": sd["facing"],
            "blocks_ok": door_blocks_ok(world, (dx, dy, dz), "north")}
    # BFS: threshold outside -> 2 cells inside the building
    tx, ty, tz = sd["threshold"]
    found, length, visited, why = bfs(world, (tx, tz), (dx, dz + 2),
                                      box_pad=20, max_cells=20000)
    seam["bfs_outside_to_inside"] = {"found": found, "path_len": length,
                                     "visited": visited, "why": why}
    report["seam_door"] = seam
    print("seam door:", json.dumps(seam, ensure_ascii=False), flush=True)

    # --- 3. door sweep: blocks + BFS for EVERY placed door
    # (was: every 4th door -- the 3 unwalkable doors hid in the unsampled
    # 3/4, so now threshold -> inward-2 is checked for all of them)
    sweep = BUILD["door_sweep"]
    ok = 0
    bad = []
    bfs_ok = 0
    bfs_fail = []
    for i, r in enumerate(sweep):
        if not r.get("door"):
            continue
        (x, y, z) = r["door"]
        good = door_blocks_ok(world, (x, y, z), r["facing"])
        if good:
            ok += 1
        else:
            bad.append(r["name"])
        (tx, ty, tz) = r["threshold"]
        inward = {"north": (x, z + 2), "south": (x, z - 2),
                  "west": (x + 2, z), "east": (x - 2, z)}[r["facing"]]
        found, _l, _v, _w = bfs(world, (tx, tz), inward,
                                box_pad=20, max_cells=20000)
        if found:
            bfs_ok += 1
        else:
            bfs_fail.append({"name": r["name"], "door": [x, y, z],
                             "why": _w, "visited": _v})
    report["door_sweep"] = {"doors_placed": sum(1 for r in sweep if r.get("door")),
                            "door_blocks_ok": ok, "door_blocks_bad": bad,
                            "bfs_checked": sum(1 for r in sweep if r.get("door")),
                            "bfs_ok": bfs_ok, "bfs_fail": bfs_fail}
    print("door sweep:", json.dumps(report["door_sweep"], ensure_ascii=False), flush=True)


    # --- 4. east gate -> learning complex BFS
    # start on the east approach (1645,749), NOT the passage centre: the
    # centre sits under the beam, and a highest-solid floor check would
    # stand the player on the beam.  The route still goes through the gate.
    # goal: the learning-complex door nearest the gate, taken from the
    # build report (a real placed door, not an assumed wall cell -- the
    # old goal (1258,700) was a wall with no door, so "no path" was
    # correct but meaningless).
    gate = (1645, 749)
    lc = [r for r in BUILD["door_sweep"] if r.get("door")
          and "学习综合体" in r["name"]]
    if lc:
        goal_door = min(lc, key=lambda r: (r["threshold"][0] - gate[0]) ** 2
                        + (r["threshold"][2] - gate[1]) ** 2)
        goal = (goal_door["threshold"][0], goal_door["threshold"][2])
        goal_name = goal_door["name"]
    else:
        goal = (1214, 803)
        goal_name = "south corridor door (fallback)"
    found, length, visited, why = bfs(world, gate, goal,
                                      box_pad=150, max_cells=200000)
    report["east_gate_bfs"] = {"from": list(gate), "to": list(goal),
                               "goal_door": goal_name,
                               "found": found, "path_len": length,
                               "visited": visited, "why": why}
    print("east gate BFS:", json.dumps(report["east_gate_bfs"], ensure_ascii=False), flush=True)


    # --- 5. courts
    courts = []
    for area in BUILD["courts"]:
        for c in area["courts"]:
            if "error" in c:
                courts.append({"area": area["area"], "error": c["error"]})
                continue
            x0, z0, x1, z1 = c["rect"]
            sy = c["surface_y"]
            green = white = 0
            for x in range(x0, x1 + 1):
                for z in range(z0, z1 + 1):
                    t = world.top_solid(x, z, y_top=64, y_bottom=-64)
                    if t and t[0] == sy:
                        if t[1] == "minecraft:green_concrete":
                            green += 1
                        elif t[1] == "minecraft:white_concrete":
                            white += 1
            # hoops: fence posts + backboards + rims at both ends
            (cx, cz) = c["centre"][0], c["centre"][2]
            hoops = 0
            for end in (x0, x1):
                if world.get_block(end, sy + 3, cz) == "minecraft:white_concrete":
                    hoops += 1
                if world.get_block(end - (1 if end == x0 else -1), sy + 1, cz) == "minecraft:dark_oak_fence":
                    hoops += 1
            courts.append({"area": area["area"], "rect": c["rect"],
                           "surface_y": sy, "green_cells": green,
                           "white_line_cells": white, "hoop_parts": hoops})
    report["courts"] = courts
    print("courts:", json.dumps(courts, ensure_ascii=False), flush=True)

    # --- 6. new buildings
    nb = []
    for rec in BUILD["missing_buildings"]:
        if rec.get("status") == "already present in world":
            nb.append({"name": rec["name"], "status": "already present"})
            continue
        if "error" in rec:
            nb.append({"name": rec["name"], "error": rec["error"]})
            continue
        x0, z0, x1, z1 = rec["rect"]
        cx, cz = (x0 + x1) // 2, (z0 + z1) // 2
        top = world.top_solid(cx, cz, y_top=64, y_bottom=-64)
        (dx, dy, dz) = rec["door"]
        nb.append({"name": rec["name"], "rect": rec["rect"],
                   "centre_top": list(top) if top else None,
                   "roof_y_expected": rec["roof_y"],
                   "door_blocks_ok": door_blocks_ok(world, (dx, dy, dz), "south")})
    report["missing_buildings"] = nb
    print("new buildings:", json.dumps(nb, ensure_ascii=False), flush=True)

    json.dump(report, open(WORK / "v3-verify-report.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("wrote v3-verify-report.json", flush=True)


if __name__ == "__main__":
    main()
