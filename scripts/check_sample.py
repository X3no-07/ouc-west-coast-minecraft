"""Acceptance checks on a built world directory (read-only).
Usage: check_sample.py <world_dir>
"""
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from finish_world import World  # noqa: E402
import anvil  # noqa: E402


def main():
    world = Path(sys.argv[1])
    w = World(world)
    import gzip
    level = anvil.loads(gzip.decompress((world / "level.dat").read_bytes()))
    print("level name:", anvil.find(level[2], "LevelName"))

    # 1. Long wing roof: sandstone positions at Y=-29, edge vs interior.
    roof_counts = Counter()
    sand = []
    for x in range(1018, 1090):
        for z in range(540, 558):
            name = w.get_block(x, -29, z)
            roof_counts[name] += 1
            if name == "minecraft:sandstone":
                sand.append((x, z))
    print("long wing Y=-29 counts:", dict(roof_counts))
    edge_sand = [(x, z) for (x, z) in sand
                 if x in (1018, 1089) or z in (540, 557)]
    print("sandstone cells:", len(sand), "of which on footprint edge:",
          len(edge_sand), "interior:", len(sand) - len(edge_sand))
    print("interior sandstone positions (first 20):",
          [c for c in sand if c not in edge_sand][:20])

    # 2. The 25 grass cells: X1044-1048, Z569-573, top surface.
    grass = Counter()
    for x in range(1044, 1049):
        for z in range(569, 574):
            y, name = w.top_solid(x, z)
            grass[(y, name)] += 1
    print("courtyard 25 cells top surface:", dict(grass))

    # 3. Walkway continuity: max step between adjacent top cells.
    def walkway(xs, zs, label):
        cells = {(x, z) for x in xs for z in zs}
        worst = 0
        worst_at = None
        for (x, z) in sorted(cells):
            y, _ = w.top_solid(x, z)
            if y is None:
                continue
            for (dx, dz) in ((1, 0), (0, 1)):
                nb = (x + dx, z + dz)
                if nb in cells:
                    y2, _ = w.top_solid(*nb)
                    if y2 is not None:
                        d = abs(y2 - y)
                        if d > worst:
                            worst, worst_at = d, ((x, z, y), (nb[0], nb[1], y2))
        print(f"{label}: max step {worst} at {worst_at}")

    walkway(range(1072, 1077), range(611, 629), "south walkway")
    walkway(range(997, 1019), range(583, 591), "west walkway")
    walkway(range(1037, 1051), range(557, 583), "courtyard")

    # 4. Wall straightness spot check: top surface along wall lines.
    for label, line in (("long wing north wall Z540",
                         [(x, 540) for x in range(1018, 1090)]),
                        ("main west wall X1050",
                         [(1050, z) for z in range(582, 612)])):
        ys = Counter()
        for (x, z) in line:
            y, name = w.top_solid(x, z)
            ys[(y, name)] += 1
        print(label, "top-surface counts:", dict(ys))


if __name__ == "__main__":
    main()
