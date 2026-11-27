#!/usr/bin/env python3
"""v10 fix-up 2: restore road 26 cross-section + north edge line.

After build_v10.py, the road 26 relay (step 2) and the north edge
line (step 3) did not fully land on z976-981: the sidewalks
(x1221/x1227) and the centre dash (x1224) stayed grey there, and the
edge line stayed grey at x1228-1234, z976 -- although the same code
landed fine on z982-986. Cause not established (the writes were
second writes to cells the plaza repave had just set grey); this
script re-applies them with unconditional world.set_block (no
read-then-skip) and re-reads the world fresh to confirm.
"""
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from finish_world import World  # noqa: E402
from build_v10 import LGREY, GREY, WHITE  # noqa: E402

WORLD_DIR = HERE / "staging-v10" / "OUC-West-Coast-v10"


def main():
    world = World(str(WORLD_DIR))
    n = 0
    # road 26 cross-section, z976-986
    for z in range(976, 987):
        for x, b in ((1221, LGREY), (1227, LGREY),
                     (1222, GREY), (1223, GREY),
                     (1225, GREY), (1226, GREY)):
            world.set_block(x, -49, z, b)
            n += 1
        dash = WHITE if (z - 977) % 4 < 2 else GREY
        world.set_block(1224, -49, z, dash)
        n += 1
    # north edge line, z976, x1190-1255 except the road gap
    for x in range(1190, 1256):
        if 1221 <= x <= 1227:
            continue
        world.set_block(x, -49, 976, WHITE)
        n += 1
    changed = world.flush()
    print(f"ROAD26 FIX: {n} cells written, {changed} changed on flush")

    # fresh read-back
    w2 = World(str(WORLD_DIR))
    bad = []
    for z in range(976, 987):
        want = {1221: LGREY, 1227: LGREY, 1222: GREY, 1223: GREY,
                1225: GREY, 1226: GREY,
                1224: WHITE if (z - 977) % 4 < 2 else GREY}
        for x, wb in want.items():
            got = w2.get_block(x, -49, z)
            if got != wb:
                bad.append(((x, z), wb, got))
    for x in range(1190, 1256):
        if 1221 <= x <= 1227:
            continue
        got = w2.get_block(x, -49, 976)
        if got != WHITE:
            bad.append(((x, 976), WHITE, got))
    print("road+edge read-back mismatches:", bad if bad else "NONE")
    rp = json.load(open(HERE / "v10-build-report.json", encoding="utf-8"))
    rp["totals"]["road26_fixup_cells"] = n
    rp["totals"]["road26_fixup_mismatch"] = len(bad)
    rp["cells_changed"] = rp.get("cells_changed", 0) + changed
    json.dump(rp, open(HERE / "v10-build-report.json", "w",
                       encoding="utf-8"), ensure_ascii=False, indent=1)
    print("report patched")


if __name__ == "__main__":
    main()
