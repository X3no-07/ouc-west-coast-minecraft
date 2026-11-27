#!/usr/bin/env python3
"""v10 fix-up: repave the learning-complex west plaza at its real level.

The first build_v10.py run skipped the whole west plaza: its paving
sits at y=-47 (a raised platform: dirt/stone at y-49/-48, paving at
y-47), not y=-49 as assumed, so the 'top > -49 -> skip' rule skipped
every cell. This script repaves only that rect, at y=-47, on the
already-built v10 world, and patches v10-build-report.json.
"""
import json
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from finish_world import World  # noqa: E402
from build_v4 import AIR  # noqa: E402
from build_v9 import PASS_TOP  # noqa: E402
from build_v10 import PLAZA_RECT, LGREY, GROUND_PAVEABLE  # noqa: E402

WORK = HERE
WORLD_DIR = WORK / "staging-v10" / "OUC-West-Coast-v10"
V3 = json.load(open(WORK / "v3-build-data.json", encoding="utf-8"))

LEVEL = -47  # probed: plaza paving top is y=-47, not -49


def main():
    t0 = time.time()
    world = World(str(WORLD_DIR))
    stats = Counter()

    def gtop(x, z):
        for y in range(64, -65, -1):
            b = world.get_block(x, y, z)
            if b is None or b in AIR or b in PASS_TOP:
                continue
            return (y, b)
        return None

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
            if t > LEVEL:
                stats["west_plaza_skipped_tall"] += 1
                continue
            if t < LEVEL - 1:
                stats["west_plaza_skipped_hole"] += 1
                continue
            if cur not in GROUND_PAVEABLE and cur != LGREY and \
                    cur != "minecraft:smooth_stone":
                stats[f"west_plaza_skipped_{cur.split(':')[1]}"] += 1
                continue
            joint = (x % 10 == 0) or (z % 10 == 0)
            want = "minecraft:smooth_stone" if joint else LGREY
            if world.get_block(x, LEVEL, z) != want:
                world.set_block(x, LEVEL, z, want)
                stats["west_plaza_slab"] += 1
            for y in range(LEVEL + 1, LEVEL + 4):
                if world.get_block(x, y, z) in PASS_TOP:
                    world.set_block(x, y, z, "minecraft:air")
                    stats["west_plaza_veg_cleared"] += 1

    changed = world.flush()
    print(f"WEST PLAZA FIX: {changed} cells changed in "
          f"{time.time() - t0:.1f}s; {dict(stats)}")
    rp = json.load(open(WORK / "v10-build-report.json", encoding="utf-8"))
    # the first run's west-plaza counters were all skips (wrong level);
    # replace them with this run's real numbers.
    for k in list(rp["totals"]):
        if k.startswith("west_plaza"):
            del rp["totals"][k]
    rp["totals"].update(dict(stats))
    rp["cells_changed"] = rp.get("cells_changed", 0) + changed
    rp["west_plaza"]["level_y"] = LEVEL
    rp["west_plaza"]["note"] = ("plaza is a raised platform, paving "
                                "top y=-47 (not -49); first build run "
                                "skipped it, repaved by fix-up")
    json.dump(rp, open(WORK / "v10-build-report.json", "w",
                       encoding="utf-8"), ensure_ascii=False, indent=1)
    print("report patched:", WORK / "v10-build-report.json")


if __name__ == "__main__":
    main()
