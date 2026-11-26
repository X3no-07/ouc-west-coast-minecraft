"""Check whether leftover sandstone/trim blocks at a roof's top layer are
on the footprint edge (retained trim) or in the interior (un-unified roof).
Usage: check_trim.py <world_dir> <plan.json>
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from finish_world import World, cells_in_entry, is_edge_cell_entry  # noqa: E402

TRIM = {"minecraft:stone_bricks", "minecraft:quartz_block",
        "minecraft:sandstone", "minecraft:smooth_sandstone",
        "minecraft:glass", "minecraft:air"}


def main():
    world = World(Path(sys.argv[1]))
    plan = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    report = json.loads(Path(sys.argv[1]).replace("world\\Arnis World 1", "")
                        .joinpath("finish-report.json").read_text(encoding="utf-8")) \
        if False else None
    # roof_y and target come from the finish report in the run dir
    run_dir = Path(sys.argv[1]).parents[1]
    frep = json.loads((run_dir / "finish-report.json").read_text(encoding="utf-8"))
    targets = {r["name"]: (r.get("roof_y"), r.get("target")) for r in frep["roofs"]}
    bad = 0
    for roof in plan["roofs"]:
        y, target = targets.get(roof["name"], (None, None))
        if y is None or target is None:
            print(f"{roof['name']}: NO ROOF (skipped)")
            continue
        cells = cells_in_entry(roof)
        interior_left = {}
        trim_left = {}
        for (x, z) in cells:
            b = world.get_block(x, y, z)
            if b == target or b is None:
                continue
            if b in TRIM:
                trim_left[b] = trim_left.get(b, 0) + 1
            else:
                interior_left[b] = interior_left.get(b, 0) + 1
        # split trim_left into edge vs interior for the record
        edge_trim = {}
        interior_trim = {}
        for (x, z) in cells:
            b = world.get_block(x, y, z)
            if b in TRIM and b != target:
                if is_edge_cell_entry(x, z, roof):
                    edge_trim[b] = edge_trim.get(b, 0) + 1
                else:
                    interior_trim[b] = interior_trim.get(b, 0) + 1
        flag = "OK" if not interior_left and not interior_trim else "CHECK"
        if flag == "CHECK":
            bad += 1
        print(f"{flag} {roof['name']}: target={target} "
              f"non-target interior={interior_left} "
              f"trim interior={interior_trim} trim edge={edge_trim}")
    print("roofs needing a look:", bad)


if __name__ == "__main__":
    main()
