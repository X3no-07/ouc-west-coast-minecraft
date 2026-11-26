"""Probe roof heights for given footprints in a built world (read-only).
Usage: check_roofs_full.py <world_dir> <plan.json> <name-substring>...
Prints, per matching roof: histogram of top-solid Y (full range) and the
top 4 blocks at the modal Y.
"""
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from finish_world import World, cells_in_entry  # noqa: E402


def main():
    world = World(Path(sys.argv[1]))
    plan = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    needles = sys.argv[3:]
    for roof in plan["roofs"]:
        if not any(n in roof["name"] for n in needles):
            continue
        cells = cells_in_entry(roof)
        ys = Counter()
        for (x, z) in cells:
            top = world.top_solid(x, z, y_top=64, y_bottom=-64)
            if top is None:
                ys["<none>"] += 1
            else:
                ys[top[0]] += 1
        print(f"{roof['name']}: cells={len(cells)} topY={dict(ys)}")
        if ys:
            mode_y = Counter({k: v for k, v in ys.items() if k != "<none>"}).most_common(1)
            if mode_y:
                y = mode_y[0][0]
                blocks = Counter(world.get_block(x, y, z) for (x, z) in cells)
                print(f"   at Y={y}: {blocks.most_common(5)}")


if __name__ == "__main__":
    main()
