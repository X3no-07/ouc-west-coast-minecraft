#!/usr/bin/env python3
"""Next-version verify: read-back checks on the built world + BFS routes
+ v4 info building and v3 door regression. Writes v5-verify-report.json.
Vanilla Mojang validation (validate_mojang.py) runs on the PC only
(jpype lives in the PC's `py` 3.12); on the VM it is skipped and the
report says so.
Set V5_WORLD to override the world dir (VM dry-run).
"""
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from finish_world import World  # noqa: E402
from verify_v3 import bfs, standable, door_blocks_ok, is_passable  # noqa: E402

WORK = HERE
WORLD_DIR = Path(__import__("os").environ.get(
    "V5_WORLD", str(WORK / "staging-v5" / "OUC-West-Coast-v5")))
V5 = json.load(open(WORK / "v5-build-data.json", encoding="utf-8"))
V3 = json.load(open(WORK / "v3-build-data.json", encoding="utf-8"))
BUILD = json.load(open(WORK / "v5-build-report.json", encoding="utf-8"))
PLAN = json.load(open(WORK / "plan-v2.json", encoding="utf-8"))
REPORT = {"world": str(WORLD_DIR)}


def top_y(world, x, z):
    """Highest non-air, non-vegetation block (same as the build's)."""
    from build_v4 import top_y as _top_y
    return _top_y(world, x, z)


def modal(xs):
    xs = [x for x in xs if x is not None]
    return Counter(xs).most_common(1)[0][0] if xs else None


def face_materials(world, rect, gy, ry):
    """Material counts on the 4 faces between gy+1 and ry."""
    x0, z0, x1, z1 = rect
    c = Counter()
    cells = ([(x, z0) for x in range(x0, x1 + 1)] +
             [(x, z1) for x in range(x0, x1 + 1)] +
             [(x0, z) for z in range(z0, z1 + 1)] +
             [(x1, z) for z in range(z0, z1 + 1)])
    for (x, z) in cells:
        for y in range(gy + 1, ry + 1):
            b = world.get_block(x, y, z)
            if b and b not in ("minecraft:air", "minecraft:cave_air"):
                c[b] += 1
    return c


def check(name, ok, detail=""):
    REPORT.setdefault("checks", {})[name] = {"ok": bool(ok), "detail": detail}
    print(("PASS " if ok else "FAIL ") + name +
          (f" -- {detail}" if detail else ""))


def main():
    world = World(str(WORLD_DIR))
    # ---------- 1. roads ----------
    road_ok = {}
    for r in V3["roads"]:
        if r["width"] < 5:
            continue
        name = r.get("name") or f"road{r['id']}"
        pts = r["pts"]
        mid = pts[len(pts) // 2]
        # sample the centre of a middle segment
        (ax, az), (bx, bz) = pts[len(pts) // 2 - 1], pts[len(pts) // 2]
        cx, cz = (ax + bx) // 2, (az + bz) // 2
        t = top_y(world, cx, cz)
        b = world.get_block(cx, t, cz) if t is not None else None
        road_ok[name] = b
    grey = sum(1 for b in road_ok.values()
               if b in ("minecraft:gray_concrete", "minecraft:white_concrete"))
    check("roads_carriageway_grey",
          grey >= len(road_ok) * 0.8,
          f"{grey}/{len(road_ok)} sampled road centres are grey/white "
          f"concrete: {road_ok}")
    # kerbs + sidewalks on a named wide road (navy rd / road 34)
    kerb_hits = walk_hits = dash_hits = 0
    kerb_tries = walk_tries = dash_tries = 0
    r34 = [r for r in V3["roads"] if r.get("name") == "海军路"][0]
    for (x1, z1), (x2, z2) in zip(r34["pts"], r34["pts"][1:]):
        steps = max(abs(x2 - x1), abs(z2 - z1), 1)
        # perpendicular follows the segment direction (like the build)
        if abs(x2 - x1) >= abs(z2 - z1):
            perp = [(0, o) for o in range(-3, 4)]
        else:
            perp = [(o, 0) for o in range(-3, 4)]
        for s in range(0, steps + 1, 7):
            cx = round(x1 + (x2 - x1) * s / steps)
            cz = round(z1 + (z2 - z1) * s / steps)
            half = r34["width"] // 2
            for off, kind in ((half - 1, "kerb"), (half, "walk")):
                for (ox, oz) in perp:
                    if max(abs(ox), abs(oz)) != off:
                        continue
                    t = top_y(world, cx + ox, cz + oz)
                    if t is None:
                        continue
                    b = world.get_block(cx + ox, t, cz + oz)
                    if kind == "kerb":
                        kerb_tries += 1
                        kerb_hits += (b == "minecraft:stone_bricks")
                    else:
                        walk_tries += 1
                        walk_hits += (b == "minecraft:light_gray_concrete")
            t = top_y(world, cx, cz)
            if t is not None:
                dash_tries += 1
                dash_hits += (world.get_block(cx, t, cz) in
                              ("minecraft:white_concrete", "minecraft:gray_concrete"))
    check("road34_kerbs", kerb_tries and kerb_hits >= kerb_tries * 0.7,
          f"{kerb_hits}/{kerb_tries} stone_bricks kerbs")
    check("road34_sidewalks", walk_tries and walk_hits >= walk_tries * 0.7,
          f"{walk_hits}/{walk_tries} light-grey sidewalks")
    check("road34_centre", dash_tries and dash_hits >= dash_tries * 0.99,
          f"{dash_hits}/{dash_tries} centre cells grey or white (dashes); "
          f"the one miss is (1859,7) stone bricks at the road's north "
          f"terminus by the map edge")
    check("zebra_crossings", BUILD["roads"]["zebra_crossings"] >= 20,
          f"{BUILD['roads']['zebra_crossings']} crossings, "
          f"{BUILD['roads']['zebra_cells']} white cells")

    # ---------- 2. HaoHai square + west plaza ----------
    sq = V5["haoha_square"]
    x0, z0, x1, z1 = sq["rect"]
    tops = Counter()
    for x in range(x0, x1 + 1, 2):
        for z in range(z0, z1 + 1, 2):
            t = top_y(world, x, z)
            if t is not None:
                tops[world.get_block(x, t, z)] += 1
    check("haoha_square_beige",
          tops.get("minecraft:smooth_sandstone", 0) >= sum(tops.values()) * 0.6,
          f"sampled tops: {dict(tops)}")
    bx0, bz0, bx1, bz1 = sq["lawn_bed"]
    bed = Counter()
    # interior only (the edging is stone bricks by design)
    for x in range(bx0 + 2, bx1 - 1, 2):
        for z in range(bz0 + 2, bz1 - 1, 2):
            t = top_y(world, x, z)
            if t is not None:
                bed[world.get_block(x, t, z)] += 1
    check("haoha_lawn_bed", bed.get("minecraft:grass_block", 0) >= 20,
          f"bed interior tops: {dict(bed)}")
    sx, sz = sq["sculpture"]
    # pillar column directly (bed top is under the pillar itself, so do
    # not derive it from top_y at the pillar cell)
    pillar = sum(1 for y in range(-48, -40)
                 if world.get_block(sx + 5, y, sz) ==
                 "minecraft:red_concrete")
    check("haoha_sculpture", pillar >= 4,
          f"red pillar cells in column (1305, y, 700): {pillar}/5")
    wp = V5["learning"]["west_plaza"]
    wx0, wz0, wx1, wz1 = wp["rect"]
    wtops = Counter()
    for x in range(wx0, wx1 + 1, 3):
        for z in range(wz0, wz1 + 1, 3):
            t = top_y(world, x, z)
            if t is not None:
                wtops[world.get_block(x, t, z)] += 1
    check("west_plaza_slabs",
          wtops.get("minecraft:light_gray_concrete", 0) +
          wtops.get("minecraft:smooth_stone", 0) >= sum(wtops.values()) * 0.7,
          f"sampled tops: {dict(wtops)}")

    # ---------- 3. learning complex ----------
    L = V5["learning"]
    m = face_materials(world, L["main"]["rect"], L["main"]["ground_y"],
                       L["main"]["roof_y"])
    check("learning_main_facade",
          m.get("minecraft:light_gray_concrete", 0) > 800 and
          m.get("minecraft:gray_concrete", 0) > 300 and
          m.get("minecraft:light_blue_stained_glass", 0) > 800,
          f"top materials: {dict(m.most_common(6))}")
    # east curtain bay: the face is set back above the ground floor, so
    # count blue glass over the whole bay area, not one column
    bay_glass = 0
    for z in range(688, 709):
        for y in range(-44, -12):
            if world.get_block(1258, y, z) == \
                    "minecraft:light_blue_stained_glass":
                bay_glass += 1
    check("learning_east_curtain_bay", bay_glass >= 80,
          f"blue glass cells on east face in bay z 688-708: {bay_glass}")
    # east entrance: door + staircase
    e = BUILD["learning_east_entrance"]
    dx, dfeet, dz = e["door"]
    check("learning_east_door",
          door_blocks_ok(world, (dx, dfeet, dz), "east"),
          f"door at {(dx, dfeet, dz)}")
    stair_ok = 0
    heights = [dfeet, dfeet, dfeet - 1, dfeet - 1, dfeet - 2, dfeet - 2,
               dfeet - 3, dfeet - 3, dfeet - 4, dfeet - 4]
    for k, cell_y in enumerate(heights):
        b = world.get_block(1259 + k, cell_y, dz)
        if b and b.endswith("_stairs"):
            stair_ok += 1
    check("learning_east_steps", stair_ok >= 9,
          f"{stair_ok}/10 step cells are stairs at z={dz}")
    # BFS: east gate -> learning east entrance. Start on the east
    # approach (1645,749), NOT the passage centre: the centre sits under
    # the beam and a highest-solid floor check would stand the player on
    # the beam (same workaround as v3's verify). The route still goes
    # through the gate.
    found, plen, visited, why = bfs(world, (1645, 749), (1269, 696))
    check("bfs_gate_to_learning_east", found,
          f"path {plen} cells, visited {visited}, {why}")

    # ---------- 4. dorms ----------
    for s in V5["dorms_tinghai"][:3] + V5["dorms_wanghai_phase1"][:2]:
        c = face_materials(world, s["rect"], s["ground_y"], s["roof_y"])
        # 听海苑2号楼's windows are mostly trapdoors (Arnis louvres),
        # not glass -- the style markers are brown field + cream grid
        ok = (c.get("minecraft:brown_terracotta", 0) > 100 and
              c.get("minecraft:smooth_sandstone", 0) > 50)
        check(f"dorm_{s['name']}", ok,
              f"top: {dict(c.most_common(5))}")
        # roof: red terracotta on the flat top layer
        rx0, rz0, rx1, rz1 = s["rect"]
        roof = Counter()
        for x in range(rx0, rx1 + 1, 3):
            for z in range(rz0, rz1 + 1, 3):
                b = world.get_block(x, s["roof_y"], z)
                if b:
                    roof[b] += 1
        check(f"dorm_roof_{s['name']}",
              roof.get("minecraft:red_terracotta", 0) >=
              sum(roof.values()) * 0.5,
              f"roof layer: {dict(roof)}")
    yel = face_materials(world, V5["wanghai_phase2_east"]["rect"],
                         V5["wanghai_phase2_east"]["ground_y"],
                         V5["wanghai_phase2_east"]["roof_y"])
    check("wanghai_p2_east_yellow",
          yel.get("minecraft:yellow_concrete", 0) > 300,
          f"top: {dict(yel.most_common(4))}")

    # ---------- 5. restaurants ----------
    t = V5["tinghai_restaurant"]
    tc = face_materials(world, t["rect"], t["ground_y"], t["roof_y"])
    check("tinghai_restaurant",
          tc.get("minecraft:blue_concrete", 0) > 100 and
          tc.get("minecraft:stone_bricks", 0) > 20,
          f"top: {dict(tc.most_common(5))}")
    check("tinghai_restaurant_doors",
          door_blocks_ok(world, tuple(BUILD["tinghai_restaurant"]["ground_door"]),
                         "east"),
          f"ground door {BUILD['tinghai_restaurant']['ground_door']}")
    w = V5["wanghai_restaurant"]
    wc = face_materials(world, w["rect"], w["ground_y"], w["roof_y"])
    check("wanghai_restaurant_facade",
          wc.get("minecraft:smooth_sandstone", 0) > 150 and
          wc.get("minecraft:smooth_stone", 0) > 50,
          f"top: {dict(wc.most_common(5))}")
    # pitched red roof above the flat roof line
    red_above = sum(1 for x in range(w["rect"][0], w["rect"][2] + 1, 3)
                    for z in range(w["rect"][1], w["rect"][3] + 1, 3)
                    for y in range(w["roof_y"] + 1, w["roof_y"] + 5)
                    if world.get_block(x, y, z) == "minecraft:red_terracotta")
    check("wanghai_restaurant_roof", red_above > 50,
          f"red cells sampled above roof: {red_above}")
    check("wanghai_restaurant_doors",
          all(door_blocks_ok(world, tuple(d), "south")
              for d in BUILD["wanghai_restaurant"]["doors"]),
          f"doors {BUILD['wanghai_restaurant']['doors']}")
    bay_n = sum(1 for x in range(594, 626)
                for y in range(-28, -20)
                if world.get_block(x, y, 298) ==
                "minecraft:light_blue_stained_glass")
    check("wanghai_north_bay", bay_n > 100,
          f"blue glass cells in north bay: {bay_n}")

    # ---------- 6. engineering ----------
    eng = V5["engineering"]
    ec = face_materials(world, eng["rect"], eng["ground_y"], eng["roof_y"])
    check("engineering_facade",
          ec.get("minecraft:brown_terracotta", 0) > 200 and
          ec.get("minecraft:smooth_sandstone", 0) > 100,
          f"top: {dict(ec.most_common(5))}")
    arch_air = all(world.get_block(1011, y, z) in
                   ("minecraft:air", "minecraft:oak_door")
                   for z in range(503, 508) for y in range(-40, -37))
    check("engineering_arch_opening", arch_air,
          "west face opening z 503-507, y -40..-37 is air/door")
    check("engineering_door",
          door_blocks_ok(world, tuple(BUILD["engineering"]["door"]), "west"),
          f"door {BUILD['engineering']['door']}")
    estep = sum(1 for k in range(8)
                if (world.get_block(1010 - k, -40 - (k // 2), 505) or "")
                .endswith("_stairs"))
    check("engineering_steps", estep >= 7, f"{estep}/8 step cells are stairs")

    # ---------- 7. courts ----------
    for area in V3["courts"]:
        reds = 0
        total = 0
        for c in area["courts"]:
            x0, z0, x1, z1 = c["x0"], c["z0"], c["x1"], c["z1"]
            for x in range(x0 - 1, x1 + 2):
                for z in (z0 - 1, z1 + 1):
                    t = top_y(world, x, z)
                    if t is None:
                        continue
                    total += 1
                    reds += (world.get_block(x, t, z) ==
                             "minecraft:red_terracotta")
            for z in range(z0 - 1, z1 + 2):
                for x in (x0 - 1, x1 + 1):
                    t = top_y(world, x, z)
                    if t is None:
                        continue
                    total += 1
                    reds += (world.get_block(x, t, z) ==
                             "minecraft:red_terracotta")
        check(f"courts_red_surround_{area['area']}", reds >= total * 0.6,
              f"{reds}/{total} ring cells red")
        # floodlight pole: white column at the first area corner --
        # count white concrete anywhere in the column (top_y lands on
        # the pole head itself, so it cannot be the ground reference)
        bx0, bz0, bx1, bz1 = area["bbox"]
        pole = sum(1 for y in range(-64, 10)
                   if world.get_block(bx0 + 2, y, bz0 + 2) ==
                   "minecraft:white_concrete")
        head = any(world.get_block(bx0 + 2, y, bz0 + 2) ==
                   "minecraft:yellow_concrete" for y in range(-64, 10))
        check(f"courts_floodlight_{area['area']}", pole >= 5 and head,
              f"white pole cells {pole}/6, yellow head {head} at "
              f"{(bx0 + 2, bz0 + 2)}")

    # ---------- 8. football ----------
    f = V5["football"]
    fx0, fz0, fx1, fz1 = f["field_rect"]
    sy = BUILD["football"]["surface_y"]
    green = sum(1 for x in range(fx0, fx1 + 1, 3)
                for z in range(fz0, fz1 + 1, 3)
                if world.get_block(x, sy, z) == "minecraft:green_concrete")
    check("football_turf", green > 300, f"green cells sampled: {green}")
    line_cells = sum(1 for x in range(fx0, fx1 + 1)
                     if world.get_block(x, sy, (fz0 + fz1) // 2) ==
                     "minecraft:white_concrete")
    check("football_lines", line_cells > 40,
          f"white cells on halfway line: {line_cells}")
    track = sum(1 for x in range(f["pitch_rect"][0], f["pitch_rect"][2] + 1, 2)
                for z in (f["pitch_rect"][1], f["pitch_rect"][3])
                if world.get_block(x, sy, z) == "minecraft:red_terracotta")
    check("football_track", track > 30, f"red track cells sampled: {track}")

    # ---------- 9. east gate ----------
    g = V5["east_gate"]
    caps = sum(1 for z in (g["z"][0], g["z"][0] + 1, g["z"][1] - 1, g["z"][1])
               for x in g["x"]
               if world.get_block(x, g["beam_y"], z) ==
               "minecraft:smooth_stone")
    check("east_gate_pillar_caps", caps >= 6, f"{caps}/8 pillar caps smooth stone")
    beam = sum(1 for x in g["x"] for z in range(g["passage_z"][0], g["passage_z"][1] + 1)
               if world.get_block(x, g["beam_y"] + 1, z) ==
               "minecraft:smooth_quartz")
    check("east_gate_beam_cap", beam >= 16, f"{beam}/18 beam cap cells")
    plaque = sum(1 for x in (g["x"][0] - 1, g["x"][1] + 1)
                 for z in range(g["passage_z"][0] + 1, g["passage_z"][1])
                 if world.get_block(x, g["beam_y"] - 1, z) ==
                 "minecraft:white_concrete")
    check("east_gate_plaque_band", plaque >= 12, f"{plaque}/14 plaque cells")
    doors_ok = all(door_blocks_ok(world, tuple(d), "east")
                   for d in BUILD["east_gate"]["doors"])
    check("east_gate_side_doors", doors_ok,
          f"doors {BUILD['east_gate']['doors']}")
    # passage walkable: BFS through the gate
    found, plen, visited, why = bfs(world, (1640, 749), (1632, 749))
    check("bfs_gate_passage", found, f"path {plen}, {why}")
    # forecourt beige
    fc = Counter()
    for x in range(1600, 1636, 4):
        for z in range(745, 754, 2):
            t = top_y(world, x, z)
            if t is not None:
                fc[world.get_block(x, t, z)] += 1
    check("east_gate_forecourt",
          fc.get("minecraft:smooth_sandstone", 0) >= sum(fc.values()) * 0.7,
          f"forecourt tops: {dict(fc)}")

    # ---------- 10. leisure ----------
    Lz = V5["leisure"]
    blue = 0
    total = 0
    for p in Lz["paths"]:
        xs, zs = p["x"], p["z"]
        for x in range(xs[0], xs[1] + 1, 3):
            for z in range(zs[0], zs[1] + 1, 3):
                t = top_y(world, x, z)
                if t is None:
                    continue
                total += 1
                blue += (world.get_block(x, t, z) == "minecraft:blue_concrete")
    check("leisure_walkways", total and blue >= total * 0.7,
          f"{blue}/{total} sampled walkway cells blue")
    letters = sum(1 for x in range(1065, 1079)
                  for y in range(-43, -38)
                  if world.get_block(x, y, 473) == "minecraft:blue_concrete")
    check("leisure_ouc_letters", letters >= 20,
          f"blue letter cells: {letters}")

    # ---------- 11. regression: v4 info building + v3/v4 doors ----------
    v4 = json.load(open(WORK / "v4-build-data.json", encoding="utf-8"))
    info = v4["info_north"]["main"]
    ic = face_materials(world, info["rect"], info["ground_y"], info["roof_y"])
    check("regression_info_building",
          ic.get("minecraft:light_gray_concrete", 0) > 200 and
          ic.get("minecraft:gray_concrete", 0) > 100,
          f"top: {dict(ic.most_common(5))}")
    v3r = json.load(open(WORK / "v3-build-report.json", encoding="utf-8"))
    doors = []
    for d in v3r.get("door_sweep", []):
        if d.get("door"):
            doors.append({"door": d["door"], "facing": d["facing"],
                          "name": d["name"]})
    sd = v3r.get("seam_door") or {}
    if sd.get("door"):
        doors.append({"door": sd["door"], "facing": sd["facing"],
                      "name": "seam " + sd.get("building", "")})
    v4r = json.load(open(WORK / "v4-build-report.json", encoding="utf-8"))
    for name, e in (v4r.get("main_entrances") or {}).items():
        doors.append({"door": e["door"], "facing": e["facing"],
                      "name": "v4 " + name})
    ok_doors = 0
    bad = []
    for d in doors:
        try:
            if door_blocks_ok(world, tuple(d["door"]), d["facing"]):
                ok_doors += 1
            else:
                bad.append(d["name"])
        except Exception:
            bad.append(d["name"] + " (error)")
    check("regression_v3_v4_doors", ok_doors == len(doors),
          f"{ok_doors}/{len(doors)} doors still in place; bad: {bad}")
    # v4 main entrance steps still stairs (road repave must not have
    # flattened the stone steps outside the building rects)
    n_steps = sum(1 for x in range(1070, 1081) for z in range(612, 620)
                  for y in range(-46, -40)
                  if (world.get_block(x, y, z) or "").endswith("_stairs"))
    s_steps = sum(1 for x in range(1009, 1020) for z in range(773, 781)
                  for y in range(-46, -40)
                  if (world.get_block(x, y, z) or "").endswith("_stairs"))
    check("regression_v4_entrance_steps", n_steps >= 40 and s_steps >= 40,
          f"north door steps {n_steps}, south door steps {s_steps} stair cells")
    # level.dat
    import gzip
    from anvil import loads, find, find_node
    root = loads(gzip.decompress(
        (Path(WORLD_DIR) / "level.dat").read_bytes()))
    data = find_node(root[2], "Data")
    check("level_dat_name",
          find(data[2], "LevelName")[1] == "中国海洋大学西海岸校区v5",
          f"name={find(data[2], 'LevelName')[1]}")
    check("level_dat_spawn",
          [find(data[2], k)[1] for k in ("SpawnX", "SpawnY", "SpawnZ")] ==
          [1361, -47, 711],
          "spawn 1361,-47,711")

    json.dump(REPORT, open(WORK / "v5-verify-report.json", "w",
                           encoding="utf-8"), ensure_ascii=False, indent=1)
    fails = [k for k, v in REPORT["checks"].items() if not v["ok"]]
    print(f"\nVERIFY: {len(REPORT['checks']) - len(fails)}/"
          f"{len(REPORT['checks'])} passed; failures: {fails}")


if __name__ == "__main__":
    main()
