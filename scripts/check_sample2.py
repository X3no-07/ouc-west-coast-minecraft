"""Follow-up checks on the built sample world (read-only)."""
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from finish_world import World  # noqa: E402


def main():
    w = World(Path(sys.argv[1]))

    # Long wing footprint cells: X1018-1088, Z540-556.  Edge rows/cols are
    # X1018, X1088, Z540, Z556.
    def is_edge(x, z):
        return x in (1018, 1088) or z in (540, 556)

    sand_edge = sand_int = slab_edge = slab_int = 0
    sand_int_pos, slab_int_pos = [], []
    for x in range(1018, 1089):
        for z in range(540, 557):
            name = w.get_block(x, -29, z)
            if name == "minecraft:sandstone":
                if is_edge(x, z):
                    sand_edge += 1
                else:
                    sand_int += 1
                    sand_int_pos.append((x, z))
            elif name == "minecraft:cut_sandstone_slab":
                if is_edge(x, z):
                    slab_edge += 1
                else:
                    slab_int += 1
                    slab_int_pos.append((x, z))
    print(f"long wing Y=-29: sandstone edge={sand_edge} interior={sand_int} "
          f"{sand_int_pos[:10]}")
    print(f"long wing Y=-29: cut_sandstone_slab edge={slab_edge} "
          f"interior={slab_int} {slab_int_pos[:10]}")

    # What is the tall column at (1049, 581)?  List blocks Y=-45..-18.
    col = [(y, w.get_block(1049, y, 581)) for y in range(-45, -17)]
    print("column (1049,581):", [(y, n) for (y, n) in col
                                 if n != "minecraft:air"])
    # Same for neighbours to see if it is a wall overhang / beam.
    for (x, z) in ((1048, 581), (1049, 580), (1049, 582), (1050, 581)):
        y, name = w.top_solid(x, z)
        print(f"top at ({x},{z}): y={y} {name}")

    # Walkway continuity with footprint rows excluded.
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

    walkway(range(1072, 1077), range(612, 629), "south walkway (excl wall)")
    walkway(range(997, 1018), range(583, 591), "west walkway (excl wall)")
    walkway(range(1038, 1050), range(558, 582), "courtyard (excl walls)")


if __name__ == "__main__":
    main()
