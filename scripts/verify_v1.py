"""Verify the merged v1 world (read-only).

- Info North: three footprints' roof-top histograms, courtyard 25 blocks.
- Walkway BFS is done separately by check_sample3.py.
Usage: verify_v1.py <world_dir>
"""
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from finish_world import World  # noqa: E402


def main():
    w = World(Path(sys.argv[1]))
    # courtyard 25 blocks at Y=-45
    c = Counter(w.get_block(x, -45, z) for x in range(1044, 1049) for z in range(569, 574))
    print("courtyard Y=-45 X1044-1048 Z569-573:", dict(c))
    assert c == Counter({"minecraft:stone_bricks": 25}), c
    # roof tops per footprint
    for name, (x0, x1, z0, z1) in {
        "long wing": (1018, 1089, 540, 557),
        "main": (1050, 1098, 582, 611),
        "west wing": (1018, 1037, 558, 611),
    }.items():
        tops = Counter()
        for x in range(x0, x1 + 1):
            for z in range(z0, z1 + 1):
                top = w.top_solid(x, z, y_top=64, y_bottom=-64)
                if top is not None:
                    tops[top] += 1
        print(f"{name} top-solid histogram (top 6): {tops.most_common(6)}")
    print("verify_v1 OK")


if __name__ == "__main__":
    main()
