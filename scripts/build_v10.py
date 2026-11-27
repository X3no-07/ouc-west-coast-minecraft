#!/usr/bin/env python3
"""v10: south gate + learning-complex west facade, on top of v9.

User instruction (2026-11-27, two photos): add the main gate and redo
the learning complex facade to match the photos; colours must be right,
and so must the ground.

Gate (south, on the campus axis): the real south gate (OSM node
12977523915, barrier=gate, name=南门) is at local (1203, 1238), about
243 cells south of the map edge -- outside this world. The gate is
built at the end of the in-map service road (road 26, x1221-1224,
z977-998) where it meets the southern perimeter road (road 16), wall
centre x~1222, z987-988. The internal road therefore TERMINATES at
the gate by design (it does not pass through the solid sign wall);
verify_v10.py checks that terminus explicitly instead of treating
the wall as a road gap.
  - sign wall: x1197-1248, z987-988, y-49..-41 (52 wide, 2 thick,
    9 high), smooth_quartz, top row quartz_block.
  - name: red_concrete 7x7 pixel font, 6 chars, 47 wide (x1199-1245),
    7 high (y-48..-42), on BOTH faces (south z989, north z986,
    north face mirrored so it reads correctly from the north).
  - flower bed: z990-992, x1200-1245, dirt + poppy/red_tulip/
    short_grass, in front (south) of the wall.
  - wings: stepped diagonals curving south-out from the wall ends,
    8 high (y-49..-42), white_concrete with light_gray_concrete
    vertical ribs every 3rd row. West wing shifted 2 east so its
    tail clears road 16's centreline.
  - banner: red_concrete x1203-1242, y-42..-41, z980 (no letters --
    text cannot be done on a banner), on white_concrete posts at
    x1202 and x1243.
  - forecourt: x1190-1255, z976-995 levelled to y-49 and paved
    gray_concrete; service road 26 re-laid through it (sidewalks
    x1221/x1227 light grey, carriageway x1222-1226 grey, centre dash
    x1224 white 2-on/2-off); white edge line + glass-pane railing
    along the north edge z976 with a gap at the road.
  - lawn south of the gate stays green (outside the forecourt rect
    the ground is untouched; the flower bed is the only planting).

Learning complex west facade (photo 1 is the WEST face: the I <3 OUC
plaza is on the west side; east face, east entrance and its 10 steps
are untouched):
  - podium face x=1152, y-48..-36, z662-734: central bay z688-708
    full-height blue_stained_glass; sides get horizontal strip
    windows (2 blue glass + 2 smooth_quartz, repeating), quartz cap.
  - tower face x=1157, y-35..-12, z662-734: wings get a
    smooth_quartz field, quartz_pillar fins every 3rd column and
    blue_stained_glass strip windows; quartz crown y-15..-12.
  - central portal, three nested quartz frames stepping back:
    outer x=1157 opening z685-711 y-35..-16, middle x=1158 opening
    z687-709 y-35..-18, inner x=1159 opening z689-707 y-35..-20,
    blue_stained_glass bay at x=1160 (z689-707, y-35..-19). The
    shaft (x1158-1160, z685-711, y-35..-16) is cleared of the
    tower's polished_andesite floor slabs first.
  - terrace in front of the portal (x1153-1156, z685-711, y=-36)
    repaved smooth_quartz.
  - outline and height unchanged; north/south faces and roof
    untouched; the z655-661 / z735-742 ends are untouched (the
    tower face does not extend there).

West plaza: rect [1110, 660, 1150, 740] repaved light_gray_concrete
with smooth_stone joints every 10 cells (large slabs, as in the
photo); cells within 2 of a road centreline (roads 14/36 clip the
south edge) and cells with a structure/tree above are skipped; the
leisure-area blue OUC letters (x1065-1078, z473) are nowhere near
this rect and are untouched.

Base: staging-v10/OUC-West-Coast-v9 (copy of v9). Renames the world
to OUC-West-Coast-v10 and level.dat to 中国海洋大学西海岸校区v10.
Writes v10-build-report.json.
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
from build_v4 import top_y, VEGETATION, AIR  # noqa: E402
from build_v9 import PASS_TOP  # noqa: E402

WORK = HERE
WORLD_DIR = Path(os.environ.get(
    "V10_WORLD", str(WORK / "staging-v10" / "OUC-West-Coast-v9")))
V3 = json.load(open(WORK / "v3-build-data.json", encoding="utf-8"))

# --- 7x7 pixel font (validated by eye in /tmp/v10-probe/font_test.png)
FONT = {
    "中": ["...#...", "..###..", "..#.#..", "..###..",
           "...#...", "...#...", "...#..."],
    "国": [".#####.", ".#...#.", ".#.#.#.", ".#...#.",
           ".#####.", "...#...", "...#..."],
    "海": ["#.#####", "..#...#", "#.#.#.#", "..#####",
           "#.#...#", "..#...#", "..#####"],
    "洋": ["#.#...#", "..#####", "#...#..", "..#####",
           "#...#..", "..#####", "....#.."],
    "大": ["...#...", "...#...", "..###..", "...#...",
           "..#.#..", ".#...#.", "#.....#"],
    "学": [".#.#.#.", "..###..", "...#...", "..#.#..",
           "...#...", "...#...", ".#####."],
}
CHARS = ["中", "国", "海", "洋", "大", "学"]

Q = "minecraft:smooth_quartz"
QB = "minecraft:quartz_block"
QP = "minecraft:quartz_pillar"
BLUE = "minecraft:blue_stained_glass"
RED = "minecraft:red_concrete"
WHITE = "minecraft:white_concrete"
LGREY = "minecraft:light_gray_concrete"
GREY = "minecraft:gray_concrete"
LGREY_RIB = "minecraft:light_gray_concrete"
PANE = "minecraft:white_stained_glass_pane"

# gate geometry
GATE_WALL = (1197, 1248, 987, 988, -49, -41)  # x0,x1,z0,z1,y0,y1
GATE_TEXT_X0 = 1199          # 47 wide: 6*7 + 5*1
GATE_TEXT_Y_TOP = -48        # 7 high: y-48..-42
GATE_PLAZA = (1190, 976, 1255, 995)  # x0,z0,x1,z1
FLOWER_BED = (1200, 990, 1245, 992)  # x0,z0,x1,z1
BANNER_Z = 980
BANNER_X = (1202, 1243)      # posts
LEARN_PODIUM_X = 1152
LEARN_TOWER_X = 1157
LEARN_Z = (662, 734)
LEARN_PODIUM_Y = (-48, -36)
LEARN_TOWER_Y = (-35, -12)
PLAZA_RECT = (1110, 660, 1150, 740)

GROUND_PAVEABLE = {
    "minecraft:grass_block", "minecraft:dirt", "minecraft:coarse_dirt",
    "minecraft:light_gray_concrete", "minecraft:gray_concrete",
    "minecraft:white_concrete", "minecraft:stone_bricks",
    "minecraft:smooth_stone", "minecraft:sand", "minecraft:gravel",
    "minecraft:podzol", "minecraft:stone", "minecraft:cobblestone",
    "minecraft:mossy_cobblestone", "minecraft:grass_path",
    "minecraft:farmland", "minecraft:smooth_sandstone",
    "minecraft:cracked_stone_bricks", "minecraft:black_concrete",
    "minecraft:cyan_terracotta", "minecraft:gray_concrete_powder",
}


def fix_level_dat(world_dir, report):
    p = Path(world_dir) / "level.dat"
    bak = p.with_name("level.dat.bak-v9")
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
            v = "中国海洋大学西海岸校区v10"
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
    stats = Counter()

    def setb(x, y, z, block, key):
        cur = world.get_block(x, y, z)
        if cur != block:
            world.set_block(x, y, z, block)
            stats[key] += 1

    def gtop(x, z):
        """Top solid block, skipping air and small plants/flowers."""
        for y in range(64, -65, -1):
            b = world.get_block(x, y, z)
            if b is None or b in AIR or b in PASS_TOP:
                continue
            return (y, b)
        return None

    # ---------- 1. gate forecourt: level to y=-49, pave grey ---------
    px0, pz0, px1, pz1 = GATE_PLAZA
    for x in range(px0, px1 + 1):
        for z in range(pz0, pz1 + 1):
            res = gtop(x, z)
            if res is None:
                stats["plaza_no_ground"] += 1
                continue
            t, cur = res
            if t > -49:
                stats["plaza_skipped_tall"] += 1
                continue
            if t < -50:
                stats["plaza_skipped_hole"] += 1
                continue
            if cur not in GROUND_PAVEABLE:
                stats[f"plaza_skipped_{cur.split(':')[1]}"] += 1
                continue
            if t == -50:
                # dip: fill at -49 (cell above is air by definition)
                world.set_block(x, -49, z, GREY)
                stats["plaza_filled_dip"] += 1
            else:
                setb(x, -49, z, GREY, "plaza_paved_grey")
            for y in range(-48, -45):
                if world.get_block(x, y, z) in PASS_TOP:
                    world.set_block(x, y, z, "minecraft:air")
                    stats["plaza_veg_cleared"] += 1

    # ---------- 2. service road 26 re-laid through the forecourt -----
    # cross-section (probed): sidewalks x1221/x1227 light grey,
    # carriageway x1222-1226 grey, centre dash x1224 white 2-on/2-off
    # (white when (z-977)%4 < 2).
    for z in range(976, 987):
        for x, b in ((1221, LGREY), (1227, LGREY),
                     (1222, GREY), (1223, GREY),
                     (1225, GREY), (1226, GREY)):
            setb(x, -49, z, b, "road26_relaid")
        dash = WHITE if (z - 977) % 4 < 2 else GREY
        setb(1224, -49, z, dash, "road26_relaid")

    # ---------- 3. white edge line + railing, north edge z976 ---------
    for x in range(px0, px1 + 1):
        if 1221 <= x <= 1227:
            continue  # road gap
        setb(x, -49, 976, WHITE, "edge_line")
        if x % 5 == 0:
            setb(x, -48, 976, WHITE, "railing_post")
        else:
            setb(x, -48, 976, PANE, "railing_pane")

    # ---------- 4. sign wall + red characters, both faces -------------
    wx0, wx1, wz0, wz1, wy0, wy1 = GATE_WALL
    for x in range(wx0, wx1 + 1):
        for z in (wz0, wz1):
            for y in range(wy0, wy1 + 1):
                setb(x, y, z, QB if y == wy1 else Q, "wall_quartz")
    # characters: south face z=989 reads left-to-right (west->east);
    # north face z=986 is mirrored (order reversed, glyphs flipped)
    # so it reads correctly from the north side too.
    for i, ch in enumerate(CHARS):
        for r in range(7):
            for c in range(7):
                if FONT[ch][r][c] != "#":
                    continue
                y = GATE_TEXT_Y_TOP + r
                xs = GATE_TEXT_X0 + i * 8 + c
                setb(xs, y, 989, RED, "chars_south")
                xn = 1245 - (i * 8 + c)
                setb(xn, y, 986, RED, "chars_north")

    # ---------- 5. flower bed (south of the wall) ----------------------
    fx0, fz0, fx1, fz1 = FLOWER_BED
    for x in range(fx0, fx1 + 1):
        for z in range(fz0, fz1 + 1):
            setb(x, -49, z, "minecraft:dirt", "flower_bed_dirt")
            k = (x * 7 + z * 3) % 5
            if k < 3:
                plant = ("minecraft:poppy", "minecraft:red_tulip",
                         "minecraft:short_grass")[(x + z) % 3]
                setb(x, -48, z, plant, "flower_bed_plant")
            else:
                cur = world.get_block(x, -48, z)
                if cur in PASS_TOP:
                    world.set_block(x, -48, z, "minecraft:air")
                    stats["flower_bed_cleared"] += 1

    # ---------- 6. wings (stepped diagonals, south of the wall) --------
    # west wing shifted 2 east so its tail clears road 16's centreline
    # (road 16 centre at z991-995 is x1189-1207).
    wings = [
        # (x0, x1, z0, z1) per segment
        (1196, 1197, 989, 990), (1194, 1195, 991, 992),
        (1192, 1193, 993, 995),   # west
        (1248, 1249, 989, 990), (1250, 1251, 991, 992),
        (1252, 1253, 993, 995),   # east
    ]
    for (x0, x1, z0, z1) in wings:
        for x in range(x0, x1 + 1):
            for z in range(z0, z1 + 1):
                rib = (z % 3 == 0)
                for y in range(-49, -41):
                    setb(x, y, z, LGREY_RIB if rib else WHITE,
                         "wing_rib" if rib else "wing_white")

    # ---------- 7. banner across the road, north of the wall -----------
    for px in BANNER_X:
        for y in range(-49, -40):
            setb(px, y, BANNER_Z, WHITE, "banner_post")
    for x in range(BANNER_X[0] + 1, BANNER_X[1]):
        for y in (-42, -41):
            setb(x, y, BANNER_Z, RED, "banner_red")

    # ---------- 8. learning podium west face ---------------------------
    # central bay full-height blue glass; sides: 2 blue + 2 quartz
    # strip windows; quartz cap row.
    for z in range(LEARN_Z[0], LEARN_Z[1] + 1):
        bay = 688 <= z <= 708
        for y in range(LEARN_PODIUM_Y[0], LEARN_PODIUM_Y[1] + 1):
            if bay:
                setb(LEARN_PODIUM_X, y, z, BLUE, "podium_bay_blue")
            elif y == -36:
                setb(LEARN_PODIUM_X, y, z, Q, "podium_cap")
            elif (y + 48) % 4 < 2:
                setb(LEARN_PODIUM_X, y, z, BLUE, "podium_strip_blue")
            else:
                setb(LEARN_PODIUM_X, y, z, Q, "podium_quartz")

    # ---------- 9. learning tower west face ---------------------------
    # clear the portal shaft first (floor slabs inside the tower)
    for x in range(1158, 1161):
        for z in range(685, 712):
            for y in range(-35, -15):
                cur = world.get_block(x, y, z)
                if cur not in ("minecraft:air", "minecraft:cave_air"):
                    world.set_block(x, y, z, "minecraft:air")
                    stats["portal_shaft_cleared"] += 1
    # tower-face opening (outer frame's void)
    for z in range(685, 712):
        for y in range(-35, -15):
            cur = world.get_block(LEARN_TOWER_X, y, z)
            if cur not in ("minecraft:air", "minecraft:cave_air"):
                world.set_block(LEARN_TOWER_X, y, z, "minecraft:air")
                stats["portal_face_cleared"] += 1
    # wings: quartz field, pillar fins every 3rd column, blue strips
    for z in list(range(662, 683)) + list(range(714, 735)):
        fin = ((z - 662) % 3 == 0) if z < 683 else ((z - 714) % 3 == 0)
        for y in range(-35, -11):
            if y >= -15:
                setb(LEARN_TOWER_X, y, z, Q, "tower_crown")
            elif fin and y <= -16:
                setb(LEARN_TOWER_X, y, z, QP, "tower_fin")
            elif y <= -34:
                setb(LEARN_TOWER_X, y, z, Q, "tower_base")
            elif (y + 33) % 4 < 2:
                setb(LEARN_TOWER_X, y, z, BLUE, "tower_strip_blue")
            else:
                setb(LEARN_TOWER_X, y, z, Q, "tower_quartz")
    # portal frames (nested, stepping back 1 cell each)
    # outer frame x=1157: jambs + lintel (opening already cleared)
    for z in list(range(683, 685)) + list(range(712, 714)):
        for y in range(-35, -11):
            setb(LEARN_TOWER_X, y, z, Q, "portal_outer_jamb")
    for z in range(685, 712):
        for y in range(-15, -11):
            setb(LEARN_TOWER_X, y, z, Q, "portal_outer_lintel")
    # middle frame x=1158: jambs z685-686/710-711 y-35..-16,
    # lintel z687-709 y-17..-16
    for z in list(range(685, 687)) + list(range(710, 712)):
        for y in range(-35, -15):
            setb(1158, y, z, Q, "portal_mid_jamb")
    for z in range(687, 710):
        for y in (-17, -16):
            setb(1158, y, z, Q, "portal_mid_lintel")
    # inner frame x=1159: jambs z687-688/708-709 y-35..-18,
    # lintel z689-707 y-19..-18
    for z in list(range(687, 689)) + list(range(708, 710)):
        for y in range(-35, -17):
            setb(1159, y, z, Q, "portal_inner_jamb")
    for z in range(689, 708):
        for y in (-19, -18):
            setb(1159, y, z, Q, "portal_inner_lintel")
    # glass bay x=1160
    for z in range(689, 708):
        for y in range(-35, -18):
            setb(1160, y, z, BLUE, "portal_glass_bay")

    # ---------- 10. terrace in front of the portal ---------------------
    for x in range(1153, 1157):
        for z in range(685, 712):
            cur = world.get_block(x, -36, z)
            if cur != Q:
                if cur in ("minecraft:air", "minecraft:cave_air"):
                    stats["terrace_floating_warn"] += 1
                world.set_block(x, -36, z, Q)
                stats["terrace_quartz"] += 1
            for y in range(-35, -29):
                cur2 = world.get_block(x, y, z)
                if cur2 not in ("minecraft:air", "minecraft:cave_air"):
                    world.set_block(x, y, z, "minecraft:air")
                    stats["terrace_cleared_above"] += 1

    # ---------- 11. west plaza repave (large light-grey slabs) ---------
    # cells within 2 of a road centreline are skipped (roads 14/36
    # clip the plaza's south edge).
    rx0, rz0, rx1, rz1 = PLAZA_RECT
    near_road = set()
    for r in V3["roads"]:
        pts = r["pts"]
        xs = [p[0] for p in pts]
        zs = [p[1] for p in pts]
        if max(xs) < rx0 - 5 or min(xs) > rx1 + 5 or \
                max(zs) < rz0 - 5 or min(zs) > rz1 + 5:
            continue
        for (x1, z1), (x2, z2) in zip(pts, pts[1:]):
            steps = max(abs(x2 - x1), abs(z2 - z1), 1)
            for s in range(steps + 1):
                cx = round(x1 + (x2 - x1) * s / steps)
                cz = round(z1 + (z2 - z1) * s / steps)
                for dx in (-2, -1, 0, 1, 2):
                    for dz in (-2, -1, 0, 1, 2):
                        near_road.add((cx + dx, cz + dz))
    for x in range(rx0, rx1 + 1):
        for z in range(rz0, rz1 + 1):
            if (x, z) in near_road:
                stats["west_plaza_skipped_road"] += 1
                continue
            res = gtop(x, z)
            if res is None:
                stats["west_plaza_no_ground"] += 1
                continue
            t, cur = res
            if t > -49:
                stats["west_plaza_skipped_tall"] += 1
                continue
            if t < -50:
                stats["west_plaza_skipped_hole"] += 1
                continue
            if cur not in GROUND_PAVEABLE and cur != LGREY and \
                    cur != "minecraft:smooth_stone":
                stats[f"west_plaza_skipped_{cur.split(':')[1]}"] += 1
                continue
            joint = (x % 10 == 0) or (z % 10 == 0)
            want = "minecraft:smooth_stone" if joint else LGREY
            if t == -50:
                world.set_block(x, -49, z, want)
                stats["west_plaza_filled_dip"] += 1
            else:
                setb(x, -49, z, want, "west_plaza_slab")
            for y in range(-48, -45):
                if world.get_block(x, y, z) in PASS_TOP:
                    world.set_block(x, y, z, "minecraft:air")
                    stats["west_plaza_veg_cleared"] += 1

    changed = world.flush()
    report = {
        "world": str(WORLD_DIR), "base": "v9",
        "note": "v10: south gate (sign wall + red 7x7 name + wings + "
                "flower bed + banner + forecourt) and learning-complex "
                "west facade (quartz + blue glass + nested portal) and "
                "west plaza repaved in large light-grey slabs. Real "
                "south gate is ~243 cells south of the map edge; gate "
                "built at the end of in-map service road 26.",
        "gate": {
            "wall": list(GATE_WALL), "wall_material": Q,
            "wall_top": QB, "text": {"chars": CHARS, "x0": GATE_TEXT_X0,
                                     "y_top": GATE_TEXT_Y_TOP,
                                     "faces": {"south": 989, "north": 986},
                                     "material": RED},
            "flower_bed": list(FLOWER_BED), "plaza": list(GATE_PLAZA),
            "banner": {"z": BANNER_Z, "posts": list(BANNER_X),
                       "material": RED, "note": "no letters on banner"},
            "road26_terminus": "road 26 centreline ends at the gate "
                               "plaza (z986); wall/flower bed south "
                               "of it are the gate, not a road gap",
        },
        "learning_west": {
            "podium": {"x": LEARN_PODIUM_X, "y": list(LEARN_PODIUM_Y),
                       "z": list(LEARN_Z), "bay": [688, 708],
                       "bay_material": BLUE,
                       "strip": "2 blue glass + 2 quartz"},
            "tower": {"x": LEARN_TOWER_X, "y": list(LEARN_TOWER_Y),
                      "z": list(LEARN_Z), "fin": QP,
                      "strip": BLUE, "crown": Q},
            "portal": {"frames": ["x1157 z685-711 y-35..-16",
                                  "x1158 z687-709 y-35..-18",
                                  "x1159 z689-707 y-35..-20"],
                       "glass_bay": {"x": 1160, "z": [689, 707],
                                     "y": [-35, -19], "material": BLUE}},
            "terrace": {"x": [1153, 1156], "z": [685, 711], "y": -36,
                        "material": Q},
            "untouched": "east face, east entrance + 10 steps, "
                         "north/south faces, roof, z655-661/z735-742 ends",
        },
        "west_plaza": {"rect": list(PLAZA_RECT),
                       "material": LGREY,
                       "joint": "minecraft:smooth_stone every 10 cells"},
        "totals": dict(stats),
        "cells_changed": changed,
        "elapsed_s": round(time.time() - t0, 1),
    }
    rp = WORLD_DIR / "Readme.txt"
    txt = rp.read_text(encoding="utf-8-sig")
    txt = txt.replace("OUC-West-Coast-v9", "OUC-West-Coast-v10")
    txt = txt.replace("西海岸校区v9", "西海岸校区v10")
    rp.write_text(txt, encoding="utf-8-sig")
    fix_level_dat(WORLD_DIR, report)
    new_dir = WORK / "staging-v10" / "OUC-West-Coast-v10"
    if new_dir.exists():
        shutil.rmtree(new_dir)
    shutil.move(str(WORLD_DIR), str(new_dir))
    report["world"] = str(new_dir)
    json.dump(report, open(WORK / "v10-build-report.json", "w",
                           encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nV10 BUILD DONE: {changed} cells changed in "
          f"{report['elapsed_s']}s; totals: {dict(stats)}")
    print("world now:", new_dir)


if __name__ == "__main__":
    main()
