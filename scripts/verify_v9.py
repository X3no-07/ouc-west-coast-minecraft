#!/usr/bin/env python3
"""v9 verify: read-back checks on the built world + BFS routes
+ v4 info building and v3 door regression. Writes v9-verify-report.json.
Vanilla Mojang validation (validate_mojang.py) runs on the PC only
(jpype lives in the PC's `py` 3.12); on the VM it is skipped and the
report says so.
Set V9_WORLD to override the world dir (VM dry-run).
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
    "V9_WORLD", str(WORK / "staging-v9" / "OUC-West-Coast-v9")))
V5 = json.load(open(WORK / "v5-build-data.json", encoding="utf-8"))
V3 = json.load(open(WORK / "v3-build-data.json", encoding="utf-8"))
BUILD = json.load(open(WORK / "v5-build-report.json", encoding="utf-8"))
RFBUILD = json.load(open(WORK / "v9-build-report.json", encoding="utf-8"))
V6_WORLD_DIR = WORK / "staging-v6" / "OUC-West-Coast-v6"
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
    # new cross-section, sampled every 7th step along each road.
    # NOTE: the "navy road" (name 海军路) is road index 1, a tertiary
    # w7 main road -- the v5 suite mislabelled it road 34. The real
    # road 34 is index 34, residential w5.
    def section_counts(road, span):
        counts = Counter()
        for (x1, z1), (x2, z2) in zip(road["pts"], road["pts"][1:]):
            steps = max(abs(x2 - x1), abs(z2 - z1), 1)
            if abs(x2 - x1) >= abs(z2 - z1):
                perp = [(0, o) for o in range(-span, span + 1)]
            else:
                perp = [(o, 0) for o in range(-span, span + 1)]
            for s in range(0, steps + 1, 7):
                cx = round(x1 + (x2 - x1) * s / steps)
                cz = round(z1 + (z2 - z1) * s / steps)
                for (ox, oz) in perp:
                    off = max(abs(ox), abs(oz))
                    t = top_y(world, cx + ox, cz + oz)
                    if t is None:
                        continue
                    counts[(off, world.get_block(cx + ox, t, cz + oz))] += 1
                t = top_y(world, cx, cz)
                if t is not None:
                    counts[("centre", world.get_block(cx, t, cz))] += 1
        return counts

    def frac(counts, offs, want):
        tries = sum(v for (o, _), v in counts.items()
                    if o in offs and o != "centre")
        hits = sum(v for (o, b), v in counts.items()
                   if o in offs and o != "centre" and b in want)
        return hits, tries

    GREYWHITE = ("minecraft:gray_concrete", "minecraft:white_concrete")
    # At kerb/walk offsets a cell is also fine when it holds a
    # neighbouring road's carriageway (grey/white asphalt), or the
    # pre-existing Arnis road-border decoration (cyan terracotta /
    # grey concrete powder form a continuous border strip exactly on
    # the kerb line of the navy road -- paving over it would destroy
    # original map decoration, and the widening rule says to pave
    # only empty land/grass), or is out of bounds: roads 9 and 13
    # run ~9 cells apart, so after widening their cross-sections
    # overlap and the kerb/sidewalk between them is legitimately
    # carriageway, not a missing kerb. Raw expected fractions are
    # reported in the detail; the pass rule only rejects cells left
    # as grass, stone, plaza tiles, etc.
    NEIGHBOUR_OK = ("minecraft:gray_concrete", "minecraft:white_concrete",
                    "minecraft:cyan_terracotta",
                    "minecraft:gray_concrete_powder")

    def frac_ok(counts, offs, want, also=()):
        tries = sum(v for (o, _), v in counts.items()
                    if o in offs and o != "centre")
        hits = sum(v for (o, b), v in counts.items()
                   if o in offs and o != "centre" and b in want)
        ok = sum(v for (o, b), v in counts.items()
                 if o in offs and o != "centre" and b in want + also)
        return hits, ok, tries

    # residential road 34: full-width grey carriageway +-2, sidewalk +-3
    c34 = section_counts(V3["roads"][34], 3)
    h, t = frac(c34, {0, 1, 2}, GREYWHITE)
    check("road34_section", t and h >= t * 0.8,
          f"{h}/{t} carriageway cells grey/white")
    h, t = frac(c34, {3}, ("minecraft:light_gray_concrete",))
    check("road34_sidewalks", t and h >= t * 0.7,
          f"{h}/{t} light-grey sidewalks at +-3")
    hc = sum(v for (o, b), v in c34.items()
             if o == "centre" and b in GREYWHITE)
    tc = sum(v for (o, b), v in c34.items() if o == "centre")
    check("road34_centre", tc and hc >= tc * 0.99,
          f"{hc}/{tc} centre cells grey or white")
    # main-road section on the navy road (index 1, tertiary w7->11)
    # and on tertiary road 13 (w7->11): kerb +-5 stone, edge line +-4
    # white, inner +-3 grey/white, sidewalk +-6 light-grey
    for name, road in (("navy_road", [r for r in V3["roads"]
                                      if r.get("name") == "海军路"][0]),
                       ("road13", V3["roads"][13])):
        c = section_counts(road, 6)
        hk, okk, tk = frac_ok(c, {5}, ("minecraft:stone_bricks",),
                              NEIGHBOUR_OK)
        he, te = frac(c, {4}, ("minecraft:white_concrete",))
        hi, ti = frac(c, {0, 1, 2, 3}, GREYWHITE)
        hw, okw, tw = frac_ok(c, {6}, ("minecraft:light_gray_concrete",),
                              NEIGHBOUR_OK)
        check(f"{name}_main_section",
              tk and okk >= tk * 0.85 and te and he >= te * 0.7 and
              ti and hi >= ti * 0.9 and tw and okw >= tw * 0.85,
              f"kerb {hk}/{tk} stone ({okk}/{tk} stone or neighbour "
              f"road), edge {he}/{te} white, inner {hi}/{ti} "
              f"grey/white, walk {hw}/{tw} light-grey ({okw}/{tw} "
              f"light-grey or neighbour road)")
    check("zebra_crossings", RFBUILD["totals"]["zebra_crossings"] >= 20,
          f"{RFBUILD['totals']['zebra_crossings']} crossings, "
          f"{RFBUILD['totals']['zebra_cells']} white cells")

    # ---------- 1b. v8: Gaoyu middle segment + 1-wide WWGG dash ----
    # the middle of Gaoyu Road (x 981-1233, z~375) must be road now:
    # one continuous roadlike run on the z=375 line from x=900 to 1447
    roadlike = {"minecraft:gray_concrete", "minecraft:white_concrete",
                "minecraft:black_concrete", "minecraft:light_gray_concrete",
                "minecraft:stone_bricks"}
    runs = []
    cur = None
    for x in range(900, 1451):
        t = top_y(world, x, 375)
        ok = t is not None and \
            world.get_block(x, t, 375) in roadlike
        if ok and cur is None:
            cur = [x, x]
        elif ok:
            cur[1] = x
        elif cur is not None:
            runs.append(tuple(cur))
            cur = None
    if cur is not None:
        runs.append(tuple(cur))
    # v9 note: the ground beside the road is now white concrete too, so
    # the roadlike run no longer ends at the road's end (1447). What
    # matters is the road segment itself is fully roadlike from 900.
    check("gaoyu_middle_filled",
          runs and runs[0][0] == 900 and runs[0][1] >= 1447,
          f"roadlike runs on z=375 x900-1450: {runs}")
    # exact WWGG dash on the new segment's clean stretch:
    # segment (1014,375)-(1136,375), x 1020-1130 avoids zebra stripes
    # at both end junctions; centre column is z=375 (o=0), phase is
    # ((x-1014)//2)%2==0 -> white, else grey. The neighbour column
    # z=376 (o=1) must be plain grey asphalt on this stretch -- the
    # centre line is 1 wide, NOT 2 wide.
    pat_ok = 0
    pat_bad = []
    for x in range(1020, 1131):
        want = ("minecraft:white_concrete"
                if ((x - 1014) // 2) % 2 == 0 else "minecraft:gray_concrete")
        t = top_y(world, x, 375)
        got = world.get_block(x, t, 375) if t is not None else None
        if got == want:
            pat_ok += 1
        else:
            pat_bad.append(((x, 375), want, got))
    check("gaoyu_centre_wwgg", not pat_bad,
          f"{pat_ok}/111 centre cells match WWGG phase; bad: {pat_bad[:6]}")
    adj_ok = 0
    adj_bad = []
    for x in range(1020, 1131):
        t = top_y(world, x, 376)
        got = world.get_block(x, t, 376) if t is not None else None
        if got == "minecraft:gray_concrete":
            adj_ok += 1
        else:
            adj_bad.append(((x, 376), got))
    check("gaoyu_centre_1_wide", not adj_bad,
          f"{adj_ok}/111 neighbour cells grey asphalt; "
          f"white/other: {adj_bad[:6]}")
    # centre line on 3 main + 3 internal roads, offset 0 only:
    # v8 is a WWGG dash, so white ~half, grey ~half, almost nothing
    # else; the neighbour column (offset 1) must be almost never white
    # (zebra stripes at junctions are the only exception)
    def centre_frac(road):
        w = g = o = 0
        w1 = t1 = 0
        for (x1, z1), (x2, z2) in zip(road["pts"], road["pts"][1:]):
            steps = max(abs(x2 - x1), abs(z2 - z1), 1)
            ew = abs(x2 - x1) >= abs(z2 - z1)
            for s in range(steps + 1):
                cx = round(x1 + (x2 - x1) * s / steps)
                cz = round(z1 + (z2 - z1) * s / steps)
                for off, is_c in ((0, True), (1, False)):
                    x, z = (cx, cz + off) if ew else (cx + off, cz)
                    if not (0 <= x < 2093 and 0 <= z < 996):
                        continue
                    t = top_y(world, x, z)
                    b = world.get_block(x, t, z) if t is not None else None
                    if is_c:
                        if b == "minecraft:white_concrete":
                            w += 1
                        elif b == "minecraft:gray_concrete":
                            g += 1
                        else:
                            o += 1
                    else:
                        t1 += 1
                        if b == "minecraft:white_concrete":
                            w1 += 1
        return w, g, o, w1, t1
    for name, road in (("navy_road", [r for r in V3["roads"]
                                      if r.get("name") == "海军路"][0]),
                       ("road13", V3["roads"][13]),
                       ("road22", V3["roads"][22]),
                       ("road34", V3["roads"][34]),
                       ("road15", V3["roads"][15]),
                       ("road17", V3["roads"][17])):
        w, g, o, w1, t1 = centre_frac(road)
        tot = w + g + o
        frac = w / tot if tot else 0
        adj = w1 / t1 if t1 else 0
        check(f"centre_wwgg_{name}",
              tot and 0.40 <= frac <= 0.62 and o <= tot * 0.05 and
              adj <= 0.15,
              f"centre white {w}, grey {g}, other {o} "
              f"(white frac {frac:.2f}); neighbour col white {w1}/{t1} "
              f"({adj:.2f})")
    # big vs small split, explicit: small roads (residential/service)
    # must have NO white edge line and NO stone kerb -- offsets +-2
    # (w5) next to the centre must be plain grey asphalt
    for name, road in (("road34", V3["roads"][34]),
                       ("road15", V3["roads"][15]),
                       ("road17", V3["roads"][17])):
        c = section_counts(road, 3)
        tg = sum(v for (o, _), v in c.items() if o == 2)
        hg = sum(v for (o, b), v in c.items()
                 if o == 2 and b == "minecraft:gray_concrete")
        check(f"small_no_edge_kerb_{name}", tg and hg >= tg * 0.8,
              f"{hg}/{tg} cells at +-2 are plain grey asphalt")

    # ---------- 1c. main-road widening: own edge lines ------------
    # The roadlike-run width is polluted where parallel main roads
    # overlap (roads 9 and 13 run ~9 cells apart, so their widened
    # bands merge), so the honest widening metric is the road's OWN
    # edge lines: fraction of sampled cross-sections where both cells
    # at |off| = half-1 are white concrete. v6 main roads had edge
    # lines at |off| = half-1 with half = 3 (w7) / 4 (w9); v8 has
    # them at half-1 = 4 (w11) / 5 (w13). Run widths are reported
    # as detail only.
    ROADLIKE_RUN = {"minecraft:gray_concrete", "minecraft:white_concrete",
                    "minecraft:black_concrete",
                    "minecraft:light_gray_concrete",
                    "minecraft:stone_bricks"}

    def run_widths(wd, road, step=20, span=10):
        ws = []
        for (x1, z1), (x2, z2) in zip(road["pts"], road["pts"][1:]):
            steps = max(abs(x2 - x1), abs(z2 - z1), 1)
            ew = abs(x2 - x1) >= abs(z2 - z1)
            for s in range(0, steps + 1, step):
                cx = round(x1 + (x2 - x1) * s / steps)
                cz = round(z1 + (z2 - z1) * s / steps)
                cells = []
                for o in range(-span, span + 1):
                    x, z = (cx, cz + o) if ew else (cx + o, cz)
                    if not (0 <= x < 2093 and 0 <= z < 996):
                        cells.append(False)
                        continue
                    t = top_y(wd, x, z)
                    b = wd.get_block(x, t, z) if t is not None else None
                    cells.append(b in ROADLIKE_RUN)
                # longest roadlike run containing the centre (span)
                lo = span
                while lo > 0 and cells[lo - 1]:
                    lo -= 1
                hi = span
                while hi < 2 * span and cells[hi + 1]:
                    hi += 1
                ws.append(hi - lo + 1)
        ws.sort()
        return ws[len(ws) // 2] if ws else 0

    def edge_frac(wd, road, half):
        ok = tot = 0
        for (x1, z1), (x2, z2) in zip(road["pts"], road["pts"][1:]):
            steps = max(abs(x2 - x1), abs(z2 - z1), 1)
            ew = abs(x2 - x1) >= abs(z2 - z1)
            for s in range(0, steps + 1, 10):
                cx = round(x1 + (x2 - x1) * s / steps)
                cz = round(z1 + (z2 - z1) * s / steps)
                cells = []
                for o in (-(half - 1), half - 1):
                    x, z = (cx, cz + o) if ew else (cx + o, cz)
                    if not (0 <= x < 2093 and 0 <= z < 996):
                        cells.append(False)
                        continue
                    t = top_y(wd, x, z)
                    cells.append(wd.get_block(x, t, z) ==
                                 "minecraft:white_concrete")
                tot += 1
                ok += all(cells)
        return ok, tot

    w6 = World(str(V6_WORLD_DIR))
    for name, road in (("navy_road", [r for r in V3["roads"]
                                      if r.get("name") == "海军路"][0]),
                       ("road13", V3["roads"][13]),
                       ("road22", V3["roads"][22]),
                       ("road7_sansha", V3["roads"][7]),
                       ("road8_shanchuan", V3["roads"][8]),
                       ("road9", V3["roads"][9])):
        old_half = road["width"] // 2
        new_half = old_half + 2
        ok6, tot6 = edge_frac(w6, road, old_half)
        ok8, tot8 = edge_frac(world, road, new_half)
        old_w = run_widths(w6, road)
        new_w = run_widths(world, road)
        check(f"widened_{name}",
              tot8 and ok8 >= tot8 * 0.7 and
              tot6 and ok6 >= tot6 * 0.7,
              f"own edge lines both white: v6 {ok6}/{tot6} at "
              f"|off|={old_half - 1} (carriageway w{road['width']}) -> "
              f"v8 {ok8}/{tot8} at |off|={new_half - 1} (carriageway "
              f"w{road['width'] + 4}); median roadlike run "
              f"v6={old_w} -> v8={new_w}")

    # ---------- 1d. centre-line continuity probe, all 44 roads -----
    # centre column (offset 0) must be roadlike at every step. A cell
    # counts as pass-through (not a gap) if a roadlike block lies
    # within 30 cells below the top block (roads 38/40 run under
    # multi-storey buildings: road at y-50/-48, roof at y-28/-26),
    # or if the top block is a stair (road 2 crosses the learning
    # complex east entrance steps, deliberately never paved over).
    # OOB steps are not gaps.
    ROADLIKE_CENTRE = {"minecraft:gray_concrete",
                       "minecraft:white_concrete",
                       "minecraft:black_concrete"}
    gaps = {}
    for ri, r in enumerate(V3["roads"] + [{
            "id": 1292071627, "type": "residential", "name": "高峪路",
            "width": 5, "pts": [[981, 375], [1014, 375], [1136, 375],
                                [1176, 375], [1233, 374]]}]):
        pts = r["pts"]
        n = 0
        for (x1, z1), (x2, z2) in zip(pts, pts[1:]):
            steps = max(abs(x2 - x1), abs(z2 - z1), 1)
            ew = abs(x2 - x1) >= abs(z2 - z1)
            for s in range(steps + 1):
                cx = round(x1 + (x2 - x1) * s / steps)
                cz = round(z1 + (z2 - z1) * s / steps)
                if not (0 <= cx < 2093 and 0 <= cz < 996):
                    continue
                t = top_y(world, cx, cz)
                if t is None:
                    n += 1
                    continue
                b = world.get_block(cx, t, cz)
                if b in ROADLIKE_CENTRE:
                    continue
                if b and b.endswith("_stairs"):
                    continue
                below = any(world.get_block(cx, t - k, cz)
                            in ROADLIKE_CENTRE for k in range(1, 31))
                if not below:
                    n += 1
        if n:
            gaps[ri] = n
    check("centreline_no_gaps", not gaps,
          f"gaps per road index: {gaps} (empty = 0 gaps on all 44 roads)")

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
          find(data[2], "LevelName")[1] == "中国海洋大学西海岸校区v9",
          f"name={find(data[2], 'LevelName')[1]}")
    check("level_dat_spawn",
          [find(data[2], k)[1] for k in ("SpawnX", "SpawnY", "SpawnZ")] ==
          [1361, -47, 711],
          "spawn 1361,-47,711")

    # ---------- 12. v9 paving ----------
    from build_v9 import RECT as V9_RECT, GREEN_POLYS as V9_GREEN
    from build_v9 import RECT_EXCLUDE as V9_RE, in_green as _in_green
    w8 = World(str(WORK / "staging-v8" / "OUC-West-Coast-v8"))
    rx0, rz0, rx1, rz1 = V9_RECT
    sw = sg = so = 0
    for x in range(rx0, rx1 + 1, 5):
        for z in range(rz0, rz1 + 1, 5):
            t = top_y(world, x, z)
            b = world.get_block(x, t, z) if t is not None else None
            if b == "minecraft:white_concrete":
                sw += 1
            elif b == "minecraft:grass_block":
                sg += 1
            else:
                so += 1
    tot = sw + sg + so
    check("paving_rect_white", sw >= tot * 0.45 and sg <= tot * 0.12,
          f"sampled rect tops: white {sw}, grass {sg}, other {so} of {tot}")
    # A white cell inside an exclusion is only a violation if v9 put
    # it there: white that was already there in v8 (court/field line
    # markings, road dashes crossing the park, plaza joints) is fine.
    bad_white = 0
    green_n = 0
    for g in V9_GREEN:
        bx0, bz0, bx1, bz1 = g["bbox"]
        for x in range(max(bx0, 0), min(bx1, 2092) + 1, 3):
            for z in range(max(bz0, 0), min(bz1, 995) + 1, 3):
                if not _in_green(x, z):
                    continue
                green_n += 1
                t = top_y(world, x, z)
                b = world.get_block(x, t, z) if t is not None else None
                if b == "minecraft:white_concrete":
                    t8 = top_y(w8, x, z)
                    b8 = w8.get_block(x, t8, z) if t8 is not None else None
                    if b8 in ("minecraft:grass_block", "minecraft:dirt"):
                        bad_white += 1
    for (ex0, ez0, ex1, ez1) in V9_RE:
        for x in range(ex0, ex1 + 1, 3):
            for z in range(ez0, ez1 + 1, 3):
                green_n += 1
                t = top_y(world, x, z)
                b = world.get_block(x, t, z) if t is not None else None
                if b == "minecraft:white_concrete":
                    t8 = top_y(w8, x, z)
                    b8 = w8.get_block(x, t8, z) if t8 is not None else None
                    if b8 in ("minecraft:grass_block", "minecraft:dirt"):
                        bad_white += 1
    check("paving_exclusions_green", bad_white == 0,
          f"{green_n} sampled exclusion cells, newly paved white: "
          f"{bad_white}")
    diff = 0
    n_out = 0
    for x in range(0, 2093, 7):
        for z in range(0, 996, 7):
            if rx0 <= x <= rx1 and rz0 <= z <= rz1:
                continue
            n_out += 1
            t9 = top_y(world, x, z)
            b9 = world.get_block(x, t9, z) if t9 is not None else None
            t8 = top_y(w8, x, z)
            b8 = w8.get_block(x, t8, z) if t8 is not None else None
            if b9 != b8:
                diff += 1
    check("paving_outside_unchanged", diff == 0,
          f"{n_out} sampled columns outside rect, changed tops: {diff}")

    json.dump(REPORT, open(WORK / "v9-verify-report.json", "w",
                           encoding="utf-8"), ensure_ascii=False, indent=1)
    fails = [k for k, v in REPORT["checks"].items() if not v["ok"]]
    print(f"\nVERIFY: {len(REPORT['checks']) - len(fails)}/"
          f"{len(REPORT['checks'])} passed; failures: {fails}")


if __name__ == "__main__":
    main()
